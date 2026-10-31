"use client";

import { RetainedRowsTable } from "./retained-rows-table";

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
      <RetainedRowsTable
        title="Current source accounts"
        rows={current}
        currency={currency}
      />
      <RetainedRowsTable
        title="Comparative source accounts"
        rows={comparative}
        currency={currency}
      />
    </section>
  );
}
