import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Known synthetic bank evidence; no bank ownership/authenticity conclusion. */
export async function runUAEBankBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  snapshot: string,
  screenshots: string,
) {
  const { headers, prefix, post, upload, evidence, completed, prepare } =
    makeWorkflowHarness(page, eid, tenant);
  const reviewerErrors: string[] = [];
  reviewer.on("pageerror", (error) => reviewerErrors.push(error.message));
  const account = "SYNTHETIC-UAE-BANK";
  const accounts = await page.request.get(
    `/api/backend/${prefix}/accounts?snapshot_id=${snapshot}`,
    { headers },
  );
  expect(accounts.status()).toBe(200);
  const cash = (await accounts.json()).items.find(
    (row: { code: string }) => row.code === "100",
  );
  expect(cash).toBeTruthy();
  const books = await prepare(
    {
      snapshot_id: snapshot,
      account_ids: [cash.id],
      bank_account: account,
      currency: "AED",
      label: "SYNTHETIC UAE committed bank books",
      from_date: "2026-06-01",
      as_of: "2026-06-30",
    },
    "workflow-ledger",
  );
  expect(books.body.source_snapshot_id).toBe(snapshot);
  expect(books.body.rows).toHaveLength(1);
  expect(books.body.rows[0].reference).toBe("SALE");
  expect(books.body.rows[0].source_record_id).toBeTruthy();
  const original = readFileSync(
    "../docs/country-workflows/sample-inputs/SYNTHETIC-UAE-bank-browser.xml",
  );
  const file = await evidence("SYNTHETIC-UAE-bank-browser.xml", original);
  const statement = await prepare({
    evidence_version_id: file.version.id,
    file_format: "camt053",
    table_type: "transactions",
    label: "SYNTHETIC UAE native bank statement",
    expected_rows: 1,
    control_totals: { AED: "100.20" },
  });
  expect(statement.body.native_controls_verified).toBe(true);
  expect(statement.body.native_metadata).toMatchObject({
    account,
    opening: "0.00",
    closing: "100.20",
    bank_identity_verified: false,
  });
  const sourceIds: Record<string, string> = {};
  for (const [role, source] of [
    ["books", books],
    ["statement", statement],
  ] as const) {
    const approved = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independent original bank and committed GL scope review",
      },
    );
    sourceIds[role] = approved.id;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("bank-brs");
  for (const [role, id] of Object.entries(sourceIds))
    await page
      .getByRole("combobox", { name: `${role} source`, exact: true })
      .selectOption(id);
  const title =
    "SYNTHETIC UAE native statement and committed GL reconciliation";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-06-30"],
    ["Bank account identifier", account],
    ["Account currency", "AED"],
    ["book opening", "0"],
    ["book closing", "100.20"],
    ["statement opening", "0"],
    ["statement closing", "100.21"],
    [
      "Scope and source rationale",
      "SYNTHETIC independent native statement and posted cash population; no bank authentication",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);

  async function submit() {
    const wait = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await wait;
    expect(response.status(), await response.text()).toBe(202);
    return (await response.json()).id as string;
  }
  const invalid = await submit();
  let rejected: {
    status?: string;
    result_id?: string | null;
    error_details?: { message: string };
  } = {};
  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          `/api/backend/${prefix}/jobs/${invalid}`,
          { headers },
        );
        expect(response.status()).toBe(200);
        rejected = await response.json();
        return rejected.status;
      },
      { timeout: 30000, intervals: [250, 500, 1000] },
    )
    .toBe("failed");
  expect(rejected.result_id).toBeNull();
  expect(rejected.error_details?.message).toContain(
    "original native bank statement",
  );
  await page.getByLabel("statement closing", { exact: true }).fill("100.20");
  const result = await completed(await submit());
  expect(result.body.blocked).toBe(false);
  expect(result.body.matches).toHaveLength(1);
  expect(result.body.rows).toHaveLength(0);
  for (const value of Object.values(
    result.body.control_comparison as Record<string, string>,
  ))
    expect(value).toMatch(/^-?0(?:\.0+)?$/);
  expect(result.body.bank_account_evidence).toMatchObject({
    status: "NOT_LINKED_ARITHMETIC_SCOPE_ONLY",
  });
  await page.goto(`/intelligence/${eid}/country-workflow?event=${result.id}`);
  const panel = page
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await expect(
    panel
      .getByText("unexplained bridge residual", { exact: true })
      .locator("..")
      .locator("dd"),
  ).toHaveText(/^-?0(?:\.0+)?$/);
  const proposals = page.getByRole("region", {
    name: "Bank matched proposals",
    exact: true,
  });
  await proposals
    .getByRole("button", { name: "Inspect proposal 1", exact: true })
    .click();
  const sourceDetails = proposals.getByRole("region", {
    name: "Matched proposal transaction details",
    exact: true,
  });
  await expect(
    sourceDetails.getByRole("cell", { name: "SALE", exact: true }),
  ).toHaveCount(2);
  await expect(
    sourceDetails.getByRole("cell", { name: "AED", exact: true }),
  ).toHaveCount(2);
  await expect(
    sourceDetails.getByRole("cell", { name: "BOOKING_DATE", exact: true }),
  ).toBeVisible();
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "SYNTHETIC independent original transaction and zero-residual assessment; not bank authentication",
    );
  const review = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const response = await review;
  expect(response.status(), await response.text()).toBe(201);
  const approved: WorkflowEvent = await response.json();
  expect(approved.body.review_status).toBe("REVIEWED");
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(approved.id);
  const downloadEvent = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const download = await downloadEvent;
  const path = await download.path();
  expect(path).not.toBeNull();
  const workbook = readFileSync(path!);
  expect(workbook.subarray(0, 2).toString()).toBe("PK");
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      [
        "import io,sys,json",
        "from decimal import Decimal",
        "from openpyxl import load_workbook",
        "rows=list(load_workbook(io.BytesIO(sys.stdin.buffer.read()))['Matched proposals'].values)",
        "assert len(rows)==2",
        "assert Decimal(str(rows[1][rows[0].index('variance')]))==0",
        "assert len(json.loads(rows[1][rows[0].index('left_ids')]))==1",
        "assert json.loads(rows[1][rows[0].index('right_ids')])==['SYNTHETIC-UAE-STMT:entry:1']",
      ].join("\n"),
    ],
    { input: workbook, timeout: 15000 },
  );
  await reviewer
    .getByRole("button", { name: "Inspect proposal 1", exact: true })
    .click();
  await expect(
    reviewer.getByRole("region", {
      name: "Matched proposal transaction details",
    }),
  ).toBeVisible();
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/AE-native-bank-reviewed-proposal.png`,
    });
  const approvedBody = structuredClone(approved.body);
  await upload(
    file.record,
    "SYNTHETIC-UAE-bank-browser-replaced.xml",
    Buffer.from(
      original
        .toString()
        .replace("SYNTHETIC-UAE-BROWSER", "SYNTHETIC-UAE-BROWSER-V2"),
    ),
  );
  const changed = await page.request.get(
    `/api/backend/${prefix}/events/${approved.id}`,
    { headers },
  );
  expect(changed.status()).toBe(200);
  const historical = await changed.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(approvedBody);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${approved.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/AE-native-bank-replacement-stale.png`,
    });
  expect(reviewerErrors).toEqual([]);
}
