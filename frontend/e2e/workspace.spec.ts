import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
const fixture = JSON.parse(
  readFileSync("../docs/phase-3/browser-fixture.json", "utf8"),
);
const dimensions = JSON.parse(
  readFileSync("../docs/phase-3/reference-dimensions.json", "utf8"),
) as { file: string; width: number; height: number }[];
const shotDir = path.resolve("../docs/phase-3/screenshots");
mkdirSync(shotDir, { recursive: true });
async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Executive Dashboard" }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Select client")
      .locator('option[value="' + fixture.client_id + '"]'),
  ).toBeAttached();
}
async function selectContext(page: Page) {
  await page.getByLabel("Select client").selectOption(fixture.client_id);
  await expect(
    page
      .getByLabel("Select entity")
      .locator('option[value="' + fixture.entity_id + '"]'),
  ).toBeAttached();
  await page.getByLabel("Select entity").selectOption(fixture.entity_id);
  await expect(
    page
      .getByLabel("Select period")
      .locator('option[value="' + fixture.period_id + '"]'),
  ).toBeAttached();
  await page.getByLabel("Select period").selectOption(fixture.period_id);
}
async function navigate(page: Page, label: string) {
  await page.keyboard.press("Control+k");
  const cmd = page.getByRole("dialog", { name: "Search your workspace" });
  await expect(cmd).toBeVisible();
  await page.getByLabel("Command search").fill(label);
  await cmd.getByRole("button").filter({ hasText: label }).first().click();
  await expect(cmd).not.toBeVisible();
}
test("real backend: authentication, client CRUD, context and financial workflows", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const cookies = await page.context().cookies();
  expect(
    cookies
      .filter((c) => c.name.startsWith("auditos_"))
      .every((c) => c.httpOnly && c.sameSite === "Strict"),
  ).toBeTruthy();
  expect(await page.evaluate(() => Object.keys(localStorage))).not.toContain(
    "access_token",
  );
  await navigate(page, "Clients");
  await page.getByRole("button", { name: "Add client", exact: true }).click();
  const create = page.getByRole("dialog", { name: "Create client" });
  await create
    .getByLabel("code", { exact: true })
    .fill("BROWSER_" + Date.now());
  await create
    .getByLabel("name", { exact: true })
    .fill("SYNTHETIC — Browser CRUD");
  await create.getByRole("button", { name: "Save client" }).click();
  await expect(create).not.toBeVisible();
  await page.getByLabel("Search clients").fill("SYNTHETIC — Browser CRUD");
  await page
    .getByRole("gridcell", { name: "SYNTHETIC — Browser CRUD", exact: true })
    .click();
  await page.getByRole("button", { name: "Edit client", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit client" });
  await edit
    .getByLabel("name", { exact: true })
    .fill("SYNTHETIC — Browser CRUD updated");
  await edit.getByRole("button", { name: "Save client" }).click();
  await expect(edit).not.toBeVisible();
  await selectContext(page);
  await navigate(page, "Engagements");
  await page
    .getByRole("link", { name: "SYNTHETIC — FY2026 External Audit" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Audit Engagement Workspace" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Planning", exact: true }).click();
  await expect(
    page.getByText("Planning workspace", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Use engagement context" }).click();
  await navigate(page, "Trial Balance");
  await expect(
    page.getByText("Trial Balance Balanced", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("gridcell", { name: "Cash and bank balances", exact: true })
    .click();
  await expect(
    page.getByText("1100 — Cash and bank balances", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Linked transactions", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "General Ledger Explorer" }),
  ).toBeVisible();
  await page
    .getByRole("gridcell", { name: /SYN-\d{4}/ })
    .first()
    .click();
  await expect(
    page.getByRole("dialog", { name: "Transaction Details" }),
  ).toBeVisible();
  await expect(page.getByText("Original source lineage")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByLabel("Filter account").selectOption("");
  await expect(
    page.getByText("1–50 of 180 records", { exact: true }),
  ).toBeVisible();
  await page.locator('button[aria-label="Next page"]').click();
  await expect(
    page.getByText("51–100 of 180 records", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search transaction descriptions").fill("adjustment");
  await expect(
    page.getByText("1–36 of 36 records", { exact: true }),
  ).toBeVisible();
  await navigate(page, "Risk Investigation");
  await expect(
    page.getByRole("gridcell", { name: "J09", exact: true }).first(),
  ).toBeVisible();
  await page.getByLabel("Materiality threshold").fill("95000");
  await page
    .getByRole("button", { name: "Run analytics", exact: true })
    .click();
  await expect(
    page.getByText("completed", { exact: true }).first(),
  ).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Refresh workflow result" }).click();
  await page
    .getByRole("gridcell", { name: "J09", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Investigation", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Request anomaly explanation" })
    .click();
  await expect(
    page.getByText("Mock diagnostic result", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("requires review", { exact: false }).first(),
  ).toBeVisible();
  await navigate(page, "Reconciliations");
  await page
    .getByRole("button", { name: "Run reconciliation", exact: true })
    .click();
  await expect(
    page.getByText("completed", { exact: true }).first(),
  ).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Refresh workflow result" }).click();
  await expect(
    page.getByText("insufficient evidence", { exact: true }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("ten reference screenshots, responsive layouts, keyboard and accessibility", async ({
  page,
}) => {
  await login(page);
  await selectContext(page);
  const measurements: unknown[] = [];
  const routes = [
    ["01", "Dashboard", "Executive Dashboard"],
    ["02", "Clients", "Client & Company Management"],
    ["03", "Integrations", "Accounting Integration Center"],
    ["04", "Trial Balance", "Trial Balance Workbench"],
    ["05", "General Ledger", "General Ledger Explorer"],
    ["06", "Risk Investigation", "AI Audit Risk Investigation Studio"],
    ["07", "Reconciliations", "Financial Reconciliation Studio"],
    ["08", "Engagements", "Audit Engagement Workspace"],
    ["09", "AI Copilot", "AI Audit Copilot"],
    ["10", "Compliance", "Compliance Command Center"],
  ];
  for (const [id, label, title] of routes) {
    await navigate(page, label);
    if (id === "08")
      await page
        .getByRole("link", { name: "SYNTHETIC — FY2026 External Audit" })
        .click();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Loading authorized records…")).toHaveCount(0);
    if (id === "04") {
      await expect(
        page.getByText("Trial Balance Balanced", { exact: true }),
      ).toBeVisible();
      await page
        .getByRole("gridcell", { name: "Cash and bank balances", exact: true })
        .click();
    }
    if (id === "06") {
      await expect(
        page.getByRole("gridcell", { name: "J09", exact: true }).first(),
      ).toBeVisible();
      await page
        .getByRole("gridcell", { name: "J09", exact: true })
        .first()
        .click();
    }
    await expect(page.getByText("Loading authorized records…")).toHaveCount(0);
    await page.screenshot({ path: path.join(shotDir, id + "-desktop.png") });
    const reference = dimensions.find((d) => d.file.startsWith(id))!;
    await page.setViewportSize({
      width: reference.width,
      height: reference.height,
    });
    await page.screenshot({
      path: path.join(shotDir, id + "-reference-viewport.png"),
    });
    measurements.push({
      reference,
      route: page.url(),
      geometry: await page.evaluate(() => ({
        width: innerWidth,
        height: innerHeight,
        bodyWidth: document.body.scrollWidth,
        bodyHeight: document.body.scrollHeight,
        renderedRows: document.querySelectorAll(".ag-row").length,
      })),
    });
    await page.setViewportSize({ width: 1672, height: 941 });
  }
  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("dialog", { name: "Search your workspace" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByLabel("Collapse navigation").click();
  await expect(page.locator(".app-shell")).toHaveClass(/sidebar-collapsed/);
  await page.getByLabel("Expand navigation").click();
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  writeFileSync(
    "../docs/phase-3/accessibility.json",
    JSON.stringify(axe.violations, null, 2),
  );
  expect(axe.violations.filter((v) => v.impact === "critical")).toEqual([]);
  for (const size of [
    { width: 1920, height: 1080 },
    { width: 1600, height: 900 },
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    await page.screenshot({
      path: path.join(shotDir, `responsive-${size.width}.png`),
    });
    const geometry = await page.evaluate(() => ({
      width: document.body.scrollWidth,
      height: document.body.scrollHeight,
    }));
    expect(geometry.width).toBeLessThanOrEqual(size.width);
    expect(geometry.height).toBeLessThanOrEqual(size.height);
    measurements.push({ responsive: size, geometry });
  }
  writeFileSync(
    "../docs/phase-3/visual-measurements.json",
    JSON.stringify(measurements, null, 2),
  );
});
test("BFF cross-origin and session boundary", async ({ request }) => {
  expect(
    (
      await request.post("/api/session", {
        headers: { Origin: "https://attacker.invalid" },
        data: {
          email: "admin@example.com",
          password: "test-strong-password-123",
        },
      })
    ).status(),
  ).toBe(403);
  expect((await request.get("/api/backend/clients")).status()).toBe(401);
  const r = await request.post("/api/session", {
    headers: { Origin: process.env.FRONTEND_URL || "http://127.0.0.1:3000" },
    data: { email: "admin@example.com", password: "test-strong-password-123" },
  });
  expect(r.status()).toBe(200);
  expect(await r.json()).toEqual({ authenticated: true });
  expect(
    (
      await request.post("/api/backend/clients", {
        headers: { Origin: "https://attacker.invalid" },
        data: { code: "x", name: "x" },
      })
    ).status(),
  ).toBe(403);
});
