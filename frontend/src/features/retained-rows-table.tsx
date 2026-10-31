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

export function RetainedRowsTable({
  title,
  rows,
  currency,
  serverPage,
}: {
  title: string;
  rows: unknown;
  currency: string;
  serverPage?: {
    offset: number;
    total: number;
    onPage: (offset: number) => void;
    isLoading?: boolean;
  };
}) {
  const [offset, setOffset] = useState(0);
  const original = Array.isArray(rows) ? rows : [];
  const records = original.filter(
    (row): row is Row =>
      row !== null && typeof row === "object" && !Array.isArray(row),
  );
  const invalid = original.length - records.length;
  const columns = [...new Set(records.flatMap((row) => Object.keys(row)))];
  const columnWidth = (key: string) =>
    key === "rate_source" || key.endsWith("evidence") ? 320 : 240;
  const limit = 25;
  const start = Math.min(
    offset,
    Math.max(0, Math.floor((records.length - 1) / limit) * limit),
  );
  const pageStart = serverPage?.offset ?? start;
  const total = serverPage?.total ?? records.length;
  const visible = serverPage
    ? records.slice(0, limit)
    : records.slice(start, start + limit);
  const changePage = serverPage?.onPage ?? setOffset;
  return (
    <section aria-label={title}>
      <h4>{title}</h4>
      <p>
        Records {visible.length ? pageStart + 1 : 0}–
        {visible.length ? Math.min(pageStart + visible.length, total) : 0} of{" "}
        {total}. Original values and references are retained without rounding.
      </p>
      {invalid > 0 && (
        <p role="alert">
          {invalid} source records are not structured rows. Inspect the complete
          immutable export.
        </p>
      )}
      {records.length === 0 ? (
        <p>No structured records retained.</p>
      ) : (
        <div className="group-source-scroll">
          <table
            aria-label={title}
            style={{
              minWidth: Math.max(
                1080,
                columns.reduce((width, key) => width + columnWidth(key), 0),
              ),
            }}
          >
            <colgroup>
              {columns.map((key) => (
                <col key={key} style={{ width: columnWidth(key) }} />
              ))}
            </colgroup>
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
              {visible.map((row, index) => (
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
          disabled={pageStart === 0 || serverPage?.isLoading}
          onClick={() => changePage(Math.max(0, pageStart - limit))}
        >
          Previous {title.toLowerCase()}
        </Button>
        <Button
          disabled={pageStart + limit >= total || serverPage?.isLoading}
          onClick={() => changePage(pageStart + limit)}
        >
          Next {title.toLowerCase()}
        </Button>
      </div>
    </section>
  );
}
