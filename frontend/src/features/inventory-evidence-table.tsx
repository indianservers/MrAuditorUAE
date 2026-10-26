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
  cutoff,
  custody = false,
}: {
  prefix: string;
  selected: string;
  initial: Row[];
  total: number;
  bridge?: boolean;
  purchase?: boolean;
  confirmation?: boolean;
  cutoff?: "controls" | "postings";
  custody?: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const field = custody
    ? "custody_quantity_controls"
    : cutoff
      ? cutoff === "controls"
        ? "cutoff_document_controls"
        : "cutoff_posting_links"
      : confirmation
        ? "confirmation_coverage_links"
        : purchase
          ? "purchase_quantity_controls"
          : bridge
            ? "count_bridges"
            : "inventory_quantity_controls";
  const parameter = custody
    ? "custody_control_offset"
    : cutoff
      ? cutoff === "controls"
        ? "cutoff_control_offset"
        : "cutoff_posting_offset"
      : confirmation
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
  const title = custody
    ? "Custody quantity controls"
    : cutoff
      ? cutoff === "controls"
        ? "Cutoff document allocation controls"
        : "Cutoff ledger posting links"
      : confirmation
        ? "Partial confirmation item links"
        : purchase
          ? "Purchase quantity controls"
          : bridge
            ? "Inventory count-date bridges"
            : "Inventory quantity controls";
  const columns = custody
    ? [
        "source_role",
        "position_id",
        "custodian",
        "site",
        "sku",
        "lot",
        "uom",
        "quantity",
        "response_quantity",
      ]
    : cutoff
      ? cutoff === "controls"
        ? [
            "document_source_id",
            "counterparty",
            "reference",
            "currency",
            "document_kind",
            "document_amount",
            "allocated_amount",
            "difference",
            "allocation_rows",
            "state",
          ]
        : [
            "posting_source_id",
            "allocation_id",
            "document_id",
            "counterparty",
            "currency",
            "account",
            "amount",
            "posting_date",
            "journal_reference",
            "evidence_reference",
          ]
      : confirmation
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
        {title} · {total}{" "}
        {custody
          ? "records"
          : cutoff === "controls"
            ? "documents"
            : cutoff || confirmation
              ? "links"
              : "partitions"}
      </summary>
      <ErrorState error={page.error} />
      <p>
        {custody
          ? "Independent quantities remain scoped to each exact position and unit. For a response source, quantity is the stated request quantity and response_quantity is the actual reply; an absent response is distinct from zero."
          : cutoff
            ? "Every allocation must exactly cover its document amount. Posting dates, partial entries and reversals remain source linked; assessed future recognition does not establish that the service has occurred."
            : confirmation
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
        {custody
          ? "custody control"
          : cutoff
            ? `cutoff ${cutoff}`
            : confirmation
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
        {custody
          ? "custody control"
          : cutoff
            ? `cutoff ${cutoff}`
            : confirmation
              ? "confirmation link"
              : bridge
                ? "bridge"
                : "quantity control"}{" "}
        rows
      </Button>
    </details>
  );
}
