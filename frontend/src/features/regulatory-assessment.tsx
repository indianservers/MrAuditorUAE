"use client";
import { useState } from "react";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState } from "@/components/ui/primitives";
export function RegulatoryAssessmentPanel({ eid }: { eid: string }) {
  const country = useScope((s) => s.country);
  const [ids, setIds] = useState<string[]>([]);
  const [facts, setFacts] = useState("{}");
  const [factSources, setFactSources] = useState("{}");
  const [date, setDate] = useState("");
  const [source, setSource] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const rules = useAPI<{
    items: {
      id: string;
      rule_key: string;
      version: number;
      state: string;
      body: {
        title: string;
        effective_from: string;
        effective_to: string | null;
        framework: string;
        method: string;
      };
    }[];
  }>(`regulatory/rules?country=${country}&limit=100`);
  const schedules = useAPI<{
    items: {
      id: string;
      label: string;
      review_status: string;
      freshness: string;
    }[];
  }>(`intelligence/engagements/${eid}/events?kind=lead&limit=100`);
  const action = useAction<{ id: string }>();
  return (
    <section className="main-panel" style={{ padding: 20 }}>
      <h2>Apply validated effective-dated rules</h2>
      <p>
        Country, entity type, framework and reporting dates come from the
        approved engagement context. Additional facts and tax-base selection are
        professional inputs. No tax thresholds or legal regime are assumed.
      </p>
      <ErrorState
        error={rules.error || schedules.error || action.error || error}
      />
      <label>
        Published rule versions
        <select
          multiple
          size={5}
          value={ids}
          onChange={(e) =>
            setIds(Array.from(e.target.selectedOptions, (o) => o.value))
          }
        >
          {rules.data?.items
            .filter((r) => r.state === "PUBLISHED")
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.rule_key} • v{r.version} • {r.body.framework} •{" "}
                {r.body.effective_from}–{r.body.effective_to || "open"} •{" "}
                {r.body.method}
              </option>
            ))}
        </select>
      </label>
      <label>
        Additional applicability facts (JSON)
        <textarea
          rows={5}
          value={facts}
          onChange={(e) => setFacts(e.target.value)}
        />
      </label>
      <label>
        Numeric fact source bindings (JSON)
        <textarea
          value={factSources}
          onChange={(e) => setFactSources(e.target.value)}
          placeholder='{"turnover":{"kind":"record","id":"approved-record-uuid","path":["amount"]}}'
        />
      </label>
      <label>
        Transaction date (for transaction-based rules)
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>
      <label>
        Reviewed source schedule (required for arithmetic)
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">No financial calculation</option>
          {schedules.data?.items
            .filter(
              (s) =>
                s.review_status === "REVIEWED" && s.freshness === "CURRENT",
            )
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.label} • {s.id}
              </option>
            ))}
        </select>
      </label>
      <label>
        Professional applicability / tax-base selection rationale
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <Button
        disabled={action.isPending || !ids.length}
        onClick={async () => {
          setError(null);
          try {
            const output = await action.mutateAsync({
              path: `regulatory/engagements/${eid}/assessments`,
              body: {
                rule_ids: ids,
                facts: JSON.parse(facts),
                fact_sources: JSON.parse(factSources),
                rationale: reason,
                ...(date ? { transaction_date: date } : {}),
                ...(source ? { source_event_id: source } : {}),
              },
            });
            setResult(output.id);
          } catch (e) {
            setError(e as Error);
          }
        }}
      >
        Evaluate current rules and retain receipt
      </Button>
      {result && (
        <Link
          className="button"
          href={`/intelligence/${eid}/lead?event=${result}`}
        >
          Review source-backed assessment
        </Link>
      )}
    </section>
  );
}
