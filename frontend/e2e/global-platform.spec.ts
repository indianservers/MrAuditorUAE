import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
);
const dataset = JSON.parse(
  readFileSync("../docs/qa-campaign/dataset.json", "utf8"),
);

test("country Settings persist and working-paper graph opens saved records", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  await page
    .getByLabel("Password", { exact: true })
    .fill(credentials.QA_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/settings");
  const country = page.getByLabel("Working country", { exact: true });
  await expect(country).toBeEnabled();
  await country.selectOption("IN");
  await expect(
    page.getByText("IN-foundation-2026.10.1", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await expect(country).toHaveValue("IN");
  await country.selectOption("AE");
  await expect(
    page.getByText("AE-foundation-2026.10.1", { exact: false }),
  ).toBeVisible();
  const headers = {
    Origin: "http://127.0.0.1:3006",
    "X-Tenant-ID": dataset.tenant_id,
  };
  const first = dataset.companies[0].engagements[0].id;
  const existing = await page.request.get("/api/backend/engagements/" + first, {
    headers,
  });
  expect(existing.ok()).toBeTruthy();
  const eng = await existing.json();
  const created = await page.request.post("/api/backend/engagements", {
    headers,
    data: {
      entity_id: eng.entity_id,
      period_id: eng.period_id,
      name: "SYNTHETIC global browser " + Date.now(),
      engagement_type: "External Audit",
    },
  });
  expect(created.status()).toBe(201);
  const eid = (await created.json()).id;
  const base = `/api/backend/engagements/${eid}/audit`;
  const body = {
    folder: "Planning",
    sections: [{ heading: "Objective", text: "Synthetic browser graph test" }],
    conclusion: "Draft human review",
  };
  const source = await page.request.post(base + "/working-papers", {
    headers,
    data: { reference: "WP-SOURCE", title: "Browser source", body },
  });
  expect(source.status()).toBe(201);
  const s = await source.json();
  const target = await page.request.post(base + "/working-papers", {
    headers,
    data: {
      reference: "WP-TARGET",
      title: "Browser dependent",
      body: { ...body, sources: [{ kind: "record", id: s.id }] },
    },
  });
  expect(target.status()).toBe(201);
  await page.goto(`/engagements/${eid}/graph`);
  await expect(
    page.getByRole("heading", { name: "Working-paper dependency graph" }),
  ).toBeVisible();
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  const updated = await page.request.patch(base + "/records/" + s.id, {
    headers,
    data: {
      version: s.version,
      reference: s.reference,
      title: s.title,
      body: { ...body, conclusion: "Reassessed browser source" },
    },
  });
  expect(updated.status()).toBe(200);
  await page.getByRole("button", { name: "Refresh graph" }).click();
  await expect(
    page.locator(".react-flow__node").filter({ hasText: "WP-TARGET" }),
  ).toContainText("STALE");
  await page.screenshot({
    path: "../docs/global-platform/working-paper-graph.png",
    fullPage: true,
  });
  await page
    .locator(".react-flow__node")
    .filter({ hasText: "WP-TARGET" })
    .click();
  await expect(
    page.getByRole("link", { name: "Open working paper and review history" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Open working paper and review history" })
    .click();
  await expect(
    page.getByText("Browser dependent", { exact: true }).first(),
  ).toBeVisible();
});
