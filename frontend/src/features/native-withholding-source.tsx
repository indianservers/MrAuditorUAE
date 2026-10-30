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
export type NativeWithholdingDraft = Record<
  | (typeof COUNTS)[number]
  | (typeof AMOUNTS)[number]
  | "tan"
  | "financial_year"
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
      "tan",
      "financial_year",
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
  if (
    !/^20\d{4}$/.test(value.financial_year) ||
    year < 2010 ||
    year > 2025 ||
    value.financial_year.slice(4) !== String((year + 1) % 100).padStart(2, "0")
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
  const counts = Object.fromEntries(
    COUNTS.map((key) => {
      if (
        !/^\d+$/.test(value[key]) ||
        Number(value[key]) < 1 ||
        Number(value[key]) > (key === "batch_count" ? 100 : 5000)
      )
        throw new Error(
          `Enter an explicit positive independent ${key.replaceAll("_", " ")}.`,
        );
      return [key, Number(value[key])];
    }),
  );
  const amounts = Object.fromEntries(
    AMOUNTS.filter((key) => key !== "purchase_value" || form === "27EQ").map(
      (key) => {
        if (!/^\d+(?:\.\d{1,2})?$/.test(value[key]))
          throw new Error(
            `Enter the independent ${key.replaceAll("_", " ")} amount, including explicit zero.`,
          );
        return [key, value[key]];
      },
    ),
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
    ...counts,
    ...amounts,
    tan: value.tan,
    financial_year: value.financial_year,
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
        Historical {form} regular uploaded observations only. Every FH/BH/CD/DD
        record must be retained and controlled. Prepared tax, allocated deposits
        and gross challan deposits are separate; this import does not establish
        filing, FVU/CSI validation, bank payment or tax credit.
      </p>
      <label>
        Native statement TAN
        <input
          value={value.tan}
          onChange={(e) => update("tan", e.target.value)}
        />
      </label>
      <label>
        Native financial year (six digits)
        <input
          value={value.financial_year}
          placeholder="202021"
          onChange={(e) => update("financial_year", e.target.value)}
        />
      </label>
      <label>
        Native statement quarter
        <select
          value={value.quarter}
          onChange={(e) => update("quarter", e.target.value)}
        >
          <option value="">Select declared quarter</option>
          {["Q1", "Q2", "Q3", "Q4"].map((q) => (
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
      {AMOUNTS.filter((key) => key !== "purchase_value" || form === "27EQ").map(
        (key) => (
          <label key={key}>
            Native {key.replaceAll("_", " ")} control (INR)
            <input
              inputMode="decimal"
              value={value[key]}
              onChange={(e) => update(key, e.target.value)}
            />
          </label>
        ),
      )}
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
    "income_tax",
    "surcharge",
    "cess",
    "total_tax",
    "allocated_deposit",
    "payment_base",
    "recorded_rate",
    "reason_flag",
    "certificate_reference",
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
    "nil_flag",
    "book_entry_flag",
    "gross_deposit",
    "allocated_deposit",
    "recorded_interest",
    "recorded_other",
    "fee",
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
