import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Paper } from "@/features/grc-forms";

const mock = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutate: mock.mutate, isPending: false }),
}));
import { ComplianceFiling } from "@/features/compliance-filing";

const paper: Paper = {
  kind: "grc-obligation",
  id: "record",
  version: 7,
  reference: "SYN-FILING",
  title: "Synthetic obligation",
  status: "APPROVED",
  body: { filing_stage: "approved_for_submission", deadline: null },
};
beforeEach(() => mock.mutate.mockClear());

it.each(["AE", "IN"])(
  "retains all comparison triggers and blocks a missing candidate period for %s",
  (country) => {
    render(
      <ComplianceFiling
        base="grc/engagements/scoped"
        paper={{
          ...paper,
          body: {
            filing_stage: "under_review",
            deadline: "2027-03-31",
            rule_evidence_id: "independent-rule",
            jurisdiction_scope: {
              entity_country: country,
              obligation_country: country,
              relationship: "domestic",
              applicability: "assessed_applicable",
            },
            deadline_rule: {
              identifier: "SYN-notice",
              date_basis: "specified_event",
              trigger: "2026-12-01",
              months_after: 1,
              timezone: country === "AE" ? "Asia/Dubai" : "Asia/Kolkata",
              later_of: [
                {
                  identifier: "SYN-period",
                  date_basis: "period_end",
                  trigger: "2026-12-31",
                  months_after: 3,
                },
              ],
            },
          },
        }}
      />,
    );
    const comparison = screen.getByRole("region", {
      name: "Later-of deadline comparison",
    });
    expect(comparison).toHaveTextContent("SYN-notice");
    expect(comparison).toHaveTextContent("SYN-period");
    expect(comparison).toHaveTextContent("2026-12-01");
    expect(comparison).toHaveTextContent("2026-12-31");
    expect(comparison).toHaveTextContent("independent-rule");
    expect(comparison).toHaveTextContent(
      "legal applicability require independent review",
    );
    expect(
      screen.getByRole("button", { name: "Record evidenced filing stage" }),
    ).toBeDisabled();
  },
);

it.each(["AE", "IN"])(
  "shows the explicit business-day calendar and trigger treatment for %s",
  (country) => {
    render(
      <ComplianceFiling
        base="grc/engagements/scoped"
        paper={{
          ...paper,
          body: {
            filing_stage: "preparing",
            jurisdiction: country,
            deadline: "2026-07-06",
            calendar_evidence_id: "separate-calendar",
            deadline_rule: {
              day_count_basis: "business",
              days_after: 5,
              trigger: "2026-06-26",
              business_trigger_policy: "exclude",
              timezone: country === "AE" ? "Asia/Dubai" : "Asia/Kolkata",
              business_calendar: {
                coverage_start: "2026-06-01",
                coverage_end: "2026-07-31",
                weekend_days: [5, 6],
                holidays: ["2026-06-29"],
                independent_holiday_count: 1,
                assessment:
                  "Synthetic independently assessed complete calendar",
              },
            },
          },
        }}
      />,
    );
    const section = screen.getByRole("region", {
      name: "Business-day deadline basis",
    });
    expect(section).toHaveTextContent("exclude the triggering day");
    expect(section).toHaveTextContent("Saturday, Sunday");
    expect(section).toHaveTextContent("2026-06-01 to 2026-07-31");
    expect(section).toHaveTextContent("2026-06-29");
    expect(section).toHaveTextContent("separate-calendar");
    expect(section).toHaveTextContent(
      "does not verify national holidays or legal applicability",
    );
  },
);

it.each([0, undefined])(
  "distinguishes a declared zero from a missing holiday control (%s)",
  (count) => {
    render(
      <ComplianceFiling
        base="grc/engagements/scoped"
        paper={{
          ...paper,
          body: {
            deadline_rule: {
              day_count_basis: "business",
              business_calendar: {
                holidays: [],
                independent_holiday_count: count,
              },
            },
          },
        }}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Business-day deadline basis" }),
    ).toHaveTextContent(
      count === 0
        ? "Explicitly none"
        : "Empty list without an independent zero control",
    );
  },
);

