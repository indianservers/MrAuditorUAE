import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

type Paper = {
  id: string;
  version: number;
  status: string;
  body: Record<string, unknown>;
};

async function login(page: Page, email: string) {
  if (!email || !process.env.AUDITOS_SMOKE_PASSWORD)
    throw new Error("Explicit isolated synthetic identities required");
  await page.goto("/login");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.AUDITOS_SMOKE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

test("source-pinned DMCC company and foreign branch procedure reviews retain separate scope and stale evidence", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const ids = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(ids.synthetic_only).toBe(true);
  const screenshots = "test-results/country-reports";
  mkdirSync(screenshots, { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 1800, height: 2200 },
  });
  const reviewer = await context.newPage();
  const errors: string[] = [];
  for (const actor of [page, reviewer]) {
    actor.setDefaultTimeout(20000);
    actor.on("pageerror", (error) => errors.push(error.message));
  }
  try {
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
    await login(reviewer, process.env.AUDITOS_SMOKE_REVIEWER_EMAIL!);
    const headers = {
      "X-Tenant-ID": ids.tenant_id,
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
    for (const country of ["AE", "IN"] as const) {
      for (const actor of [page, reviewer]) {
        await actor.goto("/settings/countries");
        await actor
          .getByRole("combobox", { name: "Working country", exact: true })
          .selectOption(country);
      }
      const currency = country === "AE" ? "AED" : "INR";
      const client = await post(page.request, "clients", {
        code: `DMCC-${country}-${Date.now()}`,
        name: "SYNTHETIC DMCC procedure client",
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: `SYNTHETIC ${country} DMCC procedure entity`,
        country,
        jurisdiction: country,
        functional_currency: currency,
        presentation_currency: currency,
      });
      const period = await post(page.request, "financial-periods", {
        entity_id: entity.id,
        start_date: "2026-01-01",
        end_date: "2026-12-31",
      });
      const engagement = await post(page.request, "engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC ${country} DMCC authority procedure`,
        engagement_type: "External Audit",
      });
      const eid = engagement.id,
        audit = `engagements/${eid}/audit`,
        base = `grc/engagements/${eid}`;
      await post(
        page.request,
        `${audit}/team`,
        {
          membership_id: ids.reviewer_membership_id,
          role_id: ids.reviewer_role_id,
        },
        200,
      );
      async function action(
        request: APIRequestContext,
        prefix: string,
        paper: Paper,
        value: string,
      ): Promise<Paper> {
        return post(
          request,
          `${prefix}/records/${paper.id}/actions`,
          {
            version: paper.version,
            action: value,
            comments:
              "SYNTHETIC independent source and assessed DMCC procedure review; no legal/client qualification",
          },
          200,
        );
      }
      const originals: Record<string, Paper> = {};
      const harness = makeWorkflowHarness(page, eid, ids.tenant_id);
      for (const [role, name] of [
        ["rule", "dmcc-company-regulations-amended.pdf"],
        ["guideline", "dmcc-afs-guidelines-2025-04-29.pdf"],
        ["facts", ""],
        ["readiness", ""],
      ]) {
        let recordId: string;
        if (name) {
          const record = await post(page.request, `${audit}/evidence`, {
            reference: `SYN-DMCC-${role}-${Date.now()}`,
            title: `Original public DMCC ${role} PDF for synthetic case`,
            body: { category: "Other", retain_until: "2036-12-31" },
          });
          const response = await page.request.post(
            `/api/backend/${audit}/evidence-files/${record.id}`,
            {
              headers,
              multipart: {
                file: {
                  name,
                  mimeType: "application/pdf",
                  buffer: readFileSync(
                    `../docs/country-workflows/authority-references/dmcc-audit-2026-10-30/${name}`,
                  ),
                },
              },
            },
          );
          expect(response.status(), await response.text()).toBe(201);
          expect((await response.json()).scan_status).toBe("CLEAN");
          recordId = record.id;
        } else {
          const file = await harness.evidence(
            `SYNTHETIC-DMCC-${role}.txt`,
            Buffer.from(
              `SYNTHETIC independently assessed ${role}; fictional membership, auditor and readiness; no real client or professional qualification`,
            ),
          );
          recordId = file.record;
        }
        let record: Paper = await get(`${audit}/records/${recordId}`);
        record = await action(page.request, audit, record, "submit");
        originals[role] = await action(
          reviewer.request,
          audit,
          record,
          "approve",
        );
      }
      const branch = country === "IN";
      const reference = `SYN-DMCC-${country}`;
      let paper: Paper = await post(
        page.request,
        `${base}/records/obligation`,
        {
          reference,
          title: `SYNTHETIC ${country} source-pinned DMCC procedure`,
          body: {
            owner_id: ids.preparer_user_id,
            entity_id: entity.id,
            module: "license",
            source_url:
              "https://dmcc.ae/members/support/knowledge-bank/compliance-and-regulations",
            jurisdiction: "AE",
            jurisdiction_scope: {
              entity_country: country,
              obligation_country: "AE",
              relationship: branch ? "foreign" : "domestic",
              applicability: "assessed_applicable",
              registration_reference: "SYNTHETIC-DMCC-123",
              assessment:
                "SYNTHETIC independently assessed exact company or foreign branch scope; no registry authenticity",
            },
            obligation_period_start: "2025-01-01",
            obligation_period_end: "2025-12-31",
            effective_from: "2025-01-01",
            deadline_kind: "firm_internal",
            rule_evidence_id: originals.rule.id,
            dmcc_guideline_evidence_id: originals.guideline.id,
            fact_evidence_ids: [originals.facts.id],
            readiness_evidence_ids: [originals.readiness.id],
            reviewer_id: ids.reviewer_user_id,
            entity_facts: {
              assessment:
                "SYNTHETIC original company, membership, auditor and operative-window facts",
            },
            required_evidence:
              "Exact source PDFs plus separate independently assessed entity and readiness evidence",
            compliance_assessment: "pending",
            filing_stage: "preparing",
            deadline_rule: {
              identifier: "SYNTHETIC-DMCC-six-month-rule",
              version: 1,
              effective_from: "2024-10-10",
              trigger: "2025-12-31",
              date_basis: "period_end",
              months_after: 6,
              timezone: "Asia/Dubai",
            },
            dmcc_audit_scope: {
              profile: "dmcc-company-2024-amended-2025-and-afs-guidance-2025/1",
              procedure: branch ? "portal_submission" : "accounts_timetable",
              legal_form: branch ? "branch" : "company_limited_by_shares",
              membership: "assessed_yes",
              dormant_whole_year: branch ? "not_applicable" : "assessed_no",
              holding_company: branch ? "not_applicable" : "assessed_no",
              accounts_notice: "not_applicable",
              audit_notice: "not_applicable",
              branch_group_auditor: branch ? "assessed_yes" : "not_applicable",
              auditor_status: branch
                ? "group_auditor_exception"
                : "assessed_approved",
              auditor_reference: "SYNTHETIC-AUDITOR-1",
              other_authority_modifications: "assessed_none",
              operative_from: "2024-10-10",
              operative_through: "2026-12-31",
              assessed_on: "2026-06-30",
              assessment:
                "SYNTHETIC independently adopted rule window and company facts; not legal or professional qualification",
            },
          },
        },
      );
      expect(paper.body.deadline).toBe("2026-06-30");
      paper = await post(
        page.request,
        `${base}/obligations/${paper.id}/filing-stage`,
        { version: paper.version, stage: "under_review" },
        200,
      );
      paper = await action(page.request, base, paper, "submit");
      paper = await action(reviewer.request, base, paper, "approve");
      async function open() {
        await reviewer.goto(`/grc/${eid}/obligations`);
        await reviewer
          .getByRole("gridcell", { name: reference, exact: true })
          .click();
        const result = reviewer.getByRole("region", {
          name: "DMCC authority procedure assessment",
          exact: true,
        });
        await expect(result).toContainText("REQUIRED ON ASSESSED FACTS");
        await expect(result).toContainText(
          branch
            ? "BRANCH GROUP AUDITOR EXCEPTION ASSESSED"
            : "DMCC APPROVED AUDITOR REQUIRED",
        );
        return result;
      }
      let result = await open();
      const filing = reviewer.getByRole("region", {
        name: "Filing readiness",
        exact: true,
      });
      await filing
        .getByRole("combobox", { name: "Next filing stage", exact: true })
        .selectOption("approved_for_submission");
      const approved = reviewer.waitForResponse(
        (r) =>
          r.url().includes(`/obligations/${paper.id}/filing-stage`) &&
          r.request().method() === "POST",
      );
      await filing
        .getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        })
        .click();
      const response = await approved;
      expect(response.status(), await response.text()).toBe(200);
      paper = await response.json();
      await expect(result).toContainText("Source freshness: CURRENT");
      const notice = reviewer.getByRole("button", {
        name: "Dismiss notification",
        exact: true,
      });
      if (await notice.count()) await notice.last().click();
      await result.screenshot({
        path: `${screenshots}/${country}-DMCC-procedure-reviewed.png`,
      });
      const retained = structuredClone(paper.body);
      await action(reviewer.request, audit, originals.guideline, "reopen");
      expect((await get(`${audit}/records/${paper.id}`)).body).toEqual(
        retained,
      );
      result = await open();
      await expect(result).toContainText("Source freshness: STALE");
      await expect(result.getByRole("alert")).toContainText(
        "Reassess the retained source documents",
      );
      await filing
        .getByLabel("Actual submission evidence record ID", { exact: true })
        .fill(originals.readiness.id);
      await expect(
        filing.getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        }),
      ).toBeDisabled();
      await result.screenshot({
        path: `${screenshots}/${country}-DMCC-guideline-withdrawn-stale.png`,
      });
      expect((await get(`entities/${entity.id}`)).country).toBe(country);
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
