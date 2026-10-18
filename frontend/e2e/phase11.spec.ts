import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const manifest = JSON.parse(
  readFileSync("../docs/phase-7/demo-manifest.json", "utf8"),
);
const credentials = JSON.parse(
  readFileSync("../.local-runtime/phase7/demo-login.local.json", "utf8"),
);
const demo = JSON.parse(
  readFileSync("../docs/phase-11/demo-verification.json", "utf8"),
);
const eid = manifest.engagements.find(
  (x: { year: number }) => x.year === 2026,
).id;
const shots = process.env.AUDITOS_SCREENSHOT_ROOT ? `${process.env.AUDITOS_SCREENSHOT_ROOT}/phase-11` : "../docs/phase-11/screenshots";
mkdirSync(shots, { recursive: true });
async function login(page: Page, email = manifest.users[1].email) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}
async function open(page: Page, area: string) {
  await page.goto(`/ai/${area}`);
  if (area !== "providers")
    await page
      .getByRole("combobox", { name: "AI engagement", exact: true })
      .selectOption(eid);
  await expect(page.locator(".ai-main")).toBeVisible();
}
test("all 16 AI workspaces use actual APIs", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const area of [
    "command-center",
    "agents",
    "investigations",
    "designer",
    "monitor",
    "approvals",
    "documents",
    "matching",
    "knowledge",
    "research",
    "citations",
    "evaluations",
    "providers",
    "usage",
    "security",
    "schedules",
  ]) {
    await open(page, area);
    if (area === "agents")
      await expect(
        page.getByRole("heading", {
          name: "Financial Data Agent",
          exact: true,
        }),
      ).toBeVisible();
    if (area === "designer") {
      await expect(page.locator(".react-flow__node").first()).toBeVisible();
      await page
        .getByRole("button", { name: "Validate graph & permissions" })
        .click();
      await expect(page.locator(".ai-main")).toContainText(
        "True".toLowerCase(),
      );
    }
    if (area === "documents")
      await expect(
        page
          .getByRole("combobox", { name: "Extraction", exact: true })
          .locator("option"),
      ).toHaveCount(101);
    await expect(page.locator(".ai-shell [role=alert]")).toHaveCount(0);
    await page.screenshot({
      path: `${shots}/${area}-1600.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});
test("reviewed plan executes in a real worker and exports a draft", async ({
  page,
}) => {
  await login(page);
  await open(page, "command-center");
  await page
    .getByLabel("Investigation request", { exact: true })
    .fill("SYNTHETIC browser evidence request investigation");
  await page
    .getByRole("combobox", { name: /Reviewed task/ })
    .selectOption("evidence-request");
  await page.getByRole("button", { name: "Review plan", exact: true }).click();
  await expect(page.locator(".ai-plan")).toContainText("audit.get_evidence");
  await page
    .getByRole("button", { name: "Create investigation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Run / resume worker", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Run / resume worker", exact: true })
    .click();
  await expect(page.locator(".ai-execution .ai-section-heading")).toContainText(
    "3/3 steps recorded",
  );
  await expect(page.locator(".ai-timeline")).toContainText("COMPLETED");
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export draft PDF", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await page.screenshot({
    path: `${shots}/worker-execution-1600.png`,
    fullPage: true,
  });
});
test("document retrieval and mismatches show stored source values", async ({
  page,
}) => {
  await login(page);
  await open(page, "knowledge");
  await page
    .getByRole("textbox", { name: "Search indexed evidence", exact: true })
    .fill("SYNTHETIC-P11-0000");
  await page
    .getByRole("button", { name: "Search authorized chunks", exact: true })
    .click();
  await expect(page.locator(".ai-main")).toContainText("keyword");
  await expect(page.locator(".ai-main")).toContainText("SYNTHETIC-P11-0000");
  await page.screenshot({
    path: `${shots}/retrieval-source-1600.png`,
    fullPage: true,
  });
});
test("command center is usable at four enterprise viewport widths", async ({
  page,
}) => {
  await login(page);
  for (const width of [768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await open(page, "command-center");
    await expect(
      page.getByRole("button", { name: "Create investigation", exact: true }),
    ).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    );
    expect(overflow).toBe(false);
    await page.screenshot({
      path: `${shots}/command-${width}.png`,
      fullPage: true,
    });
  }
});

test("configured read-only graph creates a separate executable run and citations open", async ({
  page,
}) => {
  await login(page);
  await open(page, "designer");
  await page
    .getByRole("textbox", { name: "Workflow version title", exact: true })
    .fill("SYNTHETIC browser workflow version");
  await page
    .getByRole("button", {
      name: "Save & activate read-only graph",
      exact: true,
    })
    .click();
  await expect(
    page
      .getByRole("button", {
        name: "Create run from this version",
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create run from this version", exact: true })
    .first()
    .click();
  await open(page, "monitor");
  await page
    .getByRole("combobox", { name: /Saved investigation/ })
    .selectOption({ index: 1 });
  await page
    .getByRole("button", { name: "Run / resume worker", exact: true })
    .click();
  await expect(page.locator(".ai-execution .ai-section-heading")).toContainText(
    "4/4 steps recorded",
  );
  await page.screenshot({
    path: `${shots}/custom-workflow-1600.png`,
    fullPage: true,
  });
  await open(page, "citations");
  await page
    .getByRole("textbox", { name: "Source ID", exact: true })
    .fill(demo.extractions[0].record_id);
  await page
    .getByRole("button", { name: "Verify & open source", exact: true })
    .click();
  await expect(page.locator(".ai-main")).toContainText("P11-DOC-0000");
});

import { recordReleaseEvidence } from "./release-evidence";
test.beforeEach(async ({page})=>{recordReleaseEvidence(page);});
