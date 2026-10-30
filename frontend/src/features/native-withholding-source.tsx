"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";

const COUNTS = ["batch_count", "challan_count", "party_count"] as const;
const AMOUNTS = [
  "income_tax",
  "surcharge",
  "cess",
  "allocated_deposit",
  "challan_deposit",
  "payment_base",
  "purchase_value",
] as const;
const FORM143_AMOUNTS = [
  "tax_collected",
  "allocated_deposit",
  "challan_deposit",
  "payment_base",
  "challan_tax",
  "challan_interest",
  "challan_fee",
  "challan_other",
  "allocated_interest",
  "allocated_other",
] as const;
const FORM138_AMOUNTS = [
  "tax_deducted",
  "allocated_deposit",
  "challan_deposit",
  "payment_base",
  "challan_tax",
  "challan_interest",
  "challan_fee",
  "challan_penalty",
  "allocated_interest",
  "allocated_penalty",
] as const;
const isDated = (form: string) => ["143", "138"].includes(form);
const selectedAmounts = (form: string) =>
  form === "138"
    ? [...FORM138_AMOUNTS]
    : form === "143"
      ? [...FORM143_AMOUNTS]
      : AMOUNTS.filter((key) => key !== "purchase_value" || form === "27EQ");
export type NativeWithholdingDraft = Record<
  | (typeof COUNTS)[number]
  | (typeof AMOUNTS)[number]
  | (typeof FORM143_AMOUNTS)[number]
  | (typeof FORM138_AMOUNTS)[number]
  | "annual_controls"
  | "date_width_assessment"
  | "tan"
  | "financial_year"
  | "tax_year"
  | "quarter"
  | "observed_on"
  | "record_status"
  | "crosswalk_document_version_id"
  | "assessment"
  | "groups",
  string
>;
export const EMPTY_NATIVE_WITHHOLDING: NativeWithholdingDraft =
  Object.fromEntries(
    [
      ...COUNTS,
      ...AMOUNTS,
      ...FORM143_AMOUNTS,
      ...FORM138_AMOUNTS,
      "annual_controls",
      "date_width_assessment",
      "tan",
      "financial_year",
      "tax_year",
      "quarter",
      "observed_on",
      "record_status",
      "crosswalk_document_version_id",
      "assessment",
      "groups",
    ].map((k) => [k, ""]),
  ) as NativeWithholdingDraft;

export function nativeWithholdingPayload(
  value: NativeWithholdingDraft,
  form: string,
  expectedRows: string,
) {
  if (!/^[A-Z]{4}[0-9]{5}[A-Z]$/.test(value.tan))
    throw new Error("Enter the independently checked native TAN.");
  const year = Number(value.financial_year.slice(0, 4));
  if (isDated(form) && value.tax_year !== "202627")
    throw new Error(
      `The dated Form ${form} numbered layout covers declared tax year 202627. Other years and layouts require their own profile.`,
    );
  if (
    !isDated(form) &&
    (!/^20\d{4}$/.test(value.financial_year) ||
      year < 2010 ||
      year > 2025 ||
      value.financial_year.slice(4) !==
        String((year + 1) % 100).padStart(2, "0"))
  )
    throw new Error(
      "These profiles require a historical financial year from 201011 through 202526. Successor forms are separate.",
    );
  if (
    !/^Q[1-4]$/.test(value.quarter) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.observed_on) ||
    !Number.isFinite(Date.parse(value.observed_on))
  )
    throw new Error(
      "Select the exact native quarter and independent observation cutoff.",
    );
  if (
    !["current", "superseded", "cancelled"].includes(value.record_status) ||
    !value.crosswalk_document_version_id ||
    value.assessment.trim().length < 10
  )
    throw new Error(
      "Assess the source selection and choose a separate clean retained crosswalk document.",
    );
  if (
    form === "138" &&
    (value.quarter === "Q4" ||
      value.date_width_assessment !==
        "DD29_EIGHT_DIGIT_DATE_PER_NUMBERED_REMARKS")
  )
    throw new Error(
      "Form 138 requires Q1–Q3 and an explicit assessment of the conflicting deposit-date width.",
    );
  if (form === "24Q" && value.quarter === "Q4")
    throw new Error(
      "Historical 24Q Q4 requires its separate annual salary records.",
    );
  if (form === "24Q-Q4" && (value.quarter !== "Q4" || year < 2011))
    throw new Error(
      "Annual 24Q requires historical Q4 from FY2011–12 onwards.",
    );
  const counts = Object.fromEntries(
    COUNTS.map((key) => {
      if (
        !/^\d+$/.test(value[key]) ||
        Number(value[key]) < 1 ||
        Number(value[key]) > (key === "batch_count" ? 100 : 5000) ||
        (isDated(form) && key === "batch_count" && value[key] !== "1")
      )
        throw new Error(
          `Enter an explicit positive independent ${key.replaceAll("_", " ")}.`,
        );
      return [key, Number(value[key])];
    }),
  );
  const amounts = Object.fromEntries(
    selectedAmounts(form).map((key) => {
      if (!/^\d+(?:\.\d{1,2})?$/.test(value[key]))
        throw new Error(
          `Enter the independent ${key.replaceAll("_", " ")} amount, including explicit zero.`,
        );
      return [key, value[key]];
    }),
  );
  const groups = JSON.parse(value.groups);
  if (
    !Array.isArray(groups) ||
    !/^\d+$/.test(expectedRows) ||
    groups.length !== Number(expectedRows) ||
    !groups.length
  )
    throw new Error(
      "Expected source rows must equal the independently assessed crosswalk groups.",
    );
  return {
    ...(form === "138"
      ? { date_width_assessment: value.date_width_assessment }
      : {}),
    ...counts,
    ...amounts,
    tan: value.tan,
    ...(isDated(form)
      ? { tax_year: value.tax_year }
      : { financial_year: value.financial_year }),
    quarter: value.quarter,
    observed_on: value.observed_on,
    record_status: value.record_status,
    crosswalk_document_version_id: value.crosswalk_document_version_id,
    assessment: value.assessment,
    groups,
  };
}

