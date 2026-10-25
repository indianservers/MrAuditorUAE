"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
export function BankTransactionDates({
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
  const page = useAPI<{ body: { transaction_dates: Row[] } }>(
    `${prefix}/events/${selected}?limit=1&date_offset=${offset}`,
    offset > 0,
  );
  const rows = offset ? page.data?.body.transaction_dates || [] : initial;
  const fields = [
    "source_role",
    "source_row_id",
    "transaction_date",
    "bank_booking_date",
    "bank_value_date",
    "bank_date_basis",
    "booking_date_review_required",
  ];
  return (
    <details>
      <summary>
        Bank transaction dates · {total} {total === 1 ? "entry" : "entries"}
      </summary>
      <p>
        Booking and value dates are separate. A value-date fallback requires
        explicit booking-date evidence before approval or subsequent clearance.
        Declared transaction dates remain subject to source review.
      </p>
      <ErrorState error={page.error} />
      {page.error && (
        <Button onClick={() => void page.refetch()}>Retry bank dates</Button>
      )}
      <div className="table-wrap">
        <table aria-label="Bank transaction dates">
          <caption>
            {page.isFetching && offset > 0
              ? "Loading bank dates…"
              : rows.length
                ? `Rows ${offset + 1}-${offset + rows.length} of ${total}`
                : "No bank date rows on this page"}
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
        Previous bank dates
      </Button>
      <Button
        disabled={
          !rows.length || offset + rows.length >= total || page.isFetching
        }
        onClick={() => setOffset(offset + 100)}
      >
        Next bank dates
      </Button>
    </details>
  );
}
