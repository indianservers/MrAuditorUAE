import { test, expect, Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
);
const dataset = JSON.parse(
  readFileSync("../docs/qa-campaign/dataset.json", "utf8"),
);
const headers = {
  Origin: "http://127.0.0.1:3006",
  "X-Tenant-ID": dataset.tenant_id,
};
async function login(page: Page, email = "qa.admin@auditos.example") {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(credentials.QA_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}
test("India and UAE real setup, organization persistence, workspace and lifecycle interactions", async ({
  page,
}) => {
  await login(page);
  const receipts = [];
  for (const country of ["IN", "AE"]) {
    await page.goto("/settings");
    await expect(
      page.getByLabel("Working country", { exact: true }),
    ).toBeEnabled();
    await page
      .getByLabel("Working country", { exact: true })
      .selectOption(country);
    await expect(
      page.getByText(`${country}-profile-2026.10.24`, { exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Search countries")
      .fill(country === "IN" ? "India" : "United Arab");
    if (country === "IN")
      await page.screenshot({
        path: "../docs/qa/mr-auditor-phase1/country-settings.png",
        fullPage: true,
      });
    await page.getByLabel("Organization default country").selectOption(country);
    await page
      .getByRole("button", { name: "Save organization default" })
      .click();
    await page.goto("/clients");
    const code = `P1-${country}-${Date.now()}`;
    const name = `SYNTHETIC ${country} Phase 1 ${code}`;
    await page.getByRole("button", { name: "Add client" }).click();
    let dialog = page.getByRole("dialog").last();
    await dialog.getByLabel("code", { exact: true }).fill(code);
    await dialog.getByLabel("name", { exact: true }).fill(name);
    await dialog.getByRole("button", { name: "Save client" }).click();
    await page.getByLabel("Search clients").fill(code);
    const cell = page.locator(".ag-cell strong").filter({ hasText: name });
    await expect(cell).toBeVisible();
    await cell.click();
    await page.getByRole("button", { name: "Entity", exact: true }).click();
    dialog = page.getByRole("dialog", { name: "Add legal entity" });
    await dialog
      .getByLabel("Legal name", { exact: true })
      .fill(name + " Entity");
    await expect(dialog.getByLabel("ISO country")).toHaveValue(country);
    await expect(
      dialog.getByLabel("Functional currency", { exact: true }),
    ).toHaveValue(country === "IN" ? "INR" : "AED");
    const entityResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/backend/entities") &&
        r.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    const entity = await (await entityResponse).json();
    await page.getByRole("button", { name: "Add financial period" }).click();
    dialog = page.getByRole("dialog", { name: "Create financial period" });
    await dialog.getByLabel("Start date").fill("2026-01-01");
    await dialog.getByLabel("End date").fill("2026-12-31");
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Add engagement" }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "Add engagement" }).click();
    dialog = page.getByRole("dialog", { name: "Create engagement" });
    await dialog.getByLabel("Engagement name").fill(name + " Audit");
    await expect(dialog.getByLabel("Financial period")).toHaveValue(/.+/);
    const engagementResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/backend/engagements") &&
        r.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    const response = await engagementResponse;
    expect(response.status()).toBe(201);
    const engagement = await response.json();
    receipts.push({
      country,
      entity_id: entity.id,
      engagement_id: engagement.id,
    });
    await page.goto(`/engagements/${engagement.id}/workspace`);
    await expect(
      page.getByRole("heading", { name: name + " Audit", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Review reporting context" })
      .click();
    await page
      .getByLabel("Reporting framework")
      .selectOption(country === "IN" ? "Ind AS" : "IFRS");
    await page
      .getByLabel("Context rationale")
      .fill("Synthetic browser professional reporting context assessment");
    await page
      .getByRole("button", { name: "Request independent review" })
      .click();
    await expect(page.getByText("REQUESTED", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "Review reporting context" })
      .click();
    await page.screenshot({
      path: `../docs/qa/mr-auditor-phase1/workspace-${country}.png`,
      fullPage: true,
    });
    const catalogue = await page.request.get(
      `/api/backend/jurisdictions/modules?eid=${engagement.id}`,
      { headers },
    );
    expect((await catalogue.json()).items).toHaveLength(165);
    await page.goto(`/engagements/${engagement.id}/lifecycle`);
    await expect(
      page.getByRole("heading", { name: "Audit lifecycle graph", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".react-flow__node")).toHaveCount(10);
    await expect(page.locator(".react-flow__minimap-node")).toHaveCount(10);
    const viewport = page.locator(".react-flow__viewport");
    const initialTransform = await viewport.getAttribute("style");
    await page.getByRole("button", { name: "Zoom In", exact: true }).click();
    await expect
      .poll(() => viewport.getAttribute("style"))
      .not.toBe(initialTransform);
    const beforePan = await viewport.getAttribute("style");
    const pane = await page.locator(".react-flow__pane").boundingBox();
    if (!pane) throw new Error("Graph canvas unavailable");
    await page.mouse.move(pane.x + 30, pane.y + 40);
    await page.mouse.down();
    await page.mouse.move(pane.x + 90, pane.y + 80, { steps: 8 });
    await page.mouse.up();
    await expect.poll(() => viewport.getAttribute("style")).not.toBe(beforePan);
    await page.getByRole("button", { name: "Fit View", exact: true }).click();
    await page.getByRole("button", { name: "Dark canvas" }).click();
    await page.screenshot({
      path: `../docs/qa/mr-auditor-phase1/lifecycle-${country}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Light canvas" }).click();
    await page.getByRole("button", { name: "Expand all categories" }).click();
    await expect
      .poll(() => page.locator(".react-flow__node").count())
      .toBeGreaterThan(10);
    await page.getByLabel("Search graph").fill("Materiality");
    await expect(
      page
        .locator(".react-flow__node")
        .filter({ hasText: "Materiality" })
        .first(),
    ).toBeVisible();
    await page
      .locator(".react-flow__node")
      .filter({ hasText: "Performance Materiality" })
      .click();
    await page.getByRole("button", { name: "Focus selected node" }).click();
    await page.getByLabel("Search graph").fill("");
    await page.getByLabel("Graph module filter").selectOption("05");
    await page.getByLabel("Graph layout").selectOption("hierarchy");
    const saved = page.waitForResponse(
      (r) => r.url().endsWith("/layout") && r.request().method() === "PATCH",
    );
    await page.getByRole("button", { name: "Save layout" }).click();
    expect((await saved).status()).toBe(200);
    await page.goto("/modules");
    await page
      .getByLabel("Search modules")
      .fill(country === "IN" ? "GST" : "Corporate Tax");
    await expect(
      page
        .getByText(country === "IN" ? "PLANNED" : "AVAILABLE SCOPED", {
          exact: true,
        })
        .first(),
    ).toBeVisible();
  }
  await page.goto("/groups");
  await page.getByLabel("parent entity").selectOption(receipts[1].entity_id);
  await page.getByLabel("child entity").selectOption(receipts[0].entity_id);
  await page.getByLabel("Ownership %").fill("80");
  await page.getByLabel("Effective from").fill("2026-01-01");
  await page
    .getByLabel("Ownership rationale")
    .fill("Synthetic cross-country parent and subsidiary ownership evidence");
  const relationshipResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/jurisdictions/groups") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Submit ownership relationship" })
    .click();
  const relationship = await relationshipResponse;
  expect(relationship.status()).toBe(201);
  const relationshipId = (await relationship.json()).id;
  await expect(
    page
      .getByTestId(`group-relationship-${relationshipId}`)
      .getByText("IN REVIEW", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/qa/mr-auditor-phase1/group-structure.png",
    fullPage: true,
  });
  await page.request.delete("/api/session", {
    headers: { Origin: headers.Origin },
  });
  await login(page);
  await page.goto("/settings");
  await expect(page.getByLabel("Organization default country")).toHaveValue(
    "AE",
  );
  writeFileSync(
    "../docs/qa/mr-auditor-phase1/browser-setup-receipts.json",
    JSON.stringify(receipts, null, 2),
  );
});

test("saved source impact, keyboard search and upstream navigation", async ({
  page,
}) => {
  await login(page);
  const eid = dataset.companies[0].engagements[0].id;
  await page.goto(`/engagements/${eid}/working-papers`);
  await page.getByRole("button", { name: "New record" }).click();
  const reference = `P1-SOURCE-${Date.now()}`;
  await page.getByLabel("Reference", { exact: true }).fill(reference);
  await page
    .getByLabel("Title", { exact: true })
    .fill("Synthetic Phase 1 source paper");
  await page.getByLabel(/^folder/i).fill("Planning");
  await page.getByRole("button", { name: "Add section" }).click();
  await page.getByLabel("Section 1 heading").fill("Objective");
  await page
    .getByLabel("Section 1 text")
    .fill("Synthetic source work completed for browser verification");
  await page
    .getByLabel(/^conclusion/i)
    .fill("Synthetic documented source conclusion");
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/working-papers") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version" }).click();
  const source = await (await saved).json();
  const dependent = await page.request.post(
    `/api/backend/engagements/${eid}/audit/working-papers`,
    {
      headers,
      data: {
        reference: reference + "-TARGET",
        title: "Synthetic dependent Phase 1 paper",
        body: {
          folder: "Planning",
          sections: [
            { heading: "Objective", text: "Synthetic dependent paper" },
          ],
          conclusion: "Draft human conclusion",
          sources: [{ kind: "record", id: source.id }],
        },
      },
    },
  );
  expect(dependent.status()).toBe(201);
  const changed = await page.request.patch(
    `/api/backend/engagements/${eid}/audit/records/${source.id}`,
    {
      headers,
      data: {
        version: source.version,
        reference: source.reference,
        title: source.title,
        body: { ...source.body, conclusion: "Reassessed synthetic source" },
      },
    },
  );
  expect(changed.status()).toBe(200);
  await page.goto(`/engagements/${eid}/lifecycle`);
  await page.getByLabel("Search graph").fill(reference + "-TARGET");
  const node = page
    .locator(".react-flow__node")
    .filter({ hasText: reference + "-TARGET" });
  await expect(node).toContainText("STALE");
  await node.click();
  await page.getByLabel("Dependency direction").selectOption("UPSTREAM");
  await expect(
    page.getByRole("link", { name: "Open working paper and review history" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Open working paper and review history" })
    .click();
  await expect(page.getByLabel("Reference", { exact: true })).toHaveValue(
    reference + "-TARGET",
  );
  await page.getByRole("button", { name: /Search accounts/ }).click();
  await page.getByLabel("Command search").fill(reference);
  await expect(
    page
      .getByRole("toolbar", { name: "Search results" })
      .getByText(reference, { exact: false })
      .first(),
  ).toBeVisible();
  await page.getByLabel("Command search").press("ArrowDown");
  await expect(
    page
      .getByRole("toolbar", { name: "Search results" })
      .locator("button")
      .first(),
  ).toBeFocused();
});
