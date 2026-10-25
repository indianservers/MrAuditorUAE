"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
export function InventoryEvidenceTable({
  prefix,
  selected,
  initial,
  total,
  bridge = false,
}: {
  prefix: string;
  selected: string;
  initial: Row[];
  total: number;
  bridge?: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const field = bridge ? "count_bridges" : "inventory_quantity_controls";
  const parameter = bridge ? "bridge_offset" : "inventory_offset";
  const page = useAPI<{ body: Record<string, Row[]> }>(
    `${prefix}/events/${selected}?limit=1&${parameter}=${offset}`,
    offset > 0,
  );
  const rows = offset ? page.data?.body[field] || [] : initial;
  const title = bridge
    ? "Inventory count-date bridges"
    : "Inventory quantity controls";
  const columns = bridge
    ? [
        "site",
        "sku",
        "lot",
        "uom",
        "currency",
        "original_count_date",
        "direction",
        "original_count_quantity",
        "applied_movement_quantity",
        "reporting_date_quantity",
      ]
    : [
        "site",
        "sku",
        "lot",
        "uom",
        "currency",
        "expected_rows",
        "positive_quantity",
        "negative_quantity",
      ];
  return (
    <details style={{ margin: "16px 0" }}>
      <summary>
        {title} · {total} partitions
      </summary>
      <ErrorState error={page.error} />
      <p>
        {bridge
          ? "Original count quantities and dates remain distinct from the calculated reporting-date quantities. Quantity bridging does not establish reporting-date condition or physical attendance. Complete original row links are retained in the XLSX."
          : "Independent row and directional quantity controls remain separate for every site, SKU, lot, unit and currency. Positive and negative movements cannot offset an incomplete population."}
      </p>
      <div className="table-wrap">
        <table aria-label={title}>
          <caption>
            {total
              ? `Rows ${offset + 1}–${offset + rows.length} of ${total}`
              : "Explicit nil controlled population"}
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
                    {row[column] == null || row[column] === ""
                      ? "—"
                      : String(row[column])}
                  </td>
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
        Previous {bridge ? "bridge" : "quantity control"} rows
      </Button>
      <Button
        disabled={offset + rows.length >= total || page.isFetching}
        onClick={() => setOffset(offset + 100)}
      >
        Next {bridge ? "bridge" : "quantity control"} rows
      </Button>
    </details>
  );
}
