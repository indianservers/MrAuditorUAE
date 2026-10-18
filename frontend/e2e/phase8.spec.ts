import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const tpAreas = [
  ["dashboard", "TP Executive Dashboard", "profile"],
  ["relationships", "Related Party Intelligence", "relationship"],
  ["transactions", "Controlled Transactions", "transaction"],
  ["segmentation", "Financial Segmentation", "segmentation"],
  ["far", "Functional Analysis", "far"],
  ["methods", "Method Selection", "method"],
  ["datasets", "Comparable Data Imports", "dataset"],
  ["screening", "Comparable Screening", "screening"],
  ["benchmarking", "Benchmarking Statistics", "study"],
  ["loans", "Intercompany Loan Analysis", "loan"],
  ["credit", "Credit Assessment", "credit"],
  ["remuneration", "Connected Person Remuneration", "remuneration"],
  ["services", "Intercompany Services", "service"],
  ["intangibles", "Royalties & Guarantees", "royalty"],
  ["disclosure", "TP Disclosure", "disclosure"],
  ["localfile", "Local File Builder", "localfile"],
  ["masterfile", "Master File & APA", "masterfile"],
  ["ai", "AI TP Copilot", "judgment"],
];
const manifest = JSON.parse(
  readFileSync("../docs/phase-7/demo-manifest.json", "utf8"),
);
const tp = JSON.parse(
  readFileSync("../docs/phase-8/demo-manifest.json", "utf8"),
);
const credentials = JSON.parse(
  readFileSync("../.local-runtime/phase7/demo-login.local.json", "utf8"),
);
const shots = process.env.AUDITOS_SCREENSHOT_ROOT ? `${process.env.AUDITOS_SCREENSHOT_ROOT}/phase-8` : "../docs/phase-8/screenshots";
mkdirSync(shots, { recursive: true });
async function login(page: Page, index = 1) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(manifest.users[index].email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}
test("18 TP workspaces use persisted APIs without browser errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const [area, title] of tpAreas) {
    await page.goto(`/tp/${tp.engagement_id}/${area}`);
    await expect(
      page.getByRole("navigation", { name: "TP workspaces" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByLabel("TP profile", { exact: true }).locator("option"),
    ).toHaveCount(2);
    await page.screenshot({ path: `${shots}/${area}.png`, fullPage: true });
  }
  expect(errors).toEqual([]);
});
test("source matrix calculates and exports through real API", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/tp/${tp.engagement_id}/transactions`);
  await page
    .getByLabel("TP profile", { exact: true })
    .selectOption(tp.profile_id);
  await page
    .getByRole("button", { name: "Reconcile controlled transaction matrix" })
    .click();
  await expect(
    page.getByRole("button", { name: "Export JSON", exact: true }),
  ).toBeEnabled();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
  await page.screenshot({
    path: `${shots}/matrix-calculated.png`,
    fullPage: true,
  });
});
test("dated graph and persisted benchmark chart render at four enterprise widths", async ({
  page,
}) => {
  await login(page);
  for (const width of [1920, 1600, 1440, 1366]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/tp/${tp.engagement_id}/relationships`);
    await page
      .getByLabel("TP profile", { exact: true })
      .selectOption(tp.profile_id);
    await expect(
      page.getByLabel("Approved related party relationship graph"),
    ).toBeVisible();
    await page
      .getByLabel("Approved related party relationship graph")
      .screenshot({
        path: `${shots}/graph-${width}.png`,
      });
    await page.goto(`/tp/${tp.engagement_id}/benchmarking`);
    await page.getByLabel("Immutable calculation").selectOption(tp.studies[0]);
    await expect(
      page.getByRole("heading", { name: "Accepted population range" }),
    ).toBeVisible();
    await page
      .getByRole("heading", { name: "Accepted population range" })
      .locator("..")
      .screenshot({
        path: `${shots}/benchmark-${width}.png`,
      });
  }
});
test("client sees issued-document boundary and cannot open internal TP", async ({
  page,
}) => {
  await login(page, 18);
  await page.goto("/client-portal");
  await expect(
    page.getByRole("heading", { name: "Issued Transfer Pricing documents" }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download issued PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await page.screenshot({
    path: `${shots}/client-issued-pdf.png`,
    fullPage: true,
  });
  await page.goto(`/tp/${tp.engagement_id}/loans`);
  await expect(
    page.getByRole("heading", { name: "Access restricted" }),
  ).toBeVisible();
});

test("queued loan and source service workpapers calculate in browser", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/tp/${tp.engagement_id}/loans`);
  await page.getByLabel("Queue workpaper calculations").check();
  await page.getByLabel("Search records", { exact: true }).fill("P8-LOAN-1");
  await page.getByText("P8-LOAN-1", { exact: true }).first().click();
  await page
    .getByRole("button", { name: "Open completed calculation" })
    .click();
  await expect(
    page
      .locator("dt")
      .filter({ hasText: /^total interest$/ })
      .locator("..")
      .locator("dd"),
  ).toHaveText("10000.00000000");
  await page.screenshot({
    path: `${shots}/loan-calculated.png`,
    fullPage: true,
  });
  await page.goto(`/tp/${tp.engagement_id}/services`);
  await page.getByLabel("Search records", { exact: true }).fill("P8-SERVICE-1");
  const calculations: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/calculate/"))
      calculations.push(request.url());
  });
  await page.getByText("P8-SERVICE-1", { exact: true }).first().click();
  await expect(
    page
      .locator("dt")
      .filter({ hasText: /^allocation difference$/ })
      .locator("..")
      .locator("dd"),
  ).toHaveText(/^(0(\.0+)?|0E-8)$/);
  expect(calculations).toHaveLength(1);
  await page.screenshot({
    path: `${shots}/service-calculated.png`,
    fullPage: true,
  });
});

test("AI suggestion is accepted by a separate TP reviewer", async ({
  page,
}) => {
  const proof = JSON.parse(
    readFileSync("../docs/phase-8/verification.json", "utf8"),
  );
  await login(page);
  await page.goto(`/tp/${tp.engagement_id}/ai`);
  await page
    .getByLabel("TP profile", { exact: true })
    .selectOption(tp.profile_id);
  await page
    .getByLabel("Source workpaper UUID")
    .fill(proof.browser_ai_source_id);
  await page
    .getByRole("button", { name: "Generate reviewable suggestion" })
    .click();
  await expect(page.getByText("SUGGESTED", { exact: true })).toBeVisible();
  const suggestion = await page.getByLabel("Saved AI suggestion").inputValue();
  expect(suggestion).toBeTruthy();
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel("Email address").fill(tp.users[1].email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto(`/tp/${tp.engagement_id}/ai`);
  await page.getByLabel("Saved AI suggestion").selectOption(suggestion);
  await page
    .getByLabel("Independent review rationale")
    .fill(
      "SYNTHETIC software diagnostic reviewed independently; no tax opinion or figure changes",
    );
  await page.getByRole("button", { name: "ACCEPTED", exact: true }).click();
  await expect(
    page.locator("dd").filter({ hasText: /^ACCEPTED$/ }),
  ).toBeVisible();
  await page.screenshot({
    path: `${shots}/ai-independent-review.png`,
    fullPage: true,
  });
});

import { recordReleaseEvidence } from "./release-evidence";
test.beforeEach(async ({page})=>{recordReleaseEvidence(page);});
