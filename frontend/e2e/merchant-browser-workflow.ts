import { createHash } from "node:crypto";
import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Synthetic component values are evidence inputs, not country tax rates. */
export async function runMerchantBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  country: "AE" | "IN",
  screenshots: string,
) {
  const reviewerErrors: string[] = [];
  reviewer.on("pageerror", (error) => reviewerErrors.push(error.message));
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const root =
    "../docs/country-workflows/sample-inputs/SYNTHETIC-merchant-settlements";
  const manifest = JSON.parse(readFileSync(`${root}/controls.json`, "utf8"))
    .countries[country] as {
    currency: string;
    files: Record<
      string,
      {
        file: string;
        sha256: string;
        table_type: string;
        row_count: number;
        control_total: string;
      }
    >;
    processor_component_controls: Record<string, string>;
  };
  const sourceIds: Record<string, string> = {};
  let processorSource: WorkflowEvent | undefined;
  for (const [role, fixture] of Object.entries(manifest.files)) {
    const bytes = readFileSync(`${root}/${fixture.file}`);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      fixture.sha256,
    );
    const file = await evidence(`SYNTHETIC-${fixture.file}`, bytes);
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: fixture.table_type,
      label: `SYNTHETIC ${country} merchant ${role}`,
      expected_rows: fixture.row_count,
      control_totals: { [manifest.currency]: fixture.control_total },
      ...(role === "processor"
        ? {
            merchant_component_controls: {
              [manifest.currency]: manifest.processor_component_controls,
            },
          }
        : {}),
    });
    const approved = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independent merchant component and original source review",
      },
    );
    sourceIds[role] = approved.id;
    if (role === "processor") processorSource = approved;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("merchant-settlement-bridge");
  for (const [role, id] of Object.entries(sourceIds))
    await page
      .getByRole("combobox", { name: `${role} source`, exact: true })
      .selectOption(id);
  const title = `SYNTHETIC ${country} merchant gross to net bank settlement`;
  for (const [label, value] of [
    ["Schedule title", title],
    [
      "Scope and source rationale",
      "SYNTHETIC independent books, processor and exact bank allocation assessment",
    ],
    ["Reconciliation date", "2026-06-30"],
    ["Reporting period start", "2026-06-01"],
    ["Bank account identifier", "ACCT"],
    ["Settlement currency", manifest.currency],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const response = await submitted;
  expect(response.status(), await response.text()).toBe(202);
  const result = await completed((await response.json()).id);
  expect(result.body.blocked).toBe(false);
  expect(result.body.rows).toHaveLength(1);
  expect(result.body.rows[0]).toMatchObject({
    sales: "1000",
    refunds: "100",
    chargebacks: "20",
    fees: "30",
    fee_tax: "2",
    withholding: "3",
    reserve_held: "50",
    reserve_released: "5",
    expected_net: "800",
    bank_allocated: "800",
    bank_difference: "0",
    state: "MATCHED",
  });
  expect(result.body.statutory_calculation_qualified).toBe(false);
  const self = await page.request.post(
    `/api/backend/${prefix}/events/${result.id}/review`,
    {
      headers,
      data: {
        expected_version: result.version,
        action: "approve",
        comments: "SYNTHETIC forbidden self approval",
      },
    },
  );
  expect(self.status()).toBe(403);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await expect(
    reviewer.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "SYNTHETIC independent gross, refund, fee and bank allocation evidence assessment",
    );
  const reviewedResponse = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const reviewedHTTP = await reviewedResponse;
  expect(reviewedHTTP.status(), await reviewedHTTP.text()).toBe(201);
  const reviewed = (await reviewedHTTP.json()) as WorkflowEvent;
  expect(reviewed.body.review_status).toBe("REVIEWED");
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  const settlementRow = reviewer
    .getByRole("row")
    .filter({ hasText: "BATCH-1" });
  await expect(settlementRow).toHaveCount(1);
  const components = reviewer.getByRole("region", {
    name: "Merchant settlement components",
    exact: true,
  });
  await components
    .getByText("Batch BATCH-1 · SHOP · PSP · " + manifest.currency, {
      exact: true,
    })
    .click();
  await expect(
    components.getByRole("cell", { name: "1000", exact: true }),
  ).toBeVisible();
  await expect(
    settlementRow.getByRole("cell", { name: "800", exact: true }),
  ).toHaveCount(3);
  await expect(
    reviewer.getByRole("button", { name: "Export XLSX", exact: true }),
  ).toBeVisible();
  const downloadWait = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const downloaded = await downloadWait;
  const path = await downloaded.path();
  expect(path).toBeTruthy();
  expect(downloaded.suggestedFilename()).toMatch(/\.xlsx$/);
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  const python =
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python";
  const workbook = readFileSync(path!);
  expect(workbook.subarray(0, 2).toString()).toBe("PK");
  execFileSync(
    python,
    [
      "-c",
      "import io,sys;from openpyxl import load_workbook;r=list(load_workbook(io.BytesIO(sys.stdin.buffer.read()))['Rows'].values);assert r[1][r[0].index('expected_net')]=='800';assert r[1][r[0].index('bank_allocated')]=='800';assert r[1][r[0].index('bank_difference')]=='0'",
    ],
    { input: workbook, timeout: 15000 },
  );
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .scrollIntoViewIfNeeded();
  const notification = reviewer.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  if (await notification.count()) await notification.last().click();
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/${country}-merchant-reviewed-settlement.png`,
    });
  expect(processorSource).toBeTruthy();
  await post(
    reviewer.request,
    `${prefix}/events/${processorSource!.id}/review`,
    {
      expected_version: processorSource!.version,
      action: "reject",
      comments: "SYNTHETIC withdrawal of retained processor assessment",
    },
  );
  const current = await reviewer.request.get(
    `/api/backend/${prefix}/events/${reviewed.id}`,
    { headers },
  );
  expect(current.status()).toBe(200);
  const stale = (await current.json()) as WorkflowEvent;
  expect(stale.freshness).toBe("STALE");
  expect(stale.body).toEqual(reviewed.body);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await reviewer.screenshot({
    path: `${screenshots}/${country}-merchant-withdrawn-source-stale.png`,
  });
  expect(reviewerErrors).toEqual([]);
}
