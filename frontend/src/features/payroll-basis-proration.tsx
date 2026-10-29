"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export function ProratedPayrollSource({
  eid,
  resultId,
  onCreated,
}: {
  eid: string;
  resultId: string;
  onCreated: (id: string) => void;
}) {
  const [count, setCount] = useState("");
  const [total, setTotal] = useState("");
  const [label, setLabel] = useState("");
  const [assessment, setAssessment] = useState("");
  const action = useAction<{ id: string }>();
  const valid =
    /^\d+$/.test(count) &&
    Number(count) >= 3 &&
    Number(count) <= 5000 &&
    /^\d+(\.\d{1,8})?$/.test(total) &&
    label.trim().length >= 3 &&
    assessment.trim().length >= 10;
  return (
    <section
      className="main-panel"
      style={{ padding: 20, marginTop: 16 }}
      aria-label="Reviewed monthly PF wage source"
    >
      <h3>Prepare monthly PF bases for contribution review</h3>
      <p>
        Enter independently checked controls for the entire result, including
        all three PF component bases. Their combined INR amount is a
        component-basis control, not gross payroll or a contribution total. The
        prepared source needs independent review.
      </p>
      <p>
        Use a reviewed contribution rate covering the whole month, without
        another salary ceiling or wage slab. Membership and ceiling changes are
        retained in the dated basis; changing contribution rates need separate
        assessment.
      </p>
      <ErrorState error={action.error} />
      <label>
        Monthly basis source title
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <label>
        Independent PF component-basis row count
        <input
          inputMode="numeric"
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>
      <label>
        Independent post-ceiling component-basis total (INR)
        <input
          inputMode="decimal"
          value={total}
          onChange={(e) => setTotal(e.target.value)}
        />
      </label>
      <label>
        Monthly basis control assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <Button
        disabled={!valid || action.isPending}
        onClick={async () => {
          try {
            const source = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/prorated-payroll-basis-source`,
              body: {
                result_id: resultId,
                expected_rows: Number(count),
                control_total: total,
                label: label.trim(),
                assessment: assessment.trim(),
              },
            });
            onCreated(source.id);
          } catch {
            /* useAction renders the API error. */
          }
        }}
      >
        Prepare reviewed monthly wage source
      </Button>
    </section>
  );
}

export function PayrollBasisSegments({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  const segments = rows.flatMap((row) =>
    Array.isArray(row.segment_trace)
      ? (row.segment_trace as Record<string, unknown>[])
      : [],
  );
  const fields = [
    "subject",
    "component",
    "segment_start",
    "segment_end",
    "calendar_days",
    "month_days",
    "monthly_reference_basis",
    "amount",
    "eligible",
    "cap_rule_id",
    "post_cap_segment_basis",
    "eligibility_reference",
  ];
  return (
    <section aria-label="Dated PF wage-basis evidence">
      <h3>Dated PF wage bases</h3>
      <p>
        Actual calendar days, rounded to paise per segment. All calendar days
        require explicit evidence, including excluded periods. This calculates
        wage bases; contributions and payment evidence are separate.
      </p>
      <p>
        {segments.length} segment records on this result page. Showing the first{" "}
        {Math.min(20, segments.length)}; XLSX retains every segment and ceiling
        policy.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <caption>Dated PF segment preview</caption>
          <thead>
            <tr>
              {fields.map((f) => (
                <th key={f}>{f.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segments.slice(0, 20).map((r, i) => (
              <tr key={`${String(r.id)}:${i}`}>
                {fields.map((f) => (
                  <td key={f}>
                    {r[f] == null
                      ? "Not established"
                      : typeof r[f] === "boolean"
                        ? r[f]
                          ? "Assessed eligible"
                          : "Assessed excluded"
                        : String(r[f])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
