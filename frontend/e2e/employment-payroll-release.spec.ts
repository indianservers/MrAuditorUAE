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

test("UAE then India employment payroll: corrections, separate approval, exact export and withdrawn source", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
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
          .getByLabel("Working country", { exact: true })
          .selectOption(country);
        await expect(
          actor.getByLabel("Working country", { exact: true }),
        ).toHaveValue(country);
      }
      const client = await post("clients", {
        code: `EMP-${country}-${Date.now()}`,
        name: `SYNTHETIC ${country} payroll client`,
      });
      const entity = await post("entities", {
        client_id: client.id,
        name: `SYNTHETIC ${country} employer`,
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
        name: `SYNTHETIC ${country} employment payroll`,
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
      const sources: Record<string, WorkflowEvent> = {};
      const originalIds: Record<string, string> = {};
      for (const [role, name, table, total] of [
        ["employment", "employment", "employment-payroll-episodes", null],
        ["controls", "controls", "employment-payroll-controls", "1000"],
        ["register", "register", "employment-payroll-register", "2500"],
      ] as const) {
        let bytes = readFileSync(
          `../pilot-data/synthetic-employment-payroll/${country === "AE" ? "UAE" : "India"}/${name}.csv`,
        );
        if (role === "register") {
          // These controlled fixture fields contain no quoted commas. Retain an
          // explicit superseded 1500 entry and current revision 2 of 1000.
          const [header, line] = bytes.toString("utf8").trim().split(/\r?\n/);
          const fields = header.split(",");
          const old = line.split(","),
            current = line.split(",");
          expect(old).toHaveLength(fields.length);
          old[fields.indexOf("id")] = "R0";
          old[fields.indexOf("amount")] = "1500";
          old[fields.indexOf("record_status")] = "superseded";
          current[fields.indexOf("revision")] = "2";
          bytes = Buffer.from(
            [header, old.join(","), current.join(","), ""].join("\n"),
          );
        }
        const file = await h.evidence(
          `SYNTHETIC-${country}-employment-${name}.csv`,
          bytes,
        );
        const imported = await h.prepare({
          evidence_version_id: file.version.id,
          table_type: table,
          label: `SYNTHETIC ${country} employment ${role}`,
          expected_rows: role === "register" ? 2 : 1,
          control_totals: total === null ? {} : { [currency]: total },
        });
        originalIds[role] = imported.id;
        sources[role] = await h.post(
          reviewer.request,
          `${h.prefix}/events/${imported.id}/review`,
          {
            expected_version: imported.version,
            action: "approve",
            comments:
              "SYNTHETIC independently assessed contract, service and payroll input",
          },
        );
      }
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("employment-payroll-review");
      for (const [role, source] of Object.entries(sources)) {
        const select = page.getByLabel(`${role} source`, { exact: true });
        await expect(
          select.locator(`option[value="${originalIds[role]}"]`),
        ).toHaveCount(0);
        await select.selectOption(source.id);
      }
      const title = `SYNTHETIC ${country} employment June correction`;
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reporting period start", "2026-06-01"],
        ["Reconciliation date", "2026-06-30"],
        [
          "Scope and source rationale",
          "SYNTHETIC independent joiner service and pay assessment; no salary proration inferred",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      const queued = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/${h.prefix}/jobs`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const response = await queued;
      expect(response.status(), await response.text()).toBe(202);
      const result = await h.completed((await response.json()).id);
      expect(result.body.blocked).toBe(false);
      expect(result.body.rows).toHaveLength(3);
      expect(
        result.body.rows.find((r) => r.kind === "entry-comparison"),
      ).toMatchObject({
        expected_amount: "1000",
        reported_amount: "1000",
        difference: "0",
        state: "MATCHED",
      });
      expect(
        result.body.rows.filter((r) => r.counted_in_current_payroll === true),
      ).toHaveLength(1);
      await page.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      await page
        .getByLabel("Review / exception rationale", { exact: true })
        .fill("SYNTHETIC author approval remains prohibited");
      const selfDecision = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${result.id}/review`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      expect((await selfDecision).status()).toBe(403);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      await reviewer
        .getByLabel("Review / exception rationale", { exact: true })
        .fill(
          "SYNTHETIC independently assessed joiner, original service dates, corrected pay and full history",
        );
      const reviewed = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${result.id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const reviewedResponse = await reviewed;
      expect(reviewedResponse.status(), await reviewedResponse.text()).toBe(
        201,
      );
      const approved: WorkflowEvent = await reviewedResponse.json();
      expect(approved.body.review_status).toBe("REVIEWED");
      // Approval selects a new immutable event and remounts the export scope.
      // Wait for that selection before starting a download of the reviewed event.
      await expect(
        reviewer.getByLabel("Saved source or result", { exact: true }),
      ).toHaveValue(approved.id);
      await expect(
        reviewer.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
      await reviewer
        .getByRole("combobox", { name: "Employment payroll view", exact: true })
        .selectOption("history");
      await expect(
        reviewer.getByRole("cell", { name: "1500", exact: true }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("cell", { name: "superseded", exact: true }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("cell", { name: "current", exact: true }),
      ).toBeVisible();
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `test-results/country-reports/${country}-employment-payroll-history.png`,
        });
      const downloadEvent = reviewer.waitForEvent("download");
      const exportResponse = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${approved.id}/export?format=xlsx`) &&
          r.request().method() === "GET",
      );
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      const exported = await exportResponse;
      expect(
        exported.status(),
        exported.ok() ? "Reviewed XLSX response" : await exported.text(),
      ).toBe(200);
      const download = await (await downloadEvent).path();
      expect(download).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          [
            "import io,sys",
            "from openpyxl import load_workbook",
            "w=load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True)",
            "rows=list(w['Rows'].values);assert len(rows)==4",
            "records=[dict(zip(rows[0],r)) for r in rows[1:]]",
            "entry=next(r for r in records if r['kind']=='entry-comparison')",
            "assert entry['expected_amount']==entry['reported_amount']=='1000' and entry['difference']=='0'",
            "history=[r for r in records if r['kind']=='revision-history']",
            "assert {r['retained_amount'] for r in history}=={'1000','1500'}",
            "assert {str(r['revision']) for r in history}=={'1','2'}",
          ].join("\n"),
        ],
        { input: readFileSync(download!), timeout: 15000 },
      );
      await reviewer
        .getByRole("combobox", { name: "Employment payroll view", exact: true })
        .selectOption("assessment");
      await expect(
        reviewer.getByRole("columnheader", {
          name: "expected amount",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("cell", { name: "1000", exact: true }),
      ).toHaveCount(2);
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `test-results/country-reports/${country}-employment-payroll-reviewed.png`,
        });
      const incomplete = await h.prepare(
        {
          workflow: "employment-payroll-review",
          source_ids: Object.fromEntries(
            Object.entries(sources).map(([role, source]) => [role, source.id]),
          ),
          period_start: "2026-06-01",
          as_of: "2026-07-31",
          title: `SYNTHETIC ${country} missing July payroll controls`,
          rationale:
            "SYNTHETIC July is in the declared employment episode but neither pay nor independent controls were supplied",
        },
        "country-workflow",
      );
      expect(incomplete.body.blocked).toBe(true);
      expect(
        incomplete.body.rows.filter(
          (r) => r.state === "MISSING_EMPLOYEE_MONTH_CONTROL",
        ),
      ).toEqual([
        expect.objectContaining({
          payroll_month: "2026-07",
          expected_amount: null,
        }),
      ]);
      const refused = await reviewer.request.post(
        `/api/backend/${h.prefix}/events/${incomplete.id}/review`,
        {
          headers,
          data: {
            expected_version: incomplete.version,
            action: "approve",
            comments:
              "SYNTHETIC missing monthly evidence must not be approvable as complete",
          },
        },
      );
      expect(refused.status(), await refused.text()).toBe(409);
      await h.post(
        reviewer.request,
        `${h.prefix}/events/${sources.employment.id}/review`,
        {
          expected_version: sources.employment.version,
          action: "reject",
          comments:
            "SYNTHETIC employment source withdrawn; original output must remain immutable",
        },
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
          path: `test-results/country-reports/${country}-employment-payroll-stale.png`,
        });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});