export function NativeWithholdingSource({
  value,
  onChange,
  form,
  documents,
}: {
  value: NativeWithholdingDraft;
  onChange: (draft: NativeWithholdingDraft) => void;
  form: string;
  documents: { id: string; label: string }[];
}) {
  const update = (key: keyof NativeWithholdingDraft, next: string) =>
    onChange({ ...value, [key]: next });
  return (
    <fieldset>
      <legend>Independent regular statement controls</legend>
      <p>
        {isDated(form)
          ? `Dated Form ${form} numbered workbook v1.1 (22 July 2026)`
          : `Historical ${form}`}{" "}
        regular uploaded observations only. Every FH/BH/CD/DD record must be
        retained and controlled. Prepared tax, allocated deposits and gross
        challan deposits are separate; this import does not establish filing,
        FVU/CSI validation, bank payment or tax credit.
      </p>
      {isDated(form) && (
        <p role="note">
          The download page says v1.2; this profile uses the separately retained
          numbered workbook v1.1. Missing public-sample fields are rejected.
          Selecting this profile does not qualify the complete current issuer
          layout.
        </p>
      )}
      {form === "138" && (
        <>
          <label>
            Salary deposit-date source conflict assessment
            <select
              value={value.date_width_assessment}
              onChange={(e) => update("date_width_assessment", e.target.value)}
            >
              <option value="">Assess the conflicting source field</option>
              <option value="DD29_EIGHT_DIGIT_DATE_PER_NUMBERED_REMARKS">
                Use eight-digit dates per numbered DD29 remarks
              </option>
            </select>
          </label>
          <p>
            The workbook gives DD29 a seven-character size but requires DDMMYYYY
            in its remarks. This dated observation reader uses eight digits only
            under this assessment. The original sample has earlier years and
            missing required fields. Q4 annual salary details and FVU validation
            remain separate.
          </p>
        </>
      )}
      <label>
        Native statement TAN
        <input
          value={value.tan}
          onChange={(e) => update("tan", e.target.value)}
        />
      </label>
      <label>
        {isDated(form)
          ? "Native tax year (six digits)"
          : "Native financial year (six digits)"}
        <input
          value={isDated(form) ? value.tax_year : value.financial_year}
          placeholder={isDated(form) ? "202627" : "202021"}
          onChange={(e) =>
            update(
              isDated(form) ? "tax_year" : "financial_year",
              e.target.value,
            )
          }
        />
      </label>
      <label>
        Native statement quarter
        <select
          value={value.quarter}
          onChange={(e) => update("quarter", e.target.value)}
        >
          <option value="">Select declared quarter</option>
          {(form === "24Q-Q4"
            ? ["Q4"]
            : ["138", "24Q"].includes(form)
              ? ["Q1", "Q2", "Q3"]
              : ["Q1", "Q2", "Q3", "Q4"]
          ).map((q) => (
            <option key={q}>{q}</option>
          ))}
        </select>
      </label>
      <label>
        Native observation cutoff
        <input
          type="date"
          value={value.observed_on}
          onChange={(e) => update("observed_on", e.target.value)}
        />
      </label>
      <label>
        Assessed native source selection
        <select
          value={value.record_status}
          onChange={(e) => update("record_status", e.target.value)}
        >
          <option value="">Select assessed status</option>
          {["current", "superseded", "cancelled"].map((status) => (
            <option key={status}>{status}</option>
          ))}
        </select>
      </label>
      <p>
        Current means selected by this assessment. It does not verify the
        portal's current statement or replace correction processing.
      </p>
      {COUNTS.map((key) => (
        <label key={key}>
          Native {key.replaceAll("_", " ")}
          <input
            inputMode="numeric"
            value={value[key]}
            onChange={(e) => update(key, e.target.value)}
          />
        </label>
      ))}
      {selectedAmounts(form).map((key) => (
        <label key={key}>
          Native {key.replaceAll("_", " ")} control (INR)
          <input
            inputMode="decimal"
            value={value[key]}
            onChange={(e) => update(key, e.target.value)}
          />
        </label>
      ))}
      <label>
        Retained native transaction and section crosswalk
        <select
          value={value.crosswalk_document_version_id}
          onChange={(e) =>
            update("crosswalk_document_version_id", e.target.value)
          }
        >
          <option value="">Select separate clean evidence</option>
          {documents.map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Native crosswalk groups (JSON)
        <textarea
          value={value.groups}
          onChange={(e) => update("groups", e.target.value)}
        />
      </label>
      <p>
        Each group declares transaction_reference, transaction_date, period,
        rule_reference and party_records. Party keys are batch/challan/party,
        for example 1/1/1. Cover every party once; a group may combine records
        for one PAN, source section code and month. Expected source rows count
        mapped groups; the native party count controls original DD records.
      </p>
      {form === "24Q-Q4" && (
        <label>
          Annual salary populations and totals (JSON)
          <textarea
            value={value.annual_controls}
            onChange={(e) => update("annual_controls", e.target.value)}
          />
        </label>
      )}
      {form === "24Q-Q4" && (
        <p>
          Declare all six annual record counts, including zero, and independent
          salary/pension gross income, taxable income and net tax totals, salary
          tax deducted and signed shortfall. Retain the full annual assessment
          with the selected independent crosswalk. Quarterly TDS rows and annual
          income records remain separate.
        </p>
      )}
      <label>
        Native source and crosswalk assessment
        <textarea
          maxLength={2000}
          value={value.assessment}
          onChange={(e) => update("assessment", e.target.value)}
        />
      </label>
      <p>
        The main independent INR total is total tax in DD records, not gross
        challan deposits. Retain independently assessed transaction identities
        and section references; no code-to-law mapping or tax rate is inferred.
      </p>
    </fieldset>
  );
}

export function NativeWithholdingLinks({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  const [offset, setOffset] = useState(0);
  const [group, setGroup] = useState("");
  const selected = group ? rows.filter((row) => row.group_id === group) : rows;
  const page = selected.slice(offset, offset + 100);
  const fields = [
    "group_id",
    "party_key",
    "source_line",
    "name",
    "pan",
    "native_section_code",
    "native_payment_date",
    "native_tax_date",
    ...(rows.some(
      (row) =>
        "recorded_section202_opt_out" in row ||
        ("recorded_deposit_date" in row && "recorded_deposited_flag" in row),
    )
      ? []
      : ["income_tax", "surcharge", "cess"]),
    "total_tax",
    "allocated_deposit",
    "payment_base",
    ...(rows.some((row) => "recorded_deposit_date" in row)
      ? [
          "recorded_deposit_date",
          ...(rows.some((row) => "recorded_employee_reference" in row)
            ? ["recorded_employee_reference"]
            : ["recorded_deposited_flag"]),
        ]
      : ["recorded_rate"]),
    "reason_flag",
    "certificate_reference",
    ...(rows.some((row) => "recorded_section202_opt_out" in row)
      ? [
          "recorded_nonresident_flag",
          "recorded_collectee_code",
          "recorded_pe_flag",
          "recorded_section202_opt_out",
          "recorded_deposited_flag",
          "recorded_tds_applicability",
          "recorded_tds_challan_number",
          "recorded_tds_payment_date",
        ]
      : []),
    ...(rows.some((row) => "recorded_rate_basis" in row)
      ? [
          "recorded_rate_basis",
          "nature_of_remittance_code",
          "form_15ca_reference",
          "residence_country_code",
          "deductee_email",
          "deductee_contact",
          "residence_address",
          "foreign_tax_identifier",
          "cash_withdrawal_194n",
          "cash_withdrawal_194n_first_band",
          "cash_withdrawal_194n_second_band",
          "cash_withdrawal_cooperative_194n",
          "cash_withdrawal_cooperative_first_band",
          "cash_withdrawal_cooperative_second_band",
          "recorded_115bac_opt_out",
        ]
      : []),
  ];
  return (
    <section aria-label="Native withholding party lineage">
      <h3>Original statement party links</h3>
      <p>
        These links retain prepared-statement observations and their mapped
        group. Recorded rates, reason flags and certificates are source
        observations requiring independent assessment.
      </p>
      {rows.some((row) => "recorded_rate_basis" in row) && (
        <p>
          Nonresident fields retain uploaded codes and references. Rate basis A
          records the Income Tax Act and B records DTAA. Neither establishes
          residence, treaty eligibility, a valid Form 15CA acknowledgment or the
          correct tax rate. Blank source fields remain blank.
        </p>
      )}
      {rows.some((row) => "recorded_section202_opt_out" in row) && (
        <p>
          Form 143 flags and allocation amounts are uploaded statement claims.
          They do not establish residence, PE status, an election, bank payment
          or tax credit.
        </p>
      )}
      {rows.some(
        (row) =>
          "recorded_deposit_date" in row && "recorded_deposited_flag" in row,
      ) && (
        <p>
          Form 138 salary dates and deposited flags are uploaded statement
          claims. This dated workbook v1.1 differs from page v1.2; the deposit
          date uses the explicitly assessed eight-digit interpretation of
          conflicting source instructions. It does not establish FVU acceptance,
          bank payment or tax credit.
        </p>
      )}
      <label>
        Native group ID filter
        <input
          value={group}
          onChange={(e) => {
            setGroup(e.target.value);
            setOffset(0);
          }}
        />
      </label>
      <p>
        {selected.length
          ? `Links ${offset + 1}–${offset + page.length} of ${selected.length}`
          : "No links for this group."}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Native withholding party links">
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field}>{field.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.map((row) => (
              <tr key={String(row.party_key)}>
                {fields.map((field) => (
                  <td key={field}>{String(row[field] ?? "Not recorded")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar">
        <Button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Previous native links
        </Button>
        <Button
          disabled={offset + page.length >= selected.length}
          onClick={() => setOffset(offset + 100)}
        >
          Next native links
        </Button>
      </div>
    </section>
  );
}

export function NativeWithholdingChallans({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  const [offset, setOffset] = useState(0);
  const page = rows.slice(offset, offset + 100);
  const fields = [
    "batch",
    "challan",
    "source_line",
    "challan_number",
    "ddo_serial",
    "bsr_or_form24g_reference",
    "challan_date",
    ...(rows.some((row) => "recorded_penalty" in row) ? [] : ["nil_flag"]),
    ...(rows.some((row) => "recorded_payment_mode" in row)
      ? []
      : ["book_entry_flag"]),
    "gross_deposit",
    "allocated_deposit",
    "recorded_interest",
    ...(rows.some((row) => "recorded_penalty" in row)
      ? ["recorded_penalty"]
      : ["recorded_other"]),
    "fee",
    ...(rows.some((row) => "recorded_payment_mode" in row)
      ? [
          "recorded_payment_mode",
          "recorded_tax",
          "allocated_interest",
          ...(rows.some((row) => "allocated_penalty" in row)
            ? ["allocated_penalty"]
            : ["allocated_other"]),
        ]
      : []),
  ];
  return (
    <section aria-label="Native withholding challan controls">
      <h3>Original statement challans</h3>
      <p>
        One row per original CD record. Gross challan deposits and allocated
        party tax remain separate. Identifiers and dates are uploaded statement
        claims, not verified bank or CSI receipts.
      </p>
      <p>
        Challans {offset + 1}–{offset + page.length} of {rows.length}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Native withholding challans">
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field}>{field.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.map((row) => (
              <tr key={`${row.batch}/${row.challan}`}>
                {fields.map((field) => (
                  <td key={field}>{String(row[field] ?? "Not recorded")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar">
        <Button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Previous native challans
        </Button>
        <Button
          disabled={offset + page.length >= rows.length}
          onClick={() => setOffset(offset + 100)}
        >
          Next native challans
        </Button>
      </div>
    </section>
  );
}

export function salaryAnnualPayload(value: string) {
  const parsed = JSON.parse(value);
  if (
    !parsed ||
    typeof parsed !== "object" ||
    Array.isArray(parsed) ||
    !parsed.record_counts ||
    ["SD", "S16", "C6A", "94P", "P16", "P6A"].some(
      (tag) =>
        !Number.isInteger(parsed.record_counts[tag]) ||
        parsed.record_counts[tag] < 0,
    )
  )
    throw new Error(
      "Declare all six independent annual record populations, including explicit zeros.",
    );
  return parsed;
}
