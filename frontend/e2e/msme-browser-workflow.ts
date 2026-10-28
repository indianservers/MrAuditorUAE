import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

export type WorkflowEvent = {
  id: string;
  version: number;
  freshness: string;
  body: {
    [key: string]: unknown;
    review_status: string;
    blocked?: boolean;
    msme_document_binding?: string;
    statutory_calculation_qualified?: boolean;
    rows: Record<string, unknown>[];
  };
};

/** Synthetic setup uses real upload/source APIs; calculation/review/export use UI. */
export function makeWorkflowHarness(page: Page, eid: string, tenant: string) {
  const headers = {
    "X-Tenant-ID": tenant,
    Origin: process.env.AUDITOS_E2E_ORIGIN!,
  };
  const audit = `engagements/${eid}/audit`;
  const prefix = `intelligence/engagements/${eid}`;

  async function post(request: APIRequestContext, path: string, data: unknown) {
    const response = await request.post(`/api/backend/${path}`, {
      headers,
      data,
    });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  }

  async function upload(record: string, name: string, buffer: Buffer) {
    const response = await page.request.post(
      `/api/backend/${audit}/evidence-files/${record}`,
      {
        headers,
        multipart: {
          file: {
            name,
            mimeType: name.endsWith(".csv")
              ? "text/csv"
              : name.endsWith(".xml")
                ? "application/xml"
                : "text/plain",
            buffer,
          },
        },
      },
    );
    expect(response.status(), await response.text()).toBe(201);
    const version = await response.json();
    // Requires the configured real ClamAV service; quarantine is not bypassed.
    expect(version.scan_status).toBe("CLEAN");
    return version;
  }

  async function evidence(name: string, buffer: Buffer) {
    const record = await post(page.request, `${audit}/evidence`, {
      reference: `SYNTHETIC-WORKFLOW-${randomUUID()}`,
      title: `SYNTHETIC ${name}`,
      body: { category: "Other", retain_until: "2036-12-31" },
    });
    return {
      record: record.id,
      version: await upload(record.id, name, buffer),
    };
  }

  async function completed(jobId: string): Promise<WorkflowEvent> {
    let resultId = "";
    await expect
      .poll(
        async () => {
          const response = await page.request.get(
            `/api/backend/${prefix}/jobs/${jobId}`,
            { headers },
          );
          expect(response.status()).toBe(200);
          const job = await response.json();
          if (job.status === "failed")
            throw new Error(
              `Synthetic country workflow job failed: ${job.error_details?.message}`,
            );
          resultId = job.result_id || "";
          return job.status;
        },
        { timeout: 30000, intervals: [250, 500, 1000] },
      )
      .toBe("completed");
    expect(resultId).not.toBe("");
    const response = await page.request.get(
      `/api/backend/${prefix}/events/${resultId}`,
      { headers },
    );
    expect(response.status()).toBe(200);
    return response.json();
  }

  async function prepare(
    payload: Record<string, unknown>,
    operation: "workflow-source" | "workflow-ledger" = "workflow-source",
  ) {
    const response = await page.request.post(`/api/backend/${prefix}/jobs`, {
      headers: { ...headers, "Idempotency-Key": randomUUID() },
      data: { operation, payload },
    });
    expect(response.status(), await response.text()).toBe(202);
    return completed((await response.json()).id);
  }

  return { headers, prefix, post, upload, evidence, completed, prepare };
}

