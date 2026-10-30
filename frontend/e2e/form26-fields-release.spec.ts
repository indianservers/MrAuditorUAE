import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { makeWorkflowHarness } from "./msme-browser-workflow";

const identities = JSON.parse(
  readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
);
const screenshots = "test-results/country-reports";
type Requirement = {
  key: string;
  title: string;
  disposition: string;
  source_required: boolean;
  basis: string;
};
type Pack = {
  id: string;
  requirements: Requirement[];
  sha256: string;
  inventory_counts: { requirements: number };
  statutory_completeness_qualified: boolean;
};

async function login(page: Page, email: string) {
  const password = process.env.AUDITOS_SMOKE_PASSWORD;
  if (!password || !email)
    throw new Error("Explicit isolated review identities required");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

for (const part of ["A", "B"] as const) {
  test(`synthetic Form 26 ${part}/2 complete inventory UI revision, independent review and export`, async ({
    page,
    browser,
  }) => {
    test.setTimeout(300000);
    expect(identities.synthetic_only).toBe(true);
    mkdirSync(screenshots, { recursive: true });
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
    const contexts = [];
    const actors: Record<string, Page> = {};
    try {
      for (const [name, email] of [
        ["reviewer", process.env.AUDITOS_SMOKE_REVIEWER_EMAIL],
        ["manager", identities.manager_email],
        ["partner", identities.partner_email],
      ]) {
        const context = await browser.newContext({
          baseURL: process.env.AUDITOS_E2E_ORIGIN,
          viewport: { width: 1440, height: 1000 },
        });
        contexts.push(context);
        const actor = await context.newPage();
        actor.setDefaultTimeout(20000);
        await login(actor, email);
        actors[name] = actor;
      }
      page.setDefaultTimeout(20000);
      const retrievedOn = new Date().toISOString().slice(0, 10);
      const headers = {
        "X-Tenant-ID": identities.tenant_id,
        Origin: process.env.AUDITOS_E2E_ORIGIN!,
      };
      async function post(
        request: APIRequestContext,
        path: string,
        data: unknown,
        status = 201,
      ) {
        const response = await request.post(`/api/backend/${path}`, {
          headers,
          data,
        });
        expect(response.status(), await response.text()).toBe(status);
        return response.json();
      }
      async function get(path: string) {
        const response = await page.request.get(`/api/backend/${path}`, {
          headers,
        });
        expect(response.status(), await response.text()).toBe(200);
        return response.json();
      }
      const client = await post(page.request, "clients", {
        code: `FORM-FIELDS-${part}-${Date.now()}`,
        name: "SYNTHETIC full field control client",
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: `SYNTHETIC Form 26 ${part} inventory entity`,
        country: "IN",
        jurisdiction: "India",
        functional_currency: "INR",
        presentation_currency: "INR",
      });
      const period = await post(page.request, "financial-periods", {
        entity_id: entity.id,
        start_date: "2026-04-01",
        end_date: "2027-03-31",
      });
      const engagement = await post(page.request, "engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC Form 26 ${part} inventory`,
        engagement_type: "External Audit",
      });
      const eid = engagement.id,
        audit = `engagements/${eid}/audit`,
        reg = `regulatory/engagements/${eid}`;
      for (const name of ["reviewer", "manager", "partner"])
        await post(
          page.request,
          `${audit}/team`,
          {
            membership_id: identities[`${name}_membership_id`],
            role_id: identities[`${name}_role_id`],
          },
          200,
        );
      const proposed = await post(
        page.request,
        `jurisdictions/engagements/${eid}/context`,
        {
          country: "IN",
          framework: "Ind AS",
          entity_type: "company",
          as_of: "2027-03-31",
          base_version: 0,
          reason: "Synthetic independently assessed field-inventory context",
        },
      );
      await post(
        actors.reviewer.request,
        `jurisdictions/engagements/${eid}/context/decision`,
        {
          request_id: proposed.id,
          approve: true,
          comments: "Synthetic context assessment; not client qualification",
        },
      );
      const { evidence } = makeWorkflowHarness(page, eid, identities.tenant_id);
      const document = await evidence(
        `SYNTHETIC-form26-${part}-control.txt`,
        Buffer.from(
          "SYNTHETIC field mapping control evidence only. This does not establish legal sufficiency or client audit coverage.",
        ),
      );
      async function action(
        request: APIRequestContext,
        record: { id: string; version: number },
        value: string,
      ) {
        return post(
          request,
          `${audit}/records/${record.id}/actions`,
          {
            version: record.version,
            action: value,
            comments: "Synthetic independent review-stage control decision",
          },
          200,
        );
      }
      let evidenceRecord = await get(`${audit}/records/${document.record}`);
      evidenceRecord = await action(page.request, evidenceRecord, "submit");
      evidenceRecord = await action(
        actors.reviewer.request,
        evidenceRecord,
        "approve",
      );
      const catalogue = (await get(`${reg}/report-presets`)) as {
        items: Pack[];
      };
      const pack = catalogue.items.find(
        (p) => p.id === `india-form26-index:${part}/2`,
      )!;
      expect(pack.requirements).toHaveLength(877);
      expect(pack.inventory_counts.requirements).toBe(877);
      expect(pack.statutory_completeness_qualified).toBe(false);
      const facts = {
        tax_period_start: "2026-04-01",
        tax_period_end: "2027-03-31",
        tax_audit_form: "26",
        audited_under_other_law: part === "A",
        audit_report_part: part,
      };
      const papers: { id: string; version: number }[] = [];
      const blocks: {
        key: string;
        title: string;
        kind: string;
        source_kind: string;
        source_id: string;
        requirement_keys: string[];
      }[] = [];
      for (let offset = 0; offset < 877; offset += 100) {
        const group = pack.requirements.slice(offset, offset + 100);
        let paper = await post(page.request, `${audit}/working-papers`, {
          reference: `SYN-FIELDS-${part}-${offset}-${randomUUID()}`,
          title: `SYNTHETIC field workpaper ${offset / 100 + 1}`,
          body: {
            folder: "SYNTHETIC complete field mapping controls",
            sections: [
              {
                heading: "Synthetic source mapping procedures",
                text: "SYNTHETIC mapping mechanics only. The original complete population and field support have not been professionally qualified.",
              },
            ],
            sources: [{ kind: "record", id: evidenceRecord.id }],
            financial_tables:
              offset === 0
                ? [
                    {
                      title: "SYNTHETIC assessed form-selection facts",
                      values: facts,
                    },
                  ]
                : [],
            conclusion:
              "SYNTHETIC workflow mechanics; no statutory opinion or substantive client coverage",
            report_requirement_scope: {
              preset_id: pack.id,
              period_start: facts.tax_period_start,
              period_end: facts.tax_period_end,
              items: group.map((r) => ({
                key: r.key,
                disposition: "REQUIRED",
                section_index: 0,
                supporting_sources: [{ kind: "record", id: evidenceRecord.id }],
                assessment:
                  "Synthetic exact field and population-control mapping, not qualified statutory evidence",
              })),
            },
          },
        });
        paper = await action(page.request, paper, "submit");
        paper = await action(actors.manager.request, paper, "approve");
        paper = await action(actors.partner.request, paper, "approve");
        expect(paper.status).toBe("APPROVED");
        papers.push(paper);
        blocks.push({
          key: `fields-${offset}`,
          title: `SYNTHETIC fields ${offset + 1}-${offset + group.length}`,
          kind: "working_paper_reference",
          source_kind: "record",
          source_id: paper.id,
          requirement_keys: group.map((r) => r.key),
        });
      }
      const source = await page.request.post(
        "/api/backend/regulatory/sources",
        {
          headers,
          multipart: {
            metadata: JSON.stringify({
              title: "SYNTHETIC selection rule source",
              country: "IN",
              source_url: "https://incometax.gov.in/",
              retrieved_on: retrievedOn,
            }),
            file: {
              name: "SYNTHETIC-selection.txt",
              mimeType: "text/plain",
              buffer: Buffer.from(
                "SYNTHETIC selection mechanics only, not an official legal copy or adopted legal rule.",
              ),
            },
          },
        },
      );
      expect(source.status(), await source.text()).toBe(201);
      const retained = await source.json();
      const rule = await post(page.request, "regulatory/rules", {
        rule_key: `IN-SYNTHETIC-FIELDS-${part}-${Date.now()}`,
        country: "IN",
        title: "SYNTHETIC form selection control",
        description:
          "Synthetic input binding mechanics, not adopted Indian legal content",
        framework: "Ind AS",
        period_basis: "period_start",
        effective_from: "2026-04-01",
        effective_to: "2027-03-31",
        citations: [
          {
            authority: "Synthetic reference",
            legislation: "Synthetic test only",
            url: "https://incometax.gov.in/",
            paragraph: "TEST",
            source_document_id: retained.id,
            document_sha256: retained.sha256,
            retrieval_status: "RETRIEVED",
            retrieved_on: retrievedOn,
          },
        ],
        input_requirements: Object.keys(facts),
        output_requirements: ["reviewed_conclusion"],
        applicability: [],
        validation_status: "VALIDATED",
        professional_review_status: "REVIEWED",
        last_reviewed: retrievedOn,
        amendment_reason:
          "Synthetic validation of retained form-selection controls",
        expected_sequence: 0,
      });
      await post(
        actors.reviewer.request,
        `regulatory/rules/${rule.id}/decisions`,
        {
          action: "approve",
          expected_sequence: 1,
          comments: "Synthetic fixtures only; no adopted legal rule",
          validation_cases: [
            {
              id: "SYN-FORM-FIELDS",
              kind: "checklist",
              expected_reference: "Independent synthetic form-selection inputs",
              period_start: "2026-04-01",
              period_end: "2027-03-31",
              facts,
              expected_applicability: "APPLICABLE",
            },
          ],
        },
      );
      await post(page.request, `regulatory/rules/${rule.id}/decisions`, {
        action: "publish",
        expected_sequence: 2,
        comments: "Synthetic mechanics only, not adopted legal content",
      });
      let checklist = await post(page.request, `${reg}/checklists`, {
        area: "india-tax-audit",
        title: "SYNTHETIC assessed form selection",
        rationale: "Synthetic source-bound period and report-part selection",
        items: [
          {
            clause: "SYN-FIELDS-SELECTION",
            rule_id: rule.id,
            state: "PREPARED",
            facts,
            fact_sources: Object.fromEntries(
              Object.keys(facts).map((key) => [
                key,
                {
                  kind: "record",
                  id: papers[0].id,
                  path: ["financial_tables", 0, "values", key],
                  comparison: "exact",
                },
              ]),
            ),
            procedure: "Synthetic retained facts compared independently",
            conclusion: "Synthetic exact period and audit-basis agreement",
            evidence_ids: [evidenceRecord.id],
          },
        ],
      });
      checklist = await post(
        actors.reviewer.request,
        `intelligence/engagements/${eid}/events/${checklist.id}/review`,
        {
          action: "approve",
          expected_version: checklist.version,
          comments: "Independent synthetic form-selection input review",
        },
      );
      const raw = {
        title: `SYNTHETIC Form 26 ${part}/2 full evidence inventory`,
        category: "india-tax-audit",
        rationale:
          "Synthetic complete inventory plumbing; no qualified statutory opinion",
        requirements_pack: pack.id,
        requirements: pack.requirements.map((r) => ({
          ...r,
          disposition: "REQUIRED",
        })),
        requirements_assessed: true,
        requirements_basis:
          "Synthetic declared mapping controls only; no professional field sufficiency is established",
        tax_audit_scope: {
          applicability_id: checklist.id,
          tax_period_start: "2026-04-01",
          tax_period_end: "2027-03-31",
          audited_under_other_law: part === "A",
          form: "26",
          audit_report_part: part,
        },
        blocks,
      };
      const initial = await post(page.request, `${reg}/report-templates`, raw);
      await page.goto("/settings/countries");
      await page
        .getByRole("combobox", { name: "Working country", exact: true })
        .selectOption("IN");
      await page.goto("/reports/statutory");
      await page
        .getByRole("combobox", { name: "Engagement", exact: true })
        .selectOption(eid);
      await page
        .getByRole("combobox", { name: "Saved template version", exact: true })
        .selectOption(initial.id);
      await page
        .getByRole("button", {
          name: "Load retained blocks into new revision",
          exact: true,
        })
        .click();
      await page
        .getByRole("textbox", {
          name: "Template / review rationale",
          exact: true,
        })
        .fill(
          "Synthetic browser amendment of retained field scope; no substantive legal qualification",
        );
      await expect(
        page.getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        }),
      ).toHaveValue(pack.id);
      const last = pack.requirements[876];
      await page
        .getByRole("textbox", {
          name: "Search report requirements",
          exact: true,
        })
        .fill(last.key);
      await expect(
        page.getByRole("textbox", {
          name: "Requirement reference 877",
          exact: true,
        }),
      ).toHaveValue(last.key);
      await expect(
        page.getByRole("textbox", {
          name: "Requirement reference 877",
          exact: true,
        }),
      ).toBeDisabled();
      const revisedBasis =
        "Synthetic browser revision of final field scope; substantive legal sufficiency remains unqualified";
      await page
        .getByRole("textbox", {
          name: "Applicability and source basis 877",
          exact: true,
        })
        .fill(revisedBasis);
      const lastBlock = page.getByRole("group", {
        name: `Coverage for ${blocks[8].title}`,
        exact: true,
      });
      await lastBlock
        .getByRole("textbox", {
          name: `Search Coverage for ${blocks[8].title}`,
          exact: true,
        })
        .fill(last.key);
      const lastCheckbox = lastBlock.getByRole("checkbox", {
        name: last.title,
        exact: true,
      });
      await expect(lastCheckbox).toBeChecked();
      await lastCheckbox.uncheck();
      await lastCheckbox.check();
      await expect(
        lastBlock.getByText(/77 of 100 requirements selected/),
      ).toBeVisible();
      await page.setViewportSize({ width: 2200, height: 3400 });
      const editor = page.getByRole("group", {
        name: "Declared report requirements",
        exact: true,
      });
      await editor.scrollIntoViewIfNeeded();
      await expect(
        page.getByRole("textbox", {
          name: "Requirement reference 877",
          exact: true,
        }),
      ).toBeInViewport();
      await expect(
        page.getByRole("textbox", {
          name: "Applicability and source basis 877",
          exact: true,
        }),
      ).toBeInViewport();
      await page.screenshot({
        path: `${screenshots}/IN-form26-${part}-final-field-revision.png`,
      });
      const savedResponse = page.waitForResponse(
        (r) =>
          r.url().endsWith("/report-templates") &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Save template version", exact: true })
        .click();
      const saved = await savedResponse;
      expect(saved.status(), await saved.text()).toBe(201);
      const template = await saved.json();
      expect(template.body.requirements).toHaveLength(877);
      expect(template.body.requirements.slice(0, 876)).toEqual(
        raw.requirements.slice(0, 876),
      );
      expect(template.body.requirements[876].basis).toBe(revisedBasis);
      expect(template.body.blocks).toEqual(initial.body.blocks);
      const reviewer = actors.reviewer;
      await reviewer.goto("/settings/countries");
      await reviewer
        .getByRole("combobox", { name: "Working country", exact: true })
        .selectOption("IN");
      await reviewer.goto("/reports/statutory");
      await reviewer
        .getByRole("combobox", { name: "Engagement", exact: true })
        .selectOption(eid);
      await reviewer
        .getByRole("combobox", { name: "Saved template version", exact: true })
        .selectOption(template.id);
      const coverage = reviewer.getByRole("region", {
        name: "Retained requirement coverage",
        exact: true,
      });
      await expect(
        coverage.getByRole("cell", { name: "COVERED", exact: true }),
      ).toHaveCount(877);
      await reviewer
        .getByRole("textbox", {
          name: "Template / review rationale",
          exact: true,
        })
        .fill(
          "Independent synthetic complete-population mapping mechanics review only",
        );
      const reviewedResponse = reviewer.waitForResponse((r) =>
        r.url().endsWith(`/events/${template.id}/review`),
      );
      await reviewer
        .getByRole("button", {
          name: "Record independent template approval",
          exact: true,
        })
        .click();
      const reviewed = await reviewedResponse;
      expect(reviewed.status(), await reviewed.text()).toBe(201);
      const generatedResponse = reviewer.waitForResponse(
        (r) => r.url().endsWith("/reports") && r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", {
          name: "Generate from current reviewed sources",
          exact: true,
        })
        .click();
      const generated = await generatedResponse;
      expect(generated.status(), await generated.text()).toBe(201);
      const report = await generated.json();
      expect(report.body.requirements_coverage.items).toHaveLength(877);
      expect(report.body.tax_form_content_qualified).toBe(false);
      expect(report.body.requirements_coverage.requirements_pack.sha256).toBe(
        pack.sha256,
      );
      await reviewer
        .getByRole("link", {
          name: "Review generated report and export DOCX / XLSX / PDF",
          exact: true,
        })
        .click();
      const downloadEvent = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      const file = await (await downloadEvent).path();
      expect(file).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          "import io,sys\nfrom openpyxl import load_workbook\nw=load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True)\nassert len(list(w['Requirements coverage'].values))==878",
        ],
        { input: readFileSync(file!), timeout: 15000 },
      );
      const preview = reviewer.getByRole("region", {
        name: "Saved statutory report preview",
        exact: true,
      });
      await preview
        .getByRole("textbox", {
          name: "Search saved report requirements",
          exact: true,
        })
        .fill(last.key);
      await expect(
        preview.getByRole("cell", { name: last.key, exact: true }),
      ).toBeVisible();
      await preview
        .getByRole("button", { name: "Next saved blocks", exact: true })
        .click();
      await reviewer.setViewportSize({ width: 2200, height: 3400 });
      const reportHeading = preview.getByRole("heading", {
        name: raw.title,
        exact: true,
      });
      await reportHeading.scrollIntoViewIfNeeded();
      await expect(reportHeading).toBeInViewport();
      await expect(
        preview.getByRole("heading", {
          name: `9. ${blocks[8].title}`,
          exact: true,
        }),
      ).toBeInViewport();
      await reviewer.screenshot({
        path: `${screenshots}/IN-form26-${part}-generated-current.png`,
      });
      const historical = structuredClone(report.body);
      await action(actors.partner.request, papers[8], "reopen");
      const stale = await get(
        `intelligence/engagements/${eid}/events/${report.id}`,
      );
      expect(stale.freshness).toBe("STALE");
      expect(stale.body).toEqual(historical);
      await reviewer.reload();
      await expect(
        reviewer.getByRole("combobox", { name: "Result version", exact: true }),
      ).toHaveValue(report.id);
      await expect(
        reviewer.getByText("STALE", { exact: true }).first(),
      ).toBeVisible();
      await reviewer.setViewportSize({ width: 2200, height: 3400 });
      const heading = reviewer.getByRole("heading", {
        name: raw.title,
        exact: true,
      });
      await heading.scrollIntoViewIfNeeded();
      await expect(heading).toBeInViewport();
      await expect(
        reviewer
          .getByRole("alert")
          .filter({ hasText: "This saved report is STALE" }),
      ).toBeInViewport();
      await expect(
        reviewer.getByRole("button", {
          name: "Record independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      await reviewer.screenshot({
        path: `${screenshots}/IN-form26-${part}-generated-stale.png`,
      });
    } finally {
      for (const context of contexts) await context.close();
    }
  });
}
