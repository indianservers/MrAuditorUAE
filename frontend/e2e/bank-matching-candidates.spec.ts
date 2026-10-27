import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const currentFixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/matching-fixture.json",
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

test("complete competing bank candidate review and exports in UAE then India", async ({
  page,
}) => {
  test.setTimeout(180000);
  page.setDefaultTimeout(30000);
  const folder = "../docs/country-workflows/screenshots/matching-candidates";
  mkdirSync(folder, { recursive: true });
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
    const input = currentFixture.countries[country];
    const title = `SYNTHETIC ${country} complete bank alternatives ${Date.now()}`;
    await page.goto(`/intelligence/${input.engagement}/country-workflow`);
    await page.getByLabel("Workflow", { exact: true }).selectOption("bank-brs");
    const form = page;
    for (const [label, value] of [
      ["Schedule title", title],
      ["Reconciliation date", input.payload.as_of],
      ["Scope and source rationale", input.payload.rationale],
      ["Bank account identifier", input.payload.account],
      ["Account currency", input.payload.currency],
      ...[
        "book_opening",
        "book_closing",
        "statement_opening",
        "statement_closing",
      ].map((key) => [key.replaceAll("_", " "), input.payload[key]]),
    ])
      await form.getByLabel(label, { exact: true }).fill(value);
    for (const [role, id] of Object.entries(input.payload.source_ids))
      await form
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(id as string);
    await form
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
    const candidates = panel.getByRole("region", {
      name: "Bank matching candidates",
      exact: true,
    });
    await expect(
      candidates.getByText(/These are possible alternatives/),
    ).toBeVisible();
    for (let i = 0; i < 4; i++) {
      await candidates
        .getByRole("button", { name: "Next ambiguous items", exact: true })
        .click();
      await expect(
        candidates.getByText(
          `Ambiguous items ${26 + i * 25}–${Math.min(50 + i * 25, 121)} of 121`,
          { exact: true },
        ),
      ).toBeVisible();
    }
    await candidates
      .getByRole("button", {
        name: "Inspect L120 · 121 candidates",
        exact: true,
      })
      .click();
    const details = candidates.getByRole("region", {
      name: "Candidate transaction details",
      exact: true,
    });
    await expect(details.getByText(/Book item L120/)).toBeVisible();
    await candidates
      .getByText("Ambiguous items 101–121 of 121", { exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${folder}/${country}-ambiguous-items.png` });
    for (let i = 0; i < 4; i++) {
      await details
        .getByRole("button", { name: "Next candidates", exact: true })
        .click();
      await expect(
        details.getByText(
          `Candidates ${26 + i * 25}–${Math.min(50 + i * 25, 121)} of 121`,
          { exact: true },
        ),
      ).toBeVisible();
    }
    const last = details.getByRole("cell", { name: "R120", exact: true });
    await last.scrollIntoViewIfNeeded();
    await expect(last).toBeInViewport();
    await expect(
      details
        .getByRole("cell", {
          name:
            country === "AE"
              ? "SYNTHETIC شركة ألف"
              : "SYNTHETIC भारत आपूर्तिकर्ता",
          exact: true,
        })
        .first(),
    ).toBeVisible();
    await expect(
      details.getByRole("button", { name: "Next candidates", exact: true }),
    ).toBeDisabled();
    await details.screenshot({
      path: `${folder}/${country}-last-candidates.png`,
    });
    const waiting = page.waitForEvent("download");
    await panel
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    const downloaded = await waiting;
    const path = resolve(
      `../.local-runtime/country-workflows/matching-${country}.xlsx`,
    );
    await downloaded.saveAs(path);
    const verification = JSON.parse(
      execFileSync(
        resolve("../backend/.venv/Scripts/python.exe"),
        [
          "-c",
          "import sys,json; from openpyxl import load_workbook; b=load_workbook(sys.argv[1],read_only=True); r=list(b['Matching candidates'].values); print(json.dumps({'links':len(r)-1,'last':r[-1][:4]}))",
          path,
        ],
        { encoding: "utf8" },
      ),
    );
    expect(verification).toEqual({
      links: 14641,
      last: ["L120", "R120", "121", "COMPLETE_RETAINED_CANDIDATES"],
    });
  }
});
