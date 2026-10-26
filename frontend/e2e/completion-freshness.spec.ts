import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const fixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/completion-fixture.json",
    "utf8",
  ),
);
function implementationHash() {
  return execFileSync(
    resolve("../backend/.venv/Scripts/python.exe"),
    [
      resolve("../scripts/country_workflows_run.py"),
      ".venv/Scripts/python.exe",
      "-c",
      "import sys; sys.path.insert(0, '../scripts'); from completion_preview import implementation_hash; print(implementation_hash())",
    ],
    { cwd: resolve(".."), encoding: "utf8" },
  ).trim();
}
test.beforeAll(() =>
  expect(implementationHash()).toBe(fixture.implementation_sha256),
);
test.afterAll(() =>
  expect(implementationHash()).toBe(fixture.implementation_sha256),
);

test("completion identifies stale approved work and independently reassessed sources in UAE then India", async ({
  page,
}) => {
  test.setTimeout(180000);
  const directory =
    "../docs/country-workflows/screenshots/completion-freshness";
  mkdirSync(directory, { recursive: true });
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  for (const country of ["AE", "IN"]) {
    await page.goto("/settings/countries");
    await page
      .getByLabel("Working country", { exact: true })
      .selectOption(country);
    await expect(
      page.getByLabel("Working country", { exact: true }),
    ).toHaveValue(country);
    for (const state of ["current", "stale", "reassessed"]) {
      const input = fixture.countries[country][state];
      await page.goto(`/engagements/${input.engagement}/completion`);
      const controls = page.getByRole("region", {
        name: "Engagement completion controls",
        exact: true,
      });
      await expect(
        controls.getByText(input.expected_ready ? "ready" : "outstanding", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        controls.getByText(
          `${input.checked_records} approved or locked records checked for current sources.`,
        ),
      ).toBeVisible();
      if (state === "stale") {
        await controls
          .getByText("Reviewed records needing source reassessment (3)")
          .click();
        await expect(controls.getByRole("link")).toHaveCount(3);
        for (const record of input.affected_records)
          await expect(
            controls.locator(`a[href$="?record=${record}"]`),
          ).toHaveCount(1);
        await expect(
          controls.getByText(/Historical approval is retained/),
        ).toBeVisible();
      }
      await controls.screenshot({
        path: `${directory}/${country}-${state}.png`,
      });
      const finalCheck = controls.getByText(
        "Independent quality review where required",
        { exact: true },
      );
      await finalCheck.scrollIntoViewIfNeeded();
      await expect(finalCheck).toBeVisible();
      if (state === "stale") {
        await page.screenshot({
          path: `${directory}/${country}-stale-bottom.png`,
        });
        await controls.getByRole("link", { name: /working-papers/ }).click();
        await expect(
          page.getByRole("heading", {
            name: "Working Paper Editor",
            exact: true,
          }),
        ).toBeVisible();
        await expect(
          page.getByText("APPROVED", { exact: true }).first(),
        ).toBeVisible();
        await page.screenshot({
          path: `${directory}/${country}-retained-approval.png`,
        });
      }
    }
  }
});
