import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Synthetic source setup via real APIs; calculation, approval, export and derived-source preparation via UI. */
export async function runPayrollProrationBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const root =
    "../docs/country-workflows/sample-inputs/SYNTHETIC-payroll-proration/";
  const manifest = JSON.parse(readFileSync(root + "controls.json", "utf8")) as {
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
  };
  const policy = await evidence(
    "SYNTHETIC-ceiling-assessment.txt",
    Buffer.from(
      "SYNTHETIC calendar wage and membership policy fixture; no legal qualification",
    ),
  );
  const selected: Record<string, string> = {};
  let segments!: WorkflowEvent;
  for (const [role, spec] of Object.entries(manifest.files)) {
    const bytes = readFileSync(root + spec.file);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    const original = await evidence(`SYNTHETIC-proration-${role}.csv`, bytes);
    const source = await prepare({
      evidence_version_id: original.version.id,
      table_type: spec.table_type,
      expected_rows: spec.expected_rows,
      control_totals: spec.control_totals,
      label: `SYNTHETIC dated PF ${role}`,
      ...(role === "rules"
        ? { rule_document_version_id: policy.version.id }
        : {}),
    });
    const reviewed = (await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "Synthetic independent calendar wage, membership and monthly control assessment",
      },
    )) as WorkflowEvent;
    selected[role] = reviewed.id;
    if (role === "segments") segments = reviewed;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("india-payroll-basis-proration");
  for (const [role, id] of Object.entries(selected))
    await page
      .getByRole("combobox", { name: `${role} source`, exact: true })
      .selectOption(id);
  const title = "SYNTHETIC India dated PF wage-basis controls";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-09-30"],
    [
      "Scope and source rationale",
      "Synthetic original calendar wages and independent component-basis controls",
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
  const result = await completed((await response.json()).id);
  expect(result.body.blocked).toBe(false);
  expect(result.body.monthly_basis_complete).toBe(true);
  expect(result.body.rows).toHaveLength(9);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Synthetic independent complete calendar coverage and monthly PF basis assessment",
    );
  const approved = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const approval = await approved;
  expect(approval.status(), await approval.text()).toBe(201);
  const reviewed = (await approval.json()) as WorkflowEvent;
  const original = structuredClone(reviewed.body);
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  const download = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const path = await (await download).path();
  expect(path).toBeTruthy();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,sys;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));r=list(w['Payroll basis segments'].values);assert len(r)==19;v=list(w['Rows'].values);assert len(v)==10;assert all(x[v[0].index('state')]=='MATCHED' for x in v[1:])",
    ],
    { input: readFileSync(path!), timeout: 15000 },
  );
  await reviewer.setViewportSize({ width: 2200, height: 3400 });
  const card = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await expect(
    card.getByRole("region", {
      name: "Dated PF wage-basis evidence",
      exact: true,
    }),
  ).toContainText("18 segment records");
  await expect(
    card.getByRole("columnheader", {
      name: "computed monthly basis",
      exact: true,
    }),
  ).toBeVisible();
  await card.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await expect(card.getByText("CURRENT", { exact: true })).toBeVisible();
  expect(
    (await card
      .getByRole("heading", { name: title, exact: true })
      .boundingBox())!.y,
  ).toBeGreaterThan(100);
  await card.screenshot({
    path: `${screenshots}/IN-payroll-proration-reviewed.png`,
  });
  await page.goto(`/intelligence/${eid}/country-workflow?event=${reviewed.id}`);
  await expect(
    page.getByLabel("Independent PF component-basis row count"),
  ).toHaveValue("");
  await expect(
    page.getByLabel("Independent post-ceiling component-basis total (INR)"),
  ).toHaveValue("");
  for (const [label, value] of [
    ["Monthly basis source title", "SYNTHETIC UI monthly PF wage source"],
    ["Independent PF component-basis row count", "9"],
    ["Independent post-ceiling component-basis total (INR)", "129333.31"],
    [
      "Monthly basis control assessment",
      "Synthetic independent original component-basis schedule checked",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const derivedWait = page.waitForResponse(
    (r) =>
      r.url().endsWith("/prorated-payroll-basis-source") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Prepare reviewed monthly wage source",
      exact: true,
    })
    .click();
  const derivedResponse = await derivedWait;
  expect(derivedResponse.status(), await derivedResponse.text()).toBe(201);
  const derived = (await derivedResponse.json()) as WorkflowEvent;
  expect(derived.body.rows).toHaveLength(9);
  expect(derived.body.review_status).toBe("UNVERIFIED");
  await post(reviewer.request, `${prefix}/events/${segments.id}/review`, {
    expected_version: segments.version,
    action: "reject",
    comments: "Synthetic withdrawal of original calendar wage evidence",
  });
  for (const obj of [reviewed, derived]) {
    const response = await reviewer.request.get(
      `/api/backend/${prefix}/events/${obj.id}`,
      { headers },
    );
    expect(response.status()).toBe(200);
    const stale = (await response.json()) as WorkflowEvent;
    expect(stale.freshness).toBe("STALE");
    expect(stale.body).toEqual(
      obj.id === reviewed.id ? original : derived.body,
    );
  }
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await expect(
    reviewer.getByRole("button", {
      name: "Prepare reviewed monthly wage source",
      exact: true,
    }),
  ).toHaveCount(0);
  await card.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await expect(card.getByText("STALE", { exact: true })).toBeVisible();
  await card.screenshot({
    path: `${screenshots}/IN-payroll-proration-withdrawn-stale.png`,
  });
}
