import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import {
  AnnualGSTScopeForm,
  AnnualGSTResult,
  annualGSTPayload,
  emptyAnnualGST,
} from "@/features/annual-gst-scope";

it("keeps absent turnover distinct from exact zero and retains decimal input strings", () => {
  const value = emptyAnnualGST();
  expect(annualGSTPayload(value)).toEqual({});
  value.enabled = true;
  expect(annualGSTPayload(value).gst_annual_scope).toMatchObject({
    aggregate_turnover: null,
    other_pan_turnover: null,
    pan_population_complete: false,
  });
  value.aggregate_turnover = "50000000.00000001";
  value.other_pan_turnover = "0";
  expect(annualGSTPayload(value).gst_annual_scope).toMatchObject({
    aggregate_turnover: "50000000.00000001",
    other_pan_turnover: "0",
  });
});

it("collects explicit PAN, year, rule review and taxpayer facts without defaulting completeness", () => {
  function Harness() {
    const [value, setValue] = useState(emptyAnnualGST);
    return (
      <>
        <AnnualGSTScopeForm value={value} onChange={setValue} />
        <output aria-label="Synthetic annual payload">
          {JSON.stringify(annualGSTPayload(value))}
        </output>
      </>
    );
  }
  render(<Harness />);
  fireEvent.click(screen.getByRole("checkbox", { name: /Assess GSTR-9/ }));
  fireEvent.change(screen.getByLabelText("PAN", { exact: true }), {
    target: { value: "ABCDE1234F" },
  });
  fireEvent.change(screen.getByLabelText("Annual GST financial year start"), {
    target: { value: "2025-04-01" },
  });
  fireEvent.change(screen.getByLabelText("Annual GST financial year end"), {
    target: { value: "2026-03-31" },
  });
  fireEvent.change(screen.getByLabelText("Annual GST rule review date"), {
    target: { value: "2026-10-30" },
  });
  fireEvent.change(
    screen.getByLabelText("Assessed annual GST taxpayer status"),
    { target: { value: "regular" } },
  );
  const payload = JSON.parse(
    screen.getByLabelText("Synthetic annual payload").textContent || "{}",
  );
  expect(payload.gst_annual_scope).toMatchObject({
    pan: "ABCDE1234F",
    financial_year_start: "2025-04-01",
    financial_year_end: "2026-03-31",
    rule_review_date: "2026-10-30",
    taxpayer_type: "regular",
    pan_population_complete: false,
  });
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /PAN-wide population assessed complete/,
    }),
  );
  expect(
    JSON.parse(
      screen.getByLabelText("Synthetic annual payload").textContent || "{}",
    ).gst_annual_scope.pan_population_complete,
  ).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: /Assess GSTR-9/ }));
  expect(screen.getByLabelText("Synthetic annual payload")).toHaveTextContent(
    "{}",
  );
});

it("shows separate annual-return and self-certified reconciliation candidates with pending reasons", () => {
  render(
    <AnnualGSTResult
      value={{
        gstr9: "PENDING_REVIEW",
        gstr9c: "PENDING_REVIEW",
        registration_turnover: "50000000.00000001",
        pending_reasons: ["PAN_TURNOVER_CONTROL_MISSING"],
        limitations: ["Independent professional review remains required"],
      }}
    />,
  );
  const result = screen.getByRole("region", {
    name: "Annual GST applicability candidates",
  });
  expect(result).toHaveTextContent(
    "GSTR-9: PENDING_REVIEW. GSTR-9C: PENDING_REVIEW.",
  );
  expect(result).toHaveTextContent("50000000.00000001 INR");
  expect(result).toHaveTextContent("PAN_TURNOVER_CONTROL_MISSING");
  expect(result).toHaveTextContent("Filing is not established");
});
