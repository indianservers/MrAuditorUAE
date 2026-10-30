import { expect, type Page } from "@playwright/test";
import { makeWorkflowHarness } from "./msme-browser-workflow";

export async function runWithholdingBoundaryBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { headers, prefix, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const context = await evidence(
    "SYNTHETIC-withholding-rule-assessment.txt",
    Buffer.from(
      "SYNTHETIC retained rule assessment for a deliberately invalid post-withdrawal positive 206C(1H) expectation. No legal qualification or client data.",
    ),
  );
  const sources: Record<string, string> = {};
  for (const role of ["expected", "withheld", "reported", "deposited"]) {
    const record: Record<string, string> = {
      id: `SYN-${role}`,
      registration: "SYN-COLLECTOR",
      counterparty: "SYN-BUYER",
      legal_role: "collector",
      tax_kind: "TCS",
      rule_reference: "206C(1H)",
      tax_year_start: "2026-04-01",
      tax_year_end: "2027-03-31",
      period: "2026-05",
      transaction_reference: "SYN-TCS-POST-WITHDRAWAL",
      transaction_date: "2026-05-15",
      currency: "INR",
      amount: "100",
      record_status: "current",
      source_reference: `SYN-${role}-original`,
      source_version: "1",
      due_date: "2026-06-07",
      payment_date: "2026-06-01",
      ...(role === "expected"
        ? {
            assessment_kind: "rule",
            assessment_period_start: "2026-04-01",
            assessment_period_end: "2027-03-31",
          }
        : {}),
    };
    const content =
      Object.keys(record).join(",") +
      "\n" +
      Object.values(record).join(",") +
      "\n";
    const file = await evidence(
      `SYNTHETIC-withholding-${role}.csv`,
      Buffer.from(content),
    );
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: "withholding-records",
      expected_rows: 1,
      control_totals: { INR: "100" },
      label: `SYNTHETIC TCS ${role}`,
      ...(role === "expected"
        ? { rule_document_version_id: context.version.id }
        : {}),
    });
    const reviewed = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independent retained observation and source total assessment; not legal acceptance of expected liability",
      },
    );
    sources[role] = reviewed.id;
  }
  const title = "SYNTHETIC withdrawn TCS positive expectation";
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("india-withholding-liability");
  await page
    .getByLabel("Organization legal withholding role", { exact: true })
    .selectOption("collector");
  for (const [role, id] of Object.entries(sources))
    await page.getByLabel(`${role} source`, { exact: true }).selectOption(id);
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-06-30"],
    [
      "Scope and source rationale",
      "SYNTHETIC all source amounts agree, but the named withdrawn provision must prevent liability approval",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const queued = await submitted;
  expect(queued.status(), await queued.text()).toBe(202);
  const result = await completed((await queued.json()).id);
  expect(result.body.blocked).toBe(true);
  expect(result.body.rows[0]).toMatchObject({
    comparison_state: "MATCHED",
    state: "WITHDRAWN_PROVISION_LIABILITY",
    statutory_scope_issues: ["WITHDRAWN_206C_1H_POSITIVE_EXPECTATION"],
    amounts: {
      expected: "100",
      withheld: "100",
      reported: "100",
      deposited: "100",
    },
  });
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await expect(
    reviewer.getByRole("region", {
      name: "Withholding provision boundary",
      exact: true,
    }),
  ).toContainText("2025-04-01");
  await expect(
    reviewer.getByText(
      "Correct the positive 206C(1H) expectation for the withdrawn period and regenerate the result.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    reviewer.getByText("expected: 100", { exact: true }),
  ).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  const rejected = await reviewer.request.post(
    `/api/backend/${prefix}/events/${result.id}/review`,
    {
      headers,
      data: {
        expected_version: result.version,
        action: "approve",
        comments:
          "SYNTHETIC agreeing observations cannot override withdrawal boundary",
      },
    },
  );
  expect(rejected.status()).toBe(409);
  expect(await rejected.text()).toContain("withdrawn period");
  const retained = await reviewer.request.get(
    `/api/backend/${prefix}/events/${result.id}`,
    { headers },
  );
  expect(retained.status()).toBe(200);
  const history = await retained.json();
  expect(history.body).toEqual(result.body);
  expect(history.version).toBe(result.version);
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/IN-TCS-withdrawn-positive-expectation-blocked.png`,
    });
}
