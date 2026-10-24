import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
);
const data = JSON.parse(
  readFileSync("../docs/qa-campaign/dataset.json", "utf8"),
);
test("anonymous request form isolates scope, accepts response and enforces revocation", async ({
  page,
  browser,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  await page
    .getByLabel("Password", { exact: true })
    .fill(credentials.QA_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  const headers = {
    "X-Tenant-ID": data.tenant_id,
    Origin: "http://127.0.0.1:3006",
  };
  const engagement = await page.request.post("/api/backend/engagements", {
    headers,
    data: {
      entity_id: data.companies[0].entity_id,
      period_id: data.companies[0].period_id,
      name: `SYNTHETIC collaboration browser ${Date.now()}`,
      engagement_type: "External Audit",
    },
  });
  expect(engagement.status()).toBe(201);
  const eid = (await engagement.json()).id;
  const base = `/api/backend/engagements/${eid}/audit`;
  const policy = await page.request.post(base + "/policy", {
    headers,
    data: {
      review_chain: ["Audit Manager", "Audit Partner"],
      methodology: { allow_account_free_portal: true },
    },
  });
  expect(policy.status()).toBe(200);
  const request = await page.request.post(base + "/requests", {
    headers,
    data: {
      reference: "SYNTHETIC-GUEST",
      title: "SYNTHETIC limited request",
      body: {
        client_id: data.companies[0].client_id,
        question: "SYNTHETIC provide the requested bank support only",
      },
    },
  });
  expect(request.status()).toBe(201);
  const prefix = `/api/backend/collaboration/engagements/${eid}`;
  const issued = await page.request.post(prefix + "/links", {
    headers,
    data: { request_id: (await request.json()).id, retain_until: "2032-01-01" },
  });
  expect(issued.status()).toBe(201);
  const link = await issued.json();
  const anonymous = await browser.newContext();
  const guest = await anonymous.newPage();
  const internalRequests: string[] = [];
  guest.on("request", (r) => {
    if (r.url().includes("/api/backend/")) internalRequests.push(r.url());
  });
  await guest.goto(link.share_path);
  await expect(
    guest.getByText("SYNTHETIC provide the requested bank support only"),
  ).toBeVisible();
  await expect(guest.getByRole("navigation")).toHaveCount(0);
  await guest
    .getByLabel("Your name (claimed identity, not verified)")
    .fill("SYNTHETIC guest");
  await guest
    .getByLabel("Response", { exact: true })
    .fill("SYNTHETIC client response for auditor assessment");
  await guest
    .getByRole("button", { name: "Submit for auditor review", exact: true })
    .click();
  await expect(guest.getByRole("status")).toContainText("Received for review");
  expect(internalRequests).toEqual([]);
  await guest.screenshot({
    path: "../docs/phase3/evidence/client-collaboration.png",
    fullPage: true,
  });
  const revoked = await page.request.post(prefix + `/links/${link.id}/revoke`, {
    headers,
  });
  expect(revoked.status()).toBe(200);
  await guest.reload();
  await expect(
    guest.getByText(
      "This client link is invalid, expired, revoked or its request has changed.",
    ),
  ).toBeVisible();
  await anonymous.close();
});
