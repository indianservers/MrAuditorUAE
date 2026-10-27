"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Source = {
  id: string;
  label: string;
  kind: string;
  table_type?: string;
  review_status: string;
  freshness: string;
  parser_version?: string;
  allowed_source_roles?: string[] | null;
  allowed_workflows?: string[] | null;
};

export function TurnoverBooksComposition({
  eid,
  country,
  sources,
  onCreated,
}: {
  eid: string;
  country: string;
  sources: Source[];
  onCreated: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [count, setCount] = useState("");
  const [amount, setAmount] = useState("");
  const [assessment, setAssessment] = useState("");
  const [label, setLabel] = useState("");
  const action = useAction<{ id: string }>();
  const currency = country === "AE" ? "AED" : "INR";
  const eligible = sources.filter(
    (s) =>
      s.kind === "workflow-source" &&
      s.table_type === "turnover-amounts" &&
      s.review_status === "REVIEWED" &&
      s.freshness === "CURRENT" &&
      s.parser_version !== "turnover-books-composition/1" &&
      (!s.allowed_source_roles || s.allowed_source_roles.includes("books")) &&
      (!s.allowed_workflows ||
        s.allowed_workflows.includes("tax-turnover-bridge")),
  );
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>Combine reviewed turnover book schedules</summary>
      <p>
        Combine disjoint book schedules for different accounts, registrations or
        periods. All rows, signed reversals and original source links are
        retained. Overlapping ledger account/date selections are rejected. This
        covers selected books only; scope, return and adjustment evidence remain
        separate.
      </p>
      <ErrorState error={action.error} />
      <label>
        Reviewed turnover book components
        <select
          multiple
          size={6}
          value={selected}
          onChange={(e) =>
            setSelected(Array.from(e.target.selectedOptions, (o) => o.value))
          }
        >
          {eligible.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Independent combined book row count
        <input
          inputMode="numeric"
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>
      <label>
        Independent combined signed turnover ({currency})
        <input
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      <label>
        Combined books scope and disjointness assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <label>
        Combined turnover books title
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <p>
        Select 2–50 current reviewed original sources, at most 5,000 combined
        rows. Independently review the combined source before using it as books.
      </p>
      <Button
        disabled={
          action.isPending ||
          selected.length < 2 ||
          selected.length > 50 ||
          selected.some((id) => !eligible.some((s) => s.id === id)) ||
          !/^\d+$/.test(count) ||
          Number(count) < 2 ||
          Number(count) > 5000 ||
          !amount.trim() ||
          assessment.trim().length < 10 ||
          label.trim().length < 3
        }
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/turnover-books-composition`,
              body: {
                source_ids: selected,
                currency,
                expected_rows: Number(count),
                expected_amount: amount,
                assessment,
                label,
              },
            });
            onCreated(result.id);
          } catch {
            /* The mutation displays its server error above. */
          }
        }}
      >
        Prepare combined turnover books
      </Button>
    </details>
  );
}
