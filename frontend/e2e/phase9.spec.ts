import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const demo = JSON.parse(
    readFileSync("../docs/phase-7/demo-manifest.json", "utf8"),
  ),
  dataset = JSON.parse(
    readFileSync("../docs/phase-9/demo-dataset.json", "utf8"),
  ),
  models = JSON.parse(
    readFileSync("../docs/phase-9/training-results.json", "utf8"),
  ),
  tax = JSON.parse(
    readFileSync("../docs/phase-9/dmtt-demo-results.json", "utf8"),
  ),
  credentials = JSON.parse(
    readFileSync("../.local-runtime/phase7/demo-login.local.json", "utf8"),
  );
const shots = process.env.AUDITOS_SCREENSHOT_ROOT ? `${process.env.AUDITOS_SCREENSHOT_ROOT}/phase-9` : "../docs/phase-9/screenshots";
mkdirSync(shots, { recursive: true });
async function login(p: Page) {
  await p.goto("/login");
  await p.getByLabel("Email address").fill(demo.users[1].email);
  await p.getByLabel("Password", { exact: true }).fill(credentials.password);
  await p.getByRole("button", { name: "Sign in", exact: true }).click();
  await p.waitForURL("**/dashboard");
}
async function open(p: Page, mode: string, area: string) {
  await p.goto(`/${mode}/${area}`);
  await p.getByLabel("Phase 9 engagement").selectOption(dataset.engagement_id);
}
test("24 workspaces render with real persisted datasets and tax records", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const [mode, areas] of [
    [
      "ai-lab",
      [
        "overview",
        "datasets",
        "features",
        "architecture",
        "training",
        "evaluation",
        "confusion",
        "investigator",
        "registry",
        "deployment",
        "drift",
        "feedback",
      ],
    ],
    [
      "pillar-two",
      [
        "overview",
        "scope",
        "entities",
        "income",
        "taxes",
        "deferred",
        "etr",
        "sbie",
        "topup",
        "elections",
        "reporting",
        "ai",
      ],
    ],
  ] as const) {
    for (const area of areas) {
      await open(page, mode, area);
      await expect(
        page.getByRole("navigation", { name: "Phase 9 workspaces" }),
      ).toBeVisible();
      if (
        mode === "ai-lab" &&
        ![
          "overview",
          "datasets",
          "training",
          "registry",
          "investigator",
          "drift",
          "feedback",
        ].includes(area)
      )
        await page.getByLabel("Model version").selectOption(models[1].id);
      if (mode === "pillar-two")
        await page.getByLabel("DMTT group").selectOption(tax[1].group_id);
      await page.screenshot({ path: `${shots}/${mode}-${area}.png` });
    }
  }
  expect(errors).toEqual([]);
});
test("training controls run and cancel real Node worker jobs", async ({
  page,
}) => {
  await login(page);
  await open(page, "ai-lab", "training");
  await page.getByLabel("Training dataset").selectOption(dataset.dataset_id);
  await page.getByLabel("Model family").selectOption("journal-classifier");
  await page.getByLabel("Epoch limit").fill("2");
  await page
    .getByRole("button", { name: "Start training", exact: true })
    .click();
  await expect(
    page
      .getByRole("status", { name: "" })
      .filter({ hasText: "completed" })
      .first(),
  ).toBeVisible({ timeout: 90000 });
  await page.getByLabel("Epoch limit").fill("100");
  await page
    .getByRole("button", { name: "Start training", exact: true })
    .click();
  await page.getByRole("button", { name: "Cancel active training" }).click();
  await expect(
    page
      .getByRole("status", { name: "" })
      .filter({ hasText: "cancelled" })
      .first(),
  ).toBeVisible({ timeout: 90000 });
  await page.getByLabel("Model version").selectOption(models[1].id);
  await expect(
    page.getByLabel("Measured training and validation loss").locator("canvas"),
  ).toBeVisible();
  await page
    .getByLabel("Measured training and validation loss")
    .screenshot({ path: `${shots}/measured-training.png` });
});
test("DMTT calculation uses reviewed group and displays source-backed result", async ({
  page,
}) => {
  await login(page);
  await open(page, "pillar-two", "topup");
  await page.getByLabel("DMTT group").selectOption(tax[1].group_id);
  const response = page.waitForResponse(
    (r) =>
      r.url().includes(`/groups/${tax[1].group_id}/calculate`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Calculate reviewed jurisdiction" })
    .click();
  expect((await response).status()).toBe(201);
  await expect(page.getByText("DRAFT_TECHNICAL_REVIEW").first()).toBeVisible();
  await page.screenshot({ path: `${shots}/dmtt-calculated.png` });
});
test("held-out confusion chart renders at enterprise widths", async ({
  page,
}) => {
  await login(page);
  await open(page, "ai-lab", "confusion");
  await page.getByLabel("Model version").selectOption(models[1].id);
  for (const width of [1920, 1600, 1440, 1366]) {
    await page.setViewportSize({ width, height: 1000 });
    await page
      .getByLabel("Held-out confusion matrix")
      .screenshot({ path: `${shots}/confusion-${width}.png` });
  }
});

import { recordReleaseEvidence } from "./release-evidence";
test.beforeEach(async ({page})=>{recordReleaseEvidence(page);});
