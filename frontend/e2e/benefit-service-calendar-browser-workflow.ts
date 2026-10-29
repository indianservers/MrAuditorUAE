import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Dated HR setup/reviews via API; benefit calculation, final approval and export via UI. */
export async function runBenefitServiceCalendarBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
  ruleSourceId: string,
) {
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const scope = {
    regime: "SYNTHETIC-REGIME",
    cohort: "SYNTHETIC-COHORT",
    scheme: "gratuity",
    service_end: "2026-06-30",
  };
  const full = {
    id: "CE1",
    ...scope,
    work_model: "full-time",
    work_model_assessment: "Synthetic assessed full-time contract and cohort",
    work_model_constant_for_service: true,
    annual_contract_hours: null,
    annual_full_time_hours: null,
    full_time_monthly_basic_salary: null,
    currency: "AED",
    service_start: "2024-07-01",
    excluded_service_days: 5,
    monthly_basic_salary: "3000",
    amount: "4171.23",
    contract_evidence: "SYNTHETIC-CONTRACT-CE1",
  };
  const part = {
    ...full,
    id: "CE2",
    work_model: "part-time",
    service_start: "2025-07-01",
    excluded_service_days: 0,
    annual_contract_hours: "1040",
    annual_full_time_hours: "2080",
    full_time_monthly_basic_salary: "3000",
    monthly_basic_salary: "1500",
    amount: "1050",
    contract_evidence: "SYNTHETIC-CONTRACT-CE2",
  };
  const assessment =
    "Synthetic independently assessed inclusive exclusion dates; pension treatment not inferred";
  const calendar = [
    {
      id: "C-CE1",
      employee_id: "CE1",
      ...scope,
      service_start: full.service_start,
      work_model: full.work_model,
      kind: "EXCLUDED_CALENDAR_DAYS",
      exclusion_start: "2026-06-01",
      exclusion_end: "2026-06-05",
      days: 5,
      evidence_reference: "SYNTHETIC-HR-LEAVE-CE1",
      assessment,
    },
    {
      id: "Z-CE2",
      employee_id: "CE2",
      ...scope,
      service_start: part.service_start,
      work_model: part.work_model,
      kind: "NO_EXCLUDED_DAYS_ASSESSED",
      exclusion_start: null,
      exclusion_end: null,
      days: 0,
      evidence_reference: "SYNTHETIC-HR-REVIEW-CE2",
      assessment,
    },
  ];
  const sources: Record<string, string> = { rules: ruleSourceId };
  let calendarSource!: WorkflowEvent;
  for (const [role, table, rows, controls] of [
    [
      "employees",
      "benefit-employees",
      [full, part],
      { control_totals: { AED: "5221.23" } },
    ],
    [
      "service_calendar",
      "benefit-service-exclusions",
      calendar,
      {
        control_totals: {},
        benefit_service_controls: { employee_count: 2, excluded_days: 5 },
      },
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
                String(
                  (row as Record<string, unknown>)[field] ?? "",
                ).replaceAll('"', '""') +
                '"',
            )
            .join(","),
        )
        .join("\n") +
      "\n";
    const retained = await evidence(
      `SYNTHETIC-service-calendar-${role}.csv`,
      Buffer.from(csv),
    );
    const source = await prepare({
      evidence_version_id: retained.version.id,
      table_type: table,
      expected_rows: rows.length,
      label: `SYNTHETIC dated benefit ${role}`,
      ...controls,
    });
    const reviewed = (await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "Synthetic independent service-calendar and employee source assessment",
      },
    )) as WorkflowEvent;
    sources[role] = reviewed.id;
    if (role === "service_calendar") calendarSource = reviewed;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("uae-benefit-review");
  for (const [role, id] of Object.entries(sources))
    await page
      .getByRole("combobox", {
        name: `${role} source${role === "service_calendar" ? " (optional)" : ""}`,
        exact: true,
      })
      .selectOption(id);
  const title = "SYNTHETIC UAE dated gratuity service calendar";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-06-30"],
    [
      "Scope and source rationale",
      "Synthetic independently assessed inclusive exclusions and explicit zero service records",
    ],
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
    id: "CE1",
    eligible_service_days: 725,
    calendar_excluded_service_days: 5,
    expected_benefit: "4171.23",
  });
  expect(result.body.rows[1]).toMatchObject({
    id: "CE2",
    calendar_excluded_service_days: 0,
    expected_benefit: "1050.00",
  });
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Synthetic independent dated HR exclusions, explicit zero and service threshold assessment",
    );
  const approvedWait = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const approvedResponse = await approvedWait;
  expect(approvedResponse.status(), await approvedResponse.text()).toBe(201);
  const reviewed = (await approvedResponse.json()) as WorkflowEvent;
  const original = structuredClone(reviewed.body);
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  const downloadWait = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const downloaded = await downloadWait;
  const path = await downloaded.path();
  expect(path).toBeTruthy();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,sys;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));r=list(w['Benefit service exclusions'].values);assert len(r)==3;assert r[1][r[0].index('days')]=='5';assert r[2][r[0].index('kind')]=='NO_EXCLUDED_DAYS_ASSESSED';v=list(w['Rows'].values);assert v[1][v[0].index('expected_benefit')]=='4171.23'",
    ],
    { input: readFileSync(path!), timeout: 15000 },
  );
  await reviewer.setViewportSize({ width: 1800, height: 2800 });
  const card = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  const showDates = async () => {
    const detail = reviewer.getByRole("region", {
      name: "Dated benefit service calendars",
      exact: true,
    });
    await detail
      .getByText("CE1 · declared 5 days · dated 5 days · MATCHED", {
        exact: true,
      })
      .click();
    await expect(
      detail.getByRole("cell", { name: "2026-06-01", exact: true }),
    ).toBeVisible();
    await expect(
      detail.getByRole("cell", { name: "2026-06-05", exact: true }),
    ).toBeVisible();
  };
  await showDates();
  await card.evaluate((element) => element.scrollIntoView({ block: "center" }));
  await expect(
    card.getByRole("columnheader", {
      name: "eligible service days",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (await card
      .getByRole("heading", { name: title, exact: true })
      .boundingBox())!.y,
  ).toBeGreaterThan(100);
  await expect(card.getByText("CURRENT", { exact: true })).toBeVisible();
  const notice = reviewer.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  if (await notice.count()) await notice.last().click();
  await card.screenshot({
    path: `${screenshots}/AE-benefit-service-calendar-reviewed.png`,
  });
  await post(reviewer.request, `${prefix}/events/${calendarSource.id}/review`, {
    expected_version: calendarSource.version,
    action: "reject",
    comments: "Synthetic withdrawal of reviewed dated service exclusions",
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
  await showDates();
  await card.evaluate((element) => element.scrollIntoView({ block: "center" }));
  expect(
    (await card
      .getByRole("heading", { name: title, exact: true })
      .boundingBox())!.y,
  ).toBeGreaterThan(100);
  await expect(card.getByText("STALE", { exact: true })).toBeVisible();
  await card.screenshot({
    path: `${screenshots}/AE-benefit-service-calendar-withdrawn-stale.png`,
  });
}
