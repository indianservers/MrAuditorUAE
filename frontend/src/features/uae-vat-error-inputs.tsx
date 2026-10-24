"use client";
import { useState } from "react";
import { useAction, useCan } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
export function UAEVATErrorInputs({
  eid,
  sources,
  onResult,
}: {
  eid: string;
  sources: { id: string; reference: string; title: string; status: string }[];
  onResult: (value: Record<string, unknown>) => void;
}) {
  const [source, setSource] = useState(""),
    [population, setPopulation] = useState(""),
    [review, setReview] = useState(""),
    [error, setError] = useState<Error>();
  const action = useAction<Record<string, unknown>>(),
    canRun = useCan("ai.workflow.run"),
    canCalculate = useCan("vat.calculate");
  async function calculate() {
    setError(undefined);
    try {
      const periods = population
        .trim()
        .split(/\r?\n/)
        .filter(Boolean)
        .map((line, index) => {
          const v = line.split(",").map((s) => s.trim());
          if (v.length !== 4 || v.some((s) => !s))
            throw new Error(
              `Row ${index + 1} needs period start, period end, original tax due and corrected tax due.`,
            );
          return {
            period_start: v[0],
            period_end: v[1],
            filed_tax_due_aed: v[2],
            corrected_tax_due_aed: v[3],
          };
        });
      onResult(
        await action.mutateAsync({
          path: `ai/engagements/${eid}/use-cases/8/actions`,
          body: {
            action: "historical-vat-errors",
            record_id: source,
            idempotency_key: crypto.randomUUID(),
            payload: { periods, correction_rule_review: review },
          },
        }),
      );
    } catch (e) {
      setError(
        e instanceof Error ? e : new Error("Historical schedule failed"),
      );
    }
  }
  return (
    <section aria-label="Historical VAT correction schedule">
      <h3>Historical VAT differences</h3>
      <label>
        Approved original-filing and corrected-data evidence
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Select reviewed evidence</option>
          {sources
            .filter((s) => ["APPROVED", "LOCKED"].includes(s.status))
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.reference} · {s.title}
              </option>
            ))}
        </select>
      </label>
      <p>
        Paste one row per period without a header: start date, end date, filed
        tax due in AED, corrected tax due in AED. Use plain decimals. Increases
        and decreases remain separate.
      </p>
      <label>
        Reviewed period totals
        <textarea
          value={population}
          onChange={(e) => setPopulation(e.target.value)}
          maxLength={45000}
        />
      </label>
      <label>
        Correction-rule and discovery-date review
        <textarea
          value={review}
          onChange={(e) => setReview(e.target.value)}
          maxLength={4000}
        />
      </label>
      <Button
        disabled={
          !canRun ||
          !canCalculate ||
          !source ||
          !population.trim() ||
          review.trim().length < 10 ||
          action.isPending
        }
        onClick={calculate}
      >
        Prepare correction review schedule
      </Button>
      <p>
        The schedule does not authenticate filing acceptance or decide the
        legally permitted correction route.
      </p>
      {error && <ErrorState error={error} />}
    </section>
  );
}
