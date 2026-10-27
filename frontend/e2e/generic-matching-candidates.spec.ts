import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const currentFixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/generic-candidates-fixture.json",
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
      "from app.core.operations_contracts import implementation_hash,country_workflow_hash; print(implementation_hash()+chr(58)+country_workflow_hash())",
    ],
    { cwd: resolve(".."), encoding: "utf8" },
  ).trim();
}
test.beforeAll(() =>
  expect(implementationHash()).toBe(
    `${currentFixture.implementation_sha256}:${currentFixture.country_implementation_sha256}`,
  ),
);
test.afterAll(() =>
  expect(implementationHash()).toBe(
    `${currentFixture.implementation_sha256}:${currentFixture.country_implementation_sha256}`,
  ),
);

test("generic ledger reconciliation exposes every alternative in UAE then India", async ({
  page,
}) => {
  test.setTimeout(180000);
  page.setDefaultTimeout(30000);
  const folder = "../docs/country-workflows/screenshots/generic-candidates";
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
    const input = currentFixture.countries[country];
    await page.goto(`/intelligence/${input.engagement}/reconciliation`);
    await page
      .getByLabel("Committed snapshot")
      .selectOption(input.payload.snapshot_id);
    await page
      .getByLabel("Bank GL account")
      .selectOption(input.payload.account_ids);
    await page
      .getByLabel("Supporting table")
      .selectOption(input.payload.statement_source_id);
    await page
      .getByRole("button", {
        name: "Queue transaction reconciliation",
        exact: true,
      })
      .click();
    const option = page
      .getByLabel("Result version")
      .getByRole("option", { name: /^reconciliation •/ });
    await expect(option).toHaveCount(1, { timeout: 120000 });
    await page
      .getByLabel("Result version")
      .selectOption((await option.getAttribute("value"))!);
    const summary = page.getByRole("complementary", {
      name: "Reconciliation review decisions",
      exact: true,
    });
    await expect(summary).toContainText("0 of 242");
    await expect(summary).toContainText("Requests and notes do not dispose");
    await summary.screenshot({
      path: `${folder}/${country}-review-decisions.png`,
    });
    const viewer = page.getByRole("region", {
      name: "Transaction matching candidates",
      exact: true,
    });
    for (let i = 0; i < 4; i++) {
      await viewer
        .getByRole("button", { name: "Next ambiguous items", exact: true })
        .click();
      await expect(
        viewer.getByText(
          `Ambiguous items ${26 + i * 25}–${Math.min(50 + i * 25, 121)} of 121`,
          { exact: true },
        ),
      ).toBeVisible();
    }
    await viewer
      .getByRole("button", { name: /^Inspect / })
      .last()
      .click();
    const details = viewer.getByRole("region", {
      name: "Candidate transaction details",
      exact: true,
    });
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
    const last = details.getByRole("cell", { name: "row-122", exact: true });
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
    await page.getByRole("button", { name: "Next 100", exact: true }).click();
    await expect(page.getByText("Rows 101–200", { exact: true })).toBeVisible();
    await expect(
      details.getByText("Candidates 101–121 of 121", { exact: true }),
    ).toBeVisible();
    await details.screenshot({
      path: `${folder}/${country}-last-candidates.png`,
    });
    const waiting = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    const downloaded = await waiting;
    const path = resolve(
      `../.local-runtime/country-workflows/generic-candidates-${country}.xlsx`,
    );
    await downloaded.saveAs(path);
    const exported = JSON.parse(
      execFileSync(
        resolve("../backend/.venv/Scripts/python.exe"),
        [
          "-c",
          "import sys,json; from openpyxl import load_workbook; b=load_workbook(sys.argv[1],read_only=True); r=list(b['Matching candidates'].values); d=dict((r[0],r[1]) for r in b['Reconciliation decisions'].values if len(r)==2); print(json.dumps({'links':len(r)-1,'last':r[-1][1],'unmatched':d['unmatched_transactions'],'findings':d['unmatched_with_findings']}))",
          path,
        ],
        { encoding: "utf8" },
      ),
    );
    expect(exported).toEqual({
      links: 14641,
      last: "row-122",
      unmatched: "242",
      findings: "0",
    });
  }
});
