"use client";
import Link from "next/link";
import { useAPI, useCan } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import type { Page, Engagement } from "@/types/models";
export function MLSignals() {
  const can = useCan("ml.read"),
    scope = useScope();
  const engagements = useAPI<Page<Engagement>>("engagements?limit=100", can);
  const engagement = engagements.data?.items.find(
    (e) =>
      (!scope.entity || e.entity_id === scope.entity) &&
      (!scope.period || e.period_id === scope.period),
  );
  const result = useAPI<{
    items: {
      id: string;
      body: {
        model_id: string;
        predictions: { transaction_id: string; score: number | number[] }[];
      };
    }[];
  }>(
    `ml/events?eid=${engagement?.id}&kind=inference&limit=1`,
    can && !!engagement,
  );
  if (!can) return null;
  return (
    <section className="p9-card">
      <h2>Experimental ML review signals</h2>
      <p>
        {result.data?.items.length
          ? `${result.data.items[0].body.predictions.length} persisted predictions in the latest authorized batch. Model ${result.data.items[0].body.model_id.slice(0, 8)}.`
          : "No ML inference batch is available for this engagement."}{" "}
        Deterministic audit findings remain independent. An anomaly signal does
        not establish fraud.
      </p>
      <Link href="/ai-lab/investigator">
        Inspect model signals and source transactions
      </Link>
    </section>
  );
}
