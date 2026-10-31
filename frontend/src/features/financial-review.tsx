"use client";
import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { ErrorState, Facts, Status } from "@/components/ui/primitives";
import { ReportingRecordSelect } from "./reporting-record-select";
import { money } from "@/lib/formatting/money";
import type { RecordRow } from "@/types/models";

type Review = {
  ready: boolean;
  dependencies_current: boolean;
  scope: string;
  issues: (RecordRow & {
    key: string;
    code: string;
    severity: string;
    location: string;
    message: string;
    carry_forward?: boolean;
  })[];
  casting: RecordRow[];
  changes: RecordRow[];
  presentation_lines: RecordRow[];
  resolved_issue_keys: string[];
};

export function FinancialReview({
  base,
  rid,
  precision = 2,
}: {
  base: string;
  rid: string;
  precision?: number;
}) {
  const [previous, setPrevious] = useState("");
  const review = useAPI<Review>(
    `${base}/runs/${rid}/review?${qs({ comparison_run_id: previous })}`,
    !!rid,
  );
  return (
    <section className="card" aria-label="Financial statement review">
      <h2>Financial statement review</h2>
      <ReportingRecordSelect
        path={`${base}/runs?kind=financials`}
        label="Compare earlier draft"
        value={previous}
        onChange={setPrevious}
        excludeId={rid}
        runs
      />
      <p>The current run is omitted from the choices; page counts include it.</p>
      <ErrorState error={review.error} />
      {review.isLoading && <p role="status">Checking statements…</p>}
      {review.data && (
        <>
          <Status
            value={review.data.ready ? "Checks passed" : "Review required"}
          />
          {!review.data.dependencies_current && (
            <p role="alert">
              Source inputs changed. Generate a new statement version before
              approval.
            </p>
          )}
          <p>{review.data.scope}</p>
          {review.data.issues.length ? (
            <ul>
              {review.data.issues.map((i) => (
                <li key={i.key}>
                  <strong>
                    {i.severity}: {i.location}
                  </strong>{" "}
                  — {i.message} {i.carry_forward && "(Carried forward)"}
                  <details>
                    <summary>Evidence</summary>
                    <Facts data={i.evidence as RecordRow} />
                  </details>
                </li>
              ))}
            </ul>
          ) : (
            <p>
              No issues found by the structured checks. Independent approval is
              still required.
            </p>
          )}
          <details>
            <summary>Displayed subtotal checks</summary>
            <div className="financial-review-scroll">
              <table className="financial-review-table">
                <caption>
                  Sum of displayed statement lines against rounded exact
                  subtotals
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Section</th>
                    <th scope="col">Period</th>
                    <th scope="col">Displayed sum</th>
                    <th scope="col">Rounded subtotal</th>
                    <th scope="col">Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {review.data.casting.map((r) => (
                    <tr key={String(r.section) + String(r.column)}>
                      <th scope="row">{String(r.section)}</th>
                      <td>{String(r.column)}</td>
                      <td>{money(r.displayed_sum, precision)}</td>
                      <td>{money(r.rounded_exact_total, precision)}</td>
                      <td>{money(r.rounding_difference, precision)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          {previous && (
            <details open>
              <summary>
                Changes since earlier draft ({review.data.changes.length})
              </summary>
              {review.data.changes.length ? (
                review.data.changes.map((c, i) => (
                  <details key={i}>
                    <summary>
                      {String(c.line_code || c.note_reference || c.field)} ·{" "}
                      {String(c.change)}
                    </summary>
                    <Facts data={c} />
                  </details>
                ))
              ) : (
                <p>No statement line, note or package changes.</p>
              )}
              {review.data.resolved_issue_keys.length > 0 && (
                <p>
                  Resolved issues: {review.data.resolved_issue_keys.join(", ")}
                </p>
              )}
            </details>
          )}
        </>
      )}
    </section>
  );
}
