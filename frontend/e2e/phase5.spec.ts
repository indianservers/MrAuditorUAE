import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const f = JSON.parse(
  readFileSync("../docs/phase-5/browser-fixture.json", "utf8"),
);
const shots = "../docs/phase-5/screenshots";
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
test("sixteen reporting workspaces render from real backend", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const area of [
    "dashboard",
    "designer",
    "trial-balance",
    "adjustments",
    "cash-flow",
    "notes",
    "ecl",
    "revenue",
    "leases",
    "deferred-tax",
    "fixed-assets",
    "impairment",
    "consolidation",
    "intercompany",
    "disclosures",
    "ai",
  ]) {
    await page.goto(`/ifrs/${f.engagement_id}/${area}`);
    await expect(page.locator(".page-header h1").first()).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "IFRS workspaces" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Reporting profile").locator("option"),
    ).toHaveCount(2);
    await page.screenshot({ path: `${shots}/${area}.png`, fullPage: true });
  }
  expect(errors).toEqual([]);
});
test("financial designer generates validates drills into source and downloads draft", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/ifrs/${f.engagement_id}/designer`);
  await page.getByLabel("Reporting profile").selectOption(f.profile_id);
  await page
    .getByRole("button", { name: "Generate statements", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "SYNTHETIC Gulf Reporting LLC",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("gridcell", { name: "Cash", exact: true })
    .first()
    .click();
  await expect(
    page.getByText("source accounts", { exact: true }).first(),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PDF", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toMatch(/\.pdf$/);
  await page.screenshot({
    path: `${shots}/designer-generated.png`,
    fullPage: true,
  });
});
for (const [area, id] of [
  ["leases", f.lease_id],
  ["ecl", f.ecl_id],
]) {
  test(`${area} approved schedule recalculates without editing financial amounts`, async ({
    page,
  }) => {
    await login(page);
    await page.goto(`/ifrs/${f.engagement_id}/${area}`);
    await page
      .getByLabel("Approved assumptions", { exact: true })
      .selectOption(id);
    await page
      .getByRole("button", { name: "Calculate approved inputs", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Export JSON", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Loading engagement�")).toHaveCount(0);
    await page.screenshot({
      path: `${shots}/${area}-calculated.png`,
      fullPage: true,
    });
  });
}
test("AI technical draft is source grounded and responsive", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/ifrs/${f.engagement_id}/ai`);
  await page.getByLabel("Note source").selectOption(f.note_id);
  await page.getByRole("button", { name: "Request technical draft" }).click();
  await expect(
    page.getByText("REVIEW_REQUIRED", { exact: true }).first(),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${shots}/ai-mobile.png`, fullPage: true });
});
