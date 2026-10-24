"use client";

import { useState } from "react";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Run = { id: string; kind: string };
export function ConnectedTaxReview({ eid }: { eid: string }) {
  const tax = useAPI<{ items: Run[] }>(`tax/engagements/${eid}/runs?limit=50`);
  const vat = useAPI<{ items: Run[] }>(`vat/engagements/${eid}/runs?limit=50`);
  const tp = useAPI<{ items: Run[] }>(`tp/engagements/${eid}/runs?limit=50`);
  const dmtt = useAPI<{ items: Run[] }>(`dmtt/engagements/${eid}/calculations`);
  const [selection, setSelection] = useState<Record<string, string>>({});
  const [rationale, setRationale] = useState("");
  const action = useAction<{
    id: string;
    body: { completeness: string; issues: string[] };
  }>();
  return (
    <section className="main-panel" style={{ padding: 16 }}>
      <h2>Connected tax review</h2>
      <p>
        Connect current calculations for this engagement. VAT, current tax,
        pricing and domestic top-up keep separate calculation owners and tax
        bases.
      </p>
      <div className="toolbar">
        {[
          ["ct_run_id", "Corporate tax", tax],
          ["vat_run_id", "VAT", vat],
          ["tp_run_id", "Transfer pricing", tp],
          ["dmtt_event_id", "UAE DMTT", dmtt],
        ].map(([key, label, query]) => {
          const source = query as typeof tax;
          return (
            <label key={String(key)}>
              {String(label)}
              <select
                value={selection[String(key)] || ""}
                onChange={(event) =>
                  setSelection({
                    ...selection,
                    [String(key)]: event.target.value,
                  })
                }
              >
                <option value="">Not selected</option>
                {source.data?.items.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.kind} · {run.id.slice(0, 8)}
                  </option>
                ))}
              </select>
              {source.error && (
                <span>Source access unavailable for this tax area.</span>
              )}
            </label>
          );
        })}
      </div>
      <label>
        Connected assessment rationale
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          maxLength={4000}
        />
      </label>
      <Button
        disabled={
          action.isPending ||
          rationale.length < 10 ||
          !Object.values(selection).some(Boolean)
        }
        onClick={() =>
          action.mutate({
            path: `tax/engagements/${eid}/connected-assessments`,
            body: {
              ...Object.fromEntries(
                Object.entries(selection).filter(([, value]) => value),
              ),
              rationale,
            },
          })
        }
      >
        Prepare connected review
      </Button>
      <ErrorState error={action.error} />
      {action.data && (
        <div>
          <p>
            Completeness: {action.data.body.completeness.replaceAll("_", " ")}.
            Draft; no filing submitted.
          </p>
          {action.data.body.issues.length > 0 && (
            <ul>
              {action.data.body.issues.map((issue, index) => (
                <li key={index}>{issue}</li>
              ))}
            </ul>
          )}
          <Link
            href={`/intelligence/${eid}/foundation-validation?event=${action.data.id}`}
          >
            Open sources, history and independent review
          </Link>
        </div>
      )}
    </section>
  );
}
