import { test, expect, Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
);
const data = JSON.parse(
  readFileSync("../docs/qa-campaign/dataset.json", "utf8"),
);
async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  await page
    .getByLabel("Password", { exact: true })
    .fill(credentials.QA_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

test("thirteen real role logins enforce server CRUD permissions", async ({
  browser,
}) => {
  test.setTimeout(240000);
  const roles = [
    "Platform Administrator",
    "Firm Administrator",
    "Audit Partner / Chartered Accountant",
    "Audit Manager",
    "Auditor",
    "Tax Manager",
    "TP Analyst",
    "VAT Analyst",
    "Internal Auditor",
    "Client Administrator",
    "Client Viewer",
    "Quality Reviewer",
    "Read-only Reviewer",
  ];
  const permissions = JSON.parse(
    readFileSync("../docs/qa-campaign/inventory.json", "utf8"),
  ).roles;
  const receipts = [];
  for (const role of roles) {
    const user = data.users.find((u: { role: string }) => u.role === role);
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/login");
    await page.getByLabel("Email address").fill(user.email);
    await page
      .getByLabel("Password", { exact: true })
      .fill(credentials.QA_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL("**/dashboard");
    await page.goto("/clients");
    const headers = {
      Origin: "http://127.0.0.1:3006",
      "X-Tenant-ID": data.tenant_id,
    };
    const read = await page.request.get("/api/backend/clients?limit=1", {
      headers,
    });
    expect(read.status()).toBe(
      permissions[role].includes("clients.read") ? 200 : 403,
    );
    const create = await page.request.post("/api/backend/clients", {
      headers,
      data: {
        code: `CRUD-ROLE-${roles.indexOf(role)}-${Date.now()}`,
        name: `SYNTHETIC role probe ${role}`,
      },
    });
    expect(create.status()).toBe(
      permissions[role].includes("clients.write") ? 201 : 403,
    );
    const cross = await page.request.get("/api/backend/clients", {
      headers: { "X-Tenant-ID": "00000000-0000-4000-8000-000000000001" },
    });
    expect(cross.status()).toBe(403);
    receipts.push({
      role,
      read: read.status(),
      create: create.status(),
      crossTenant: cross.status(),
      scope:
        "Real login and client CRUD authorization; specialist form workflow not covered by this probe",
    });
    await page.screenshot({
      path: `../docs/qa-crud/screenshots/role-${roles.indexOf(role)}.png`,
      fullPage: true,
    });
    writeFileSync(
      "../docs/qa-crud/browser-role-results.json",
      JSON.stringify(receipts, null, 2),
    );
    await context.close();
    await new Promise((resolve) => setTimeout(resolve, 3500));
  }
});
test("client form create edit archive restore with separate persisted API assertions", async ({
  page,
}) => {
  await login(page);
  await page.goto("/clients");
  const code = `CRUD-${Date.now()}`;
  const name = `SYNTHETIC CRUD دبي ${code}`;
  await page.getByRole("button", { name: "Add client" }).click();
  const dialog = page.getByRole("dialog").last();
  await dialog.getByLabel("code", { exact: true }).fill(code);
  await dialog.getByLabel("name", { exact: true }).fill(name);
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/backend/clients") &&
      r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Save client" }).click();
  const result = await created;
  expect(result.status()).toBe(201);
  const row = await result.json();
  await page.getByLabel("Search clients").fill(code);
  const cell = page.locator(".ag-cell strong").filter({ hasText: name });
  await expect(cell).toBeVisible();
  await page.screenshot({
    path: "../docs/qa-crud/screenshots/client-created.png",
    fullPage: true,
  });
  for (const status of ["archived", "active"]) {
    await cell.click();
    await page
      .getByRole("button", { name: "Edit client", exact: true })
      .click();
    const form = page.getByRole("dialog", { name: "Edit client", exact: true });
    await form
      .getByRole("combobox", { name: "status", exact: true })
      .selectOption(status);
    await form
      .getByLabel("Lifecycle reason")
      .fill(`Synthetic browser lifecycle review for ${status}`);
    const saved = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/backend/clients/${row.id}`) &&
        r.request().method() === "PATCH",
    );
    await form.getByRole("button", { name: "Save client" }).click();
    expect((await saved).status()).toBe(200);
    await expect(cell).toHaveCount(0);
    await page.getByLabel("Client status filter").selectOption(status);
    await expect(cell).toBeVisible();
    await page.screenshot({
      path: `../docs/qa-crud/screenshots/client-${status}.png`,
      fullPage: true,
    });
  }
  await page.reload();
  await page.getByLabel("Search clients").fill(code);
  await expect(cell).toBeVisible();
  const persisted = await page.request.get(`/api/backend/clients/${row.id}`, {
    headers: { Origin: "http://127.0.0.1:3006", "X-Tenant-ID": data.tenant_id },
  });
  expect(persisted.status()).toBe(200);
  const final = await persisted.json();
  expect(final.status).toBe("active");
  expect(final.version).toBe(row.version + 2);
  expect(final.name).toBe(name);
  writeFileSync(
    "../docs/qa-crud/browser-client-receipt.json",
    JSON.stringify(
      {
        id: row.id,
        code,
        initialVersion: row.version,
        finalVersion: final.version,
        status: final.status,
      },
      null,
      2,
    ),
  );
});

test("working paper actual form creates a persisted draft", async ({
  page,
}) => {
  await login(page);
  const eid = data.companies[0].engagements[0].id;
  await page.goto(`/engagements/${eid}/working-papers`);
  await page.getByRole("button", { name: "New record" }).click();
  await page
    .getByLabel("Reference", { exact: true })
    .fill(`CRUD-PAPER-${Date.now()}`);
  await page
    .getByLabel("Title", { exact: true })
    .fill("SYNTHETIC browser lifecycle paper");
  await page.getByLabel(/^folder/i).fill("Planning");
  await page.getByRole("button", { name: "Add section" }).click();
  await page.getByLabel("Section 1 heading").fill("Objective");
  await page
    .getByLabel("Section 1 text")
    .fill("Synthetic browser evidence without production data");
  await page
    .getByLabel(/^conclusion/i)
    .fill("Synthetic draft conclusion for controlled review");
  const save = page.waitForResponse(
    (r) =>
      r.url().includes("/audit/working-papers") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version" }).click();
  const response = await save;
  expect(response.status()).toBe(201);
  const row = await response.json();
  const get = await page.request.get(
    `/api/backend/engagements/${eid}/audit/records/${row.id}`,
    {
      headers: {
        Origin: "http://127.0.0.1:3006",
        "X-Tenant-ID": data.tenant_id,
      },
    },
  );
  expect(get.status()).toBe(200);
  expect((await get.json()).body.conclusion).toContain(
    "Synthetic draft conclusion",
  );
  await page.getByLabel("Search audit records").fill(row.reference);
  await page.getByRole("button", { name: row.reference, exact: true }).click();
  await page
    .getByLabel(/^conclusion/i)
    .fill("Synthetic revised conclusion persisted through the browser");
  const edited = page.waitForResponse(
    (r) =>
      r.url().includes(`/records/${row.id}`) &&
      r.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Save version" }).click();
  expect((await edited).status()).toBe(200);
  await expect(
    page.getByRole("button", { name: "Save version" }),
  ).toBeEnabled();
  for (const operation of ["archive", "restore"]) {
    await page
      .getByLabel("Decision comments")
      .fill(`Synthetic browser ${operation} with professional reason`);
    const lifecycle = page.waitForResponse(
      (r) =>
        r.url().includes(`/records/${row.id}/actions`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: new RegExp(`^${operation}$`, "i") })
      .click();
    const changed = await lifecycle;
    expect(changed.status(), await changed.text()).toBe(200);
    await expect(
      page.getByRole("button", {
        name: new RegExp(
          `^${operation === "archive" ? "restore" : "archive"}$`,
          "i",
        ),
      }),
    ).toBeVisible();
  }
  const history = await page.request.get(
    `/api/backend/engagements/${eid}/audit/records/${row.id}/history`,
    { headers: { "X-Tenant-ID": data.tenant_id } },
  );
  expect((await history.json()).versions).toHaveLength(4);
  await page.screenshot({
    path: "../docs/qa-crud/screenshots/working-paper-created.png",
    fullPage: true,
  });
});

test("two tabs invalidate cached grids and reject an older open edit", async ({
  page,
  context,
}) => {
  await login(page);
  const code = `CRUD-RACE-${Date.now()}`;
  const headers = {
    Origin: "http://127.0.0.1:3006",
    "X-Tenant-ID": data.tenant_id,
  };
  const created = await page.request.post("/api/backend/clients", {
    headers,
    data: { code, name: "SYNTHETIC concurrent draft" },
  });
  expect(created.status()).toBe(201);
  const row = await created.json();
  const second = await context.newPage();
  for (const tab of [page, second]) {
    await tab.goto("/clients");
    await tab.getByLabel("Search clients").fill(code);
    await tab
      .locator(".ag-cell strong")
      .filter({ hasText: "SYNTHETIC concurrent draft" })
      .click();
    await tab.getByRole("button", { name: "Edit client", exact: true }).click();
  }
  const firstForm = page.getByRole("dialog", {
    name: "Edit client",
    exact: true,
  });
  await firstForm
    .getByLabel("name", { exact: true })
    .fill("SYNTHETIC first editor persisted");
  const saved = page.waitForResponse(
    (r) => r.url().includes(row.id) && r.request().method() === "PATCH",
  );
  await firstForm.getByRole("button", { name: "Save client" }).click();
  expect((await saved).status()).toBe(200);
  const secondForm = second.getByRole("dialog", {
    name: "Edit client",
    exact: true,
  });
  await secondForm
    .getByLabel("name", { exact: true })
    .fill("SYNTHETIC stale editor overwrite");
  const conflict = second.waitForResponse(
    (r) => r.url().includes(row.id) && r.request().method() === "PATCH",
  );
  await secondForm.getByRole("button", { name: "Save client" }).click();
  expect((await conflict).status()).toBe(409);
  await expect(secondForm.getByRole("alert")).toContainText("version conflict");
  await second.screenshot({
    path: "../docs/qa-crud/screenshots/concurrent-edit-conflict.png",
    fullPage: true,
  });
  await secondForm.getByRole("button", { name: "Close dialog" }).click();
  await expect(
    second
      .locator(".ag-cell strong")
      .filter({ hasText: "SYNTHETIC first editor persisted" }),
  ).toBeVisible();
  const persisted = await page.request.get(`/api/backend/clients/${row.id}`, {
    headers,
  });
  expect((await persisted.json()).name).toBe(
    "SYNTHETIC first editor persisted",
  );
  await second.close();
});
