import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync(
    "../.local-runtime/country-workflows/evidence-rescan-fixture.json",
    "utf8",
  ),
);

test("retained quarantined originals rescan into new versions in UAE then India", async ({
  page,
}) => {
  expect(fixture.synthetic).toBe(true);
  expect(fixture.scanner).toBe("UNCONFIGURED_QUARANTINE_PATH");
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  mkdirSync("../docs/country-workflows/screenshots/evidence-rescan", {
    recursive: true,
  });
  for (const country of ["AE", "IN"]) {
    await page.goto("/settings/countries");
    await page
      .getByLabel("Working country", { exact: true })
      .selectOption(country);
    const input = fixture.countries[country];
    await page.goto(
      `/engagements/${input.engagement}/evidence?record=${input.record}`,
    );
    const versions = page.locator(".audit-evidence-version");
    await expect(versions).toHaveCount(1);
    const rescan = page.getByRole("button", {
      name: "Rescan retained original",
      exact: true,
    });
    await rescan.click();
    await expect(versions).toHaveCount(2);
    for (const version of await versions.all()) {
      await expect(version).toContainText("QUARANTINED");
      await expect(version).toContainText(input.sha256);
    }
    await expect(versions.first()).toContainText("Version 2");
    await expect(versions.last()).toContainText("Version 1");
    await expect(rescan).toHaveCount(1);
    await expect(
      page.getByRole("button", { name: "Download verified attachment" }),
    ).toHaveCount(0);
    await rescan.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `../docs/country-workflows/screenshots/evidence-rescan/${country}-retained-quarantine.png`,
    });
  }
});
