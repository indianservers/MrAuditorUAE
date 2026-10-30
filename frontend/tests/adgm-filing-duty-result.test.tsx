import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { ADGMAccountsResult } from "@/features/adgm-accounts-result";
import {
  ADGMFilingDutyResult,
  type ADGMFilingDutyAssessment,
} from "@/features/adgm-filing-duty-result";

const assessed: ADGMFilingDutyAssessment = {
  procedure: "individual_accounts",
  filing_required: false,
  chapter_8_applies: true,
  unlimited_company_exemption: false,
  dormant_individual_accounts_exemption: true,
  supporting_documents_required: true,
  reason: "DORMANT_SUBSIDIARY_INDIVIDUAL_ACCOUNTS_EXEMPTION",
  missing_criteria: [],
  checks: Array.from({ length: 29 }, (_, index) => ({
    key: `SYNTHETIC-condition-${index}`,
    answer: "assessed_yes",
    evidence_ids: [`SYNTHETIC-original-${index}`],
    assessment: "SYNTHETIC independently assessed original for the exact year",
  })),
  supporting_documents: [
    "Written members agreement",
    "Authenticated parent guarantee",
    "Parent consolidated accounts",
    "Parent auditor report",
    "Parent consolidated annual report",
  ].map((title, index) => ({
    key: `SYNTHETIC-document-${index}`,
    title,
    delivery_assessment: "assessed_yes",
  })),
  limitations:
    "Conditions are independently assessed inputs, not registry authentication or proof of external delivery.",
};

it("keeps individual-accounts exemption separate from all five supporting filings", () => {
  render(<ADGMFilingDutyResult assessment={assessed} />);
  const region = screen.getByRole("region", {
    name: "ADGM filing duty conditions",
  });
  expect(region).toHaveTextContent(
    "Individual-accounts exemption does not remove the five supporting-document filings",
  );
  expect(
    within(
      within(region).getByRole("list", {
        name: "Dormant subsidiary supporting documents",
      }),
    ).getAllByRole("listitem"),
  ).toHaveLength(5);
  expect(region).toHaveTextContent(
    "Authenticated parent guarantee: assessed yes",
  );
  expect(region).toHaveTextContent(
    "Parent consolidated annual report: assessed yes",
  );
});

it("retains and displays all source-bound checks beyond twenty", () => {
  render(<ADGMFilingDutyResult assessment={assessed} />);
  const summary = screen.getByText(
    "Review source-bound filing-duty conditions (29)",
  );
  summary.click();
  const checks = screen.getByRole("list", {
    name: "Retained filing duty checks",
  });
  expect(within(checks).getAllByRole("listitem")).toHaveLength(29);
  expect(checks).toHaveTextContent("SYNTHETIC-original-28");
});

it("shows missing conditions and delivery as unresolved instead of a clean exemption", () => {
  render(
    <ADGMFilingDutyResult
      assessment={{
        ...assessed,
        filing_required: null,
        dormant_individual_accounts_exemption: null,
        missing_criteria: ["guarantee_authenticated"],
        supporting_documents: assessed.supporting_documents.map((item) => ({
          ...item,
          delivery_assessment: "unassessed",
        })),
      }}
    />,
  );
  expect(
    screen.getByText(/1 relevant conditions remain unassessed/),
  ).toBeVisible();
  expect(
    screen.getByRole("list", {
      name: "Dormant subsidiary supporting documents",
    }),
  ).toHaveTextContent("Authenticated parent guarantee: unassessed");
  expect(screen.getByText("Unresolved")).toBeVisible();
});

it("does not present missing current-version metadata as a previous v2 exemption", () => {
  render(
    <ADGMAccountsResult
      assessment={{
        profile: "SYNTHETIC-v2",
        state: "ASSESSED_NO_FILING_DUTY",
        filing_required: false,
        issues: [],
        filing_duty_assessment: assessed,
      }}
      available={false}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "No filing duty, exemption or timetable is inferred",
  );
  expect(
    screen.queryByRole("region", { name: "ADGM filing duty conditions" }),
  ).toBeNull();
});

it("retains the scoped v2 outcome and supporting duties with a stale-source warning", () => {
  render(
    <ADGMAccountsResult
      assessment={{
        profile: "SYNTHETIC-v2",
        state: "ASSESSED_NO_FILING_DUTY",
        filing_required: false,
        issues: [],
        filing_duty_assessment: assessed,
      }}
      available
      freshness="STALE"
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Reassess the original source documents",
  );
  expect(
    screen.getByText("Selected procedure not required on assessed facts"),
  ).toBeVisible();
  expect(screen.queryByText("Assessed exempt; no filing deadline")).toBeNull();
  expect(
    screen.getByRole("list", {
      name: "Dormant subsidiary supporting documents",
    }),
  ).toBeVisible();
});
