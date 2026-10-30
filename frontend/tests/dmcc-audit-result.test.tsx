import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import {
  DMCCAuditResult,
  type DMCCAssessment,
} from "@/features/dmcc-audit-result";

const branch: DMCCAssessment = {
  profile: "retained-profile",
  state: "REQUIRED_ON_ASSESSED_FACTS",
  procedure: "portal_submission",
  legal_form: "branch",
  procedure_required: true,
  accounts_required: null,
  audit_required: null,
  group_accounts_required: null,
  approved_auditor_rule: "BRANCH_GROUP_AUDITOR_EXCEPTION_ASSESSED",
  assessed_on: "2026-06-30",
  issues: [],
  limitations:
    "Retained assessed facts; no registry authenticity qualification",
};
it("keeps a branch auditor exception separate from required portal submission", () => {
  render(<DMCCAuditResult assessment={branch} available freshness="CURRENT" />);
  const region = screen.getByRole("region", {
    name: "DMCC authority procedure assessment",
  });
  expect(within(region).getByText("Required on assessed facts")).toBeVisible();
  expect(region).toHaveTextContent("BRANCH GROUP AUDITOR EXCEPTION ASSESSED");
  expect(within(region).getAllByText("Unresolved")).toHaveLength(3);
  expect(region).toHaveTextContent(
    "separate from the UAE corporate-tax audit threshold",
  );
});
it("shows unknown applicability and unresolved issues rather than a false exemption", () => {
  render(
    <DMCCAuditResult
      assessment={{
        ...branch,
        state: "REVIEW_REQUIRED",
        procedure_required: null,
        issues: [
          "DORMANT_PORTAL_TREATMENT_REQUIRES_SEPARATE_AUTHORITY_ASSESSMENT",
        ],
      }}
      available
      freshness="CURRENT"
    />,
  );
  expect(
    screen.getByRole("list", { name: "Unresolved DMCC assessment issues" }),
  ).toHaveTextContent("DORMANT PORTAL TREATMENT");
  expect(screen.queryByText("Not required on assessed facts")).toBeNull();
});
it("does not treat unavailable current-version metadata as a determination", () => {
  render(<DMCCAuditResult assessment={branch} available={false} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "No requirement or exemption is inferred",
  );
  expect(screen.queryByText("Required on assessed facts")).toBeNull();
});
it("retains the assessed determination with a stale-source warning", () => {
  render(<DMCCAuditResult assessment={branch} available freshness="STALE" />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Reassess the retained source documents",
  );
  expect(screen.getByText("Required on assessed facts")).toBeVisible();
});
