import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync("../.local-runtime/mr-auditor-business/fixture.json", "utf8"),
);
test("real synthetic records to assistant collection, shared lease calculation, source inspection and unposted draft", async ({
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
  await page.goto("/ai/uae-use-cases");
  await page.getByLabel("AI engagement").selectOption(fixture.engagement_id);
  await expect(page.getByRole("heading", { name: /Mr Auditor/ })).toBeVisible();
  await page
    .getByLabel("Business question", { exact: true })
    .selectOption("31");
  await expect(
    page.getByRole("heading", { name: "IFRS lease accounting" }),
  ).toBeVisible();
  const shots = "../docs/mr-auditor-business/evidence/screenshots";
  mkdirSync(shots, { recursive: true });
  await page.screenshot({
    path: shots + "/synthetic-case-inputs.png",
    fullPage: true,
  });
  await page
    .getByLabel("Ask Mr Auditor")
    .fill(
      "Review this synthetic office lease, show its source evidence, and prepare the liability schedule for professional review.",
    );
  await page
    .getByRole("button", { name: "Start source-linked analysis" })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Analysis · (COMPLETED|PARTIALLY_COMPLETED)/,
    }),
  ).toBeVisible({ timeout: 90000 });
  await page.getByLabel("Approved engine input").selectOption(fixture.lease_id);
  await page.getByRole("button", { name: "Run governed calculation" }).click();
  await expect(
    page.getByRole("heading", { name: "Retained engine result" }),
  ).toBeVisible();
  await expect(
    page.getByText("NOT_FILED_NOT_POSTED", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Inspect source" }).first().click();
  await expect(
    page.getByRole("complementary", { name: "Source evidence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "Open original evidence versions and review history",
    }),
  ).toBeVisible();
  await page
    .getByLabel("Workpaper preparation notes")
    .fill(
      "SYNTHETIC browser review: lease terms and calculated balances are linked to the approved source; independent approval is outstanding.",
    );
  await page
    .getByRole("button", { name: "Create source-linked draft workpaper" })
    .click();
  await expect(
    page.getByText("governed_draft_creation", { exact: true }),
  ).toBeVisible();
  const directory = "../docs/mr-auditor-business/evidence/screenshots";
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: directory + "/synthetic-connected-lease.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
