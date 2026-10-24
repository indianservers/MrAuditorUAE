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
    ["Schedule title", "SYNTHETIC queued browser BRS"],
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
        .getByRole("option", { name: /SYNTHETIC queued browser BRS/ })
        .count(),
    )
    .toBe(1);
  await page
    .getByRole("button", { name: "Open result", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", {
      name: "SYNTHETIC queued browser BRS",
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
      title: "SYNTHETIC native browser CAMT",
    },
    {
      engagement: fixture.uae_engagement,
      format: "uae-wps-sif",
      evidence: fixture.wps_evidence,
      count: "2",
      total: "AED=1500",
      title: "SYNTHETIC native browser WPS",
    },
    {
      engagement: fixture.india_engagement,
      format: "india-inv01-json",
      evidence: fixture.india_invoice_evidence,
      count: "5",
      total: "INR=18",
      title: "SYNTHETIC native browser INV01",
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
    if (source.format === "india-inv01-json") {
      await page.getByLabel("Entity GSTIN").fill("27ABCDE5678G1Z8");
      await page.getByLabel("Invoice direction").selectOption("purchase");
      await page.getByLabel("Reporting month").fill("2026-06");
      await expect(
        page
          .getByLabel("Source file format")
          .getByRole("option", { name: /UAE WPS/ }),
      ).toHaveCount(0);
    } else {
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
    if (source.format === "india-inv01-json")
      await expect(
        page.getByText(
          "FIVE_TAX_COMPONENTS_PER_DOCUMENT_INCLUDING_ZERO_COMPONENTS",
          { exact: true },
        ),
      ).toBeVisible();
    await page.screenshot({
      path: `${shots}/${source.format}-native-review.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});
