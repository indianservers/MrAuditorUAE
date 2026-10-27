"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Source = {
  id: string;
  label: string;
  kind: string;
  table_type?: string;
  freshness: string;
  review_status: string;
};

export function VATCompositionSource({
  eid,
  sources,
  onCreated,
  layouts = {
    "aggregate-14": {
      label: "Aggregate Box 1 - fourteen rows",
      boxes: Array.from({ length: 14 }, (_, index) => String(index + 1)),
    },
  },
}: {
  layouts?: Record<string, { label: string; boxes: string[] }>;
  eid: string;
  sources: Source[];
  onCreated: (id: string) => void;
}) {
  const [layout, setLayout] = useState("aggregate-14");
  const [selected, setSelected] = useState<string[]>([]);
  const [label, setLabel] = useState("");
  const [base, setBase] = useState("");
  const [tax, setTax] = useState("");
  const [adjustment, setAdjustment] = useState("");
  const [assessment, setAssessment] = useState("");
  const action = useAction<{ id: string }>();
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>Compose reviewed VAT201 book schedules</summary>
      <p>
        Combine disjoint reviewed schedules covering every explicit row of the
        selected layout for one TRN and period. Missing boxes are not nil.
        Totals include summary boxes and are not net tax payable. Independently
        review the composed source; retain filed-return evidence separately.
      </p>
      <ErrorState error={action.error} />
      <label>
        VAT201 composition layout
        <select
          value={layout}
          onChange={(event) => setLayout(event.target.value)}
        >
          {Object.entries(layouts).map(([value, item]) => (
            <option key={value} value={value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {["emirate-20", "ecommerce-20"].includes(layout) && (
        <p>
          Retain all seven assessed Box 1a-1g allocations and Boxes 2-14.
          Aggregate Box 1 cannot be spread automatically. This compares emirate
          totals. For the e-commerce layout retain both explicit three-amount
          supply breakdowns for every emirate, including zero. Qualifying
          registrant status, reporting periods and legal allocation remain
          separately assessed.
        </p>
      )}
      <label>
        Composed VAT201 source title
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <label>
        Reviewed VAT201 component schedules
        <select
          multiple
          size={6}
          style={{ height: 160 }}
          value={selected}
          onChange={(e) =>
            setSelected(
              Array.from(e.target.selectedOptions, (option) => option.value),
            )
          }
        >
          {sources
            .filter(
              (s) =>
                s.kind === "workflow-source" &&
                s.table_type === "return-boxes" &&
                s.freshness === "CURRENT" &&
                s.review_status === "REVIEWED",
            )
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
        </select>
      </label>
      <p>
        Select two to {layouts[layout]?.boxes.length || 14} schedules. Every
        selected row is included; overlapping boxes are rejected rather than
        summed.
      </p>
      <label>
        Independent composed taxable amount
        <input
          value={base}
          onChange={(e) => setBase(e.target.value)}
          inputMode="decimal"
        />
      </label>
      <label>
        Independent composed tax total
        <input
          value={tax}
          onChange={(e) => setTax(e.target.value)}
          inputMode="decimal"
        />
      </label>
      <label>
        Independent composed adjustment total
        <input
          value={adjustment}
          onChange={(e) => setAdjustment(e.target.value)}
          inputMode="decimal"
        />
      </label>
      <label>
        VAT201 composition scope assessment
        <textarea
          style={{ height: 90 }}
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <Button
        disabled={
          action.isPending ||
          selected.length < 2 ||
          selected.length > (layouts[layout]?.boxes.length || 14) ||
          !label ||
          !base ||
          !tax ||
          !adjustment ||
          assessment.trim().length < 10
        }
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/vat201-composition-source`,
              body: {
                source_ids: selected,
                layout,
                label,
                taxable_amount: base,
                tax,
                adjustment,
                assessment,
              },
            });
            onCreated(result.id);
          } catch {
            /* The mutation exposes the server error above. */
          }
        }}
      >
        Prepare composed VAT201 books
      </Button>
    </details>
  );
}
