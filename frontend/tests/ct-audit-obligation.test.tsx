import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CTAuditObligationNotice } from "@/features/ct-audit-obligation";
describe("CT audit obligation", () => {
  it("preserves unknown revenue and obligation without displaying a zero or exemption", () => {
    render(
      <CTAuditObligationNotice
        result={{
          audit_statement_obligation: {
            assessment: "REVIEW_REQUIRED",
            decision: "MD84-2025",
            source_url: "https://mof.gov.ae/",
            required_for_ct: null,
            threshold_revenue: null,
            statement_kind: "AUDITED_FINANCIAL_STATEMENTS",
            declared_required: false,
            evidence_record_id: null,
            issues: ["Assess scoped revenue"],
          },
        }}
      />,
    );
    expect(screen.getAllByText("Not assessed")).toHaveLength(2);
    expect(screen.getByText("Assess scoped revenue")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Read MD84-2025" }),
    ).toHaveAttribute("href", "https://mof.gov.ae/");
    expect(screen.getByText(/Company-law, licensing/)).toBeTruthy();
  });
  it("does not invent an audit assessment for a legacy run", () => {
    render(<CTAuditObligationNotice result={{ current_tax: "0" }} />);
    expect(
      screen.queryByLabelText("CT audited statements obligation"),
    ).toBeNull();
  });
});