export async function runMSMEBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { headers, prefix, post, upload, evidence, completed, prepare } =
    makeWorkflowHarness(page, eid, tenant);
  const reviewerErrors: string[] = [];
  reviewer.on("pageerror", (error) => reviewerErrors.push(error.message));

  const sourceIds: Record<string, string> = {};
  let assessmentContext = "";
  for (const [role, filename, table, total] of [
    ["assessments", "assessments.csv", "msme-supplier-assessments", null],
    ["invoices", "invoices.csv", "msme-invoices", "100"],
    ["bank", "bank.csv", "transactions", "-100"],
    ["allocations", "allocations.csv", "item-allocations", "100"],
  ] as const) {
    const file = await evidence(
      `SYNTHETIC-${filename}`,
      readFileSync(
        `../docs/country-workflows/sample-inputs/SYNTHETIC-msme-payments/${filename}`,
      ),
    );
    let context: Record<string, string> = {};
    if (role === "assessments" || role === "invoices") {
      const packet = await evidence(
        `SYNTHETIC-${role}-context.txt`,
        Buffer.from(
          `SYNTHETIC ${role} supporting packet; no client/legal qualification`,
        ),
      );
      if (role === "assessments") assessmentContext = packet.record;
      context = {
        msme_context_evidence_version_id: packet.version.id,
        msme_context_assessment: `SYNTHETIC ${role} facts assessed against this separate retained packet`,
      };
    }
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: table,
      label: `SYNTHETIC browser MSE ${role}`,
      expected_rows: 1,
      control_totals: total === null ? {} : { INR: total },
      ...context,
    });
    const approved = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independent source and retained-context assessment",
      },
    );
    expect(approved.body.review_status).toBe("REVIEWED");
    sourceIds[role] = approved.id;
  }

  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("india-msme-payment-timing");
  for (const [role, id] of Object.entries(sourceIds))
    await page.getByLabel(`${role} source`, { exact: true }).selectOption(id);
  const title = "SYNTHETIC browser MSE invoice payment result";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-04-30"],
    ["Buyer identifier", "SYNTHETIC-BUYER"],
    ["First invoice month", "2026-04"],
    ["Last invoice month", "2026-04"],
    ["Bank settlement window starts", "2026-04-01"],
    ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
    ["Account currency", "INR"],
    [
      "Scope and source rationale",
      "SYNTHETIC complete invoice and bank source assessment; no legal qualification",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByRole("combobox", { name: "Bank payment sign", exact: true })
    .selectOption("debit-negative");
  const submission = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/${prefix}/jobs`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const submitted = await submission;
  expect(submitted.status(), await submitted.text()).toBe(202);
  const result = await completed((await submitted.json()).id);
  expect(result.body.msme_document_binding).toBe(
    "RETAINED_DOCUMENT_BYTES_VERIFIED",
  );
  expect(result.body.blocked).toBe(false);
  expect(result.body.statutory_calculation_qualified).toBe(false);
  expect(result.body.rows).toHaveLength(1);
  expect(result.body.rows[0]).toMatchObject({
    due_date: "2026-04-16",
    state: "MATCHED",
    allocated_paid: "100",
    unpaid_amount: "0",
    late_paid_amount: "0",
    overdue_unpaid_amount: "0",
  });
  await page.goto(`/intelligence/${eid}/country-workflow?event=${result.id}`);
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  const invoice = page.getByRole("row").filter({
    has: page.getByRole("cell", { name: "SYNTHETIC-1", exact: true }),
  });
  await expect(
    invoice.getByRole("cell", { name: "2026-04-16", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Review / exception rationale", { exact: true })
    .fill("SYNTHETIC own-output approval must remain prohibited");
  const selfDecision = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  expect((await selfDecision).status()).toBe(403);

  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "SYNTHETIC independent invoice, supporting documents and bank allocation assessment",
    );
  const decision = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const response = await decision;
  expect(response.status(), await response.text()).toBe(201);
  const approved: WorkflowEvent = await response.json();
  expect(approved.body.review_status).toBe("REVIEWED");
  await expect(
    reviewer
      .getByRole("region", { name: "MSE payment-timing scope" })
      .getByText(/retained versions were verified for this calculation/),
  ).toBeVisible();
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(approved.id);
  const downloadEvent = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
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
        "import io,sys",
        "from openpyxl import load_workbook",
        "rows=list(load_workbook(io.BytesIO(sys.stdin.buffer.read()))['Rows'].values)",
        "assert len(rows)==2",
        "assert rows[1][rows[0].index('due_date')]=='2026-04-16'",
        "assert str(rows[1][rows[0].index('allocated_paid')])=='100'",
      ].join("\n"),
    ],
    { input: workbook, timeout: 15000 },
  );
  const notice = reviewer.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  if (await notice.count()) await notice.first().click();
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({ path: `${screenshots}/IN-msme-reviewed-payment-result.png` });
  const original = structuredClone(approved.body);
  await upload(
    assessmentContext,
    "SYNTHETIC-assessments-replaced.txt",
    Buffer.from("SYNTHETIC replaced supplier context for staleness check"),
  );
  const stale = await page.request.get(
    `/api/backend/${prefix}/events/${approved.id}`,
    { headers },
  );
  expect(stale.status()).toBe(200);
  const historical: WorkflowEvent = await stale.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(original);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${approved.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await expect(
    reviewer
      .getByRole("region", { name: "MSE payment-timing scope" })
      .getByText(/This MSE calculation is not current/),
  ).toBeVisible();
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/IN-msme-context-replacement-stale.png`,
    });
  expect(reviewerErrors).toEqual([]);
}
