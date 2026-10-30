import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WithholdingPANReview } from "@/features/withholding-pan-review";

const contract = "withholding-missing-pan-treatment/1";
const base = {
  id: "SYN-1",
  transaction_reference: "SYN-TX-1",
  legal_role: "collector",
  period: "2026-05",
  counterparty: "PANNOTAVBL",
  pan_status: "PANNOTAVBL",
  pan_authentication: "NOT_PERFORMED",
};
describe("missing PAN treatment review", () => {
  it("keeps matching amounts separate from pending identity/treatment", () => {
    render(
      <WithholdingPANReview
        contract={contract}
        counts={{ rows_with_marker: 1, pending_rows: 1, documented_rows: 0 }}
        rows={[
          {
            ...base,
            pan_treatment_state: "PENDING_ASSESSMENT",
            pan_issues: ["PAN_TREATMENT_ASSESSMENT_MISSING"],
          },
        ]}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Row exception notes do not resolve",
    );
    expect(
      screen.getByRole("region", { name: "Missing PAN treatment review" }),
    ).toHaveTextContent("NOT_PERFORMED");
    expect(
      screen.getByText(
        "Complete result: 1 marker rows; 1 pending; 0 documented.",
      ),
    ).toBeVisible();
  });
  it("retains document/reference scope without claiming PAN authentication", () => {
    render(
      <WithholdingPANReview
        contract={contract}
        counts={{ rows_with_marker: 1, pending_rows: 0, documented_rows: 1 }}
        rows={[
          {
            ...base,
            pan_treatment_state: "DOCUMENTED_ON_RETAINED_ASSESSMENT",
            pan_issues: [],
            pan_treatment: {
              party_reference: "SYN-PARTY-01",
              treatment_reference: "SYN-RULE-01",
              assessed_on: "2026-06-01",
              assessment: "SYNTHETIC professionally assessed facts only",
            },
            assessment_provenance: {
              assessment_evidence_version_id: "SYN-DOC-VERSION",
              assessment_sha256: "a".repeat(64),
            },
          },
        ]}
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Review party and treatment evidence"));
    expect(screen.getByText("SYN-PARTY-01")).toBeVisible();
    expect(screen.getByText("SYN-DOC-VERSION")).toBeVisible();
    expect(screen.getByText("a".repeat(64))).toBeVisible();
    expect(screen.getByText(/does not authenticate PAN/)).toBeVisible();
  });
  it("shows complete-result pending counts when the affected row is on another page", () => {
    render(
      <WithholdingPANReview
        contract={contract}
        counts={{ rows_with_marker: 1, pending_rows: 1, documented_rows: 0 }}
        rows={[{ counterparty: "SYN-ORDINARY-PARTY" }]}
      />,
    );
    expect(screen.getByRole("alert")).toBeVisible();
    expect(
      screen.getByText(/No missing-PAN rows are on this page/),
    ).toBeVisible();
    expect(screen.getByText(/1 pending/)).toBeVisible();
  });
  it("requires regeneration for retained results without the current control", () => {
    render(<WithholdingPANReview rows={[{ counterparty: "PANINVALID" }]} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Regenerate this retained result",
    );
  });
  it("does not infer a missing PAN from an ordinary internal party identifier", () => {
    render(
      <WithholdingPANReview rows={[{ counterparty: "SYN-ERP-PARTY-01" }]} />,
    );
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
