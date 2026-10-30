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

describe("dated salary source", () => {
  const salary = {
    ...value,
    tax_year: "202627",
    tax_deducted: "100",
    challan_tax: "900",
    challan_interest: "50",
    challan_fee: "0",
    challan_penalty: "50",
    allocated_interest: "50",
    allocated_penalty: "50",
    date_width_assessment: "DD29_EIGHT_DIGIT_DATE_PER_NUMBERED_REMARKS",
  };
  it("requires the source-date assessment and excludes Q4", () => {
    const payload = nativeWithholdingPayload(salary, "138", "1");
    expect(payload).toMatchObject({
      tax_deducted: "100",
      challan_penalty: "50",
      date_width_assessment: salary.date_width_assessment,
    });
    expect(payload).not.toHaveProperty("financial_year");
    expect(payload).not.toHaveProperty("tax_collected");
    expect(() =>
      nativeWithholdingPayload({ ...salary, quarter: "Q4" }, "138", "1"),
    ).toThrow(/Q1–Q3/);
    expect(() =>
      nativeWithholdingPayload(
        { ...salary, date_width_assessment: "" },
        "138",
        "1",
      ),
    ).toThrow(/assessment/);
    render(
      <NativeWithholdingSource
        value={salary}
        onChange={vi.fn()}
        form="138"
        documents={[]}
      />,
    );
    expect(
      screen.queryByRole("option", { name: "Q4" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByLabelText(/Salary deposit-date source conflict assessment/),
    ).toHaveValue(salary.date_width_assessment);
    expect(
      screen.getByLabelText("Native challan penalty control (INR)"),
    ).toHaveValue("50");
  });
  it("shows deposit dates and penalty without invented rate or component tax", () => {
    render(
      <>
        <NativeWithholdingLinks
          rows={[
            {
              recorded_deposit_date: "2026-05-09",
              recorded_deposited_flag: "Y",
              total_tax: "100",
            },
          ]}
        />
        <NativeWithholdingChallans
          rows={[
            {
              recorded_payment_mode: "B",
              recorded_penalty: "50",
              allocated_penalty: "50",
            },
          ]}
        />
      </>,
    );
    const parties = screen.getByRole("table", {
      name: "Native withholding party links",
    });
    expect(within(parties).getByText("2026-05-09")).toBeVisible();
    expect(
      within(parties).queryByRole("columnheader", { name: "recorded rate" }),
    ).not.toBeInTheDocument();
    expect(
      within(parties).queryByRole("columnheader", { name: "income tax" }),
    ).not.toBeInTheDocument();
    const challans = screen.getByRole("table", {
      name: "Native withholding challans",
    });
    expect(
      within(challans).getByRole("columnheader", { name: "allocated penalty" }),
    ).toBeVisible();
    expect(
      within(challans).queryByRole("columnheader", { name: "recorded other" }),
    ).not.toBeInTheDocument();
  });
});

describe("historical salary source", () => {
  it("retains component tax and employee reference without a fabricated rate", () => {
    render(
      <NativeWithholdingLinks
        rows={[
          {
            recorded_employee_reference: "001",
            recorded_deposit_date: "2018-12-14",
            income_tax: "1000.00",
            surcharge: "0.00",
            cess: "0.00",
          },
        ]}
      />,
    );
    const table = screen.getByRole("table", {
      name: "Native withholding party links",
    });
    expect(
      within(table).getByRole("columnheader", { name: "income tax" }),
    ).toBeVisible();
    expect(
      within(table).getByRole("columnheader", {
        name: "recorded employee reference",
      }),
    ).toBeVisible();
    expect(within(table).getByText("001")).toBeVisible();
    expect(
      within(table).queryByRole("columnheader", { name: "recorded rate" }),
    ).not.toBeInTheDocument();
    expect(
      within(table).queryByRole("columnheader", {
        name: "recorded deposited flag",
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Form 138 salary dates/)).not.toBeInTheDocument();
  });
  it("uses historical controls and requires a separate Q4 salary format", () => {
    expect(nativeWithholdingPayload(value, "24Q", "1")).toMatchObject({
      financial_year: "202021",
      income_tax: "100",
    });
    expect(() =>
      nativeWithholdingPayload({ ...value, quarter: "Q4" }, "24Q", "1"),
    ).toThrow(/annual salary/);
    render(
      <NativeWithholdingSource
        value={value}
        onChange={vi.fn()}
        form="24Q"
        documents={[]}
      />,
    );
    expect(
      screen.queryByRole("option", { name: "Q4" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Native financial year (six digits)"),
    ).toHaveValue("202021");
  });
});

describe("native withholding controls", () => {
  it("separates dated Form 143 controls from legacy component and financial-year inputs", () => {
    const dated = {
      ...value,
      tax_year: "202627",
      tax_collected: "700",
      challan_tax: "210000",
      challan_interest: "1000",
      challan_fee: "1000",
      challan_other: "1000",
      allocated_interest: "1000",
      allocated_other: "1000",
    };
    const payload = nativeWithholdingPayload(dated, "143", "1");
    expect(payload).toMatchObject({
      tax_year: "202627",
      tax_collected: "700",
      allocated_interest: "1000",
    });
    for (const field of [
      "financial_year",
      "income_tax",
      "surcharge",
      "cess",
      "purchase_value",
    ])
      expect(payload).not.toHaveProperty(field);
    expect(() =>
      nativeWithholdingPayload({ ...dated, tax_year: "202728" }, "143", "1"),
    ).toThrow(/dated Form 143/);
    expect(() =>
      nativeWithholdingPayload(
        { ...dated, allocated_interest: "" },
        "143",
        "1",
      ),
    ).toThrow(/allocated interest/);
    expect(
      nativeWithholdingPayload({ ...dated, allocated_other: "0" }, "143", "1"),
    ).toMatchObject({ allocated_other: "0" });
    render(
      <NativeWithholdingSource
        value={dated}
        onChange={vi.fn()}
        form="143"
        documents={[]}
      />,
    );
    expect(screen.getByLabelText("Native tax year (six digits)")).toHaveValue(
      "202627",
    );
    expect(
      screen.queryByLabelText("Native financial year (six digits)"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("v1.2");
    expect(
      screen.queryByLabelText("Native income tax control (INR)"),
    ).not.toBeInTheDocument();
    expect(nativeWithholdingPayload(dated, "26Q", "1")).not.toHaveProperty(
      "tax_collected",
    );
  });
  it("shows Form 143 source flags and book mode without presenting bank settlement or invented component tax", () => {
    render(
      <>
        <NativeWithholdingLinks
          rows={[
            {
              party_key: "1/1/1",
              recorded_section202_opt_out: "N",
              recorded_nonresident_flag: "Y",
              recorded_pe_flag: "N",
              recorded_deposited_flag: "Y",
              total_tax: "700.00",
            },
          ]}
        />
        <NativeWithholdingChallans
          rows={[
            {
              recorded_payment_mode: "B",
              ddo_serial: "00001",
              allocated_interest: "1000.00",
              allocated_other: "1000.00",
            },
          ]}
        />
      </>,
    );
    const party = screen.getByRole("table", {
      name: "Native withholding party links",
    });
    expect(
      within(party).queryByRole("columnheader", { name: "income tax" }),
    ).not.toBeInTheDocument();
    expect(
      within(party).getByRole("columnheader", {
        name: "recorded deposited flag",
      }),
    ).toBeVisible();
    expect(
      screen.getByText(/They do not establish residence/),
    ).toHaveTextContent("bank payment");
    const challan = screen.getByRole("table", {
      name: "Native withholding challans",
    });
    expect(
      within(challan).queryByRole("columnheader", { name: "book entry flag" }),
    ).not.toBeInTheDocument();
    expect(within(challan).getByRole("cell", { name: "B" })).toBeVisible();
    expect(within(challan).getByRole("cell", { name: "00001" })).toBeVisible();
  });
  it("preserves nonresident source codes and blanks while distinguishing treaty claims from qualification", () => {
    render(
      <NativeWithholdingLinks
        rows={[
          {
            party_key: "1/1/1",
            group_id: "27Q:group:1",
            recorded_rate_basis: "B",
            nature_of_remittance_code: "021",
            residence_country_code: "113",
            foreign_tax_identifier: "0007-FOREIGN",
            form_15ca_reference: "",
          },
        ]}
      />,
    );
    const table = screen.getByRole("table", {
      name: "Native withholding party links",
    });
    expect(
      within(table).getByRole("columnheader", { name: "recorded rate basis" }),
    ).toBeVisible();
    expect(
      within(table).getByRole("cell", { name: "0007-FOREIGN" }),
    ).toBeVisible();
    expect(within(table).getByRole("cell", { name: "021" })).toBeVisible();
    expect(screen.getByText(/Neither establishes/)).toHaveTextContent(
      "treaty eligibility",
    );
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    const cells = within(table).getAllByRole("row")[1].querySelectorAll("td");
    expect(cells[headers.indexOf("form 15ca reference")].textContent).toBe("");
    expect(nativeWithholdingPayload(value, "27Q", "1")).not.toHaveProperty(
      "purchase_value",
    );
  });
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