it("requires actual submission evidence and retains the scoped version", () => {
  render(<ComplianceFiling base="grc/engagements/scoped" paper={paper} />);
  expect(screen.getByText(/Deadline: Unresolved/)).toBeVisible();
  const button = screen.getByRole("button", {
    name: "Record evidenced filing stage",
  });
  expect(button).toBeDisabled();
  const id = "11111111-1111-4111-8111-111111111111";
  fireEvent.change(
    screen.getByLabelText("Actual submission evidence record ID"),
    { target: { value: id } },
  );
  fireEvent.click(button);
  expect(mock.mutate).toHaveBeenCalledWith({
    path: "grc/engagements/scoped/obligations/record/filing-stage",
    body: { version: 7, stage: "submitted", submission_evidence_id: id },
  });
});

it("keeps acknowledgment evidence separate from a submission", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{ ...paper, body: { filing_stage: "submitted" } }}
    />,
  );
  expect(
    screen.getByLabelText("Separate acknowledgment evidence record ID"),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("returns an approved filing to preparing without replacing retained receipts", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "acknowledged",
          jurisdiction: "AE",
          submission_evidence_id: "saved-submission",
          acknowledgment_evidence_id: "saved-ack",
        },
      }}
    />,
  );
  expect(screen.getByText(/Jurisdiction: AE/)).toBeVisible();
  expect(screen.getByText("saved-submission")).toBeVisible();
  expect(screen.getByText("saved-ack")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Next filing stage"), {
    target: { value: "preparing" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  );
  expect(mock.mutate).toHaveBeenCalledWith({
    path: "grc/engagements/scoped/obligations/record/filing-stage",
    body: { version: 7, stage: "preparing" },
  });
});

it("requires reopening locked records and does not offer an enabled transition", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{ ...paper, status: "LOCKED" }}
    />,
  );
  expect(screen.getByText(/Reopen the locked record/)).toBeVisible();
  expect(screen.getByLabelText("Next filing stage")).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("rejects a 36-character non-UUID receipt", () => {
  render(<ComplianceFiling base="grc/engagements/scoped" paper={paper} />);
  fireEvent.change(
    screen.getByLabelText("Actual submission evidence record ID"),
    { target: { value: "-".repeat(36) } },
  );
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("requires the stage-specific permission for approval and management", () => {
  const { rerender } = render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{ ...paper, body: { filing_stage: "under_review" } }}
      canApprove={false}
      canManage
    />,
  );
  expect(screen.getByText(/filing approval permission/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Next filing stage"), {
    target: { value: "preparing" },
  });
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeEnabled();
  rerender(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={paper}
      canApprove
      canManage={false}
    />,
  );
  expect(screen.getByText(/filing management permission/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("keeps entity country and foreign obligation country distinct and blocks unassessed filing approval", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "under_review",
          jurisdiction: "IN",
          jurisdiction_scope: {
            entity_country: "AE",
            obligation_country: "IN",
            relationship: "foreign",
            applicability: "potential",
          },
        },
      }}
    />,
  );
  expect(screen.getByText(/Declared entity country: AE/)).toHaveTextContent(
    "Obligation country: IN",
  );
  expect(screen.getByText(/Assess country applicability/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Next filing stage"), {
    target: { value: "preparing" },
  });
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeEnabled();
});

it("shows the explicit obligation period without substituting the home engagement year", () => {
  const { rerender } = render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "under_review",
          jurisdiction: "IN",
          obligation_period_start: "2025-04-01",
          obligation_period_end: "2026-03-31",
          jurisdiction_scope: {
            entity_country: "AE",
            obligation_country: "IN",
            relationship: "foreign",
            applicability: "assessed_applicable",
          },
        },
      }}
    />,
  );
  expect(
    screen.getByText(/Obligation period: 2025-04-01 to 2026-03-31/),
  ).toBeVisible();
  rerender(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "under_review",
          jurisdiction: "IN",
          jurisdiction_scope: {
            entity_country: "AE",
            obligation_country: "IN",
            relationship: "foreign",
            applicability: "potential",
          },
        },
      }}
    />,
  );
  expect(screen.getByText(/Obligation period: Not specified/)).toBeVisible();
});

it("flags a historical country-scoped period rule without inventing a period", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "under_review",
          jurisdiction: "IN",
          deadline_rule: { date_basis: "period_end" },
          jurisdiction_scope: {
            entity_country: "AE",
            obligation_country: "IN",
            relationship: "foreign",
            applicability: "assessed_applicable",
          },
        },
      }}
    />,
  );
  expect(
    screen.getByText(/Record the explicit obligation period/),
  ).toBeVisible();
  expect(screen.getByText(/Obligation period: Not specified/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});
