import { test, expect, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

async function login(page: Page, email: string | undefined) {
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

function csv(rows: Record<string, unknown>[]) {
  const fields = Object.keys(rows[0]);
  const quote = (value: unknown) =>
    `"${String(value ?? "").replaceAll('"', '""')}"`;
  return Buffer.from(
    [
      fields.join(","),
      ...rows.map((row) => fields.map((field) => quote(row[field])).join(",")),
      "",
    ].join("\n"),
  );
}

test("UAE then India assessed ICFR duties retain separate scope, originals, review, complete export and staleness", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const ids = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(ids.synthetic_only).toBe(true);
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 2200, height: 1800 },
  });
  const reviewer = await context.newPage();
  const errors: string[] = [];
  for (const actor of [page, reviewer]) {
    actor.setDefaultTimeout(20000);
    actor.on("pageerror", (error) => errors.push(error.message));
  }
  mkdirSync("test-results/country-reports", { recursive: true });
  await page.setViewportSize({ width: 2200, height: 1800 });
  try {
    await login(page, process.env.AUDITOS_SMOKE_EMAIL);
    await login(reviewer, process.env.AUDITOS_SMOKE_REVIEWER_EMAIL);
    const headers = {
      "X-Tenant-ID": ids.tenant_id,
      Origin: process.env.AUDITOS_E2E_ORIGIN!,
    };
    async function post(path: string, data: unknown, status = 201) {
      const response = await page.request.post(`/api/backend/${path}`, {
        headers,
        data,
      });
      expect(response.status(), await response.text()).toBe(status);
      return response.json();
    }
    for (const country of ["AE", "IN"] as const) {
      const currency = country === "AE" ? "AED" : "INR";
      for (const actor of [page, reviewer]) {
        await actor.goto("/settings/countries");
        await actor
          .getByRole("combobox", { name: "Working country", exact: true })
          .selectOption(country);
      }
      const client = await post("clients", {
        code: `ICFR-${country}-${Date.now()}`,
        name: `SYNTHETIC ${country} ICFR client`,
      });
      const entity = await post("entities", {
        client_id: client.id,
        name: `SYNTHETIC ${country} ICFR entity`,
        country,
        jurisdiction: country === "AE" ? "UAE" : "India",
        functional_currency: currency,
        presentation_currency: currency,
      });
      const period = await post("financial-periods", {
        entity_id: entity.id,
        start_date: country === "AE" ? "2026-01-01" : "2026-04-01",
        end_date: country === "AE" ? "2026-12-31" : "2027-03-31",
      });
      const engagement = await post("engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC ${country} ICFR duties`,
        engagement_type: "External Audit",
      });
      const eid = engagement.id;
      await post(
        `engagements/${eid}/audit/team`,
        {
          membership_id: ids.reviewer_membership_id,
          role_id: ids.reviewer_role_id,
        },
        200,
      );
      const h = makeWorkflowHarness(page, eid, ids.tenant_id);
      const folder = `../docs/country-workflows/sample-inputs/SYNTHETIC-icfr-duty-coverage/${country === "AE" ? "UAE" : "India"}`;
      const authority = await h.evidence(
        `SYNTHETIC-${country}-icfr-authority.txt`,
        readFileSync(`${folder}/authority.txt`),
      );
      const assessment = await h.evidence(
        `SYNTHETIC-${country}-icfr-assessment.txt`,
        readFileSync(`${folder}/assessment.txt`),
      );
      const scopeBytes = Buffer.from(
        readFileSync(`${folder}/scopes.csv`, "utf8")
          .replaceAll(
            "00000000-0000-4000-8000-000000000001",
            authority.version.id,
          )
          .replaceAll(
            "00000000-0000-4000-8000-000000000002",
            assessment.version.id,
          ),
      );
      const sources: Record<string, WorkflowEvent> = {};
      let originalScope: WorkflowEvent;
      for (const [role, table, content, count] of [
        ["scopes", "icfr-duty-scopes", scopeBytes, 2],
        ["checks", "checks", readFileSync(`${folder}/checks.csv`), 1],
      ] as const) {
        const file = await h.evidence(
          `SYNTHETIC-${country}-icfr-${role}.csv`,
          content,
        );
        const source = await h.prepare({
          evidence_version_id: file.version.id,
          table_type: table,
          label: `SYNTHETIC ${country} ICFR ${role}`,
          expected_rows: count,
          control_totals: {},
        });
        if (role === "scopes") {
          originalScope = source;
          expect(source.body.icfr_scope_document_binding).toBe(
            "RETAINED_DOCUMENT_BYTES_VERIFIED",
          );
        }
        sources[role] = await h.post(
          reviewer.request,
          `${h.prefix}/events/${source.id}/review`,
          {
            expected_version: source.version,
            action: "approve",
            comments:
              "SYNTHETIC independent scope and declared evidence source review",
          },
        );
      }
      const title = `SYNTHETIC ${country} separate ICFR duties`;
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByRole("combobox", { name: "Workflow", exact: true })
        .selectOption("icfr-duty-coverage");
      await page
        .getByText(/\d+ synthetic reference scenarios across country workflows/)
        .click();
      const references = page.getByRole("list", {
        name: "Reference scenarios",
        exact: true,
      });
      await expect(references.getByRole("listitem")).toHaveCount(5);
      const referencePanel = page
        .getByText(/\d+ synthetic reference scenarios across country workflows/)
        .locator("..");
      await referencePanel.screenshot({
        path: `test-results/country-reports/${country}-scenario-engagement-default.png`,
      });
      await expect(
        references.getByText(
          new RegExp(`^RW-.*SYNTHETIC ${country === "AE" ? "IN" : "AE"} `),
        ),
      ).toHaveCount(0);
      await page
        .getByLabel("Reference scenario countries", { exact: true })
        .selectOption("all");
      await page
        .getByLabel("Reference scenario workflows", { exact: true })
        .selectOption("all");
      await page
        .getByLabel("Search reference scenarios", { exact: true })
        .fill("RW-160");
      await expect(references.getByRole("listitem")).toHaveCount(1);
      await expect(
        references.getByText(/^RW-160 · SYNTHETIC IN /),
      ).toBeVisible();
      await expect(references.getByText(/^India · /)).toBeVisible();
      await references
        .getByText("Expected synthetic outcome for RW-160", { exact: true })
        .click();
      await expect(references.locator("pre")).toContainText('"blocked": false');
      await referencePanel.screenshot({
        path: `test-results/country-reports/${country}-scenario-cross-country.png`,
      });
      await expect(
        page.getByRole("combobox", { name: "Workflow", exact: true }),
      ).toHaveValue("icfr-duty-coverage");
      await page
        .getByText(/\d+ synthetic reference scenarios across country workflows/)
        .click();
      for (const [role, source] of Object.entries(sources))
        await page
          .getByLabel(`${role} source`, { exact: true })
          .selectOption(source.id);
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reporting period start", "2026-06-01"],
        ["Reconciliation date", "2026-06-30"],
        ["Subject population, comma separated", "SYN-COMPONENT"],
        ["Required check identifiers, comma separated", "404a:CTRL"],
        [
          "Scope and source rationale",
          "SYNTHETIC independently assessed issuer/group scope; not a legal or effectiveness opinion",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      const queue = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/${h.prefix}/jobs`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const queued = await queue;
      expect(queued.status(), await queued.text()).toBe(202);
      const result = await h.completed((await queued.json()).id);
      expect(result.body.blocked).toBe(false);
      expect(result.body.effectiveness_conclusion).toBe("NOT_DETERMINED");
      expect(result.body.statutory_calculation_qualified).toBe(false);
      expect(result.body.rows).toHaveLength(3);
      await page.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      await page
        .getByLabel("Review / exception rationale", { exact: true })
        .fill("SYNTHETIC author approval remains prohibited");
      const self = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${result.id}/review`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      expect((await self).status()).toBe(403);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      await reviewer
        .getByLabel("Review / exception rationale", { exact: true })
        .fill(
          "SYNTHETIC independent assessment of separately declared duties and retained support; no effectiveness opinion",
        );
      const decision = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${result.id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const reviewed = await decision;
      expect(reviewed.status(), await reviewed.text()).toBe(201);
      const approved: WorkflowEvent = await reviewed.json();
      await expect(
        reviewer.getByLabel("Saved source or result", { exact: true }),
      ).toHaveValue(approved.id);
      await expect(
        reviewer.getByRole("cell", {
          name: "Management assessment",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("cell", {
          name: "Auditor attestation",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("cell", { name: "NOT-APPLICABLE", exact: true }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("region", { name: "ICFR duty scope and evidence" }),
      ).toContainText("files were checked against retained originals");
      const downloadEvent = reviewer.waitForEvent("download");
      const exporting = reviewer.waitForResponse((r) =>
        r.url().endsWith(`/events/${approved.id}/export?format=xlsx`),
      );
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      expect((await exporting).status()).toBe(200);
      const file = await (await downloadEvent).path();
      expect(file).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          [
            "import io,sys",
            "from openpyxl import load_workbook",
            "rows=list(load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True)['Rows'].values)",
            "assert len(rows)==4;records=[dict(zip(rows[0],r)) for r in rows[1:]]",
            "scopes={r['duty']:r for r in records if r['kind']=='scope-decision'}",
            "assert scopes['404a']['state']=='SUPPORTED' and scopes['404b']['state']=='NOT-APPLICABLE'",
            `assert scopes['404a']['assessment_evidence_version_id']==${JSON.stringify(assessment.version.id)}`,
          ].join("\n"),
        ],
        { input: readFileSync(file!), timeout: 15000 },
      );
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `test-results/country-reports/${country}-icfr-reviewed.png`,
        });
      const missingFile = await h.evidence(
        `SYNTHETIC-${country}-missing-auditor-scope.csv`,
        csv([originalScope!.body.rows[0]]),
      );
      const missingSource = await h.prepare({
        evidence_version_id: missingFile.version.id,
        table_type: "icfr-duty-scopes",
        label: `SYNTHETIC ${country} missing auditor scope`,
        expected_rows: 1,
        control_totals: {},
      });
      const missingApproved = await h.post(
        reviewer.request,
        `${h.prefix}/events/${missingSource.id}/review`,
        {
          expected_version: missingSource.version,
          action: "approve",
          comments:
            "SYNTHETIC known incomplete scope file; not a completeness opinion",
        },
      );
      const missing = await h.prepare(
        {
          workflow: "icfr-duty-coverage",
          title: `SYNTHETIC ${country} unresolved auditor scope`,
          source_ids: { scopes: missingApproved.id, checks: sources.checks.id },
          period_start: "2026-06-01",
          as_of: "2026-06-30",
          subjects: ["SYN-COMPONENT"],
          required_checks: ["404a:CTRL"],
          rationale:
            "SYNTHETIC missing 404b decision must remain unresolved even with supported management evidence",
        },
        "country-workflow",
      );
      expect(missing.body.blocked).toBe(true);
      expect(missing.body.rows).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            duty: "404b",
            state: "MISSING_SCOPE_DECISION",
          }),
        ]),
      );
      const refused = await reviewer.request.post(
        `/api/backend/${h.prefix}/events/${missing.id}/review`,
        {
          headers,
          data: {
            expected_version: missing.version,
            action: "approve",
            comments:
              "SYNTHETIC unknown auditor scope cannot be approved as complete",
          },
        },
      );
      expect(refused.status()).toBe(409);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${missing.id}`,
      );
      await expect(
        reviewer.getByRole("cell", {
          name: "MISSING_SCOPE_DECISION",
          exact: true,
        }),
      ).toBeVisible();
      await reviewer
        .getByRole("heading", {
          name: `SYNTHETIC ${country} unresolved auditor scope`,
          exact: true,
        })
        .locator("..")
        .screenshot({
          path: `test-results/country-reports/${country}-icfr-pending-scope.png`,
        });
      await h.upload(
        assessment.record,
        `SYNTHETIC-${country}-changed-ICFR-facts.txt`,
        Buffer.from(
          "SYNTHETIC changed issuer/group duty facts require fresh assessment",
        ),
      );
      const staleResponse = await reviewer.request.get(
        `/api/backend/${h.prefix}/events/${approved.id}`,
        { headers },
      );
      expect(staleResponse.status()).toBe(200);
      const stale = await staleResponse.json();
      expect(stale.freshness).toBe("STALE");
      expect(stale.body).toEqual(approved.body);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${approved.id}`,
      );
      await expect(
        reviewer.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `test-results/country-reports/${country}-icfr-stale.png`,
        });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
