import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  EMPTY_NATIVE_WITHHOLDING,
  nativeWithholdingPayload,
  NativeWithholdingSource,
  NativeWithholdingLinks,
  NativeWithholdingChallans,
} from "@/features/native-withholding-source";

const value = {
  ...EMPTY_NATIVE_WITHHOLDING,
  tan: "MUMN77777A",
  financial_year: "202021",
  quarter: "Q1",
  observed_on: "2026-10-30",
  record_status: "current",
  crosswalk_document_version_id: "SYN-CROSSWALK",
  assessment: "Independent synthetic native file and crosswalk assessment",
  batch_count: "1",
  challan_count: "1",
  party_count: "1",
  income_tax: "100",
  surcharge: "0",
  cess: "0",
  allocated_deposit: "100",
  challan_deposit: "1000",
  payment_base: "1000",
  groups: JSON.stringify([
    {
      transaction_reference: "SYN-1",
      transaction_date: "2020-04-01",
      period: "2020-04",
      rule_reference: "SYN-ASSESSED",
      party_records: ["1/1/1"],
    },
  ]),
};

describe("native withholding controls", () => {
  it("shows each challan once and preserves leading-zero references and distinct gross/allocated amounts", () => {
    render(
      <NativeWithholdingChallans
        rows={[
          {
            batch: 1,
            challan: 1,
            challan_number: "00078",
            bsr_or_form24g_reference: "0000809",
            gross_deposit: "100000.00",
            allocated_deposit: "1900.00",
          },
        ]}
      />,
    );
    expect(
      screen
        .getByRole("table", { name: "Native withholding challans" })
        .querySelectorAll("tbody tr"),
    ).toHaveLength(1);
    expect(screen.getByText("0000809")).toBeInTheDocument();
    expect(screen.getByText("100000.00")).toBeInTheDocument();
    expect(screen.getByText("1900.00")).toBeInTheDocument();
    expect(
      screen.getByText(/not verified bank or CSI receipts/),
    ).toBeInTheDocument();
  });
  it("keeps prepared tax, allocated deposit and challan gross separate without floating point conversion", () => {
    expect(nativeWithholdingPayload(value, "26Q", "1")).toMatchObject({
      income_tax: "100",
      allocated_deposit: "100",
      challan_deposit: "1000",
      party_count: 1,
    });
    expect(nativeWithholdingPayload(value, "26Q", "1")).not.toHaveProperty(
      "purchase_value",
    );
  });
  it.each([
    "surcharge",
    "cess",
    "record_status",
    "crosswalk_document_version_id",
  ])("requires an explicit %s rather than supplying defaults", (field) => {
    expect(() =>
      nativeWithholdingPayload({ ...value, [field]: "" }, "26Q", "1"),
    ).toThrow();
  });
  it("rejects successor periods, decimal counts, inconsistent group totals and invalid JSON", () => {
    for (const change of [
      { financial_year: "202627" },
      { party_count: "1.1" },
      { groups: "{}" },
      { groups: "invalid" },
    ])
      expect(() =>
        nativeWithholdingPayload({ ...value, ...change }, "26Q", "1"),
      ).toThrow();
    expect(() => nativeWithholdingPayload(value, "26Q", "2")).toThrow(
      "Expected source rows",
    );
    expect(() => nativeWithholdingPayload(value, "27EQ", "1")).toThrow(
      "purchase value",
    );
  });
  it("collects separate clean-document selection and explicit status without inferring filing", () => {
    const changed = vi.fn();
    render(
      <NativeWithholdingSource
        value={value}
        onChange={changed}
        form="26Q"
        documents={[
          { id: "SYN-CROSSWALK", label: "Retained separate mapping" },
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText("Native income tax control (INR)"), {
      target: { value: "100.01" },
    });
    expect(changed).toHaveBeenCalledWith({ ...value, income_tax: "100.01" });
    expect(screen.getByText(/does not establish filing/)).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Native purchase value control (INR)"),
    ).not.toBeInTheDocument();
  });
  it("pages complete party lineage and resets the page on an exact group filter", () => {
    const rows = Array.from({ length: 121 }, (_, i) => ({
      group_id: i < 120 ? "G1" : "G2",
      party_key: `1/1/${i + 1}`,
      source_line: i + 4,
      total_tax: "100.00",
      allocated_deposit: "90.00",
    }));
    render(<NativeWithholdingLinks rows={rows} />);
    const table = screen.getByRole("table", {
      name: "Native withholding party links",
    });
    expect(within(table).getAllByRole("row")).toHaveLength(101);
    fireEvent.click(screen.getByRole("button", { name: "Next native links" }));
    expect(screen.getByText("Links 101–121 of 121")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Native group ID filter"), {
      target: { value: "G2" },
    });
    expect(screen.getByText("Links 1–1 of 1")).toBeInTheDocument();
    expect(screen.getByText("1/1/121")).toBeInTheDocument();
  });
});
