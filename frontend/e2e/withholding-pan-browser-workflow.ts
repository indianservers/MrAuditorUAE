import { expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

export async function runWithholdingPANBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { headers, prefix, evidence, prepare, post, completed, upload } =
    makeWorkflowHarness(page, eid, tenant);
  const rule = await evidence(
    "SYNTHETIC-pan-treatment-rule.txt",
    Buffer.from(
      "SYNTHETIC independently assessed missing-PAN identity and rule treatment only; no registry or statutory qualification",
    ),
  );
  const ids: Record<string, string> = {};
  const base = {
    registration: "MUMN77777A",
    counterparty: "PANNOTAVBL",
    legal_role: "collector",
    tax_kind: "TCS",
    rule_reference: "SYN-PAN-RULE",
    tax_year_start: "2026-04-01",
    tax_year_end: "2027-03-31",
    period: "2026-05",
    transaction_reference: "SYN-PAN-TX-1",
    transaction_date: "2026-05-15",
    currency: "INR",
    amount: "100",
    record_status: "current",
    source_version: "SYNTHETIC-1",
    due_date: "2026-06-07",
    payment_date: "2026-06-01",
  };
  async function source(role: string, documented = false) {
    const row: Record<string, unknown> = {
      ...base,
      id: `SYN-${role}`,
      source_reference: `SYN-${role}`,
    };
    if (role === "expected")
      Object.assign(row, {
        assessment_kind: "rule",
        assessment_period_start: "2026-04-01",
        assessment_period_end: "2027-03-31",
        ...(documented
          ? {
              pan_treatment: {
                marker: "PANNOTAVBL",
                party_reference: "SYN-ASSESSED-PARTY-01",
                treatment_reference: "SYN-PAN-RULE",
                assessed_on: "2026-06-01",
                assessment:
                  "SYNTHETIC independently assessed missing-PAN identity and treatment; not PAN authentication",
              },
            }
          : {}),
      });
    const quote = (value: unknown) =>
      `"${(typeof value === "object" ? JSON.stringify(value) : String(value)).replaceAll('"', '""')}"`;
    const csv =
      Object.keys(row).map(quote).join(",") +
      "\r\n" +
      Object.values(row).map(quote).join(",") +
      "\r\n";
    const file = await evidence(
      `SYNTHETIC-pan-${role}${documented ? "-documented" : ""}.csv`,
      Buffer.from(csv),
    );
    const imported = await prepare({
      evidence_version_id: file.version.id,
      table_type: "withholding-records",
      label: `SYNTHETIC missing PAN ${role}${documented ? " documented" : ""}`,
      expected_rows: 1,
      control_totals: { INR: "100" },
      ...(role === "expected"
        ? { rule_document_version_id: rule.version.id }
        : {}),
    });
    const approved = await post(
      reviewer.request,
      `${prefix}/events/${imported.id}/review`,
      {
        expected_version: imported.version,
        action: "approve",
        comments:
          "SYNTHETIC independent source and retained rule-context review",
      },
    );
    return approved.id as string;
  }
  for (const role of ["expected", "withheld", "reported", "deposited"])
    ids[role] = await source(role);
  async function queue(title: string) {
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByRole("combobox", { name: "Workflow", exact: true })
      .selectOption("india-withholding-liability");
    await page
      .getByRole("combobox", {
        name: "Organization legal withholding role",
        exact: true,
      })
      .selectOption("collector");
    for (const [role, id] of Object.entries(ids))
      await page
        .getByRole("combobox", { name: `${role} source`, exact: true })
        .selectOption(id);
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "SYNTHETIC equal source amounts with explicit missing-PAN facts; no legal tax-rate or entitlement inference",
      );
    const submission = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await submission;
    expect(response.status(), await response.text()).toBe(202);
    return completed((await response.json()).id);
  }
  const pending = await queue("SYNTHETIC missing PAN pending assessment");
  expect(pending.body.blocked).toBe(true);
  expect(pending.body.rows[0].comparison_state).toBe("MATCHED");
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${pending.id}`,
  );
  const panel = reviewer.getByRole("region", {
    name: "Missing PAN treatment review",
    exact: true,
  });
  await expect(panel).toContainText("1 pending");
  await expect(panel.getByRole("alert")).toContainText(
    "Row exception notes do not resolve",
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await reviewer
    .getByRole("heading", { name: String(pending.body.title), exact: true })
    .locator("..")
    .screenshot({ path: `${screenshots}/IN-PAN-marker-pending.png` });
  ids.expected = await source("expected", true);
  const supported = await queue("SYNTHETIC documented missing PAN treatment");
  expect(supported.body.blocked).toBe(false);
  expect(supported.body.rows[0].amounts).toEqual(pending.body.rows[0].amounts);
  expect(supported.body.rows[0].pan_authentication).toBe("NOT_PERFORMED");
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${supported.id}`,
  );
  await expect(panel).toContainText("0 pending; 1 documented");
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "SYNTHETIC independently checked identity reference, rule scope, date and original supporting evidence; PAN not authenticated",
    );
  const reviewing = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${supported.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const reviewedResponse = await reviewing;
  expect(reviewedResponse.status(), await reviewedResponse.text()).toBe(201);
  const reviewed = await reviewedResponse.json();
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(reviewer.getByText("REVIEWED", { exact: true })).toBeVisible();
  await panel
    .getByText("Review party and treatment evidence", { exact: true })
    .click();
  await expect(panel).toContainText(rule.version.id);
  await expect(panel).toContainText("NOT_PERFORMED");
  const card = reviewer
    .getByRole("heading", { name: String(supported.body.title), exact: true })
    .locator("..");
  await card.screenshot({
    path: `${screenshots}/IN-PAN-treatment-reviewed.png`,
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
        "v=list(w['Withholding PAN treatment'].values);assert len(v)==2;r=dict(zip(v[0],v[1]))",
        "assert r['pan_status']=='PANNOTAVBL' and r['pan_authentication']=='NOT_PERFORMED'",
        "assert r['party_reference']=='SYN-ASSESSED-PARTY-01'",
        `assert r['assessment_sha256']=='${rule.version.sha256}'`,
      ].join("\n"),
    ],
    { input: readFileSync(downloaded!), timeout: 15000 },
  );
  await upload(
    rule.record,
    "SYNTHETIC-pan-treatment-rule-v2.txt",
    Buffer.from(
      "SYNTHETIC changed supporting identity/rule assessment requires regeneration",
    ),
  );
  const historicalResponse = await reviewer.request.get(
    `/api/backend/${prefix}/events/${reviewed.id}`,
    { headers },
  );
  expect(historicalResponse.status()).toBe(200);
  const historical = await historicalResponse.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(reviewed.body);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await panel
    .getByText("Review party and treatment evidence", { exact: true })
    .click();
  await card.screenshot({
    path: `${screenshots}/IN-PAN-rule-replaced-stale.png`,
  });
}
