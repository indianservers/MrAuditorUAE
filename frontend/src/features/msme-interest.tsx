"use client";

import { useState } from "react";

type Row = Record<string, unknown>;
const text = (value: unknown): string =>
  value == null
    ? "Not supplied"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
const records = (value: unknown): Row[] =>
  Array.isArray(value)
    ? value.filter((item): item is Row => !!item && typeof item === "object")
    : [];

/** Pagination changes presentation only; financial strings retain server precision. */
function Trace({ title, rows }: { title: string; rows: Row[] }) {
  const [page, setPage] = useState(0);
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const pages = Math.max(1, Math.ceil(rows.length / 10));
  const current = Math.min(page, pages - 1);
  return (
    <details>
      <summary>
        {title} ({rows.length})
      </summary>
      {rows.length ? (
        <>
          <div style={{ overflowX: "auto" }}>
            <table aria-label={title}>
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>{column.replaceAll("_", " ")}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows
                  .slice(current * 10, current * 10 + 10)
                  .map((row, index) => (
                    <tr key={current * 10 + index}>
                      {columns.map((column) => (
                        <td
                          key={column}
                          style={{ maxWidth: 400, overflowWrap: "anywhere" }}
                        >
                          {text(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <nav aria-label={`${title} pages`}>
            <button
              type="button"
              disabled={!current}
              onClick={() => setPage(current - 1)}
            >
              Previous
            </button>
            <span>
              {" "}
              Page {current + 1} of {pages}{" "}
            </span>
            <button
              type="button"
              disabled={current + 1 >= pages}
              onClick={() => setPage(current + 1)}
            >
              Next
            </button>
          </nav>
        </>
      ) : (
        <p>No records retained for this selection.</p>
      )}
    </details>
  );
}

export { Trace as MSMERecordTrace };

export function MSMEInterestDetails({
  rows,
  expectedTotal,
  complete,
  principalExceptions,
  binding,
  bankControls,
  rates,
}: {
  rows: Row[];
  expectedTotal?: string;
  complete?: boolean;
  principalExceptions?: number;
  binding?: string;
  bankControls?: Row[];
  rates?: Row[];
}) {
  return (
    <section aria-label="MSE assessed interest scope">
      <h3>Assessed MSE interest</h3>
      <p>
        {complete
          ? "Outstanding interest total"
          : "Partial outstanding interest subtotal"}
        : INR {expectedTotal ?? "Unknown"}. Principal timing exceptions:{" "}
        {principalExceptions ?? "Unknown"}. Matching interest does not clear
        overdue principal.
      </p>
      <p>
        {binding === "RETAINED_DOCUMENT_BYTES_VERIFIED"
          ? "Interest policy and bank-rate document bytes were verified. Their applicability and interpretation remain independently assessed."
          : binding === "NO_INTEREST_FACTS_CLAIMED"
            ? "No resolved interest policy claimed. Missing facts remain unknown."
            : "Interest supporting document verification needs updating."}
      </p>
      <p>
        Monthly compounding uses the retained first interest day, assessed
        principal, explicit three-times bank-rate policy and selected accrual
        conventions. No current RBI rate is supplied. Tax deductions, Section 22
        disclosures, filing and global cash reservations are separate
        procedures.
      </p>
      {rows.map((row, index) => {
        const policy =
          row.interest_policy && typeof row.interest_policy === "object"
            ? (row.interest_policy as Row)
            : {};
        return (
          <details key={`${text(row.id)}:${index}`}>
            <summary>
              Invoice {text(row.reference ?? row.id)} — interest{" "}
              {text(row.expected_amount)} INR
            </summary>
            <p>
              Principal timing: {text(row.timing_state)}.{" "}
              {text(row.timing_reasons)}
            </p>
            <p>
              Unresolved interest facts: {text(row.interest_resolution_issue)}
            </p>
            <dl>
              {[
                "amount",
                "history_from",
                "interest_start",
                "start_basis",
                "start_assessment",
                "rate_group",
                "bank_rate_multiplier",
                "rest_basis",
                "day_basis",
                "event_timing",
                "rest_rounding",
                "rounding",
              ].map((key) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{text(policy[key])}</dd>
                </div>
              ))}
            </dl>
            <Trace title="Accrual intervals" rows={records(row.segments)} />
            <Trace
              title="Principal and interest events"
              rows={records(row.balance_events)}
            />
            <Trace title="Monthly rests" rows={records(row.monthly_rests)} />
          </details>
        );
      })}
      <Trace title="Bank allocation controls" rows={bankControls ?? []} />
      <Trace title="Retained bank-rate sources" rows={rates ?? []} />
      <p>
        Invoice details cover the current result page. Trace tables paginate
        without dropping records; the XLSX retains the complete calculation.
      </p>
    </section>
  );
}
