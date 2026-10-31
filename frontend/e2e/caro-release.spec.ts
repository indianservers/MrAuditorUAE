import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { makeWorkflowHarness } from "./msme-browser-workflow";

async function login(page: Page, email: string) {
  if (!email || !process.env.AUDITOS_SMOKE_PASSWORD)
    throw new Error("Isolated synthetic review identities required");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.AUDITOS_SMOKE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}
type Requirement = {
  key: string;
  title: string;
  disposition: string;
  source_required: boolean;
  basis: string;
};
type RecordVersion = { id: string; version: number };

for (const scope of ["standalone", "consolidated"] as const) {
  test(`CARO ${scope} UI revision, separate review, complete export and stale evidence`, async ({
    page,
    browser,
  }) => {
    test.setTimeout(300000);
    const ids = JSON.parse(
      readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
    );
    expect(ids.synthetic_only).toBe(true);
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
    const contexts = [],
      actors: Record<string, Page> = {};
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    try {
      for (const [name, email] of [
        ["reviewer", process.env.AUDITOS_SMOKE_REVIEWER_EMAIL],
        ["manager", ids.manager_email],
        ["partner", ids.partner_email],
      ]) {
        const context = await browser.newContext({
          baseURL: process.env.AUDITOS_E2E_ORIGIN,
          viewport: { width: 1600, height: 1200 },
        });
        contexts.push(context);
        actors[name] = await context.newPage();
        actors[name].on("pageerror", (e) => errors.push(e.message));
        await login(actors[name], email);
      }
      const reviewer = actors.reviewer;
      for (const actor of [page, reviewer]) {
        actor.setDefaultTimeout(20000);
        await actor.goto("/settings/countries");
        await actor
          .getByRole("combobox", { name: "Working country", exact: true })
          .selectOption("IN");
      }
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
      const client = await post(page.request, "clients", {
        code: `CARO-${scope}-${Date.now()}`,
        name: "SYNTHETIC CARO browser",
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: "SYNTHETIC India company",
        country: "IN",
        jurisdiction: "Synthetic",
        functional_currency: "INR",
        presentation_currency: "INR",
      });
      const period = await post(page.request, "financial-periods", {
        entity_id: entity.id,
        start_date: "2025-04-01",
        end_date: "2026-03-31",
      });
      const eng = await post(page.request, "engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC CARO ${scope}`,
        engagement_type: "External Audit",
      });
      const eid = eng.id,
        audit = `engagements/${eid}/audit`,
        reg = `regulatory/engagements/${eid}`;
      const { evidence, upload, prefix } = makeWorkflowHarness(
        page,
        eid,
        ids.tenant_id,
      );
      for (const name of ["reviewer", "manager", "partner"])
        await post(
          page.request,
          `${audit}/team`,
          {
            membership_id: ids[`${name}_membership_id`],
            role_id: ids[`${name}_role_id`],
          },
          200,
        );
      const folder =
        "../docs/country-workflows/authority-references/india-company-reporting-2026-10-31";
      const documents = [];
      for (const [role, file] of [
        ["small_company_amendment", "small-company-gsr880-2025.pdf"],
        ["caro_commencement", "caro2020-commencement-amendment.pdf"],
        ["ifc_notification", "ifc-private-gsr583-2017-original.pdf"],
      ]) {
        const source = await evidence(file, readFileSync(`${folder}/${file}`));
        documents.push({
          role,
          evidence_version_id: source.version.id,
          sha256: source.version.sha256,
        });
      }
      // Unpinned legal documents are explicitly synthetic controls, not a qualified source chain.
      const guide = readFileSync(`${folder}/caro2020-icai-guidance-2020.pdf`);
      for (const role of ["companies_act", "caro_order", "ifc_corrigendum"]) {
        const source = await evidence(
          `SYNTHETIC-unqualified-${role}.pdf`,
          Buffer.concat([
            guide,
            Buffer.from(`\n% SYNTHETIC ${role} ${randomUUID()}\n`),
          ]),
        );
        documents.push({
          role,
          evidence_version_id: source.version.id,
          sha256: source.version.sha256,
        });
      }
      const facts = {
        country: "IN",
        entity_reference: "SYNTHETIC-CARO",
        financial_period_start: "2025-04-01",
        financial_period_end: "2026-03-31",
        report_date: "2026-06-30",
        statement_scope: scope,
        is_indian_company: true,
        is_foreign_company: false,
        is_private_company: true,
        is_public_company: false,
        banking_company: false,
        insurance_company: false,
        section8_company: false,
        one_person_company: false,
        holding_or_subsidiary: false,
        holding_or_subsidiary_of_public_company: false,
        governed_by_special_act: false,
        other_special_exemption_claimed: false,
        small_paid_up_capital: "100000001",
        preceding_financial_year_turnover: "1000000001",
        caro_capital_reserves_and_surplus: "20000000",
        caro_max_bank_fi_borrowings: "20000000",
        caro_current_year_total_revenue: "110000000",
        latest_audited_turnover: "600000000",
        max_bank_fi_body_corporate_borrowings: "300000000",
        financial_statements_filing_default: false,
        annual_return_filing_default: false,
        facts_assessment:
          "SYNTHETIC assessed boundary inputs only, no client or legal qualification",
      };
      for (const role of ["legal_adoption", "company_facts"]) {
        const source = await evidence(
          `SYNTHETIC-${role}.txt`,
          Buffer.from(
            `SYNTHETIC control mechanics only, not independent legal qualification: ${role}\n${JSON.stringify(facts)}`,
          ),
        );
        documents.push({
          role,
          evidence_version_id: source.version.id,
          sha256: source.version.sha256,
        });
      }
      const preparedScope = await post(
        page.request,
        `${prefix}/india-company-reporting-scope`,
        {
          profile: "india-company-reporting-scope/1",
          label: "SYNTHETIC CARO eligibility",
          facts,
          adopted_from: "2025-04-01",
          adopted_through: "2026-06-30",
          source_chain_status: "independently_assessed",
          other_operative_changes: "assessed_none",
          legal_adoption_assessment:
            "SYNTHETIC mechanical adoption assertion, not actual legal qualification",
          documents,
        },
      );
      const scopeResult = await post(
        reviewer.request,
        `${prefix}/events/${preparedScope.id}/review`,
        {
          action: "approve",
          expected_version: preparedScope.version,
          comments:
            "SYNTHETIC independent control review, not legal qualification",
        },
      );
      const catalogue = await get(`${reg}/report-presets`);
      const pack = catalogue.items.find(
        (p: { id: string }) => p.id === `india-caro-index:${scope}/1`,
      ) as { id: string; requirements: Requirement[] };
      expect(pack.requirements).toHaveLength(scope === "standalone" ? 50 : 3);
      const doc = await evidence(
        "SYNTHETIC-CARO-procedures.txt",
        Buffer.from(
          pack.requirements
            .map(
              (r) =>
                `SYNTHETIC ${r.key}: assessed test procedure; no actual audit opinion`,
            )
            .join("\n"),
        ),
      );
      async function action(
        request: APIRequestContext,
        record: RecordVersion,
        value: string,
      ) {
        return post(
          request,
          `${audit}/records/${record.id}/actions`,
          {
            version: record.version,
            action: value,
            comments: "SYNTHETIC independent review-stage decision",
          },
          200,
        );
      }
      let sourceRecord = await get(`${audit}/records/${doc.record}`);
      sourceRecord = await action(page.request, sourceRecord, "submit");
      sourceRecord = await action(reviewer.request, sourceRecord, "approve");
      const blocks = [];
      for (let offset = 0; offset < pack.requirements.length; offset += 25) {
        const group = pack.requirements.slice(offset, offset + 25);
        let paper = await post(page.request, `${audit}/working-papers`, {
          reference: `SYN-CARO-${randomUUID()}`,
          title: `SYNTHETIC CARO ${scope} ${offset}`,
          body: {
            folder: "SYNTHETIC CARO",
            sections: group.map((r) => ({
              heading: r.title,
              text: `SYNTHETIC ${r.key} applicability, test procedure and assessed conclusion; not a real client audit`,
            })),
            sources: [{ kind: "record", id: sourceRecord.id }],
            conclusion:
              "SYNTHETIC linked procedure controls, no opinion qualification",
            report_requirement_scope: {
              preset_id: pack.id,
              period_start: "2025-04-01",
              period_end: "2026-03-31",
              items: group.map((r, index) => ({
                key: r.key,
                disposition: "REQUIRED",
                section_index: index,
                supporting_sources: [{ kind: "record", id: sourceRecord.id }],
                assessment: `SYNTHETIC exact source mapping ${r.key}`,
              })),
            },
          },
        });
        paper = await action(page.request, paper, "submit");
        paper = await action(actors.manager.request, paper, "approve");
        paper = await action(actors.partner.request, paper, "approve");
        blocks.push({
          key: `clauses${offset}`,
          title: `Reviewed CARO group ${offset}`,
          kind: "working_paper_reference",
          source_kind: "record",
          source_id: paper.id,
          requirement_keys: group.map((r) => r.key),
        });
      }
      const initial = await post(page.request, `${reg}/report-templates`, {
        title: `SYNTHETIC CARO ${scope} draft`,
        category: "caro",
        company_reporting_scope_id: scopeResult.id,
        requirements_pack: pack.id,
        requirements: pack.requirements.map((r) => ({
          ...r,
          disposition: "REQUIRED",
        })),
        requirements_assessed: true,
        requirements_basis:
          "SYNTHETIC all numbered assessments linked, no legal sufficiency claim",
        blocks,
        rationale: "SYNTHETIC retained draft for browser review controls",
      });
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
      await expect(
        page.getByLabel("Reviewed CARO company-scope result", { exact: true }),
      ).toHaveValue(scopeResult.id);
      const last = pack.requirements.at(-1)!;
      const editedBasis =
        "SYNTHETIC browser-reviewed final CARO reason assessment; no legal qualification";
      await page
        .getByLabel("Search report requirements", { exact: true })
        .fill(last.key);
      await expect(
        page.getByLabel(`Requirement reference ${pack.requirements.length}`, {
          exact: true,
        }),
      ).toHaveValue(last.key);
      await page
        .getByRole("textbox", {
          name: `Applicability and source basis ${pack.requirements.length}`,
          exact: true,
        })
        .fill(editedBasis);
      const saving = page.waitForResponse(
        (r) =>
          r.url().endsWith("/report-templates") &&
          r.request().method() === "POST",
      );
      await page
        .getByLabel("Template / review rationale", { exact: true })
        .fill(
          "SYNTHETIC browser amendment of the retained CARO reason assessment",
        );
      await page
        .getByRole("button", { name: "Save template version", exact: true })
        .click();
      const saved = await saving;
      expect(saved.status(), await saved.text()).toBe(201);
      const template = await saved.json();
      expect(template.body.company_reporting_scope_id).toBe(scopeResult.id);
      expect(template.body.blocks).toEqual(initial.body.blocks);
      expect(
        template.body.requirements.find((r: Requirement) => r.key === last.key)
          ?.basis,
      ).toBe(editedBasis);
      await reviewer.goto("/reports/statutory");
      await reviewer
        .getByRole("combobox", { name: "Engagement", exact: true })
        .selectOption(eid);
      await reviewer
        .getByRole("combobox", { name: "Saved template version", exact: true })
        .selectOption(template.id);
      await reviewer
        .getByLabel("Template / review rationale", { exact: true })
        .fill("SYNTHETIC independent complete CARO mapping mechanics review");
      const approving = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${template.id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", {
          name: "Record independent template approval",
          exact: true,
        })
        .click();
      expect((await approving).status()).toBe(201);
      const generating = reviewer.waitForResponse(
        (r) => r.url().endsWith("/reports") && r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", {
          name: "Generate from current reviewed sources",
          exact: true,
        })
        .click();
      const generated = await generating;
      expect(generated.status(), await generated.text()).toBe(201);
      const report = await generated.json();
      expect(
        report.body.requirements.find((r: Requirement) => r.key === last.key)
          ?.basis,
      ).toBe(editedBasis);
      await reviewer
        .getByRole("link", {
          name: "Review generated report and export DOCX / XLSX / PDF",
          exact: true,
        })
        .click();
      const preview = reviewer.getByRole("region", {
        name: "Saved statutory report preview",
        exact: true,
      });
      await expect(
        preview.getByRole("link", {
          name: "Open retained company reporting scope",
          exact: true,
        }),
      ).toHaveAttribute(
        "href",
        `/intelligence/${eid}/country-workflow?event=${scopeResult.id}`,
      );
      await preview
        .getByLabel("Search saved report requirements", { exact: true })
        .fill(last.key);
      await expect(
        preview.getByRole("cell", { name: last.key, exact: true }),
      ).toBeVisible();
      await expect(
        preview.getByRole("cell", { name: editedBasis, exact: true }),
      ).toBeVisible();
      const notices = reviewer.getByRole("button", {
        name: "Dismiss notification",
        exact: true,
      });
      while (await notices.count()) await notices.first().click();
      mkdirSync("test-results/country-reports", { recursive: true });
      await preview
        .getByRole("heading", {
          name: "Saved requirement coverage",
          exact: true,
        })
        .locator("..")
        .screenshot({
          path: `test-results/country-reports/IN-CARO-${scope}-last-matter.png`,
        });
      const downloading = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      const file = await (await downloading).path();
      expect(file).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          `import io,sys;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True);rows=list(w['Requirements coverage'].values);expected=${JSON.stringify(pack.requirements.map((item) => item.key))};assert len(rows)==len(expected)+1;assert {r[0] for r in rows[1:]}==set(expected);assert next(dict(zip(rows[0],r)) for r in rows[1:] if r[0]==${JSON.stringify(last.key)})['basis']==${JSON.stringify(editedBasis)}`,
        ],
        { input: readFileSync(file!), timeout: 15000 },
      );
      sourceRecord = await action(
        actors.partner.request,
        sourceRecord,
        "reopen",
      );
      await upload(
        sourceRecord.id,
        "SYNTHETIC-replaced-CARO.txt",
        Buffer.from(
          "SYNTHETIC changed procedure evidence requires reassessment",
        ),
      );
      await reviewer.reload();
      await expect(preview.getByRole("alert")).toContainText("STALE");
      await expect(
        reviewer.getByRole("button", {
          name: "Record independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      const retained = await get(`${prefix}/events/${report.id}`);
      expect(retained.body).toEqual(report.body);
      await preview
        .getByLabel("Search saved report requirements", { exact: true })
        .fill(last.key);
      await preview
        .getByRole("heading", { level: 2 })
        .evaluate((node) => node.scrollIntoView({ block: "start" }));
      await expect(preview.getByRole("alert")).toBeInViewport();
      await expect(
        preview.getByRole("cell", { name: editedBasis, exact: true }),
      ).toBeInViewport();
      await reviewer.screenshot({
        path: `test-results/country-reports/IN-CARO-${scope}-stale.png`,
      });
      expect(errors).toEqual([]);
    } finally {
      for (const context of contexts) await context.close();
    }
  });
}
