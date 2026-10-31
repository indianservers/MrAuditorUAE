import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { UAECTAuditDutyResult } from "@/features/uae-ct-audit-duty-result";

const sample = {
  registration: "SYNTHETIC-CT",
  period_start: "2026-01-01",
  period_end: "2026-09-30",
  audited_financial_statements_required: false,
  dated_source_requirement: false,
  statement_type: "NO_MD84_AUDIT_DUTY_ON_ASSESSED_FACTS",
  revenue_aed: "50000000",
  threshold_basis: "whole_person",
  revenue_exceeds_threshold: false,
  issues: [],
};

it("shows the exact threshold result without implying a company-law audit exemption", () => {
  render(<UAECTAuditDutyResult row={sample} />);
  const result = screen.getByRole("region", {
    name: "UAE corporate-tax audit duty summary",
  });
  expect(result).toHaveTextContent(
    "MD84 preparation and maintenance duty: Not required under the selected MD84 assessment",
  );
  expect(result).toHaveTextContent("AED 50000000");
  expect(result).toHaveTextContent(
    "Company-law and free-zone audit exemptions are not established",
  );
  expect(result).toHaveTextContent("2026-01-01 to 2026-09-30");
});

it("keeps unresolved current rules distinct from a positive dated-source branch and unknown revenue", () => {
  render(
    <UAECTAuditDutyResult
      row={{
        ...sample,
        audited_financial_statements_required: null,
        dated_source_requirement: true,
        statement_type: "AUDITED_SPECIAL_PURPOSE_FINANCIAL_STATEMENTS",
        revenue_aed: null,
        threshold_basis: "NOT_NEEDED_FOR_SELECTED_BRANCH",
        revenue_exceeds_threshold: null,
        tax_group_procedures:
          "SEPARATE_FTA_FORM_FRAMEWORK_AND_SUBMISSION_REQUIREMENTS",
        issues: ["OPERATIVE_RULE_CHANGES_UNRESOLVED"],
      }}
    />,
  );
  const result = screen.getByRole("region", {
    name: "UAE corporate-tax audit duty summary",
  });
  expect(result).toHaveTextContent(
    "MD84 preparation and maintenance duty: Unresolved",
  );
  expect(result).toHaveTextContent("Dated source assessmentRequired");
  expect(result).toHaveTextContent("Not established");
  expect(
    within(result).getByRole("list", {
      name: "Unresolved corporate-tax duty issues",
    }),
  ).toHaveTextContent("Changes to the operative rules remain unresolved");
  expect(result).toHaveTextContent(
    "This duty assessment does not complete them",
  );
});

it("preserves exact long AED values and treats string booleans as unresolved", () => {
  render(
    <UAECTAuditDutyResult
      row={{
        ...sample,
        audited_financial_statements_required: "false",
        revenue_aed: "12345678901234567890123456.78",
        revenue_exceeds_threshold: "false",
      }}
    />,
  );
  const result = screen.getByRole("region", {
    name: "UAE corporate-tax audit duty summary",
  });
  expect(result).toHaveTextContent(
    "MD84 preparation and maintenance duty: Unresolved",
  );
  expect(result).toHaveTextContent("AED 12345678901234567890123456.78");
  expect(result).toHaveTextContent("Not determined for this branch");
});

it("keeps explicitly reported zero distinct from absent revenue", () => {
  render(<UAECTAuditDutyResult row={{ ...sample, revenue_aed: "0" }} />);
  const result = screen.getByRole("region", {
    name: "UAE corporate-tax audit duty summary",
  });
  expect(within(result).getByText("AED 0", { exact: true })).toBeVisible();
  expect(
    within(result).queryByText("Not established", { exact: true }),
  ).not.toBeInTheDocument();
});
