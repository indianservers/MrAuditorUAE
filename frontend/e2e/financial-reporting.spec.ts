import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync("../.local-runtime/financial-reporting/fixture.json", "utf8"),
);
const shots = "../docs/financial-reporting/screenshots";
mkdirSync(shots, { recursive: true });

test("real financial comparison, statement review, draft comparison and export", async ({
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
  await page.goto("/financials/trial-balance");
  await page
    .getByLabel("Select client", { exact: true })
    .selectOption(fixture.client_id);
  await page
    .getByLabel("Select entity", { exact: true })
    .selectOption(fixture.entity_id);
  await page
    .getByLabel("Select period", { exact: true })
    .selectOption(fixture.period_id);
  await page
    .getByLabel("Compare period", { exact: true })
    .selectOption(fixture.prior_snapshot_id);
  await expect(
    page.getByRole("columnheader", { name: /Prior closing/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("gridcell", { name: "Old expense", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("controls reconciled", { exact: true }),
  ).toBeVisible();
  await page
    .getByText("Monthly movements and source controls", { exact: true })
    .click();
  await expect(
    page.getByRole("rowheader", { name: "2026-06", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/financial-comparison.png`,
    fullPage: true,
  });
  await page.goto(`/ifrs/${fixture.engagement_id}/designer`);
  await page
    .getByLabel("Reporting profile", { exact: true })
    .selectOption(fixture.profile_id);
  await page
    .getByRole("button", { name: "Generate statements", exact: true })
    .click();
  const review = page.getByRole("region", {
    name: "Financial statement review",
    exact: true,
  });
  await expect(
    review.getByText("Checks passed", { exact: true }),
  ).toBeVisible();
  await review
    .getByLabel("Compare earlier draft", { exact: true })
    .selectOption(fixture.run_id);
  await expect(
    review.getByText("No statement line, note or package changes.", {
      exact: true,
    }),
  ).toBeVisible();
  await review.getByText("Displayed subtotal checks", { exact: true }).click();
  await expect(
    review.getByRole("rowheader", { name: "assets", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "INCOME", exact: true }).click();
  await expect(
    page.getByRole("gridcell", { name: "50.00", exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "EQUITY", exact: true }).click();
  await expect(
    page.getByRole("gridcell", {
      name: "Current period profit / loss",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("gridcell", { name: "Capital", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PDF", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/draft\.pdf$/);
  await (
    await download
  ).saveAs("../.local-runtime/financial-reporting/synthetic-financials.pdf");
  await page.screenshot({
    path: `${shots}/statement-review.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: `${shots}/statement-review-mobile.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
