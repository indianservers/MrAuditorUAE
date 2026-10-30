import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import {
  ADGMAccountsResult,
  type ADGMAccountsAssessment,
} from "@/features/adgm-accounts-result";

const assessed: ADGMAccountsAssessment = {
  profile: "SYNTHETIC-profile",
  state: "TIMETABLE_ON_ASSESSED_FACTS",
  filing_required: true,
  company_status_at_reference_end: "private",
  accounting_reference_start: "2025-07-01",
  accounting_reference_end: "2026-06-30",
  period_classification: "subsequent",
  shortened_period: "assessed_no",
  assessed_on: "2026-10-31",
  issues: [],
};

it("shows the reference period and retained status without claiming accounts acceptance", () => {
  render(
    <ADGMAccountsResult assessment={assessed} available freshness="CURRENT" />,
  );
  const region = screen.getByRole("region", {
    name: "ADGM accounts timetable assessment",
  });
  expect(region).toHaveTextContent("2025-07-01 to 2026-06-30");
  expect(region).toHaveTextContent("Required on assessed facts");
  expect(region).toHaveTextContent("can differ from the accounts period end");
  expect(region).toHaveTextContent(
    "does not establish a complete accounts or audit pack",
  );
});

it("does not reuse a previous version's determination while verification is pending", () => {
  render(<ADGMAccountsResult assessment={assessed} available={false} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "No filing duty, exemption or timetable is inferred",
  );
  expect(screen.queryByText("Required on assessed facts")).toBeNull();
});

it("retains the historical assessment with a stale-source warning", () => {
  render(
    <ADGMAccountsResult assessment={assessed} available freshness="STALE" />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Reassess the original source documents",
  );
  expect(screen.getByText("Required on assessed facts")).toBeVisible();
});

it("distinguishes an assessed exemption from unresolved applicability", () => {
  const { rerender } = render(
    <ADGMAccountsResult
      assessment={{ ...assessed, filing_required: false }}
      available
      freshness="CURRENT"
    />,
  );
  expect(screen.getByText("Assessed exempt; no filing deadline")).toBeVisible();
  rerender(
    <ADGMAccountsResult
      assessment={{
        ...assessed,
        filing_required: null,
        issues: ["SECTION_415_FILING_DUTY_AND_EXCEPTIONS_REQUIRE_ASSESSMENT"],
      }}
      available
      freshness="CURRENT"
    />,
  );
  expect(screen.getByText("Unresolved")).toBeVisible();
  expect(
    screen.getByRole("list", { name: "Unresolved ADGM timetable issues" }),
  ).toHaveTextContent("SECTION 415");
  expect(screen.queryByText("Assessed exempt; no filing deadline")).toBeNull();
});
