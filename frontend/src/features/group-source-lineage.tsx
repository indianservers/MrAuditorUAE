"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
const LABELS: Record<string, string> = {
  engagement_id: "Member engagement",
  run_id: "Member financial run",
  source_amount: "Source amount (original currency)",
  rate: "Translation rate",
  translated: "Translated amount",
  rate_source: "Rate source",
};

function SourceTable({
  title,
  rows,
  currency,
}: {
  title: string;
  rows: unknown;
  currency: string;
}) {
  const [offset, setOffset] = useState(0);
  const original = Array.isArray(rows) ? rows : [];
  const records = original.filter(
    (row): row is Row =>
      row !== null && typeof row === "object" && !Array.isArray(row),
  );
  const invalid = original.length - records.length;
  const columns = [...new Set(records.flatMap((row) => Object.keys(row)))];
  const limit = 25;
  const start = Math.min(
    offset,
    Math.max(0, Math.floor((records.length - 1) / limit) * limit),
  );
  return (
    <section aria-label={title}>
      <h4>{title}</h4>
      <p>
        Records {records.length ? start + 1 : 0}–
        {Math.min(start + limit, records.length)} of {records.length}. Original
        values and references are retained without rounding.
      </p>
      {invalid > 0 && (
        <p role="alert">
          {invalid} source records are not structured rows. Inspect the complete
          immutable export.
        </p>
      )}
      {records.length === 0 ? (
        <p>No structured source accounts retained for this line.</p>
      ) : (
        <div className="group-source-scroll">
          <table aria-label={title}>
            <thead>
              <tr>
                {columns.map((key) => (
                  <th key={key} scope="col">
                    {key === "translated"
                      ? `Translated amount (${currency})`
                      : (LABELS[key] ?? key.replaceAll("_", " "))}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.slice(start, start + limit).map((row, index) => (
                <tr key={start + index}>
                  {columns.map((key) => (
                    <td
                      key={key}
                      style={{
                        minWidth: key === "rate_source" ? 240 : 160,
                        maxWidth: 360,
                        overflowWrap: "anywhere",
                        whiteSpace: "normal",
                        verticalAlign: "top",
                      }}
                    >
                      {row[key] === undefined || row[key] === null
                        ? "Not supplied"
                        : typeof row[key] === "object"
                          ? JSON.stringify(row[key])
                          : String(row[key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="toolbar">
        <Button
          disabled={start === 0}
          onClick={() => setOffset(Math.max(0, start - limit))}
        >
          Previous {title.toLowerCase()}
        </Button>
        <Button
          disabled={start + limit >= records.length}
          onClick={() => setOffset(start + limit)}
        >
          Next {title.toLowerCase()}
        </Button>
      </div>
    </section>
  );
}

export function GroupSourceLineage({
  current,
  comparative,
  currency,
}: {
  current: unknown;
  comparative: unknown;
  currency: string;
}) {
  return (
    <section
      aria-label="Group financial source lineage"
      className="group-source-lineage"
    >
      <h3>Selected group line: source accounts</h3>
      <p>
        Current and prior reported sources have separate populations. Rates and
        amounts are observations from the retained calculations; no restatement
        is performed here.
      </p>
      <SourceTable
        title="Current source accounts"
        rows={current}
        currency={currency}
      />
      <SourceTable
        title="Comparative source accounts"
        rows={comparative}
        currency={currency}
      />
    </section>
  );
}
