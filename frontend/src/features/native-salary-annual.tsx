"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";

type AnnualRecord = {
  source_line: number;
  record_type: string;
  batch: number;
  parent_record: number;
  record_number: number;
  pan: string;
  fields: string[];
};
const tags = ["SD", "S16", "C6A", "94P", "P16", "P6A"];

export function NativeSalaryAnnualDetails({
  annual,
}: {
  annual: Record<string, unknown>;
}) {
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [fieldOffset, setFieldOffset] = useState(0);
  const valid =
    annual.contract === "historical-salary-annual-observations/1" &&
    Array.isArray(annual.records) &&
    annual.records.every(
      (row) =>
        row &&
        typeof row === "object" &&
        Number.isInteger(row.source_line) &&
        tags.includes(row.record_type) &&
        Number.isInteger(row.batch) &&
        Number.isInteger(row.parent_record) &&
        Number.isInteger(row.record_number) &&
        typeof row.pan === "string" &&
        Array.isArray(row.fields) &&
        row.fields.every((v: unknown) => typeof v === "string"),
    );
  if (!valid)
    return (
      <p role="alert">
        The saved annual salary records are unavailable for inspection. Reassess
        the source before relying on this result.
      </p>
    );
  const records = annual.records as AnnualRecord[];
  const filtered = type
    ? records.filter((row) => row.record_type === type)
    : records;
  const page = filtered.slice(offset, offset + 100);
  const active = page.find((row) => row.source_line === selected) || page[0];
  const columns = annual.columns as
    Record<string, { number: number; label: string }[]> | undefined;
  const fields = active?.fields.slice(fieldOffset, fieldOffset + 25) || [];
  const controls =
    annual.controls && typeof annual.controls === "object"
      ? (annual.controls as Record<string, unknown>)
      : {};
  const counts =
    annual.record_counts && typeof annual.record_counts === "object"
      ? (annual.record_counts as Record<string, unknown>)
      : {};
  const totals =
    annual.totals && typeof annual.totals === "object"
      ? (annual.totals as Record<string, unknown>)
      : {};
  const move = (next: number) => {
    setOffset(next);
    setSelected(null);
    setFieldOffset(0);
  };
  return (
    <section aria-label="Native annual salary observations">
      <h3>Annual salary and specified-senior records</h3>
      <p>
        Independent annual assessment:{" "}
        {String(controls.assessment || "Not recorded")}
      </p>
      <p>
        {tags
          .map((tag) => `${tag}: ${String(counts[tag] ?? "Not recorded")}`)
          .join(" · ")}
      </p>
      <p>
        These are complete declared annual observations, separate from quarterly
        TDS rows. Recorded component arithmetic does not establish tax rates,
        deduction entitlement, all-quarter reconciliation, FVU acceptance,
        filing or payment.
      </p>
      <dl>
        {Object.entries(totals).map(([key, value]) => (
          <div key={key}>
            <dt>{key.replaceAll("_", " ")}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>
      <label>
        Annual record type
        <select
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            move(0);
          }}
        >
          <option value="">All annual types</option>
          {tags.map((tag) => (
            <option key={tag}>{tag}</option>
          ))}
        </select>
      </label>
      <p>
        {filtered.length
          ? `Annual records ${offset + 1}–${offset + page.length} of ${filtered.length}`
          : "No records of this annual type."}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Annual original records">
          <thead>
            <tr>
              {[
                "Source line",
                "Type",
                "Batch",
                "Parent",
                "Record",
                "PAN",
                "Inspect",
              ].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.map((row) => (
              <tr key={row.source_line}>
                <td>{row.source_line}</td>
                <td>{row.record_type}</td>
                <td>{row.batch}</td>
                <td>{row.parent_record}</td>
                <td>{row.record_number}</td>
                <td>{row.pan}</td>
                <td>
                  <Button
                    onClick={() => {
                      setSelected(row.source_line);
                      setFieldOffset(0);
                    }}
                  >
                    Inspect annual line {row.source_line}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar">
        <Button
          disabled={!offset}
          onClick={() => move(Math.max(0, offset - 100))}
        >
          Previous annual records
        </Button>
        <Button
          disabled={offset + page.length >= filtered.length}
          onClick={() => move(offset + 100)}
        >
          Next annual records
        </Button>
      </div>
      {active && (
        <>
          <h4>
            Original {active.record_type} fields — source line{" "}
            {active.source_line}
          </h4>
          <p>
            Fields {fieldOffset + 1}–{fieldOffset + fields.length} of{" "}
            {active.fields.length}. Blank source values remain unrecorded;
            explicit zero and negative values are retained.
          </p>
          <table aria-label="Annual numbered source fields">
            <thead>
              <tr>
                <th>Field</th>
                <th>Source label</th>
                <th>Recorded value</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((value, index) => {
                const n = fieldOffset + index;
                return (
                  <tr key={n}>
                    <td>{n + 1}</td>
                    <td>
                      {String(
                        columns?.[active.record_type]?.[n]?.label ||
                          `Field ${n + 1}`,
                      )}
                    </td>
                    <td>{value === "" ? "Not recorded" : value}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="toolbar">
            <Button
              disabled={!fieldOffset}
              onClick={() => setFieldOffset(Math.max(0, fieldOffset - 25))}
            >
              Previous annual fields
            </Button>
            <Button
              disabled={fieldOffset + fields.length >= active.fields.length}
              onClick={() => setFieldOffset(fieldOffset + 25)}
            >
              Next annual fields
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
