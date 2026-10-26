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
  purchase = false,
  confirmation = false,
}: {
  prefix: string;
  selected: string;
  initial: Row[];
  total: number;
  bridge?: boolean;
  purchase?: boolean;
  confirmation?: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const field = confirmation
    ? "confirmation_coverage_links"
    : purchase
      ? "purchase_quantity_controls"
      : bridge
        ? "count_bridges"
        : "inventory_quantity_controls";
  const parameter = confirmation
    ? "confirmation_link_offset"
    : purchase
      ? "purchase_offset"
      : bridge
        ? "bridge_offset"
        : "inventory_offset";
  const page = useAPI<{ body: Record<string, Row[]> }>(
    `${prefix}/events/${selected}?limit=1&${parameter}=${offset}`,
    offset > 0,
  );
  const rows = offset ? page.data?.body[field] || [] : initial;
  const title = confirmation
    ? "Partial confirmation item links"
    : purchase
      ? "Purchase quantity controls"
      : bridge
        ? "Inventory count-date bridges"
        : "Inventory quantity controls";
  const columns = confirmation
    ? [
        "source_row_id",
        "confirmation_source_row_id",
        "item_id",
        "as_of",
        "account",
        "counterparty",
        "side",
        "currency",
        "book_amount",
        "evidence_reference",
      ]
    : purchase
      ? [
          "order_id",
          "line_reference",
          "vendor",
          "currency",
          "uom",
          "document_type",
          "expected_rows",
          "quantity",
        ]
      : bridge
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
        {title} · {total} {confirmation ? "links" : "partitions"}
      </summary>
      <ErrorState error={page.error} />
      <p>
        {confirmation
          ? "Reviewed item mappings declare the scope of a partial reply. They do not confirm the remaining items or authenticate the response. Every link is retained in the XLSX."
          : purchase
            ? "Independent row and quantity controls remain separate for each order, line, vendor, currency, unit and document type. Payment quantities are excluded. No unit conversion is inferred."
            : bridge
              ? "Original count quantities and dates remain distinct from the calculated reporting-date quantities. Quantity bridging does not establish reporting-date condition or physical attendance. Complete original row links are retained in the XLSX."
              : "Independent row and directional quantity controls remain separate for every site, SKU, lot, unit and currency. Positive and negative movements cannot offset an incomplete population."}
      </p>
      <div className="table-wrap">
        <table aria-label={title}>
          <caption>
            {total
              ? `Rows ${offset + 1}–${offset + rows.length} of ${total}`
              : purchase
                ? "No non-payment quantity partitions in this source"
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
        Previous{" "}
        {confirmation
          ? "confirmation link"
          : bridge
            ? "bridge"
            : "quantity control"}{" "}
        rows
      </Button>
      <Button
        disabled={offset + rows.length >= total || page.isFetching}
        onClick={() => setOffset(offset + 100)}
      >
        Next{" "}
        {confirmation
          ? "confirmation link"
          : bridge
            ? "bridge"
            : "quantity control"}{" "}
        rows
      </Button>
    </details>
  );
}
