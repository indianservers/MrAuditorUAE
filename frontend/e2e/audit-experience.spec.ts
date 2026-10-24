import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
);
test("portfolio setup creates a real engagement and opens the actionable audit journey", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  await page
    .getByLabel("Password", { exact: true })
    .fill(credentials.QA_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/engagements");
  await expect(
    page.getByRole("heading", { name: "Your audit portfolio" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await expect(page.locator(".ag-root")).toBeVisible();
  await page.getByRole("button", { name: "Cards", exact: true }).click();
  await page.screenshot({
    path: "../docs/ui-refresh/portfolio.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "New engagement", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Continue", exact: true }),
  ).toBeDisabled();
  const entity = page.getByLabel("Legal entity", { exact: true });
  await expect(entity).toBeVisible();
  await expect.poll(() => entity.locator("option").count()).toBeGreaterThan(1);
  await entity.selectOption("66c8d070-f9f9-4f41-9c19-8d5d803705a0");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const name = `SYNTHETIC UI refresh ${Date.now()}`;
  await page.getByLabel("Engagement name", { exact: true }).fill(name);
  const period = page.getByLabel("Financial period", { exact: true });
  await expect(period).toBeVisible();
  await expect.poll(() => period.locator("option").count()).toBeGreaterThan(1);
  await period.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.screenshot({
    path: "../docs/ui-refresh/setup.png",
    fullPage: true,
  });
  const created = page.waitForResponse(
    (r) =>
      r.url().includes("/api/backend/engagements") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create engagement", exact: true })
    .click();
  expect((await created).status()).toBe(201);
  await page.waitForURL("**/workspace");
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "A clear path from source to opinion" }),
  ).toBeVisible();
  await expect(page.locator(".audit-stage")).toHaveCount(8);
  await page
    .getByRole("button", { name: "Focus on attention", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Show all stages", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({
    path: "../docs/ui-refresh/journey.png",
    fullPage: true,
  });
  await page.setViewportSize({width:780,height:1000});
  const command = await page.locator(".audit-command").boundingBox();
  expect(command).not.toBeNull();
  expect(command!.width).toBeLessThanOrEqual(780);
  await page.screenshot({path:"../docs/ui-refresh/journey-narrow.png",fullPage:true});
  await page.setViewportSize({width:1600,height:1100});
  await page
    .locator(".audit-stage")
    .filter({ hasText: "Independent review" })
    .click();
  await page.waitForURL("**/review-notes");
  await expect(
    page.getByRole("heading", { name: "Reviewer Command Center" }),
  ).toBeVisible();
});
