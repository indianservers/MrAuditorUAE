import { expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** API source setup; the browser calculates, independently reviews and exports. */
export async function runMSMETaxBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const root = "../docs/country-workflows/sample-inputs/SYNTHETIC-msme-tax/";
  const manifest = JSON.parse(readFileSync(root + "controls.json", "utf8")) as {
    net_expected_tax_adjustment: string;
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
    docs[name] = await evidence("SYNTHETIC-tax-" + name, bytes);
  }
  const selected: Record<string, string> = {};
  for (const [role, spec] of Object.entries(manifest.files)) {
    const bytes = readFileSync(root + spec.file);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    const csv = await evidence("SYNTHETIC-tax-" + spec.file, bytes);
    const source = await prepare({
      evidence_version_id: csv.version.id,
      table_type: spec.table_type,
      expected_rows: spec.expected_rows,
      control_totals: spec.control_totals,
      label: "SYNTHETIC annual tax " + role,
      ...(["assessments", "invoices"].includes(role)
        ? {
            msme_context_evidence_version_id: docs["facts.txt"].version.id,
            msme_context_assessment:
              "Synthetic retained supplier eligibility, invoice acceptance and terms facts",
          }
        : {}),
      ...(["tax_bases", "interest_pnl"].includes(role)
        ? {
            rule_document_version_id:
              docs[role === "tax_bases" ? "basis.txt" : "pnl.txt"].version.id,
          }
        : {}),
    });
    selected[role] = (
      await post(reviewer.request, `${prefix}/events/${source.id}/review`, {
        expected_version: source.version,
        action: "approve",
        comments:
          "Independent synthetic expense, prior allowance and P&L support controls only",
      })
    ).id;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("india-msme-annual-tax");
  for (const [role, id] of Object.entries(selected))
    await page.getByLabel(`${role} source`, { exact: true }).selectOption(id);
  const title = "SYNTHETIC India annual MSE tax bridge";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2027-03-31"],
    ["Annual tax year starts (April 1)", "2026-04-01"],
    ["Settlement observations through", "2027-04-05"],
    ["Buyer identifier", "SYNTHETIC-BUYER"],
    ["First invoice month", "2026-03"],
    ["Last invoice month", "2027-03"],
    ["Bank settlement window starts", "2026-03-01"],
    ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
    ["Account currency", "INR"],
    [
      "Scope and source rationale",
      "Synthetic full invoice history, independently assessed expense bases, prior tax balances and actual bank dates",
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
  expect(result.body.net_expected_tax_adjustment).toBe(
    manifest.net_expected_tax_adjustment,
  );
  expect(result.body.rows).toHaveLength(6);
  expect(result.body.rows.every((row) => row.state === "MATCHED")).toBe(true);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Independent authored tax bridge: interest 15, current addback 100, prior release 150; not client qualification",
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
    name: "MSE annual tax scope",
    exact: true,
  });
  const net = scope.getByText(/Net expected adjustment to income/);
  await expect(net).toHaveText(/INR -35.*not tax payable or a refund/);
  const totals = scope.getByRole("table", {
    name: "Separate MSE tax adjustments",
    exact: true,
  });
  for (const [metric, amount] of [
    ["P&L interest adjustment", "15"],
    ["Current expense disallowance", "100"],
    ["Release of earlier disallowance", "150"],
  ]) {
    const row = totals.getByRole("row").filter({ hasText: metric });
    await expect(
      row.getByRole("cell", { name: amount, exact: true }),
    ).toHaveCount(2);
  }
  const prior = scope
    .locator("details")
    .filter({
      has: reviewer.locator("summary").filter({ hasText: /^SYN-PRIOR —/ }),
    })
    .first();
  await prior.locator(":scope > summary").click();
  await expect(
    prior.getByText("opening previously allowed unpaid", { exact: true }),
  ).toBeVisible();
  await prior
    .getByText("Tax settlements and original bank links (2)", { exact: true })
    .click();
  const trace = prior.getByRole("table", {
    name: "Tax settlements and original bank links",
    exact: true,
  });
  await expect(
    trace.getByRole("cell", { name: "PRIOR_ALREADY_ALLOWED", exact: true }),
  ).toBeVisible();
  await expect(
    trace.getByRole("cell", { name: "2026-04-04", exact: true }),
  ).toBeVisible();
  await prior.locator(":scope > summary").click();
  const downloadEvent = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const path = await (await downloadEvent).path();
  expect(path).not.toBeNull();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,sys\nfrom openpyxl import load_workbook\nw=load_workbook(io.BytesIO(sys.stdin.buffer.read()))\nassert w['Rows'].max_row==7\nassert w['MSE annual tax totals'].max_row==4\nassert w['MSE tax settlements'].max_row==4\nr=list(w['Rows'].values)\nh=r[0]\nassert sum(1 for a in r[1:] if a[h.index('state')]=='MATCHED')==6",
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
      await expect(net).toBeInViewport();
      await expect(
        totals
          .getByRole("row")
          .filter({ hasText: "Release of earlier disallowance" }),
      ).toBeInViewport();
      await reviewer.screenshot({
        path: `${screenshots}/${name}.png`,
        fullPage: true,
      });
    } finally {
      if (viewport) await reviewer.setViewportSize(viewport);
    }
  }
  await capture("IN-msme-annual-tax-reviewed");
  const replacement = await page.request.post(
    `/api/backend/engagements/${eid}/audit/evidence-files/${docs["basis.txt"].record}`,
    {
      headers,
      multipart: {
        file: {
          name: "SYNTHETIC-replaced-tax-basis.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("SYNTHETIC replacement tax treatment support"),
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
    scope.getByText(/This saved tax calculation is not current/),
  ).toBeVisible();
  await capture("IN-msme-annual-tax-support-replaced-stale");
}
