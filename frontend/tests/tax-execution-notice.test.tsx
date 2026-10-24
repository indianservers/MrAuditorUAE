import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TaxExecutionNotice } from "@/features/tax-execution-notice";

describe("tax execution state separation", () => {
  it("discloses legacy provenance without manufacturing a status", () => {
    render(<TaxExecutionNotice result={{ current_tax: "0" }} />);
    expect(
      screen.getByText(/Legacy tax execution metadata is incomplete/),
    ).toBeInTheDocument();
  });
  it("keeps calculation, review, filing and payment states separate", () => {
    render(
      <TaxExecutionNotice
        result={{
          tax_execution: {
            tax_type: "CT",
            input_completeness: "partial",
            source_snapshots: [{ id: "synthetic" }],
            unresolved_questions: ["Missing relief election"],
            rounding: "Explicit rounding",
          },
        }}
      />,
    );
    expect(screen.getByText(/Input completeness: partial/)).toBeInTheDocument();
    expect(screen.getByText(/Filing: not submitted/)).toBeInTheDocument();
    expect(screen.getByText("Missing relief election")).toBeInTheDocument();
  });
});
