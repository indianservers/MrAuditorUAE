import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Reuses the independently reviewed processor payout; actual scanner, queue and worker. */
export async function runMerchantReserveBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  country: "AE" | "IN",
  screenshots: string,
  settlementId: string,
) {
  const { prefix, headers, evidence, prepare, post, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const currency = country === "AE" ? "AED" : "INR";
  const common = { merchant: "SHOP", processor: "PSP", currency };
  const sources: Record<string, string> = { settlements: settlementId };
  let ledger!: WorkflowEvent;
  for (const [role, table, rows, controls] of [
    [
      "movements",
      "merchant-reserve-movements",
      [
        {
          id: "H1",
          ...common,
          settlement_id: "PAYOUT",
          date: "2026-06-30",
          sequence: 1,
          kind: "HELD",
          amount: "50",
          reference: "HOLD-1",
          evidence_reference: "SYNTHETIC-STMT",
          assessment: "Synthetic independently assessed hold chronology",
        },
        {
          id: "R1",
          ...common,
          settlement_id: "PAYOUT",
          date: "2026-06-30",
          sequence: 2,
          kind: "RELEASED",
          amount: "5",
          reference: "RELEASE-1",
          evidence_reference: "SYNTHETIC-STMT",
          assessment: "Synthetic independently assessed release chronology",
        },
      ],
      {
        control_totals: {},
        merchant_reserve_controls: {
          [currency]: { held: "50", released: "5" },
        },
      },
    ],
    [
      "balances",
      "merchant-reserve-balances",
      [
        {
          id: "POSITION",
          ...common,
          period_start: "2026-06-01",
          period_end: "2026-06-30",
          opening_balance: "100",
          closing_balance: "145",
          ledger_account: "RESERVE-AR",
          account_assessment:
            "Synthetic independently assessed reserve receivable mapping",
          evidence_reference: "SYNTHETIC-STMT",
        },
      ],
      {
        control_totals: {},
        merchant_reserve_controls: {
          [currency]: { opening_balance: "100", closing_balance: "145" },
        },
      },
    ],
    [
      "ledger",
      "balance-controls",
      [
        {
          id: "OPEN",
          account: "RESERVE-AR",
          side: "receivable",
          currency,
          as_of: "2026-05-31",
          amount: "100",
        },
        {
          id: "CLOSE",
          account: "RESERVE-AR",
          side: "receivable",
          currency,
          as_of: "2026-06-30",
          amount: "145",
        },
      ],
      { control_totals: { [currency]: "245" } },
    ],
  ] as const) {
    const fields = Object.keys(rows[0]);
    const csv =
      fields.join(",") +
      "\n" +
      rows
        .map((row) =>
          fields
            .map(
              (field) =>
                '"' +
                String((row as Record<string, unknown>)[field]).replaceAll(
                  '"',
                  '""',
                ) +
                '"',
            )
            .join(","),
        )
        .join("\n") +
      "\n";
    const file = await evidence(
      `SYNTHETIC-${country}-reserve-${role}.csv`,
      Buffer.from(csv),
    );
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: table,
      label: `SYNTHETIC ${country} reserve ${role}`,
      expected_rows: rows.length,
      ...controls,
    });
    const approved = (await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "Synthetic independently assessed reserve source and controls",
      },
    )) as WorkflowEvent;
    sources[role] = approved.id;
    if (role === "ledger") ledger = approved;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("merchant-reserve-rollforward");
  for (const [role, id] of Object.entries(sources))
    await page
      .getByRole("combobox", { name: `${role} source`, exact: true })
      .selectOption(id);
  const title = `SYNTHETIC ${country} processor reserve continuity`;
  for (const [label, value] of [
    ["Schedule title", title],
    [
      "Scope and source rationale",
      "Synthetic independent opening and closing reserve and dated gross movement assessment",
    ],
    ["Reconciliation date", "2026-06-30"],
    ["Reporting period start", "2026-06-01"],
    ["Reserve comparison currency", currency],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const submitted = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/${prefix}/jobs`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const response = await submitted;
  expect(response.status(), await response.text()).toBe(202);
  const result = await completed((await response.json()).id);
  expect(result.body.blocked).toBe(false);
  expect(result.body.rows[0]).toMatchObject({
    kind: "RESERVE_POSITION",
    computed_closing: "145",
    closing_difference: "0",
  });
  expect(result.body.payment_state).toBe("NOT_ASSESSED_BY_RESERVE_ROLLFORWARD");
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Synthetic independent reserve position and opening closing ledger evidence assessment",
    );
  const approvedResponse = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const approvedHTTP = await approvedResponse;
  expect(approvedHTTP.status(), await approvedHTTP.text()).toBe(201);
  const reviewed = (await approvedHTTP.json()) as WorkflowEvent;
  const original = structuredClone(reviewed.body);
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  const downloadWait = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const download = await downloadWait;
  const path = await download.path();
  expect(path).toBeTruthy();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,sys;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));r=list(w['Reserve movements'].values);assert len(r)==3;assert r[-1][r[0].index('balance_after')]=='145';assert len(list(w['Reserve balance links'].values))==2",
    ],
    { input: readFileSync(path!), timeout: 15000 },
  );
  await reviewer.setViewportSize({ width: 1800, height: 1800 });
  const card = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await card.scrollIntoViewIfNeeded();
  await expect(card.getByText("CURRENT", { exact: true })).toBeVisible();
  await expect(
    card.getByRole("columnheader", { name: "computed closing", exact: true }),
  ).toBeInViewport();
  const notice = reviewer.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  if (await notice.count()) await notice.last().click();
  await card.screenshot({
    path: `${screenshots}/${country}-reserve-reviewed-ledger.png`,
  });
  await post(reviewer.request, `${prefix}/events/${ledger.id}/review`, {
    expected_version: ledger.version,
    action: "reject",
    comments: "Synthetic withdrawal of independent reserve ledger review",
  });
  const refreshed = await reviewer.request.get(
    `/api/backend/${prefix}/events/${reviewed.id}`,
    { headers },
  );
  expect(refreshed.status()).toBe(200);
  const stale = (await refreshed.json()) as WorkflowEvent;
  expect(stale.freshness).toBe("STALE");
  expect(stale.body).toEqual(original);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await card.scrollIntoViewIfNeeded();
  await expect(card.getByText("STALE", { exact: true })).toBeVisible();
  await card.screenshot({
    path: `${screenshots}/${country}-reserve-ledger-withdrawn-stale.png`,
  });
}
