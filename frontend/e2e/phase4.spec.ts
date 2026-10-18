import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
const f = JSON.parse(
  readFileSync("../docs/phase-4/browser-fixture.json", "utf8"),
);
const shots = path.resolve("../docs/phase-4/screenshots");
mkdirSync(shots, { recursive: true });
async function login(page: Page, email = "admin@example.com") {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(
      email === "admin@example.com"
        ? "test-strong-password-123"
        : "synthetic-password-123",
    );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await expect(page.getByLabel("User menu")).toBeVisible();
}
test("all Phase 4 workspaces render with real records and screenshots", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const routes = [
    ...[
      "acceptance",
      "independence",
      "planning",
      "materiality",
      "risks",
      "programs",
      "procedures",
      "testing",
      "working-papers",
      "evidence",
      "findings",
      "review-notes",
      "completion",
      "requests",
      "ai",
      "team",
    ].map((area) => ({
      route: `/engagements/${f.engagement_id}/${area}`,
      name: area,
    })),
    ...[
      "users",
      "roles",
      "permissions",
      "teams",
      "activity",
      "firm-settings",
    ].map((area) => ({ route: `/admin/${area}`, name: "admin-" + area })),
  ];
  const inventory = [];
  for (const r of routes) {
    await page.goto(r.route);
    await expect(page.locator(".page-header h1")).toBeVisible();
    await expect(page.locator(".loading")).toHaveCount(0);
    await page.waitForTimeout(350);
    const first = page.locator(".ag-cell .text-button").first();
    if (await first.isVisible()) await first.click();
    await page.screenshot({
      path: path.join(shots, r.name + ".png"),
      fullPage: true,
    });
    inventory.push({ ...r, screenshot: r.name + ".png" });
  }
  await page.goto(`/engagements/${f.engagement_id}/working-papers`);
  await expect(
    page.getByRole("heading", { name: "Working Paper Editor" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(shots, "working-papers-mobile.png"),
    fullPage: true,
  });
  await page.goto("/join");
  await expect(
    page.getByRole("heading", { name: "Accept invitation" }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(shots, "invitation-activation.png"),
    fullPage: true,
  });
  inventory.push({
    route: "/join",
    name: "invitation-activation",
    screenshot: "invitation-activation.png",
  });
  writeFileSync(
    "../docs/phase-4/screenshot-inventory.json",
    JSON.stringify(inventory, null, 2),
  );
  expect(errors).toEqual([]);
});
test("auditor prepares and submits a working paper, manager and partner review", async ({
  page,
}) => {
  await login(page, "auditor@phase4.example");
  await page.goto(`/engagements/${f.engagement_id}/working-papers`);
  await page.getByRole("button", { name: "New record" }).click();
  const ref = "BROWSER-" + Date.now();
  await page.getByLabel("Reference", { exact: true }).fill(ref);
  await page
    .getByLabel("Title", { exact: true })
    .fill("SYNTHETIC browser working paper");
  await page.getByLabel(/^folder/).fill("Revenue");
  await page
    .getByLabel("Section 1 text")
    .fill(
      "Synthetic browser test: source evidence requires professional inspection",
    );
  await page
    .getByLabel(/^conclusion/)
    .fill("Draft human conclusion for independent review");
  await page.getByRole("button", { name: "Save version" }).click();
  await expect(
    page.getByRole("button", { name: ref, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: ref, exact: true }).click();
  await page
    .getByLabel("Decision comments")
    .fill("Prepared by the synthetic auditor");
  await page.getByRole("button", { name: "submit", exact: true }).click();
  await expect(page.locator(".audit-review-actions")).toContainText(
    "REVIEW REQUIRED",
  );
  // Self-approval remains denied by the backend, including crafted requests.
  const self = await page.evaluate(
    async (tenant) => {
      const r = await fetch(
        "/api/backend/engagements/" + tenant.e + "/audit/working-papers",
        { headers: { "X-Tenant-ID": tenant.t } },
      );
      return r.status;
    },
    { e: f.engagement_id, t: f.tenant_id },
  );
  expect(self).toBe(200);
  await page.context().clearCookies();
  await login(page, "manager@phase4.example");
  await page.goto(`/engagements/${f.engagement_id}/working-papers`);
  await page.getByRole("button", { name: ref, exact: true }).click();
  await page
    .getByLabel("Decision comments")
    .fill("Synthetic manager review: work inspected for workflow verification");
  await page.getByRole("button", { name: "approve", exact: true }).click();
  await expect(
    page
      .getByText("Request accepted by the backend.", { exact: false })
      .first(),
  ).toBeVisible();
  await page.context().clearCookies();
  await login(page, "partner@phase4.example");
  await page.goto(`/engagements/${f.engagement_id}/working-papers`);
  await page.getByRole("button", { name: ref, exact: true }).click();
  await page
    .getByLabel("Decision comments")
    .fill("Synthetic independent partner review decision");
  await page.getByRole("button", { name: "approve", exact: true }).click();
  await expect(page.locator(".audit-review-actions")).toContainText("APPROVED");
  await page.getByRole("button", { name: "History" }).click();
  await expect(
    page.getByText("Human decisions", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(shots, "working-paper-reviewed-history.png"),
    fullPage: true,
  });
});
test("client responds to assigned request and cannot open internal risks", async ({
  page,
}) => {
  const loginResponse = await page.request.post(
    "http://127.0.0.1:58002/api/v1/auth/login",
    {
      form: {
        username: "admin@example.com",
        password: "test-strong-password-123",
      },
    },
  );
  const tokens = await loginResponse.json();
  const headers = {
    Authorization: "Bearer " + tokens.access_token,
    "X-Tenant-ID": f.tenant_id,
  };
  const reference = "PBC-BROWSER-" + Date.now();
  const made = await page.request.post(
    `http://127.0.0.1:58002/api/v1/engagements/${f.engagement_id}/audit/requests`,
    {
      headers,
      data: {
        reference,
        title: "SYNTHETIC browser invoice request",
        body: {
          client_id: f.client_id,
          question: "Upload the selected synthetic invoice for auditor review",
        },
      },
    },
  );
  expect(made.status()).toBe(201);
  const request = await made.json();
  const sent = await page.request.post(
    `http://127.0.0.1:58002/api/v1/engagements/${f.engagement_id}/audit/records/${request.id}/actions`,
    {
      headers,
      data: {
        version: request.version,
        action: "SENT",
        comments: "Synthetic browser collaboration scenario",
      },
    },
  );
  expect(sent.status()).toBe(200);
  await login(page, "client@phase4.example");
  await page.goto("/client-portal");
  await expect(
    page.getByRole("heading", { name: "Document Request Portal" }),
  ).toBeVisible();
  await page.getByRole("button", { name: reference, exact: true }).click();
  await page.getByLabel("Upload requested evidence").setInputFiles({
    name: "SYNTHETIC-client-invoice.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("invoice,amount\nSYNTHETIC,12500\n"),
  });
  await expect(
    page
      .getByText("Request accepted by the backend.", { exact: false })
      .first(),
  ).toBeVisible();
  await page
    .getByLabel("Response to the auditor")
    .fill(
      "Synthetic invoice attached; auditor must review original documentation",
    );
  await page.getByRole("button", { name: "Send response" }).click();
  await expect(page.locator(".audit-inspector")).toContainText("RESPONDED");
  await page.screenshot({
    path: path.join(shots, "client-portal.png"),
    fullPage: true,
  });
  const denied = await page.evaluate(
    async ({ e, t }) => {
      const r = await fetch(`/api/backend/engagements/${e}/audit/risks`, {
        headers: { "X-Tenant-ID": t },
      });
      return r.status;
    },
    { e: f.engagement_id, t: f.tenant_id },
  );
  expect(denied).toBe(403);
  await page.goto(`/engagements/${f.engagement_id}/risks`);
  await expect(
    page.getByRole("heading", { name: "Access restricted" }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(shots, "client-internal-access-denied.png"),
    fullPage: true,
  });
});
