import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const f = JSON.parse(
  readFileSync("../docs/phase-6/browser-fixture.json", "utf8"),
);
const shots = "../docs/phase-6/screenshots";
mkdirSync(shots, { recursive: true });
async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}
test("all twenty tax workspaces render actual backend data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const area of [
    "dashboard",
    "taxpayers",
    "computation",
    "adjustments",
    "reliefs",
    "small-business",
    "qfzp",
    "income-segmentation",
    "de-minimis",
    "free-zone-compliance",
    "interest",
    "losses",
    "tax-groups",
    "restructuring",
    "transitional",
    "related-parties",
    "returns",
    "calendar",
    "ai",
    "rules",
  ]) {
    await page.goto(`/tax/${f.engagement_id}/${area}`);
    await expect(
      page.getByRole("navigation", { name: "Corporate Tax workspaces" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Tax profile", { exact: true }).locator("option"),
    ).toHaveCount(3);
    await page.screenshot({ path: `${shots}/${area}.png`, fullPage: true });
  }
  expect(errors).toEqual([]);
});
test("mainland bridge recalculates traces source and exports PDF", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/tax/${f.engagement_id}/computation`);
  await page
    .getByLabel("Tax profile", { exact: true })
    .selectOption(f.profile_id);
  await page
    .getByRole("button", { name: "Calculate Corporate Tax", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Accounting-to-tax reconciliation",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("110,250.00", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("gridcell", { name: "Current Corporate Tax", exact: true })
    .click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PDF", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await page.screenshot({
    path: `${shots}/mainland-calculated.png`,
    fullPage: true,
  });
});
test("QFZP matrix calculates with reviewed contracts", async ({ page }) => {
  await login(page);
  await page.goto(`/tax/${f.engagement_id}/qfzp`);
  await page
    .getByLabel("Tax profile", { exact: true })
    .selectOption(f.qfzp_profile_id);
  await page
    .getByLabel("Approved assessment", { exact: true })
    .selectOption(f.qfzp_id);
  await page
    .getByRole("button", { name: "Calculate assessment", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "QFZP decision matrix", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/qfzp-calculated.png`,
    fullPage: true,
  });
});
test("interest schedule calculates and mobile tax route remains usable", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/tax/${f.engagement_id}/interest`);
  await page
    .getByLabel("Approved assessment", { exact: true })
    .selectOption(f.interest_id);
  await page
    .getByRole("button", { name: "Calculate assessment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Export JSON", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/interest-calculated.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/tax/${f.engagement_id}/dashboard`);
  await expect(page.getByLabel("Tax profile", { exact: true })).toBeVisible();
  await page.screenshot({
    path: `${shots}/mobile-dashboard.png`,
    fullPage: true,
  });
});

test("Tax Group uses one threshold across two approved member packages", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/tax/${f.engagement_id}/tax-groups`);
  await page
    .getByLabel("Approved assessment", { exact: true })
    .selectOption(f.group_id);
  await page
    .getByRole("button", { name: "Calculate assessment", exact: true })
    .click();
  await expect(
    page.getByText("254,250.00", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/group-calculated.png`,
    fullPage: true,
  });
});

test("AI assistance remains an explicitly unapproved sourced suggestion", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/tax/${f.engagement_id}/ai`);
  await page
    .getByLabel("Tax profile", { exact: true })
    .selectOption(f.profile_id);
  await page
    .getByLabel("Source adjustment", { exact: true })
    .selectOption(f.adjustment_id);
  await page
    .getByRole("button", { name: "Request tax analysis", exact: true })
    .click();
  await expect(
    page.getByText("SUGGESTED", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({ path: `${shots}/ai-suggestion.png`, fullPage: true });
});
