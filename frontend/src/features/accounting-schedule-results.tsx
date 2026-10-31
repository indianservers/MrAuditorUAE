"use client";

import { useState } from "react";
import { Facts } from "@/components/ui/primitives";
import { RetainedRowsTable } from "./retained-rows-table";

type Row = Record<string, unknown>;
const object = (value: unknown): Row =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Row)
    : {};

export function AccountingScheduleResults({
  kind,
  data,
}: {
  kind: string;
  data: Row;
}) {
  const [raw, setRaw] = useState(false);
  const inventory = kind === "inventory";
  const currency = object(data.execution).presentation_currency;
  const tables = inventory
    ? [
        "schedule",
        "movements",
        "transfers",
        "issues",
        ...(Array.isArray(data.identified_layers) ? ["identified_layers"] : []),
        ...(Array.isArray(data.identified_allocations)
          ? ["identified_allocations"]
          : []),
      ]
    : ["issues"];
  const nested = inventory ? [] : ["obligation_rollforward", "payroll_bridge"];
  const limitations = Array.isArray(data.limitations) ? data.limitations : null;
  const meta = Object.fromEntries(
    Object.entries(data).filter(
      ([key]) =>
        ![
          "execution",
          ...tables,
          ...nested,
          ...(limitations ? ["limitations"] : []),
        ].includes(key),
    ),
  );
  return (
    <section
      className="retained-schedules"
      aria-label={
        inventory
          ? "Inventory costing results"
          : "Employee benefit accounting results"
      }
    >
      <h3>
        {inventory
          ? "Inventory costing and NRV"
          : "Benefit obligation and payroll reconciliation"}
      </h3>
      <p>
        Values are shown at their retained precision. Reporting currency:{" "}
        {typeof currency === "string" ? currency : "Not established"}.
      </p>
      <Facts data={meta} />
      {limitations && (
        <ul aria-label="Retained schedule limitations">
          {limitations.map((text, index) => (
            <li key={index}>{String(text)}</li>
          ))}
        </ul>
      )}
      {nested.map((key) => (
        <section
          key={key}
          aria-label={
            key === "obligation_rollforward"
              ? "Benefit obligation rollforward"
              : "Payroll accounting bridge"
          }
        >
          <h4>
            {key === "obligation_rollforward"
              ? "Benefit obligation rollforward"
              : "Payroll accounting bridge"}
          </h4>
          <Facts data={object(data[key])} />
          {Object.keys(object(data[key])).length === 0 && (
            <p>No structured values retained for this schedule.</p>
          )}
        </section>
      ))}
      {tables.map((key) => {
        const title =
          key === "schedule"
            ? "Inventory item costing"
            : key === "movements"
              ? "Inventory cost movements"
              : key === "transfers"
                ? "Inventory transfers"
                : key === "identified_layers"
                  ? "Identified project cost layers"
                  : key === "identified_allocations"
                    ? "Identified project issue allocations"
                    : "Accounting schedule issues";
        const table = (
          <RetainedRowsTable
            title={title}
            rows={data[key]}
            columnOrder={
              key === "identified_layers"
                ? [
                    "layer_reference",
                    "original_quantity",
                    "original_cost",
                    "remaining_quantity",
                    "remaining_cost",
                    "source_evidence",
                  ]
                : key === "identified_allocations"
                  ? [
                      "issue_reference",
                      "layer_reference",
                      "quantity",
                      "cost",
                      "allocation_evidence",
                      "source_evidence",
                      "remaining_quantity",
                      "remaining_cost",
                    ]
                  : undefined
            }
            currency={typeof currency === "string" ? currency : ""}
          />
        );
        return key === "schedule" || key === "issues" ? (
          <div key={key}>{table}</div>
        ) : (
          <details key={key}>
            <summary>
              {title} (
              {Array.isArray(data[key]) ? data[key].length : "Unstructured"})
            </summary>
            {table}
          </details>
        );
      })}
      <details onToggle={(event) => setRaw(event.currentTarget.open)}>
        <summary>Complete retained calculation and provenance</summary>
        {raw && (
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </details>
    </section>
  );
}
