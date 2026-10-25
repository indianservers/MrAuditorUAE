"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
export function PayrollPostingLinks({
  prefix,
  selected,
  initial,
  total,
}: {
  prefix: string;
  selected: string;
  initial: Row[];
  total: number;
}) {
  const [offset, setOffset] = useState(0);
  const page = useAPI<{ body: { payroll_posting_links: Row[] } }>(
    `${prefix}/events/${selected}?limit=1&posting_offset=${offset}`,
    offset > 0,
  );
  const rows = offset ? page.data?.body.payroll_posting_links || [] : initial;
  const fields = [
    "source_role",
    "source_row_id",
    "comparison_row_id",
    "account",
    "wage_month",
    "component",
    "category",
    "currency",
    "amount",
  ];
  return (
    <details>
      <summary>Payroll posting source links · {total} entries</summary>
      <p>
        Every retained expected and posted line links to its comparison group.
        Original source event IDs, posting dates, subjects and evidence
        references are retained in the full XLSX.
      </p>
      <ErrorState error={page.error} />
      <div className="table-wrap">
        <table aria-label="Payroll posting source links">
          <caption>
            {total
              ? `Rows ${offset + 1}-${offset + rows.length} of ${total}`
              : "Explicit nil movement populations"}
          </caption>
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field}>{field.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {fields.map((field) => (
                  <td key={field}>{String(row[field] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button
        disabled={offset === 0 || page.isFetching}
        onClick={() => setOffset(Math.max(0, offset - 100))}
      >
        Previous posting links
      </Button>
      <Button
        disabled={offset + rows.length >= total || page.isFetching}
        onClick={() => setOffset(offset + 100)}
      >
        Next posting links
      </Button>
    </details>
  );
}
