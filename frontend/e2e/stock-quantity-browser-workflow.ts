import { expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

export async function runStockQuantityBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  country: string,
  currency: string,
  screenshots: string,
) {
  const { headers, prefix, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const sources: Record<string, WorkflowEvent> = {};
  for (const role of ["books", "count"] as const) {
    const positions =
      role === "books"
        ? [
            ["GOOD", "10"],
            ["NEGATIVE", "5"],
            ["MISSING", "8"],
          ]
        : [
            ["GOOD", "4"],
            ["NEGATIVE", "-5"],
          ];
    const content =
      [
        "id,site,sku,lot,uom,currency,quantity,unit_cost,unit_nrv,ownership,condition,count_date",
        ...positions.map(
          ([sku, quantity]) =>
            `${role}-${sku},WH,${sku},L,PCS,${currency},${quantity},10,12,owned,good,2026-06-30`,
        ),
      ].join("\n") + "\n";
    const file = await evidence(
      `SYNTHETIC-${country}-stock-${role}.csv`,
      Buffer.from(content),
    );
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: "stock",
      label: `SYNTHETIC ${country} stock coverage ${role}`,
      expected_rows: positions.length,
      control_totals: {},
      inventory_quantity_controls: positions.map(([sku, quantity]) => ({
        site: "WH",
        sku,
        lot: "L",
        uom: "PCS",
        currency,
        expected_rows: 1,
        positive_quantity: quantity.startsWith("-") ? "0" : quantity,
        negative_quantity: quantity.startsWith("-") ? quantity : "0",
      })),
    });
    sources[role] = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independent declared source count and directional quantity control assessment",
      },
    );
  }
  const title = `SYNTHETIC ${country} declared count coverage`;
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("stock-audit");
  for (const [role, source] of Object.entries(sources))
    await page
      .getByLabel(`${role} source`, { exact: true })
      .selectOption(source.id);
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-06-30"],
    [
      "Scope and source rationale",
      "SYNTHETIC declared selected counts only; no physical attendance or quantity aggregation",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const queued = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const response = await queued;
  expect(response.status(), await response.text()).toBe(202);
  let result = await completed((await response.json()).id);
  const originalRows = result.body.rows;
  expect(result.body.quantity_coverage_contract).toBe(
    "stock-declared-count-coverage/1",
  );
  expect(originalRows.find((r) => r.sku === "GOOD")).toMatchObject({
    book_quantity: "10",
    count_quantity: "4",
    count_supported_quantity: "4",
    quantity_coverage_percent: "40.0",
    state: "VARIANCE",
  });
  expect(originalRows.find((r) => r.sku === "NEGATIVE")).toMatchObject({
    quantity_coverage_percent: null,
    state: "NEGATIVE_QUANTITY",
  });
  expect(originalRows.find((r) => r.sku === "MISSING")).toMatchObject({
    quantity_coverage_percent: null,
    state: "BOOKS_ONLY",
  });
  expect(result.body.coverage).toMatchObject({
    book_value: "230",
    count_supported_value: "40",
  });
  const rejected = await reviewer.request.post(
    `/api/backend/${prefix}/events/${result.id}/review`,
    {
      headers,
      data: {
        expected_version: result.version,
        action: "approve",
        comments:
          "SYNTHETIC unresolved exceptions must block independent approval",
      },
    },
  );
  expect(rejected.status()).toBe(409);
  // Dispositions acknowledge unresolved evidence; they must not change quantities.
  for (const row of originalRows)
    result = await post(page.request, `${prefix}/events/${result.id}/review`, {
      expected_version: result.version,
      action: "accept",
      item_id: row.id,
      comments:
        "SYNTHETIC partial count, negative quantity or missing count documented; no full-count or physical assertion",
    });
  const approved: WorkflowEvent = await post(
    reviewer.request,
    `${prefix}/events/${result.id}/review`,
    {
      expected_version: result.version,
      action: "approve",
      comments:
        "SYNTHETIC independent assessment of retained declared quantities and documented evidence gaps",
    },
  );
  expect(
    approved.body.rows.find((r) => r.sku === "GOOD")?.quantity_coverage_percent,
  ).toBe("40.0");
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${approved.id}`,
  );
  await expect(reviewer.getByText("REVIEWED", { exact: true })).toBeVisible();
  await expect(
    reviewer.getByText(/Quantity coverage: Aligned declared/),
  ).toBeVisible();
  const good = reviewer
    .getByRole("row")
    .filter({ has: reviewer.getByRole("cell", { name: "GOOD", exact: true }) });
  await expect(
    good.getByRole("cell", { name: "40.0", exact: true }),
  ).toBeVisible();
  const panel = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await panel.screenshot({
    path: `${screenshots}/${country}-stock-quantity-reviewed.png`,
  });
  const downloading = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const downloaded = await (await downloading).path();
  expect(downloaded).not.toBeNull();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      [
        "import io,sys",
        "from openpyxl import load_workbook",
        "w=load_workbook(io.BytesIO(sys.stdin.buffer.read()))",
        "rows=list(w['Rows'].values); assert len(rows)==4",
        "records=[dict(zip(rows[0],r)) for r in rows[1:]]",
        "assert next(r for r in records if r['sku']=='GOOD')['quantity_coverage_percent']=='40.0'",
        "assert next(r for r in records if r['sku']=='NEGATIVE')['quantity_coverage_percent'] is None",
      ].join("\n"),
    ],
    { input: readFileSync(downloaded!), timeout: 15000 },
  );
  await post(reviewer.request, `${prefix}/events/${sources.count.id}/review`, {
    expected_version: sources.count.version,
    action: "reject",
    comments:
      "SYNTHETIC withdrawal of uploaded declared count evidence requires reassessment",
  });
  const historicalResponse = await reviewer.request.get(
    `/api/backend/${prefix}/events/${approved.id}`,
    { headers },
  );
  expect(historicalResponse.status()).toBe(200);
  const historical = await historicalResponse.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(approved.body);
  expect(historical.version).toBe(approved.version);
  await reviewer.goto(`/intelligence/${eid}/lead?event=${approved.id}`);
  await expect(
    reviewer.getByRole("button", {
      name: "Create connected working-paper draft",
      exact: true,
    }),
  ).toBeDisabled();
  await reviewer.screenshot({
    path: `${screenshots}/${country}-stock-quantity-stale-paper-disabled.png`,
    fullPage: true,
  });
}
