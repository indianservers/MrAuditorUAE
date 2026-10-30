"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
const collections = {
  fifo_allocations: "FIFO issue allocations",
  fifo_event_costs: "FIFO movement costs",
  fifo_closing_layers: "FIFO closing layers",
  inventory_fifo_controls: "FIFO source controls",
};

function Collection({
  prefix,
  selected,
  field,
  title,
  initial,
  total,
}: {
  prefix: string;
  selected: string;
  field: string;
  title: string;
  initial: Row[];
  total: number;
}) {
  const [offset, setOffset] = useState(0);
  const page = useAPI<{ body: Record<string, Row[]> }>(
    `${prefix}/events/${selected}?limit=1&fifo_offset=${offset}&fifo_limit=20`,
    offset > 0,
  );
  const rows = offset ? page.data?.body[field] || [] : initial;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <details>
      <summary>
        {title} · {total}
      </summary>
      <ErrorState error={page.error} />
      <div className="table-wrap">
        <table aria-label={title}>
          <caption>
            {total
              ? `Rows ${offset + 1}–${offset + rows.length} of ${total}`
              : "No rows"}
          </caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column}>
                    {row[column] == null ? "Not supplied" : String(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button
        disabled={offset === 0 || page.isFetching}
        onClick={() => setOffset(Math.max(0, offset - 20))}
      >
        Previous {title}
      </Button>
      <Button
        disabled={
          offset + 20 >= total || page.isFetching || Boolean(page.error)
        }
        onClick={() => setOffset(offset + 20)}
      >
        Next {title}
      </Button>
    </details>
  );
}

export function InventoryFIFODetails({
  prefix,
  selected,
  body,
  totals,
}: {
  prefix: string;
  selected: string;
  body: Partial<Record<keyof typeof collections, Row[]>>;
  totals?: Record<string, number>;
}) {
  return (
    <section aria-label="FIFO cost evidence">
      <p>
        Assessed FIFO gross-cost evidence. Review the policy, opening layer
        order and cost inclusion independently. Physical count, ownership, NRV,
        tax treatment and framework applicability require separate evidence.
        Complete allocations and controls are retained in the XLSX.
      </p>
      {Object.entries(collections).map(([field, title]) => {
        const initial = body[field as keyof typeof collections];
        return initial ? (
          <Collection
            key={`${selected}:${field}`}
            prefix={prefix}
            selected={selected}
            field={field}
            title={title}
            initial={initial}
            total={totals?.[field] ?? initial.length}
          />
        ) : null;
      })}
    </section>
  );
}
