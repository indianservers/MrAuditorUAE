"use client";
import { useState } from "react";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { IntelligenceExports } from "./intelligence-exports";
type Paper = { id: string; reference: string; status: string };
type Rollup = {
  id: string;
  version: number;
  freshness: string;
  body: {
    review_status: string;
    title: string;
    blocked: boolean;
    unique_findings: number;
    workpaper_reference_count: number;
    duplicate_references_eliminated: number;
    totals_by_currency: Record<
      string,
      {
        positive_impact: string;
        negative_impact: string;
        finding_count: number;
      }
    >;
    rows: {
      id: string;
      reference: string;
      status: string;
      financial_impact: string | null;
      currency: string | null;
      workpaper_ids: string[];
      aggregation: string;
      issues: string[];
      correction_status?: string;
    }[];
    issues: { source_id: string; code: string }[];
    limitations: string[];
  };
};
export function TaxCloseExposures({ eid }: { eid: string }) {
  const scope = useScope((s) => `${s.tenant}:${s.country}`);
  return <ExposureForm key={`${scope}:${eid}`} eid={eid} />;
}
function ExposureForm({ eid }: { eid: string }) {
  const tenant = useScope((s) => s.tenant);
  const [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<Record<string, string>>({}),
    [resultId, setResultId] = useState(""),
    [title, setTitle] = useState(""),
    [rationale, setRationale] = useState("");
  const base = `engagements/${eid}/audit`,
    prefix = `intelligence/engagements/${eid}`;
  const papers = useAPI<{ items: Paper[]; total: number }>(
    `${base}/working-papers?limit=50&offset=${offset}`,
  );
  const history = useEventHistory<{ id: string; kind: string; label: string }>(
    prefix,
  );
  const detail = useAPI<Rollup>(`${prefix}/events/${resultId}`, !!resultId);
  const action = useAction<Rollup>();
  const canPrepare = useCan("workingpaper.create"),
    canReview = useCan("workingpaper.approve");
  const result = detail.data;
  async function review(decision: "approve" | "reject") {
    if (!result) return;
    const next = await action
      .mutateAsync({
        path: `${prefix}/events/${result.id}/review`,
        body: {
          action: decision,
          expected_version: result.version,
          comments: rationale,
        },
      })
      .catch(() => null);
    if (next) setResultId(next.id);
  }
  return (
    <section className="main-panel" aria-label="Tax-close finding roll-up">
      <h2>Tax-close finding roll-up</h2>
      <p>
        Select reviewed workpapers in the tax-close population. Each linked
        audit finding is counted once by its exact ID across these papers.
        Different findings are not assumed to be duplicates; this is a gross
        impact schedule, not a net tax liability.
      </p>
      <ErrorState
        error={papers.error || history.error || detail.error || action.error}
      />
      <fieldset disabled={!canPrepare || action.isPending}>
        <legend>Reviewed source workpapers</legend>
        {(papers.data?.items || [])
          .filter((p) => ["APPROVED", "LOCKED"].includes(p.status))
          .map((p) => (
            <label key={p.id}>
              <input
                type="checkbox"
                checked={!!selected[p.id]}
                disabled={!selected[p.id] && Object.keys(selected).length >= 50}
                onChange={(e) =>
                  setSelected((old) => {
                    const next = { ...old };
                    if (e.target.checked) next[p.id] = p.reference;
                    else delete next[p.id];
                    return next;
                  })
                }
              />
              {p.reference} · {p.status}
            </label>
          ))}
        <Button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Previous roll-up papers
        </Button>
        <Button
          disabled={offset + 50 >= (papers.data?.total || 0)}
          onClick={() => setOffset(offset + 50)}
        >
          Next roll-up papers
        </Button>
        <p>{Object.keys(selected).length} selected workpapers (maximum 50).</p>
        {Object.entries(selected).map(([id, label]) => (
          <Button
            key={id}
            onClick={() =>
              setSelected((old) => {
                const next = { ...old };
                delete next[id];
                return next;
              })
            }
          >
            Remove {label}
          </Button>
        ))}
        <label>
          Roll-up title
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
      </fieldset>
      <label>
        Tax-close population and review rationale
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
      </label>
      <Button
        disabled={
          !canPrepare ||
          action.isPending ||
          !Object.keys(selected).length ||
          title.trim().length < 3 ||
          rationale.trim().length < 10
        }
        onClick={async () => {
          const created = await action
            .mutateAsync({
              path: `regulatory/engagements/${eid}/tax-close-rollups`,
              body: { workpaper_ids: Object.keys(selected), title, rationale },
            })
            .catch(() => null);
          if (created) setResultId(created.id);
        }}
      >
        Prepare finding roll-up
      </Button>
      <label>
        Retained finding roll-up
        <select value={resultId} onChange={(e) => setResultId(e.target.value)}>
          <option value="">Choose retained result</option>
          {result &&
            !history.data?.items.some((item) => item.id === result.id) && (
              <option value={result.id}>
                {result.body.title} � v{result.version}
              </option>
            )}
          {history.data?.items
            .filter((i) => i.kind === "tax-close-rollup")
            .map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
        </select>
      </label>
      {history.hasOlder && (
        <Button disabled={history.loadingOlder} onClick={history.loadOlder}>
          Load older finding roll-ups
        </Button>
      )}
      {result && (
        <>
          <h3>{result.body.title}</h3>
          <Status value={result.freshness} />
          <Status value={result.body.review_status} />
          <p>
            {result.body.unique_findings} distinct findings,{" "}
            {result.body.workpaper_reference_count} workpaper references,{" "}
            {result.body.duplicate_references_eliminated} repeated references
            eliminated.
          </p>
          <table>
            <caption>
              Gross reviewed impacts by currency; positive and negative amounts
              remain separate
            </caption>
            <thead>
              <tr>
                <th>Currency</th>
                <th>Positive impact</th>
                <th>Negative impact</th>
                <th>Findings counted</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.body.totals_by_currency).map(
                ([currency, values]) => (
                  <tr key={currency}>
                    <td>{currency}</td>
                    <td>{values.positive_impact}</td>
                    <td>{values.negative_impact}</td>
                    <td>{values.finding_count}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          <table>
            <caption>Each selected linked finding appears once</caption>
            <thead>
              <tr>
                <th>Finding</th>
                <th>Impact</th>
                <th>Currency</th>
                <th>Review</th>
                <th>Workpapers</th>
              </tr>
            </thead>
            <tbody>
              {result.body.rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.reference}
                    <details>
                      <summary>Source identity</summary>
                      {row.id}
                    </details>
                  </td>
                  <td>{row.financial_impact ?? "Unquantified"}</td>
                  <td>{row.currency ?? "Not assessed"}</td>
                  <td>
                    {row.status} · {row.aggregation}
                  </td>
                  <td>
                    <details>
                      <summary>{row.workpaper_ids.length} papers</summary>
                      <ul>
                        {row.workpaper_ids.map((id) => (
                          <li key={id}>{id}</li>
                        ))}
                      </ul>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.body.issues.length > 0 && (
            <ul aria-label="Unresolved roll-up issues">
              {result.body.issues.map((issue, i) => (
                <li key={i}>
                  {issue.source_id}: {issue.code}
                </li>
              ))}
            </ul>
          )}
          <ul>
            {result.body.limitations.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
          <Button
            disabled={
              !canReview ||
              action.isPending ||
              result.body.blocked ||
              result.freshness !== "CURRENT" ||
              rationale.trim().length < 10
            }
            onClick={() => review("approve")}
          >
            Independently approve finding roll-up
          </Button>
          <Button
            disabled={
              !canReview ||
              action.isPending ||
              result.freshness !== "CURRENT" ||
              rationale.trim().length < 10
            }
            onClick={() => review("reject")}
          >
            Reject finding roll-up
          </Button>
          <IntelligenceExports
            key={`${tenant}:${result.id}`}
            tenant={tenant}
            prefix={prefix}
            eventId={result.id}
            filename="tax-close-findings"
          />
        </>
      )}
    </section>
  );
}
