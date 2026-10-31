import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

export async function runCTAuditDutyBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { headers, prefix, post, evidence, upload } = makeWorkflowHarness(
    page,
    eid,
    tenant,
  );
  const rule = await evidence(
    "original-md84-2025.pdf",
    readFileSync(
      "../docs/country-workflows/authority-references/uae-ct-audit-2025/md84-2025-original.pdf",
    ),
  );
  const facts = await evidence(
    "SYNTHETIC-md84-facts.txt",
    Buffer.from(
      "SYNTHETIC independent boundary scenarios for a declared completed tax period 2026-01-01 to 2026-09-30; resident taxable person, not Tax Group or QFZP; AED revenues exactly 50000000 and 50000000.01; no client or legal period-validity qualification",
    ),
  );
  let retained: { id: string; body: Record<string, unknown> } | undefined;
  for (const [amount, required] of [
    ["50000000", false],
    ["50000000.01", true],
  ] as const) {
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByText("Assess UAE corporate-tax audited statement duty", {
        exact: true,
      })
      .click();
    const title = `SYNTHETIC MD84 boundary ${amount}`;
    for (const [name, value] of [
      ["CT audit duty title", title],
      ["CT registration reference", "SYNTHETIC-CT-BOUNDARY"],
      ["Assessed complete-period AED revenue", amount],
      ["CT tax period start", "2026-01-01"],
      ["CT tax period end", "2026-09-30"],
      ["CT assessed on", "2026-10-01"],
      ["CT adopted from", "2025-01-01"],
      ["CT adopted through", "2026-12-31"],
      [
        "CT operative rule assessment",
        "SYNTHETIC independently adopted original MD84 and assessed no operative changes for this declared scenario",
      ],
      [
        "CT entity and revenue assessment",
        "SYNTHETIC complete declared short tax-period facts and exact AED revenue; no client period-validity qualification",
      ],
    ])
      await page.getByLabel(name, { exact: true }).fill(value);
    for (const [name, value] of [
      ["CT taxable person", "assessed_yes"],
      ["CT tax group", "assessed_no"],
      ["CT qualifying free zone person", "assessed_no"],
      ["CT designated zone distribution", "assessed_no"],
      ["CT residency", "resident"],
      ["CT revenue basis", "whole_person"],
      ["CT other rule changes", "assessed_none"],
      ["Original MD84 rule PDF", rule.version.id],
      ["Separate CT period and classification facts", facts.version.id],
    ])
      await page
        .getByRole("combobox", { name, exact: true })
        .selectOption(value);
    const pending = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/${prefix}/uae-ct-audit-duty`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", {
        name: "Prepare CT audited statement duty",
        exact: true,
      })
      .click();
    const response = await pending;
    expect(response.status(), await response.text()).toBe(201);
    const result = await response.json();
    expect(result.body.rows[0].audited_financial_statements_required).toBe(
      required,
    );
    expect(result.body.rows[0].entity_audit_exemption_established).toBe(false);
    expect(result.body.exception_count).toBe(0);
    const self = await page.request.post(
      `/api/backend/${prefix}/events/${result.id}/review`,
      {
        headers,
        data: {
          expected_version: result.version,
          action: "approve",
          comments: "SYNTHETIC self-review remains forbidden",
        },
      },
    );
    expect(self.status()).toBe(403);
    retained = await post(
      reviewer.request,
      `${prefix}/events/${result.id}/review`,
      {
        expected_version: result.version,
        action: "approve",
        comments:
          "SYNTHETIC independent MD84 duty review only; no company-law exemption, audit opinion or filing",
      },
    );
    await reviewer.goto(
      `/intelligence/${eid}/country-workflow?event=${retained!.id}`,
    );
    await expect(reviewer.getByText("REVIEWED", { exact: true })).toBeVisible();
    const summary = reviewer.getByRole("region", {
      name: "UAE corporate-tax audit duty summary",
      exact: true,
    });
    await expect(summary).toContainText(
      required
        ? "MD84 preparation and maintenance duty: Required"
        : "MD84 preparation and maintenance duty: Not required under the selected MD84 assessment",
    );
    await expect(
      summary.getByText(`AED ${amount}`, { exact: true }),
    ).toBeVisible();
    await summary.screenshot({
      path: `${screenshots}/AE-CT-MD84-${required ? "above-limit" : "at-limit"}-summary.png`,
    });
    await reviewer
      .getByRole("heading", { name: title, exact: true })
      .locator("..")
      .screenshot({
        path: `${screenshots}/AE-CT-MD84-${required ? "above-limit" : "at-limit"}-reviewed.png`,
      });
    const downloading = reviewer.waitForEvent("download");
    await reviewer
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    expect((await downloading).suggestedFilename()).toContain(".xlsx");
  }
  await upload(
    facts.record,
    "SYNTHETIC-revised-md84-facts.txt",
    Buffer.from(
      "SYNTHETIC corrected tax-period classifications require a new duty assessment",
    ),
  );
  const stale = await reviewer.request.get(
    `/api/backend/${prefix}/events/${retained!.id}`,
    { headers },
  );
  expect(stale.status()).toBe(200);
  const historical = await stale.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(retained!.body);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${retained!.id}`,
  );
  await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await reviewer
    .getByRole("heading", {
      name: "SYNTHETIC MD84 boundary 50000000.01",
      exact: true,
    })
    .locator("..")
    .screenshot({ path: `${screenshots}/AE-CT-MD84-facts-replaced-stale.png` });
}
