import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const currentFixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/document-worker-fixture.json",
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

test("real document extraction, retained originals and ZIP member selection in UAE then India", async ({
  page,
}) => {
  test.setTimeout(240000);
  page.setDefaultTimeout(30000);
  const folder = "../docs/country-workflows/screenshots/document-worker";
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
    for (const [index, kind] of [
      "digital",
      "scan",
      "zip-selected",
      "zip-batch",
    ].entries()) {
      const filename =
        kind === "digital"
          ? "digital.pdf"
          : kind === "scan"
            ? "scan.png"
            : "documents.zip";
      const file = input.files[filename];
      await page.goto(`/intelligence/${input.engagement}/ocr`);
      await page
        .getByLabel("Evidence version")
        .selectOption(file.payload.evidence_version_id);
      if (kind === "zip-selected")
        await page.getByLabel("ZIP member (optional)").fill("invoice.pdf");
      await page
        .getByRole("button", { name: "Queue document extraction", exact: true })
        .click();
      const options = page
        .getByLabel("Result version")
        .getByRole("option", { name: /^ocr •/ });
      await expect(options).toHaveCount(index + 1, { timeout: 150000 });
      await page
        .getByLabel("Result version")
        .selectOption((await options.first().getAttribute("value"))!);
      const invoice = page.getByLabel("invoice_number", { exact: true });
      if (kind === "zip-batch") {
        await expect(invoice).toHaveValue("");
        await expect(
          page.getByText(/Multiple documents retained separately/).first(),
        ).toBeVisible();
      } else {
        for (const [field, value] of Object.entries(file.expected.fields))
          await expect(page.getByLabel(field, { exact: true })).toHaveValue(
            String(value),
          );
      }
      const original = page.getByRole("img", {
        name: "Original document with extracted text regions",
        exact: true,
      });
      await expect(original).toBeVisible();
      await original.screenshot({
        path: `${folder}/${country}-${kind}-original.png`,
      });
      await invoice.scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `${folder}/${country}-${kind}-fields.png`,
      });
      if (kind === "zip-batch") {
        const selector = page.getByLabel("Source page");
        await expect(selector.getByRole("option")).toHaveCount(2);
        const previousHref = await original
          .locator("image")
          .getAttribute("href");
        await selector.selectOption("1");
        await expect(original.locator("image")).not.toHaveAttribute(
          "href",
          previousHref!,
        );
        await expect(original).toBeVisible();
        await original.screenshot({
          path: `${folder}/${country}-zip-batch-second-original.png`,
        });
        const single = page
          .getByLabel("Result version")
          .getByRole("option", { name: /^ocr .*digital.pdf/ });
        await expect(single).toHaveCount(1);
        const batchId = await page.getByLabel("Result version").inputValue();
        const singleId = (await single.getAttribute("value"))!;
        await page.getByLabel("Result version").selectOption(singleId);
        await expect(
          page.getByLabel("invoice_number", { exact: true }),
        ).toHaveValue(file.expected.fields.invoice_number);
        // Warm both detail queries so switching does not unmount on an empty fetch.
        await page.getByLabel("Result version").selectOption(batchId);
        await expect(selector).toHaveValue("0");
        await expect(original).toBeVisible();
        const firstPageHref = await original
          .locator("image")
          .getAttribute("href");
        await selector.selectOption("1");
        await expect(original.locator("image")).not.toHaveAttribute(
          "href",
          firstPageHref!,
        );
        await page.getByLabel("Result version").selectOption(singleId);
        await expect(
          page.getByLabel("invoice_number", { exact: true }),
        ).toHaveValue(file.expected.fields.invoice_number);
        await expect(page.getByLabel("Source page")).toHaveValue("0");
        await expect(original).toBeVisible();
        await original.screenshot({
          path: `${folder}/${country}-restored-single-page.png`,
        });
      }
    }
  }
});
