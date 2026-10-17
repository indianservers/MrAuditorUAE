import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync("../docs/phase-3/browser-fixture.json", "utf8"),
);
const origin = process.env.FRONTEND_URL || "http://127.0.0.1:3000";
for (const format of ["CSV", "XLSX"]) {
  test(`real ${format} import: preview, mapping, background validation and activation`, async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByLabel("Email address").fill("admin@example.com");
    await page
      .getByLabel("Password", { exact: true })
      .fill("test-strong-password-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Executive Dashboard" }),
    ).toBeVisible();
    const tenants = await (
      await page.request.get("/api/backend/tenants")
    ).json();
    const headers = { "X-Tenant-ID": tenants[0].id, Origin: origin };
    const entityResponse = await page.request.post("/api/backend/entities", {
      headers,
      data: {
        client_id: fixture.client_id,
        name: "SYNTHETIC — Browser Import " + Date.now(),
        country: "AE",
        jurisdiction: "Synthetic only",
        functional_currency: "AED",
        presentation_currency: "AED",
      },
    });
    expect(entityResponse.status()).toBe(201);
    const entity = await entityResponse.json();
    const periodResponse = await page.request.post(
      "/api/backend/financial-periods",
      {
        headers,
        data: {
          entity_id: entity.id,
          start_date: "2026-01-01",
          end_date: "2026-12-31",
        },
      },
    );
    expect(periodResponse.status()).toBe(201);
    const period = await periodResponse.json();
    await page.getByLabel("Select client").selectOption(fixture.client_id);
    await page.getByLabel("Select entity").selectOption(entity.id);
    await page.getByLabel("Select period").selectOption(period.id);
    await page.getByRole("link", { name: "Integrations", exact: true }).click();
    await page
      .getByRole("button", { name: "Import data", exact: true })
      .click();
    const modal = page.getByRole("dialog", { name: "Import financial data" });
    const csv =
      "Custom Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID\n1100,Synthetic cash,B-1,2026-06-01,123.45,0,B-L1\n4100,Synthetic revenue,B-1,2026-06-01,0,123.45,B-L2\n";
    if (format === "CSV") {
      await modal.locator("input[type=file]").setInputFiles({
        name: "SYNTHETIC-browser-upload.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(csv),
      });
    } else {
      await modal
        .locator("input[type=file]")
        .setInputFiles("tests/fixtures/synthetic-multi-sheet.xlsx");
      await modal
        .getByLabel("Worksheet", { exact: true })
        .selectOption("Journal Data");
    }
    await expect(
      modal.getByRole("heading", { name: "Column mapping" }),
    ).toBeVisible();
    await expect(
      modal
        .getByLabel("Map account_code", { exact: true })
        .locator("option")
        .filter({ hasText: "Custom Code" }),
    ).toBeAttached();
    await modal
      .getByLabel("Map account_code", { exact: true })
      .selectOption("Custom Code");
    await modal
      .getByRole("button", { name: "Upload preserved source" })
      .click();
    await modal.getByRole("button", { name: "Validate in background" }).click();
    await expect(
      modal.getByRole("button", { name: "Review activation" }),
    ).toBeVisible({ timeout: 60_000 });
    await modal.getByRole("button", { name: "Review activation" }).click();
    const confirm = page.getByRole("dialog", {
      name: "Activate financial population?",
    });
    await confirm.getByRole("button", { name: "Confirm activation" }).click();
    await expect(confirm).not.toBeVisible();
    await expect(modal.getByText("active", { exact: true })).toBeVisible();
    await modal
      .getByRole("button", { name: "Return to integration center" })
      .click();
    await expect(modal).not.toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByLabel("Command search").fill("Trial Balance");
    await page
      .getByRole("dialog", { name: "Search your workspace" })
      .getByRole("button")
      .filter({ hasText: "Trial Balance" })
      .click();
    await expect(
      page.getByText("Trial Balance Balanced", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("gridcell", { name: "Synthetic cash", exact: true }),
    ).toBeVisible();
  });
}
