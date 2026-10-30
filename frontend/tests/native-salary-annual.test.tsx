import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NativeSalaryAnnualDetails } from "@/features/native-salary-annual";
import {
  EMPTY_NATIVE_WITHHOLDING,
  NativeWithholdingSource,
  nativeWithholdingPayload,
  salaryAnnualPayload,
} from "@/features/native-withholding-source";

function annualFixture() {
  return {
    contract: "historical-salary-annual-observations/1",
    controls: {
      assessment: "SYNTHETIC independent complete annual assessment",
    },
    record_counts: { SD: 201, S16: 0, C6A: 0, "94P": 1, P16: 0, P6A: 0 },
    totals: { salary_shortfall: "-1600.00", pension_gross_income: "49000.00" },
    columns: {
      SD: Array.from({ length: 88 }, (_, i) => ({
        number: i + 1,
        label: `Original salary field ${i + 1}`,
      })),
      "94P": Array.from({ length: 28 }, (_, i) => ({
        number: i + 1,
        label: `Original senior field ${i + 1}`,
      })),
    },
    records: Array.from({ length: 202 }, (_, i) => ({
      source_line: i + 5,
      record_type: i === 201 ? "94P" : "SD",
      batch: 1,
      parent_record: i + 1,
      record_number: i + 1,
      pan: "SYN-PAN",
      fields: Array.from({ length: i === 201 ? 28 : 88 }, (_, n) =>
        n === 17
          ? "-1000.00"
          : n === 87
            ? "SYN-last-88"
            : n === 0
              ? String(i + 5)
              : "",
      ),
    })),
  };
}

describe("complete annual salary records", () => {
  it("pages every original record and all numbered fields independently", () => {
    render(<NativeSalaryAnnualDetails annual={annualFixture()} />);
    expect(screen.getByText("-1600.00")).toBeVisible();
    expect(
      screen
        .getByRole("table", { name: "Annual original records" })
        .querySelectorAll("tbody tr"),
    ).toHaveLength(100);
    fireEvent.click(
      screen.getByRole("button", { name: "Next annual records" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Next annual records" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Inspect annual line 205" }),
    );
    for (let n = 0; n < 3; n++)
      fireEvent.click(
        screen.getByRole("button", { name: "Next annual fields" }),
      );
    expect(screen.getByText(/Fields 76–88 of 88/)).toBeVisible();
    expect(screen.getByText("SYN-last-88")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Annual record type"), {
      target: { value: "94P" },
    });
    expect(
      screen.getByRole("heading", {
        name: "Original 94P fields — source line 206",
      }),
    ).toBeVisible();
    expect(screen.getByText(/Fields 1–25 of 28/)).toBeVisible();
    expect(screen.queryByText("SYN-last-88")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next annual records" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Annual record type"), {
      target: { value: "P6A" },
    });
    expect(screen.getByText("No records of this annual type.")).toBeVisible();
  });
  it("keeps empty fields distinct from recorded zero and a signed amount", () => {
    const annual = annualFixture();
    annual.records = annual.records.slice(0, 1);
    annual.records[0].fields[1] = "0.00";
    render(<NativeSalaryAnnualDetails annual={annual} />);
    const table = screen.getByRole("table", {
      name: "Annual numbered source fields",
    });
    expect(within(table).getByText("0.00")).toBeVisible();
    expect(within(table).getByText("-1000.00")).toBeVisible();
    expect(within(table).getAllByText("Not recorded").length).toBeGreaterThan(
      0,
    );
  });
  it("exposes missing saved annual data instead of rendering a partial healthy table", () => {
    render(
      <NativeSalaryAnnualDetails
        annual={{
          contract: "historical-salary-annual-observations/1",
          records: [{ fields: ["1"] }],
        }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("unavailable");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
  it("requires all six independent annual counts and a distinct Q4 payload", () => {
    const value = {
      ...EMPTY_NATIVE_WITHHOLDING,
      tan: "MUMN77777A",
      financial_year: "202425",
      quarter: "Q4",
      observed_on: "2026-10-31",
      record_status: "current",
      crosswalk_document_version_id: "SYN-crosswalk",
      assessment: "SYNTHETIC independent quarterly and annual assessment",
      batch_count: "1",
      challan_count: "1",
      party_count: "1",
      income_tax: "1000",
      surcharge: "0",
      cess: "0",
      allocated_deposit: "1000",
      challan_deposit: "1000",
      payment_base: "10000",
      groups: JSON.stringify([{ party_records: ["1/1/1"] }]),
      annual_controls: JSON.stringify({
        record_counts: { SD: 1, S16: 1, C6A: 1, "94P": 1, P16: 1, P6A: 1 },
      }),
    };
    expect(nativeWithholdingPayload(value, "24Q-Q4", "1")).toMatchObject({
      quarter: "Q4",
      financial_year: "202425",
    });
    expect(nativeWithholdingPayload(value, "24Q-Q4", "1")).not.toHaveProperty(
      "salary_annual_controls",
    );
    expect(salaryAnnualPayload(value.annual_controls).record_counts.P6A).toBe(
      1,
    );
    expect(() => salaryAnnualPayload('{"record_counts":{"SD":1}}')).toThrow(
      /all six/,
    );
    expect(() =>
      nativeWithholdingPayload({ ...value, quarter: "Q3" }, "24Q-Q4", "1"),
    ).toThrow(/Q4/);
    render(
      <NativeWithholdingSource
        form="24Q-Q4"
        value={value}
        onChange={vi.fn()}
        documents={[]}
      />,
    );
    expect(
      screen.queryByRole("option", { name: "Q3" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Annual salary populations and totals (JSON)"),
    ).toHaveValue(value.annual_controls);
  });
});
