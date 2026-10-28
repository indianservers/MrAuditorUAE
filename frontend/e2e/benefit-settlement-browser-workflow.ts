import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

function csv(rows: Record<string, unknown>[]) {
  const fields = Object.keys(rows[0]);
  return Buffer.from(
    fields.join(",") +
      "\n" +
      rows
        .map((row) =>
          fields
            .map(
              (field) =>
                '"' +
                (typeof row[field] === "object" && row[field] !== null
                  ? JSON.stringify(row[field])
                  : String(row[field] ?? "")
                ).replaceAll('"', '""') +
                '"',
            )
            .join(","),
        )
        .join("\n") +
      "\n",
  );
}

/** Native scanners/queue/worker; synthetic setup/reviews use APIs, the new form uses UI. */
export async function runBenefitSettlementBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, headers, post, evidence, upload, prepare } =
    makeWorkflowHarness(page, eid, tenant);
  const errors: string[] = [];
  reviewer.on("pageerror", (error) => errors.push(error.message));
  async function approve(source: WorkflowEvent) {
    return post(reviewer.request, `${prefix}/events/${source.id}/review`, {
      expected_version: source.version,
      action: "approve",
      comments:
        "SYNTHETIC independent gratuity source review; no legal qualification",
    }) as Promise<WorkflowEvent>;
  }
  const ruleDocument = await evidence(
    "SYNTHETIC-gratuity-rule.txt",
    Buffer.from(
      "SYNTHETIC supplied parameters only; no operative legal source qualification",
    ),
  );
  const sourceIds: Record<string, string> = {};
  for (const [role, filename, table, total] of [
    [
      "employees",
      "SYNTHETIC-benefit-employees.csv",
      "benefit-employees",
      "3150",
    ],
    [
      "rules",
      "SYNTHETIC-benefit-rules-select-retained-document.csv",
      "benefit-rules",
      null,
    ],
  ] as const) {
    const file = await evidence(
      filename,
      readFileSync(`../docs/country-workflows/sample-inputs/${filename}`),
    );
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: table,
      label: `SYNTHETIC gratuity ${role}`,
      expected_rows: 2,
      control_totals: total === null ? {} : { AED: total },
      ...(role === "rules"
        ? { rule_document_version_id: ruleDocument.version.id }
        : {}),
    });
    sourceIds[role] = (await approve(source)).id;
  }
  const parent = await approve(
    await prepare(
      {
        workflow: "uae-benefit-review",
        source_ids: sourceIds,
        as_of: "2026-06-30",
        currency: "AED",
        title: "SYNTHETIC reviewed gratuity calculation",
        rationale:
          "Synthetic assessed full-time and part-time service spans under supplied parameters",
      },
      "country-workflow",
    ),
  );
  const support = await evidence(
    "SYNTHETIC-gratuity-settlement-context.txt",
    Buffer.from(
      "SYNTHETIC assessed employer and employee service identities with due-date references",
    ),
  );
  await page.goto(`/intelligence/${eid}/country-workflow?event=${parent.id}`);
  await page.reload();
  await page
    .getByLabel("Saved source or result", { exact: true })
    .selectOption(parent.id);
  const form = page.getByRole("region", {
    name: "Expected gratuity settlement",
    exact: true,
  });
  await expect(form).toBeVisible();
  await form
    .getByLabel("Gratuity expectation title", { exact: true })
    .fill("SYNTHETIC expected gratuity settlement");
  await form
    .getByLabel("Assessed employer registration", { exact: true })
    .fill("SYN-EMPLOYER");
  await form
    .getByLabel("Retained settlement scope and due-date evidence", {
      exact: true,
    })
    .selectOption(support.version.id);
  for (const id of ["E1", "E2"]) {
    await form
      .getByRole("checkbox", { name: `Select gratuity ${id}`, exact: true })
      .check();
    await expect(
      form.getByLabel(`Assessed due date for ${id}`, { exact: true }),
    ).toHaveValue("");
    await form
      .getByLabel(`Assessed due date for ${id}`, { exact: true })
      .fill("2026-07-14");
    await form
      .getByLabel(`Due-date evidence reference for ${id}`, { exact: true })
      .fill(`SYN-SUPPORT-${id}`);
  }
  await form
    .getByLabel("Independent selected employee count", { exact: true })
    .fill("2");
  await form
    .getByLabel("Independent expected gratuity total (AED)", { exact: true })
    .fill("3150");
  await form
    .getByLabel("Employer, employee scope and due-date assessment", {
      exact: true,
    })
    .fill(
      "Synthetic independently assessed employer and original service spans; no client/legal conclusion",
    );
  await page.setViewportSize({ width: 1440, height: 2000 });
  await form.scrollIntoViewIfNeeded();
  await form.screenshot({
    path: `${screenshots}/AE-gratuity-settlement-preparation.png`,
  });
  const preparedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/${eid}/benefit-settlement-source`) &&
      response.request().method() === "POST",
  );
  await form
    .getByRole("button", {
      name: "Prepare expected gratuity source",
      exact: true,
    })
    .click();
  const response = await preparedResponse;
  expect(response.status(), await response.text()).toBe(201);
  const derived = (await response.json()) as WorkflowEvent;
  expect(derived.body.review_status).toBe("UNVERIFIED");
  const self = await page.request.post(
    `/api/backend/${prefix}/events/${derived.id}/review`,
    {
      headers,
      data: {
        expected_version: derived.version,
        action: "approve",
        comments: "SYNTHETIC preparer cannot self-approve",
      },
    },
  );
  expect(self.status()).toBe(403);
  const expected = await approve(derived);
  const reported = expected.body.rows.map((row) => ({
    id: "R-" + row.source_result_row_id,
    registration: row.registration,
    subject: row.subject,
    period: row.period,
    component: row.component,
    currency: row.currency,
    amount: row.amount,
    due_date: row.due_date,
    benefit_scope: row.benefit_scope,
  }));
  const allocations = expected.body.rows.map((row) => ({
    id: "A-" + row.source_result_row_id,
    expected_id: row.id,
    reported_id: "R-" + row.source_result_row_id,
    transaction_id: "BANK",
    currency: "AED",
    amount: row.amount,
    evidence_reference: "SYN-EMPLOYEE-ADVICE",
    rationale:
      "Synthetic independent employee split of a pooled booked bank outflow",
  }));
  const settlementIds: Record<string, string> = { expected: expected.id };
  for (const [role, table, rows, total] of [
    ["reported", "obligations", reported, "3150"],
    [
      "bank",
      "transactions",
      [
        {
          id: "BANK",
          account: "BANK-1",
          reference: "SYN-GRATUITY-BANK",
          date: "2026-07-10",
          currency: "AED",
          amount: "-3150",
        },
      ],
      "-3150",
    ],
    ["allocations", "obligation-allocations", allocations, "3150"],
  ] as [string, string, Record<string, unknown>[], string][]) {
    const file = await evidence(`SYNTHETIC-gratuity-${role}.csv`, csv(rows));
    settlementIds[role] = (
      await approve(
        await prepare({
          evidence_version_id: file.version.id,
          table_type: table,
          label: `SYNTHETIC independent gratuity ${role}`,
          expected_rows: rows.length,
          control_totals: { AED: total },
        }),
      )
    ).id;
  }
  const title = "SYNTHETIC gratuity bank settlement review";
  const result = await prepare(
    {
      workflow: "obligation-bank-allocations",
      source_ids: settlementIds,
      as_of: "2026-07-31",
      currency: "AED",
      account: "BANK-1",
      obligation_month_start: "2026-06",
      obligation_month_end: "2026-06",
      settlement_start: "2026-07-01",
      bank_payment_sign: "debit-negative",
      title,
      rationale:
        "Synthetic reviewed employee service identity and independent pooled bank allocation",
    },
    "country-workflow",
  );
  expect(
    result.body.rows
      .filter((row) => row.kind === "obligation")
      .map((row) => row.outstanding_amount),
  ).toEqual(["0.00", "0.00"]);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer.reload();
  await reviewer
    .getByLabel("Saved source or result", { exact: true })
    .selectOption(result.id);
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill("SYNTHETIC independent service scopes and bank payout assessment");
  const reviewResponse = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const reviewHTTP = await reviewResponse;
  expect(reviewHTTP.status(), await reviewHTTP.text()).toBe(201);
  const reviewed = (await reviewHTTP.json()) as WorkflowEvent;
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  await expect(
    reviewer.getByRole("columnheader", {
      name: "benefit service start",
      exact: true,
    }),
  ).toBeVisible();
  const downloadWait = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const download = await downloadWait;
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  const path = await download.path();
  expect(path).toBeTruthy();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,json,sys;from openpyxl import load_workbook;r=list(load_workbook(io.BytesIO(sys.stdin.buffer.read()))['Rows'].values);v=dict(zip(r[0],r[1]));assert v['expected_amount']=='2100.00';assert v['bank_settled']=='2100.00';assert json.loads(v['benefit_scope'])['service_end']=='2026-06-30'",
    ],
    { input: readFileSync(path!), timeout: 15000 },
  );
  await reviewer.setViewportSize({ width: 1800, height: 1500 });
  const notification = reviewer.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  if (await notification.count()) await notification.last().click();
  let card = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({
    path: `${screenshots}/AE-gratuity-reviewed-bank-settlement.png`,
  });
  const original = structuredClone(reviewed.body);
  await upload(
    support.record,
    "SYNTHETIC-gratuity-context-v2.txt",
    Buffer.from(
      "SYNTHETIC changed scope support; no prior conclusion may remain current",
    ),
  );
  await reviewer.reload();
  await reviewer
    .getByLabel("Saved source or result", { exact: true })
    .selectOption(reviewed.id);
  const stale = await reviewer.request.get(
    `/api/backend/${prefix}/events/${reviewed.id}`,
    { headers },
  );
  expect(stale.status()).toBe(200);
  const staleBody = await stale.json();
  expect(staleBody.freshness).toBe("STALE");
  expect(staleBody.body).toEqual(original);
  card = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await expect(card.getByText("STALE", { exact: true })).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await card.screenshot({
    path: `${screenshots}/AE-gratuity-context-replaced-stale.png`,
  });
  expect(errors).toEqual([]);
}
