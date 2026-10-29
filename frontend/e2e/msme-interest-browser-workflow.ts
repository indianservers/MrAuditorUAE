import { expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Actual API source setup; calculation, independent approval and XLSX use the UI. */
export async function runMSMEInterestBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const root =
    "../docs/country-workflows/sample-inputs/SYNTHETIC-msme-interest/";
  const manifest = JSON.parse(readFileSync(root + "controls.json", "utf8")) as {
    expected_total: string;
    files: Record<
      string,
      {
        file: string;
        sha256: string;
        table_type: string;
        expected_rows: number;
        control_totals: Record<string, string>;
      }
    >;
    documents: Record<string, { sha256: string }>;
  };
  const docs: Record<string, Awaited<ReturnType<typeof evidence>>> = {};
  for (const [name, spec] of Object.entries(manifest.documents)) {
    const bytes = readFileSync(root + name);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    docs[name] = await evidence("SYNTHETIC-interest-" + name, bytes);
  }
  const selected: Record<string, string> = {};
  for (const [role, spec] of Object.entries(manifest.files)) {
    const bytes = readFileSync(root + spec.file);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    const csv = await evidence("SYNTHETIC-interest-" + spec.file, bytes);
    const source = await prepare({
      evidence_version_id: csv.version.id,
      table_type: spec.table_type,
      expected_rows: spec.expected_rows,
      control_totals: spec.control_totals,
      label: "SYNTHETIC interest " + role,
      ...(["assessments", "invoices"].includes(role)
        ? {
            msme_context_evidence_version_id: docs["facts.txt"].version.id,
            msme_context_assessment:
              "Synthetic retained supplier eligibility, invoice acceptance and terms facts",
          }
        : {}),
      ...(["interest_policies", "bank_rates"].includes(role)
        ? {
            rule_document_version_id:
              docs[role === "interest_policies" ? "policy.txt" : "rate.txt"]
                .version.id,
          }
        : {}),
    });
    const reviewed = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "Independent synthetic source controls and assessed interest evidence only",
      },
    );
    selected[role] = reviewed.id;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("india-msme-interest");
  for (const [role, id] of Object.entries(selected))
    await page.getByLabel(`${role} source`, { exact: true }).selectOption(id);
  const title = "SYNTHETIC India assessed MSE interest";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-07-31"],
    ["Buyer identifier", "SYNTHETIC-BUYER"],
    ["First invoice month", "2026-05"],
    ["Last invoice month", "2026-05"],
    ["Bank settlement window starts", "2026-05-16"],
    ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
    ["Account currency", "INR"],
    [
      "Scope and source rationale",
      "Synthetic full invoice history, explicit bank principal and interest shares, assessed rate and conventions",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByRole("combobox", { name: "Bank payment sign", exact: true })
    .selectOption("debit-negative");
  const queued = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const submission = await queued;
  expect(submission.status(), await submission.text()).toBe(202);
  const result = await completed((await submission.json()).id);
  expect(result.body.blocked).toBe(false);
  expect(result.body.expected_total).toBe(manifest.expected_total);
  expect(result.body.principal_timing_exception_count).toBe(1);
  expect(result.body.rows[0]).toMatchObject({
    expected_amount: "93.23",
    reported_amount: "93.23",
    state: "MATCHED",
    principal_remaining: "35600",
  });
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Independent synthetic interest controls; retained principal overdue exception is separate",
    );
  const approval = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const response = await approval;
  expect(response.status(), await response.text()).toBe(201);
  const approved: WorkflowEvent = await response.json();
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(approved.id);
  const scope = reviewer.getByRole("region", {
    name: "MSE assessed interest scope",
    exact: true,
  });
  await expect(scope.getByText(/Outstanding interest total/)).toHaveText(
    /INR 93.23.*Principal timing exceptions: 1/,
  );
  await scope
    .getByText("Bank allocation controls (1)", { exact: true })
    .click();
  const bank = scope.getByRole("table", {
    name: "Bank allocation controls",
    exact: true,
  });
  await expect(
    bank.getByRole("cell", { name: "900", exact: true }),
  ).toBeVisible();
  await expect(
    bank.getByRole("cell", { name: "90", exact: true }),
  ).toBeVisible();
  await expect(
    bank.getByRole("cell", { name: "10", exact: true }),
  ).toBeVisible();
  const downloadEvent = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const download = await downloadEvent;
  const path = await download.path();
  expect(path).not.toBeNull();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,sys\nfrom openpyxl import load_workbook\nw=load_workbook(io.BytesIO(sys.stdin.buffer.read()))\nassert w['MSE monthly rests'].max_row==3\nassert w['MSE interest bank controls'].max_row==2\nr=list(w['Rows'].values)\nassert r[1][r[0].index('expected_amount')]=='93.23'",
    ],
    { input: readFileSync(path!), timeout: 15000 },
  );
  async function capture(name: string) {
    const viewport = reviewer.viewportSize();
    try {
      await reviewer.setViewportSize({ width: 2200, height: 3400 });
      const heading = reviewer.getByRole("heading", {
        name: title,
        exact: true,
      });
      await heading.scrollIntoViewIfNeeded();
      await expect(heading).toBeInViewport();
      await expect(
        scope.getByText(/Outstanding interest total/),
      ).toBeInViewport();
      await expect(
        bank.getByRole("cell", { name: "10", exact: true }),
      ).toBeInViewport();
      await reviewer.screenshot({
        path: `${screenshots}/${name}.png`,
        fullPage: true,
      });
    } finally {
      if (viewport) await reviewer.setViewportSize(viewport);
    }
  }
  await capture("IN-msme-interest-reviewed");
  const replacement = await page.request.post(
    `/api/backend/engagements/${eid}/audit/evidence-files/${docs["rate.txt"].record}`,
    {
      headers,
      multipart: {
        file: {
          name: "SYNTHETIC-replaced-interest-rate.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("SYNTHETIC replacement assessed rate evidence"),
        },
      },
    },
  );
  expect(replacement.status(), await replacement.text()).toBe(201);
  const stale = await page.request.get(
    `/api/backend/${prefix}/events/${approved.id}`,
    { headers },
  );
  expect(stale.status()).toBe(200);
  const historical: WorkflowEvent = await stale.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(approved.body);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${approved.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await expect(
    reviewer.getByText(/This MSE calculation is not current/),
  ).toBeVisible();
  await scope
    .getByText("Bank allocation controls (1)", { exact: true })
    .click();
  await capture("IN-msme-interest-rate-replaced-stale");
}
