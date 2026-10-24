import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccountingExecutionNotice } from "@/features/accounting-execution-notice";

describe("accounting execution controls", () => {
  it("requires provenance regeneration for historical runs", () => {
    render(<AccountingExecutionNotice />);
    expect(screen.getByRole("status")).toHaveTextContent("regenerate");
  });
  it("shows draft posting state separately from reviewed inputs and unresolved issues", () => {
    render(
      <AccountingExecutionNotice
        receipt={{
          framework: "full_ifrs",
          functional_currency: "AED",
          presentation_currency: "AED",
          source_completeness: "partial",
          unresolved_issues: [
            {
              code: "ACTUARIAL_INPUTS_MISSING",
              remediation: "Supply reviewed expert inputs",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/At calculation: draft/)).toHaveTextContent(
      "journals not posted",
    );
    expect(
      screen.getByText(/Source completeness: partial/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Supply reviewed expert inputs/),
    ).toBeInTheDocument();
  });
});
