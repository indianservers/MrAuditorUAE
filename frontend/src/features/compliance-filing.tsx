"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
import type { Paper } from "./grc-forms";

const stages = [
  "not_started",
  "preparing",
  "under_review",
  "approved_for_submission",
  "submitted",
  "acknowledged",
];

export function ComplianceFiling({
  base,
  paper,
}: {
  base: string;
  paper: Paper;
}) {
  const current = String(paper.body.filing_stage || "not_started");
  const next = stages[Math.min(stages.indexOf(current) + 1, stages.length - 1)];
  const [stage, setStage] = useState(next);
  const [receipt, setReceipt] = useState("");
  const action = useAction();
  const receiptRequired = stage === "submitted" || stage === "acknowledged";
  return (
    <section aria-label="Filing readiness">
      <h3>Filing readiness</h3>
      <p>
        {paper.reference} · version {paper.version} ·{" "}
        {current.replaceAll("_", " ")}
      </p>
      <p>
        Deadline:{" "}
        {String(
          paper.body.extension_deadline || paper.body.deadline || "Unresolved",
        )}
        . Record an evidenced human decision; this does not submit to an
        authority.
      </p>
      <label>
        Next filing stage
        <select
          value={stage}
          onChange={(e) => {
            setStage(e.target.value);
            setReceipt("");
          }}
        >
          {[...new Set([next, "preparing"])].map((value) => (
            <option key={value} value={value}>
              {value.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>
      {receiptRequired && (
        <label>
          {stage === "submitted"
            ? "Actual submission evidence record ID"
            : "Separate acknowledgment evidence record ID"}
          <input value={receipt} onChange={(e) => setReceipt(e.target.value)} />
        </label>
      )}
      <p>
        Approval for submission requires the designated independent reviewer and
        current approved readiness evidence. Generated returns and exports do
        not establish submission.
      </p>
      <Button
        disabled={
          action.isPending ||
          stage === current ||
          (receiptRequired && !/^[0-9a-f-]{36}$/i.test(receipt))
        }
        onClick={() =>
          action.mutate({
            path: `${base}/obligations/${paper.id}/filing-stage`,
            body: {
              version: paper.version,
              stage,
              ...(receiptRequired
                ? {
                    [stage === "submitted"
                      ? "submission_evidence_id"
                      : "acknowledgment_evidence_id"]: receipt,
                  }
                : {}),
            },
          })
        }
      >
        Record evidenced filing stage
      </Button>
      <ErrorState error={action.error} />
    </section>
  );
}
