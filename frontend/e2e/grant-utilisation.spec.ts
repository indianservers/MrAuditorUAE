import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
const currentFixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/grant-fixture.json",
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
      "from app.core.operations_contracts import country_workflow_hash; print(country_workflow_hash())",
    ],
    { cwd: resolve(".."), encoding: "utf8" },
  ).trim();
}
test.beforeAll(() =>
  expect(implementationHash()).toBe(currentFixture.implementation_sha256),
);
test.afterAll(() =>
  expect(implementationHash()).toBe(currentFixture.implementation_sha256),
);

test("grant expenditure controls and retained mandates for UAE then India", async ({
  page,
}) => {
  test.setTimeout(240000);
  page.setDefaultTimeout(30000);
  const saved = JSON.parse(
    readFileSync(
      "../.local-runtime/country-workflows/grant-fixture.json",
      "utf8",
    ),
  );
  const folder = "../docs/country-workflows/screenshots/grant-utilisation";
  mkdirSync(folder, { recursive: true });
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  for (const country of ["AE", "IN"] as const) {
    await page.goto("/settings/countries");
    await page
      .getByLabel("Working country", { exact: true })
      .selectOption(country);
    await expect(
      page.getByLabel("Working country", { exact: true }),
    ).toHaveValue(country);
    for (const kind of [
      "matched",
      "credit",
      "nil",
      "over-budget",
      "unallocated",
    ] as const) {
      const input = saved.cases[country][kind];
      const title = `SYNTHETIC ${country} grant ${kind} ${Date.now()}`;
      await page.goto(`/intelligence/${input.engagement}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("grant-utilisation");
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", input.payload.as_of],
        ["Reporting period start", input.payload.period_start],
        ["Scope and source rationale", input.payload.rationale],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      for (const [role, identifier] of Object.entries(input.payload.source_ids))
        await page
          .getByLabel(`${role} source`, { exact: true })
          .selectOption(identifier as string);
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const option = page
        .getByLabel("Saved source or result")
        .locator("option")
        .filter({ hasText: title });
      await expect(option).toHaveCount(1, { timeout: 120000 });
      await page
        .getByLabel("Saved source or result")
        .selectOption((await option.getAttribute("value"))!);
      const panel = page
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      const scope = panel.getByRole("region", {
        name: "Grant utilisation scope",
        exact: true,
      });
      await expect(
        scope.getByText(/They do not establish cash available/),
      ).toBeVisible();
      const closing = ["credit", "unallocated"].includes(kind)
        ? "450"
        : kind === "nil"
          ? "200"
          : "500";
      const category = panel
        .getByRole("row")
        .filter({ hasText: "category-budget" });
      await expect(
        category.getByRole("cell", { name: closing, exact: true }).first(),
      ).toBeVisible();
      if (kind === "unallocated")
        await expect(
          panel.getByRole("button", {
            name: "Independent approval",
            exact: true,
          }),
        ).toBeDisabled();
      for (const notice of await page
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await scope.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${folder}/${country}-${kind}-scope.png` });
      await scope.locator("summary").click();
      for (const [index, document] of Object.values(
        input.documents,
      ).entries()) {
        const waiting = page.waitForEvent("download");
        await scope
          .getByRole("button", {
            name: `Download grant evidence ${index + 1}`,
            exact: true,
          })
          .click();
        const downloaded = await waiting;
        const path = resolve(
          `../.local-runtime/country-workflows/grant-${country}-${kind}-${index}.txt`,
        );
        await downloaded.saveAs(path);
        expect(
          createHash("sha256").update(readFileSync(path)).digest("hex"),
        ).toBe((document as { sha256: string }).sha256);
      }
      await scope.screenshot({
        path: `${folder}/${country}-${kind}-documents.png`,
      });
    }
  }
});
