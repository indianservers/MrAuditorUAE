import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const credentials = JSON.parse(
  readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
);
const data = JSON.parse(
  readFileSync("../docs/qa-campaign/dataset.json", "utf8"),
);
test("real queued lead schedule, preserved results, review guard and connector truthfulness", async ({
  page,
}) => {
  await expect
    .poll(async () => {
      try {
        return (
          await page.request.get("http://127.0.0.1:58009/health/ready")
        ).status();
      } catch {
        return 0;
      }
    })
    .toBe(200);
  await page.goto("/login");
  await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  await page
    .getByLabel("Password", { exact: true })
    .fill(credentials.QA_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  const eid = data.companies[0].engagements[0].id;
  await page.goto(`/intelligence/${eid}/lead`);
  await expect(
    page.getByRole("heading", { name: "Lead schedules", exact: true }),
  ).toBeVisible();
  const snapshots = page.getByLabel("Committed snapshot");
  await expect(snapshots.locator("option")).not.toHaveCount(1);
  await snapshots.selectOption({ index: 1 });
  const accounts = page.getByLabel("Explicit account selection (first 1,000)");
  await expect(accounts.locator("option").first()).toBeAttached();
  await accounts.selectOption({ index: 0 });
  await page
    .getByLabel("Auditor rationale / review comments")
    .fill(
      "SYNTHETIC browser review of retained committed cash source balances",
    );
  const queued = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/intelligence/engagements/${eid}/jobs`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue lead schedules", exact: true })
    .click();
  const response = await queued;
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(
      async () => {
        const result = await page.request.get(
          `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
          { headers: { "X-Tenant-ID": data.tenant_id } },
        );
        return (await result.json()).status;
      },
      { timeout: 90000 },
    )
    .toBe("completed");
  const result = await (
    await page.request.get(
      `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
      { headers: { "X-Tenant-ID": data.tenant_id } },
    )
  ).json();
  await page.goto(`/intelligence/${eid}/lead?event=${result.result_id}`);
  await expect(
    page.getByRole("columnheader", { name: "account_code", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("System-generated source calculations", { exact: false }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Create connected working-paper draft" }),
  ).toBeDisabled();
  await page
    .getByLabel("Auditor rationale / review comments")
    .fill("SYNTHETIC self-review must be rejected by the backend controls");
  const denied = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.result_id}/review`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Record independent approval", exact: true })
    .click();
  expect((await denied).status()).toBe(403);
  await expect(page.locator(".error[role=alert]")).toBeVisible();
  await page
    .getByRole("columnheader", { name: "account_code", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../docs/phase2/evidence/lead-workbench.png",
    fullPage: true,
  });
  await page.goto("/integrations");
  for (const name of [
    "Busy Accounting",
    "Marg ERP",
    "SAP Business One",
    "Oracle NetSuite",
    "Microsoft Dynamics",
  ]) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(
    page
      .getByText(
        "Live API adapter is not implemented. A normalized export can use file import.",
      )
      .first(),
  ).toBeVisible();
});
