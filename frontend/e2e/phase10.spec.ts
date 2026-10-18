import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const demo = JSON.parse(
  readFileSync("../docs/phase-10/demo-verification.json", "utf8"),
);
const manifest = JSON.parse(
  readFileSync("../docs/phase-7/demo-manifest.json", "utf8"),
);
const credentials = JSON.parse(
  readFileSync("../.local-runtime/phase7/demo-login.local.json", "utf8"),
);
const shots = process.env.AUDITOS_SCREENSHOT_ROOT ? `${process.env.AUDITOS_SCREENSHOT_ROOT}/phase-10` : "../docs/phase-10/screenshots";
mkdirSync(shots, { recursive: true });
async function login(page: Page, email = manifest.users[1].email) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}
const areas = [
  "command",
  "universe",
  "plan",
  "engagement",
  "testing",
  "reports",
  "risks",
  "heatmap",
  "kris",
  "controls",
  "rcm",
  "effectiveness",
  "sod",
  "rules",
  "executions",
  "alerts",
  "deficiencies",
  "remediation",
  "obligations",
  "policies",
  "third-parties",
  "copilot",
  "board",
  "quality",
];
test("all 24 GRC workspaces render actual authorized data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const area of areas) {
    await page.goto(`/grc/${demo.engagement_id}/${area}`);
    await expect(page.locator(".grc-workspace")).toBeVisible();
    await expect(page.locator(".grc-shell [role=alert]")).toHaveCount(0);
    if (area === "command")
      await expect(page.locator(".grc-command")).toContainText(
        "Reviewed workpapers",
      );
    if (area === "heatmap") {
      await page
        .getByRole("button", { name: /Likelihood 5, impact 5/ })
        .click();
      await expect(page.locator(".grc-heat ul li")).toHaveCount(4);
    }
    if (!["command", "copilot"].includes(area)) {
      await expect(page.locator(".ag-row").first()).toBeVisible();
      expect(
        await page
          .locator(".grid-body")
          .first()
          .evaluate((el) => el.getBoundingClientRect().height),
      ).toBeGreaterThan(150);
    }
    if (area === "rcm") {
      await page
        .getByRole("button", {
          name: "Inspect relationship graph",
          exact: true,
        })
        .click();
      await page
        .getByRole("combobox", { name: /Focus risk/ })
        .selectOption({ index: 1 });
      await expect(page.locator(".react-flow__node").first()).toBeVisible();
    }
    await page.screenshot({
      path: `${shots}/${area}-1600.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});
test("typed scoring editor persists a real draft", async ({ page }) => {
  await login(page);
  await page.goto(`/grc/${demo.engagement_id}/heatmap`);
  await page
    .getByRole("button", { name: "Scoring & appetite", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Prepare Scoring", exact: true })
    .click();
  const form = page.locator(".grc-editor");
  const reference = `P10-BROWSER-${Date.now()}`;
  await form.getByLabel("Reference", { exact: true }).fill(reference);
  await form
    .getByLabel("Title", { exact: true })
    .fill("SYNTHETIC browser scoring draft");
  await form.getByLabel("Version number", { exact: true }).fill("1");
  await form.getByLabel("Appetite", { exact: true }).fill("9");
  await form
    .getByLabel("Criteria weights new key", { exact: true })
    .fill("risk");
  await form
    .getByRole("button", { name: "Add Criteria weights entry", exact: true })
    .click();
  await form.getByLabel("Risk", { exact: true }).fill("1");
  await form.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(form).toHaveCount(0);
  await page.getByLabel("Search references and titles").fill(reference);
  await expect(page.locator(".ag-row").first()).toContainText(reference);
  await page.locator(".ag-row").first().click();
  await page.getByRole("button", { name: "Edit draft", exact: true }).click();
  await page
    .locator(".grc-editor")
    .getByLabel("Title", { exact: true })
    .fill("SYNTHETIC revised browser scoring draft");
  await page
    .locator(".grc-editor")
    .getByRole("button", { name: "Save draft", exact: true })
    .click();
  await expect(page.locator(".grc-editor")).toHaveCount(0);
  await page
    .getByLabel("Review rationale", { exact: true })
    .fill("Synthetic revised draft submitted for independent review");
  await page
    .getByRole("button", { name: "Submit for review", exact: true })
    .click();
  await expect(page.locator(".ag-row").first()).toContainText(
    "REVIEW_REQUIRED",
  );
});
test("enterprise views fit four viewport widths", async ({ page }) => {
  await login(page);
  for (const width of [1920, 1440, 1024, 768]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/grc/${demo.engagement_id}/remediation`);
    await expect(page.locator(".grc-lanes")).toBeVisible();
    await expect(page.locator(".ag-row").first()).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `${shots}/remediation-${width}.png`,
      fullPage: true,
    });
  }
});
test("board viewer reads only a published package", async ({ page }) => {
  await login(
    page,
    demo.users.find((x: { role: string }) => x.role === "Board Viewer").email,
  );
  await page.goto("/board");
  await page
    .getByLabel("Engagement reference", { exact: true })
    .fill(demo.engagement_id);
  await page
    .getByLabel("Published package reference", { exact: true })
    .fill(demo.board_publication);
  await page
    .getByRole("button", { name: "Open authorized package", exact: true })
    .click();
  await expect(page.locator(".grc-board")).toContainText(
    "SYNTHETIC committee briefing",
  );
  await page.goto(`/grc/${demo.engagement_id}/risks`);
  await expect(
    page.getByText("Access restricted", { exact: true }),
  ).toBeVisible();
});

import { recordReleaseEvidence } from "./release-evidence";
test.beforeEach(async ({page})=>{recordReleaseEvidence(page);});
