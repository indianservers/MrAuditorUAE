import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const manifest = JSON.parse(
  readFileSync("../docs/phase-7/demo-manifest.json", "utf8"),
);
const loginData = JSON.parse(
  readFileSync("../.local-runtime/phase7/demo-login.local.json", "utf8"),
);
const entry = manifest.engagements.find(
  (e: { year: number }) => e.year === 2026,
);
const shots = process.env.AUDITOS_SCREENSHOT_ROOT ? `${process.env.AUDITOS_SCREENSHOT_ROOT}/phase-7` : "../docs/phase-7/screenshots";
mkdirSync(shots, { recursive: true });
async function login(page: Page, index = 1) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(manifest.users[index].email);
  await page.getByLabel("Password", { exact: true }).fill(loginData.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (index !== 24) await page.waitForURL("**/dashboard");
}
test("fourteen VAT workspaces render persisted synthetic data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  for (const area of [
    "dashboard",
    "profiles",
    "sales",
    "purchases",
    "transactions",
    "reconciliation",
    "returns",
    "invoices",
    "imports",
    "exceptions",
    "einvoicing",
    "asp",
    "ai",
    "rules",
  ]) {
    await page.goto(`/vat/${entry.id}/${area}`);
    await expect(
      page.getByRole("navigation", { name: "VAT workspaces" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("VAT profile", { exact: true }).locator("option"),
    ).toHaveCount(2);
    await page.screenshot({ path: `${shots}/vat-${area}.png`, fullPage: true });
  }
  expect(errors).toEqual([]);
});
test("VAT calculation retrieves ledger reconciliation and downloads immutable JSON", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/vat/${entry.id}/reconciliation`);
  await page
    .getByLabel("VAT profile", { exact: true })
    .selectOption({ index: 1 });
  await page
    .getByRole("button", { name: "Prepare VAT reconciliation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Export VAT JSON", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export VAT JSON", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
  await page.screenshot({
    path: `${shots}/vat-calculated.png`,
    fullPage: true,
  });
});
test("readonly VAT reviewer cannot prepare and mobile workspace remains usable", async ({
  page,
}) => {
  await login(page, 22);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/vat/${entry.id}/reconciliation`);
  await page
    .getByLabel("VAT profile", { exact: true })
    .selectOption({ index: 1 });
  await expect(
    page.getByRole("button", {
      name: "Prepare VAT reconciliation",
      exact: true,
    }),
  ).toBeDisabled();
  await page.screenshot({
    path: `${shots}/vat-mobile-readonly.png`,
    fullPage: true,
  });
});
test("prior phase audit IFRS and Corporate Tax workspaces remain usable", async ({
  page,
}) => {
  await login(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const groups = [
    {
      root: "ifrs",
      nav: "IFRS workspaces",
      areas: [
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
      ],
    },
    {
      root: "tax",
      nav: "Corporate Tax workspaces",
      areas: [
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
      ],
    },
  ];
  for (const group of groups) {
    for (const area of group.areas) {
      await page.goto(`/${group.root}/${entry.id}/${area}`);
      await expect(
        page.getByRole("navigation", { name: group.nav }),
      ).toBeVisible();
    }
    await page.screenshot({
      path: `${shots}/${group.root}-regression.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});
test("audit administration and core route regression", async ({ page }) => {
  await login(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const area of [
    "acceptance",
    "independence",
    "planning",
    "materiality",
    "risks",
    "programs",
    "procedures",
    "testing",
    "working-papers",
    "evidence",
    "findings",
    "review-notes",
    "completion",
    "requests",
    "ai",
    "team",
  ]) {
    await page.goto(`/engagements/${entry.id}/${area}`);
    await expect(
      page.getByRole("navigation", { name: "Engagement workspaces" }),
    ).toBeVisible();
  }
  for (const route of [
    "/dashboard",
    "/clients",
    "/engagements",
    "/integrations",
    "/reports",
    "/settings",
    "/admin/users",
    "/admin/roles",
    "/admin/permissions",
    "/admin/teams",
    "/admin/activity",
    "/admin/firm-settings",
  ]) {
    await page.goto(route);
    await expect(page.locator(".page-header h1")).toBeVisible();
  }
  await page.screenshot({
    path: `${shots}/core-regression.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

import { recordReleaseEvidence } from "./release-evidence";
test.beforeEach(async ({page})=>{recordReleaseEvidence(page);});
