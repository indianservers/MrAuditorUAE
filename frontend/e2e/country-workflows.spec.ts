import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync("../.local-runtime/country-workflows/fixture.json", "utf8"),
);
const shots = "../docs/country-workflows/screenshots/native-sources";
mkdirSync(shots, { recursive: true });

test("UAE source controls, BRS exceptions, exports and India isolation", async ({
  page,
}) => {
  const runSuffix = Date.now().toString();
  const queuedBRSTitle = `SYNTHETIC queued browser BRS ${runSuffix}`;
  const payrollTitle = `SYNTHETIC queued reviewed payroll calculation ${runSuffix}`;
  let gstr2bSource = "";
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
  await expect(
    page.getByRole("heading", { name: "Reconcile and assess evidence" }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Workflow")
      .getByRole("option", { name: "India GST document reconciliation" }),
  ).toHaveCount(0);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.uae_result);
  await expect(
    page.getByText("SYNTHETIC account reconciliation", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("UNPRESENTED_PAYMENT_CANDIDATE", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("cell", {
      name: "UNCREDITED_DEPOSIT_CANDIDATE",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "UNBOOKED_BANK_ITEM", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/uae-bank-review.png`,
    fullPage: true,
  });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export XLSX", exact: true }).click();
  await expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
  await page
    .getByRole("link", { name: "Prepare sources", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Prepare controlled source tables" }),
  ).toBeVisible();
  await page.getByText("CSV field contract", { exact: true }).click();
  await expect(
    page.getByText("amount · required", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/controlled-source-import.png`,
    fullPage: true,
  });
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await expect(
    page
      .getByLabel("Workflow")
      .getByRole("option", { name: "UAE VAT document reconciliation" }),
  ).toHaveCount(0);
  await expect(
    page
      .getByLabel("Workflow")
      .getByRole("option", { name: "India GST document reconciliation" }),
  ).toHaveCount(1);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.india_result);
  await expect(
    page.getByRole("cell", { name: "VARIANCE", exact: true }),
  ).toBeVisible();
  await page
    .getByText("Country-specific scope guidance", { exact: true })
    .click();
  await expect(
    page.getByText("Form 26 under 2025 Act / 2026 Rules", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/india-gst-review.png`,
    fullPage: true,
  });
  await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.uae_vat_result);
  await expect(
    page.getByRole("heading", {
      name: "SYNTHETIC UAE VAT201 box bridge",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "1:DXB", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/uae-vat201-bridge.png`,
    fullPage: true,
  });
  for (const [label, value] of [
    ["Schedule title", queuedBRSTitle],
    ["Reconciliation date", "2026-06-30"],
    ["Bank account identifier", "BANK-1"],
    ["book opening", "0"],
    ["book closing", "100"],
    ["statement opening", "0"],
    ["statement closing", "95"],
    [
      "Scope and source rationale",
      "Synthetic browser-to-Redis-to-worker execution using retained sources",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByLabel("books source", { exact: true })
    .selectOption(fixture.uae_book_source);
  await page
    .getByLabel("statement source", { exact: true })
    .selectOption(fixture.uae_statement_source);
  const queued = page.waitForResponse(
    (r) =>
      r.url().includes(`/engagements/${fixture.uae_engagement}/jobs`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  expect((await queued).status()).toBe(202);
  await expect(
    page.getByRole("button", { name: "Open result", exact: true }).first(),
  ).toBeVisible();
  await expect
    .poll(async () =>
      page
        .getByLabel("Saved source or result")
        .getByRole("option", { name: new RegExp(queuedBRSTitle) })
        .count(),
    )
    .toBe(1);
  await page
    .getByRole("button", { name: "Open result", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", {
      name: queuedBRSTitle,
      exact: true,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/real-worker-result.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
  for (const source of [
    {
      engagement: fixture.uae_engagement,
      format: "camt053",
      evidence: fixture.camt_evidence,
      count: "2",
      total: "AED=95",
      title: `SYNTHETIC native browser CAMT ${runSuffix}`,
    },
    {
      engagement: fixture.uae_engagement,
      format: "uae-wps-sif",
      evidence: fixture.wps_evidence,
      count: "2",
      total: "AED=1500",
      title: `SYNTHETIC native browser WPS ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "india-inv01-json",
      evidence: fixture.india_invoice_evidence,
      count: "5",
      total: "INR=18",
      title: `SYNTHETIC native browser INV01 ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "india-epfo-ecr",
      evidence: fixture.india_ecr_evidence,
      count: "7",
      total: "INR=6100",
      title: `SYNTHETIC native browser ECR ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "india-gstr2b-json",
      evidence: fixture.india_gstr2b_evidence,
      count: "4",
      total: "INR=18",
      title: `SYNTHETIC native browser GSTR2B ${runSuffix}`,
    },
  ]) {
    await page.goto(`/intelligence/${source.engagement}/workflow-source`);
    await page.getByLabel("Source file format").selectOption(source.format);
    await page.getByLabel("Schedule title", { exact: true }).fill(source.title);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(source.evidence);
    await page.getByLabel("Expected data rows").fill(source.count);
    await page.getByLabel("Independent totals by currency").fill(source.total);
    if (source.format === "india-epfo-ecr") {
      await page
        .getByLabel("EPFO establishment registration")
        .fill("SYNTHETIC-EPFO-001");
      await page.getByLabel("ECR wage month").fill("2026-06");
      await page.getByLabel("Independent ECR member count").fill("2");
    }
    if (source.format === "india-gstr2b-json") {
      await page.getByLabel("Recipient GSTIN").fill("27ABCDE5678G1Z8");
      await page.getByLabel("GSTR-2B return month").fill("2026-06");
      await page.getByLabel("Independent GSTR-2B document count").fill("1");
    }
    if (source.format === "india-inv01-json") {
      await page.getByLabel("Entity GSTIN").fill("27ABCDE5678G1Z8");
      await page.getByLabel("Invoice direction").selectOption("purchase");
      await page.getByLabel("Reporting month").fill("2026-06");
      await expect(
        page
          .getByLabel("Source file format")
          .getByRole("option", { name: /UAE WPS/ }),
      ).toHaveCount(0);
    } else if (source.engagement === fixture.uae_engagement) {
      await expect(
        page
          .getByLabel("Source file format")
          .getByRole("option", { name: /India INV-01/ }),
      ).toHaveCount(0);
    }
    const queuedNative = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${source.engagement}/jobs`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    expect((await queuedNative).status()).toBe(202);
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(source.title) });
    await expect(option).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await option.getAttribute("value"))!);
    await expect(
      page.getByRole("heading", { name: source.title, exact: true }),
    ).toBeVisible();
    await page
      .getByText("Original source controls and calculation basis", {
        exact: true,
      })
      .click();
    if (source.format === "uae-wps-sif")
      await expect(
        page.getByText("NOT_EVIDENCED_BY_INSTRUCTION_FILE", { exact: true }),
      ).toBeVisible();
    if (source.format === "india-epfo-ecr")
      await expect(
        page.getByText("NOT_EVIDENCED_BY_RETURN_TEXT", { exact: true }).first(),
      ).toBeVisible();
    if (source.format === "india-inv01-json")
      await expect(
        page.getByText(
          "FIVE_TAX_COMPONENTS_PER_DOCUMENT_INCLUDING_ZERO_COMPONENTS",
          { exact: true },
        ),
      ).toBeVisible();
    if (source.format === "india-gstr2b-json") {
      gstr2bSource = (await option.getAttribute("value"))!;
      await expect(
        page.getByText("FOUR_TAX_COMPONENT_ROWS_PER_SOURCE_DOCUMENT", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByText(
          "SUM_OF_DOCUMENT_TAX_FIELDS_INCLUDING_REVERSALS_NOT_ITC_ENTITLEMENT",
          { exact: true },
        ),
      ).toBeVisible();
    }
    await page.screenshot({
      path: `${shots}/${source.format}-native-review.png`,
      fullPage: true,
    });
  }
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await page.getByLabel("Workflow", { exact: true }).selectOption("india-gst");
  const gstTitle = `SYNTHETIC queued native GST comparison ${runSuffix}`;
  await page.getByLabel("Schedule title", { exact: true }).fill(gstTitle);
  await page
    .getByLabel("Reconciliation date", { exact: true })
    .fill("2026-06-30");
  await page
    .getByLabel("books source", { exact: true })
    .selectOption(fixture.india_gstr2b_books);
  await page
    .getByLabel("return source", { exact: true })
    .selectOption(gstr2bSource);
  await page
    .getByLabel("Scope and source rationale", { exact: true })
    .fill(
      "Independent book register compared against native GSTR-2B source components",
    );
  const gstQueued = page.waitForResponse(
    (response) =>
      response
        .url()
        .includes(`/engagements/${fixture.india_engagement}/jobs`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  expect((await gstQueued).status()).toBe(202);
  const gstOption = page
    .getByLabel("Saved source or result")
    .getByRole("option", { name: new RegExp(gstTitle) });
  await expect(gstOption).toHaveCount(1);
  await page
    .getByLabel("Saved source or result")
    .selectOption((await gstOption.getAttribute("value"))!);
  await expect(
    page.getByRole("heading", { name: gstTitle, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
  await page
    .getByRole("heading", { name: gstTitle, exact: true })
    .locator("..")
    .screenshot({ path: `${shots}/india-native-gstr2b-reconciliation.png` });
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("india-payroll-rules");
  await page.getByLabel("Schedule title", { exact: true }).fill(payrollTitle);
  await page
    .getByLabel("Reconciliation date", { exact: true })
    .fill("2026-06-30");
  await page
    .getByLabel("bases source", { exact: true })
    .selectOption(fixture.india_payroll_bases);
  await page
    .getByLabel("rules source", { exact: true })
    .selectOption(fixture.india_payroll_rules);
  await page
    .getByLabel("reported source", { exact: true })
    .selectOption(fixture.india_payroll_reported);
  await page
    .getByLabel("Scope and source rationale", { exact: true })
    .fill(
      "Independent source-bound rules and assessed wage bases compared to ECR",
    );
  const payrollQueued = page.waitForResponse(
    (r) =>
      r.url().includes(`/engagements/${fixture.india_engagement}/jobs`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  expect((await payrollQueued).status()).toBe(202);
  const payrollOption = page
    .getByLabel("Saved source or result")
    .getByRole("option", {
      name: new RegExp(payrollTitle),
    });
  await expect(payrollOption).toHaveCount(1);
  await page
    .getByLabel("Saved source or result")
    .selectOption((await payrollOption.getAttribute("value"))!);
  await expect(
    page.getByRole("heading", {
      name: payrollTitle,
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
  await page
    .getByRole("heading", { name: payrollTitle, exact: true })
    .locator("..")
    .screenshot({ path: `${shots}/india-payroll-contribution-summary.png` });
  await page.getByLabel("Show rule provenance and source references").check();
  await expect(
    page.getByRole("cell", { name: "employer-minus-eps", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", {
      name: "NOT_PERFORMED_BY_CONTRIBUTION_REVIEW",
      exact: true,
    }),
  ).toHaveCount(3);
  await page.screenshot({
    path: `${shots}/india-payroll-rule-review.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
