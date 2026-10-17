import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync("../docs/phase-3/browser-fixture.json", "utf8"),
);
test("measure real paginated ledger requests and bounded DOM rendering", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Executive Dashboard" }),
  ).toBeVisible();
  await page.getByLabel("Select client").selectOption(fixture.client_id);
  await page.getByLabel("Select entity").selectOption(fixture.entity_id);
  await page.getByLabel("Select period").selectOption(fixture.period_id);
  await page.keyboard.press("Control+k");
  await page.getByLabel("Command search").fill("General Ledger");
  await page
    .getByRole("dialog", { name: "Search your workspace" })
    .getByRole("button")
    .filter({ hasText: "General Ledger" })
    .click();
  await expect(
    page.getByText("1–50 of 180 records", { exact: true }),
  ).toBeVisible();
  const samples = [];
  for (const offset of [0, 50, 100, 150, 0]) {
    const r = await page.evaluate(
      async ({ fixture, offset }) => {
        const tenants = await (await fetch("/api/backend/tenants")).json();
        const start = performance.now();
        const response = await fetch(
          "/api/backend/workspace/ledger?" +
            new URLSearchParams({
              entity_id: fixture.entity_id,
              period_id: fixture.period_id,
              offset: String(offset),
              limit: "50",
            }),
          { headers: { "X-Tenant-ID": tenants[0].id } },
        );
        const text = await response.text();
        const json = JSON.parse(text);
        return {
          milliseconds: performance.now() - start,
          bytes: new TextEncoder().encode(text).length,
          status: response.status,
          rows: json.items?.length,
          total: json.total,
        };
      },
      { fixture, offset },
    );
    expect(r.status).toBe(200);
    expect(r.rows).toBeLessThanOrEqual(50);
    samples.push(r);
  }
  const rendered = await page.locator(".ag-row").count();
  expect(rendered).toBeLessThanOrEqual(50);
  expect(rendered).toBeGreaterThan(0);
  writeFileSync(
    "../docs/phase-3/performance.json",
    JSON.stringify(
      {
        environment: "Windows local development server; Chromium; warm backend",
        population: 180,
        limit: 50,
        samples,
        rendered_center_rows: rendered,
        limitation:
          "This measures the labeled 180-line browser fixture. No million-row frontend throughput or concurrent-user claim is made.",
      },
      null,
      2,
    ),
  );
});
