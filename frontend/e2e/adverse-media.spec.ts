import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
const currentFixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/media-fixture.json",
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

test("adverse-media search coverage and retained identity evidence for UAE then India", async ({
  page,
}) => {
  test.setTimeout(240000);
  page.setDefaultTimeout(30000);
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED")
      console.info(
        "Browser request failed",
        new URL(request.url()).pathname,
        request.failure()?.errorText,
      );
  });
  const saved = JSON.parse(
    readFileSync(
      "../.local-runtime/country-workflows/media-fixture.json",
      "utf8",
    ),
  );
  const folder = "../docs/country-workflows/screenshots/adverse-media";
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
      "collision",
      "nil",
      "same-subject",
      "unresolved",
      "unavailable",
    ] as const) {
      const input = saved.cases[country][kind];
      const title = `SYNTHETIC ${country} media ${kind} ${Date.now()}`;
      await page.goto(`/intelligence/${input.engagement}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("adverse-media-review");
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", input.payload.as_of],
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
        name: "Adverse-media review scope",
        exact: true,
      });
      await expect(
        scope.getByText(/No mentions is not clearance/),
      ).toBeVisible();
      if (["unresolved", "unavailable"].includes(kind)) {
        await expect(
          panel.getByRole("button", {
            name: "Independent approval",
            exact: true,
          }),
        ).toBeDisabled();
        await expect(panel.getByText(/Approval blocked:/)).toBeVisible();
      }
      if (["collision", "same-subject", "unresolved"].includes(kind)) {
        const assessments = panel.getByRole("region", {
          name: "Retained media assessments",
          exact: true,
        });
        await assessments.locator("summary").first().click();
        await expect(
          assessments.getByText(/Identity rationale:/),
        ).toBeVisible();
        await expect(assessments.getByText(/Risk rationale:/)).toBeVisible();
        await assessments.screenshot({
          path: `${folder}/${country}-${kind}-assessment.png`,
        });
      }
      await expect(
        page.getByRole("button", { name: "Dismiss notification", exact: true }),
      ).toHaveCount(0, { timeout: 10000 });
      await scope.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${folder}/${country}-${kind}-scope.png` });
      await scope.locator("summary").click();
      await expect(
        scope.getByRole("button", { name: /Download media evidence/ }),
      ).toHaveCount(Object.keys(input.documents).length);
      for (const [index, document] of Object.values(
        input.documents,
      ).entries()) {
        const waiting = page.waitForEvent("download");
        await scope
          .getByText(`SHA-256: ${(document as { sha256: string }).sha256}`, {
            exact: true,
          })
          .locator("..")
          .getByRole("button")
          .click();
        const downloaded = await waiting;
        const path = resolve(
          `../.local-runtime/country-workflows/media-${country}-${kind}-${index}.txt`,
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
