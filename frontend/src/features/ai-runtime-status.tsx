"use client";

import { useAPI } from "@/hooks/use-api";
import { ErrorState, Facts } from "@/components/ui/primitives";

export function AIRuntimeStatus({ eid }: { eid: string }) {
  const status = useAPI<{
    language: Record<string, unknown>;
    local_ml: Record<string, unknown>;
  }>(`ai/engagements/${eid}/runtime-status`);
  return (
    <section aria-label="AI runtime status">
      <h2>AI runtime status</h2>
      <ErrorState error={status.error} />
      {status.data ? (
        <>
          <Facts data={status.data.language} />
          <Facts data={status.data.local_ml} />
        </>
      ) : (
        <p>Runtime status unavailable</p>
      )}
      <p>
        Deterministic calculations and local ML operate independently of the
        language gateway. Model readiness requires a validated artifact and
        approved deployment.
      </p>
    </section>
  );
}
