import { expect, type Page } from "@playwright/test";
import { makeWorkflowHarness } from "./msme-browser-workflow";

export async function runPensionSupportBasisBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, post, evidence, prepare } = makeWorkflowHarness(
    page,
    eid,
    tenant,
  );
  const ruleFile = await evidence(
    "SYNTHETIC-pension-rule-assessment.txt",
    Buffer.from(
      "SYNTHETIC arithmetic only: employee 7%, employer gross 18%, support 3%; cap 10000; support excludes salary >=20000. These deliberately fictional rates are not UAE law.",
    ),
  );
  const scope = {
    authority: "SYNTHETIC-AUTHORITY",
    scheme: "SYNTHETIC-SCHEME",
    membership_cohort: "SYNTHETIC-CONTINUING",
    pension_country: "AE",
    nationality: "AE",
    employment_sector: "private",
    jurisdiction: "AE-DU",
  };
  const bases = ["EMPLOYEE", "EMPLOYER", "GOVERNMENT"].map((component) => ({
    ...scope,
    id: `B-${component}`,
    registration: "SYNTHETIC-ESTABLISHMENT",
    subject: "SYNTHETIC-PERSON",
    period: "2026-06",
    component: `PENSION:${component}`,
    currency: "AED",
    amount: component === "GOVERNMENT" ? "20000" : "19999.99",
    eligible: true,
    membership_reference: "SYNTHETIC-CONTINUITY",
    salary_basis_reference: `SYNTHETIC-SALARY-${component}`,
    evidence_reference: "SYNTHETIC-PAYROLL",
    assessment:
      "SYNTHETIC contradictory declared salaries retained for rejection",
  }));
  const rules = ["EMPLOYEE", "EMPLOYER", "GOVERNMENT"].map((component, i) => ({
    ...scope,
    id: `RULE-${component}`,
    component: `PENSION:${component}`,
    effective_from: "2026-01-01",
    effective_to: "2026-12-31",
    formula: component === "EMPLOYER" ? "employer-minus-government" : "rate",
    rate: ["0.07", "0.18", "0.03"][i],
    rounding: "nearest-fils",
    minimum_basis: "1000",
    salary_cap: "10000",
    exclusive_eligibility_ceiling: component === "GOVERNMENT" ? "20000" : "",
    source_url: "https://synthetic.example/pension-rule",
    source_sha256: ruleFile.version.sha256,
    source_evidence_version_id: ruleFile.version.id,
    source_version: "SYNTHETIC-1",
    evidence_reference: "SYNTHETIC-RULE",
    applicability_review:
      "SYNTHETIC independently assessed arithmetic, no statutory rule adoption",
  }));
  const reported = bases.map((basis, i) => ({
    ...scope,
    id: `R-${i}`,
    registration: basis.registration,
    subject: basis.subject,
    period: basis.period,
    component: basis.component,
    currency: "AED",
    amount: ["700", "1800", "0"][i],
    evidence_reference: "SYNTHETIC-REPORTED-CONTRIBUTIONS",
  }));
  const csv = (rows: Record<string, unknown>[]) => {
    const keys = Object.keys(rows[0]);
    const quote = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    return (
      [
        keys.map(quote).join(","),
        ...rows.map((r) => keys.map((k) => quote(r[k])).join(",")),
      ].join("\n") + "\n"
    );
  };
  const sources: Record<string, string> = {};
  for (const [role, table, rows, totals] of [
    ["bases", "pension-bases", bases, { AED: "59999.98" }],
    ["rules", "pension-rules", rules, {}],
    ["reported", "pension-reported", reported, { AED: "2500" }],
  ] as const) {
    const file = await evidence(
      `SYNTHETIC-pension-${role}.csv`,
      Buffer.from(csv(rows)),
    );
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: table,
      expected_rows: 3,
      control_totals: totals,
      label: `SYNTHETIC pension ${role}`,
    });
    const reviewed = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independent observation review; contradictory declarations do not establish compliant pension amounts",
      },
    );
    sources[role] = reviewed.id;
  }
  const result = await prepare(
    {
      workflow: "uae-pension-review",
      source_ids: sources,
      currency: "AED",
      as_of: "2026-06-30",
      title: "SYNTHETIC pension salary contradiction",
      rationale:
        "Reported totals agree but support uses a different salary; no matched employer contribution may be inferred",
    },
    "country-workflow",
  );
  expect(result.body.blocked).toBe(true);
  expect(result.body.expected_total_complete).toBe(false);
  const employer = result.body.rows.find(
    (r) => r.component === "PENSION:EMPLOYER",
  );
  expect(employer).toMatchObject({
    assessed_base: "19999.99",
    government_assessed_base: "20000",
    expected_amount: null,
    state: "GOVERNMENT_SUPPORT_SALARY_BASIS_MISMATCH",
  });
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await expect(
    reviewer.getByRole("columnheader", {
      name: "government assessed base",
      exact: true,
    }),
  ).toBeVisible();
  const row = reviewer
    .getByRole("row")
    .filter({ hasText: "GOVERNMENT_SUPPORT_SALARY_BASIS_MISMATCH" });
  await expect(row).toHaveCount(1);
  await row
    .getByRole("cell", { name: "20000", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    row.getByRole("cell", { name: "19999.99", exact: true }),
  ).toBeVisible();
  await expect(
    row.getByRole("cell", { name: "20000", exact: true }),
  ).toBeVisible();
  await reviewer.screenshot({
    path: `${screenshots}/AE-pension-conflicting-salary-bases.png`,
    fullPage: false,
  });
  const approval = reviewer.getByRole("button", {
    name: "Independent approval",
    exact: true,
  });
  await expect(approval).toBeDisabled();
  await approval.screenshot({
    path: `${screenshots}/AE-pension-conflicting-salary-approval-disabled.png`,
  });
}
