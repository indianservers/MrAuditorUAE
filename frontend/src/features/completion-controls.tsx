"use client";
import { useState } from "react";
import Link from "next/link";
import { Button, Status } from "@/components/ui/primitives";

export type CompletionCheck = {
  code: string;
  passed: boolean;
  description?: string;
  record_ids?: string[];
  checked_records?: number;
  source_issues?: { record_id: string; kind: string; freshness: string }[];
};

function SourceIssues({
  issues,
  eid,
}: {
  issues: NonNullable<CompletionCheck["source_issues"]>;
  eid: string;
}) {
  const [limit, setLimit] = useState(25);
  return (
    <details style={{ flexBasis: "100%", minWidth: 0 }}>
      <summary>
        Reviewed records needing source reassessment ({issues.length})
      </summary>
      <p>
        Historical approval is retained. Reassess the changed sources, save
        revised work and obtain independent approval before release.
      </p>
      <ul>
        {issues.slice(0, limit).map((issue) => (
          <li key={issue.record_id} style={{ overflowWrap: "anywhere" }}>
            <Link
              href={`/engagements/${eid}/${encodeURIComponent(issue.kind)}?record=${encodeURIComponent(issue.record_id)}`}
            >
              {issue.kind} · {issue.record_id}
            </Link>{" "}
            <Status value={issue.freshness} />
          </li>
        ))}
      </ul>
      {limit < issues.length && (
        <Button onClick={() => setLimit((value) => value + 25)}>
          Show more affected records
        </Button>
      )}
    </details>
  );
}

export function CompletionControls({
  eid,
  checks,
  ready,
}: {
  eid: string;
  checks: CompletionCheck[];
  ready?: boolean;
}) {
  return (
    <section
      className="audit-completion"
      aria-label="Engagement completion controls"
    >
      <h3>
        Completion controls <Status value={ready ? "ready" : "outstanding"} />
      </h3>
      {checks.map((check) => (
        <div key={check.code} style={{ flexWrap: "wrap" }}>
          <span className={check.passed ? "check-pass" : "check-open"}>
            {check.passed ? "✓" : "○"}
          </span>
          <span>
            {check.description ||
              check.code.replaceAll("_", " ").replaceAll("-", " ")}
          </span>
          <Status value={check.passed ? "passed" : "review required"} />
          {check.checked_records !== undefined && (
            <p style={{ flexBasis: "100%", margin: 0 }}>
              {check.checked_records} approved or locked records checked for
              current sources.
            </p>
          )}
          {!!check.source_issues?.length && (
            <SourceIssues
              key={check.source_issues
                .map((issue) => issue.record_id + issue.freshness)
                .join(":")}
              issues={check.source_issues}
              eid={eid}
            />
          )}
        </div>
      ))}
    </section>
  );
}
