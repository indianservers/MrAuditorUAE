"use client";
import { useState } from "react";
import Link from "next/link";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { useAPI, useAction } from "@/hooks/use-api";
import type { Page, RecordRow } from "@/types/models";
import { PageHeader } from "./shared";

type Statements = {
  id: string;
  version: number;
  freshness: string;
  body: {
    review_status: string;
    currency: string;
    framework: string;
    division: string;
    totals: Record<string, string>;
    period_profit: string;
    comparative_totals?: Record<string, string> | null;
    comparative_period_profit?: string | null;
    balance_sheet_difference_including_unappropriated_profit: string;
    rows: {
      account_code: string;
      name: string;
      classification: string;
      statement_group: string;
      source_closing_debit_positive: string;
      presented_amount: string;
      comparative_amount: string | null;
      source_snapshot_id?: string | null;
      comparative_source_snapshot_id?: string | null;
      current_account_in_source?: boolean;
      comparative_account_in_source?: boolean;
    }[];
    limitations: string[];
  };
};
export function IndiaFinancialReporting() {
  const [eid, setEid] = useState("");
  const [snapshot, setSnapshot] = useState("");
  const [mapping, setMapping] = useState("");
  const [applicability, setApplicability] = useState("");
  const [division, setDivision] = useState("II");
  const [comparative, setComparative] = useState("");
  const [comments, setComments] = useState("");
  const [selected, setSelected] = useState("");
  const engagements = useAPI<Page<RecordRow>>("engagements?limit=100");
  const engagement = useAPI<RecordRow>(`engagements/${eid}`, !!eid);
  const inputs = useAPI<{ snapshots: { id: string; label: string }[] }>(
    `intelligence/engagements/${eid}/inputs`,
    !!eid,
  );
  const profiles = useAPI<{ items: RecordRow[] }>(
    `accounting/mappings?entity_id=${engagement.data?.entity_id || ""}&period_id=${engagement.data?.period_id || ""}&limit=100`,
    !!engagement.data,
  );
  const cases = useAPI<{
    items: {
      id: string;
      label: string;
      review_status: string;
      freshness: string;
    }[];
  }>(
    `intelligence/engagements/${eid}/events?kind=statutory-checklist&limit=100`,
    !!eid,
  );
  const runs = useAPI<{
    items: {
      id: string;
      label: string;
      version: number;
      review_status: string;
      freshness: string;
    }[];
  }>(
    `intelligence/engagements/${eid}/events?kind=india-financial-statements&limit=100`,
    !!eid,
  );
  const detail = useAPI<Statements>(
    `intelligence/engagements/${eid}/events/${selected}`,
    !!eid && !!selected,
  );
  const action = useAction<Statements>();
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="India financial reporting"
        title="Schedule III Source Reconciliation"
        description="Derive statement drafts from actual trial balances, approved presentation mappings and reviewed AS / Ind AS applicability. IFRS equivalence is never assumed."
      />
      <div className="toolbar" style={{ padding: 16 }}>
        <label>
          Engagement
          <select
            value={eid}
            onChange={(e) => {
              setEid(e.target.value);
              setSnapshot("");
              setMapping("");
              setApplicability("");
              setComparative("");
              setSelected("");
            }}
          >
            <option value="">Select Indian reporting engagement</option>
            {engagements.data?.items.map((e) => (
              <option key={e.id} value={e.id}>
                {String(e.name)}
              </option>
            ))}
          </select>
        </label>
        <Link className="button" href="/audit/india/disclosures">
          Review disclosure applicability
        </Link>
        {eid && (
          <Link className="button" href={`/engagements/${eid}/workspace`}>
            Approved reporting context
          </Link>
        )}
      </div>
      <ErrorState
        error={
          engagements.error ||
          engagement.error ||
          inputs.error ||
          profiles.error ||
          cases.error ||
          runs.error ||
          detail.error ||
          action.error
        }
      />
      {eid && (
        <>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Source and format controls</h2>
            <label>
              Committed accounting snapshot
              <select
                value={snapshot}
                onChange={(e) => setSnapshot(e.target.value)}
              >
                <option value="">Select retained source</option>
                {inputs.data?.snapshots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Approved presentation mapping
              <select
                value={mapping}
                onChange={(e) => setMapping(e.target.value)}
              >
                <option value="">Select reviewed complete mapping</option>
                {profiles.data?.items
                  .filter((p) => p.approved)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {String(p.name)} • v{String(p.version)}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Reviewed Indian disclosure / division applicability case
              <select
                value={applicability}
                onChange={(e) => setApplicability(e.target.value)}
              >
                <option value="">Select reviewed case</option>
                {cases.data?.items
                  .filter(
                    (c) =>
                      c.review_status === "REVIEWED" &&
                      c.freshness === "CURRENT",
                  )
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Schedule III division
              <select
                value={division}
                onChange={(e) => setDivision(e.target.value)}
              >
                <option value="I">Division I • AS</option>
                <option value="II">Division II • Ind AS</option>
                <option value="III">
                  Division III • applicable Ind AS NBFC presentation
                </option>
              </select>
            </label>
            <label>
              Earlier-period snapshot ID (optional)
              <input
                value={comparative}
                onChange={(e) => setComparative(e.target.value)}
              />
            </label>
            <label>
              Source / presentation rationale
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
              />
            </label>
            <Button
              primary
              disabled={
                action.isPending || !snapshot || !mapping || !applicability
              }
              onClick={async () => {
                const result = await action
                  .mutateAsync({
                    path: `regulatory/engagements/${eid}/india-statements`,
                    body: {
                      snapshot_id: snapshot,
                      mapping_profile_id: mapping,
                      applicability_id: applicability,
                      division,
                      rationale: comments,
                      ...(comparative
                        ? { comparative_snapshot_id: comparative }
                        : {}),
                    },
                  })
                  .catch(() => null);
                if (result) setSelected(result.id);
              }}
            >
              Generate source-reconciled statement draft
            </Button>
            <p>
              Cash flow, equity movements, note contents and statutory
              completeness require actual reviewed schedules. Missing balances
              are never silently excluded.
            </p>
          </section>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Reconciliation and preserved versions</h2>
            <label>
              Statement version
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Select retained run</option>
                {runs.data?.items.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label} • v{r.version} • {r.review_status} • {r.freshness}
                  </option>
                ))}
              </select>
            </label>
            {detail.data && (
              <>
                <Status value={detail.data.freshness} />
                <Status value={detail.data.body.review_status} />
                <p>
                  {detail.data.body.framework} • Division{" "}
                  {detail.data.body.division} • {detail.data.body.currency}
                </p>
                <div className="toolbar">
                  {Object.entries(detail.data.body.totals).map(
                    ([label, amount]) => (
                      <div key={label}>
                        <strong>{label}</strong>
                        <p>{amount}</p>
                      </div>
                    ),
                  )}
                </div>
                <p>Period profit: {detail.data.body.period_profit}</p>
                {detail.data.body.comparative_totals && (
                  <section aria-label="Retained comparative statement totals">
                    <h3>Comparative totals</h3>
                    <dl>
                      {Object.entries(detail.data.body.comparative_totals).map(
                        ([label, amount]) => (
                          <div key={label}>
                            <dt>{label}</dt>
                            <dd>{amount}</dd>
                          </div>
                        ),
                      )}
                    </dl>
                    <p>
                      Comparative period profit:{" "}
                      {detail.data.body.comparative_period_profit}
                    </p>
                  </section>
                )}
                <p>
                  Statement equation difference:{" "}
                  {
                    detail.data.body
                      .balance_sheet_difference_including_unappropriated_profit
                  }
                </p>
                <div style={{ overflowX: "auto" }}>
                  <table>
                    <thead>
                      <tr>
                        {[
                          "Account",
                          "Name",
                          "Approved group",
                          "Source balance",
                          "Presented amount",
                          "Comparative",
                          "Current source snapshot",
                          "Comparative source snapshot",
                        ].map((h) => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.body.rows.map((r) => (
                        <tr key={r.account_code}>
                          <td>{r.account_code}</td>
                          <td>{r.name}</td>
                          <td>{r.statement_group}</td>
                          <td>
                            {r.current_account_in_source === false
                              ? "Not in current source"
                              : r.source_closing_debit_positive}
                          </td>
                          <td>{r.presented_amount}</td>
                          <td>
                            {r.comparative_amount ??
                              (r.comparative_account_in_source === false
                                ? "Not in comparative source"
                                : "Not supplied")}
                          </td>
                          <td>
                            {r.source_snapshot_id ??
                              (r.current_account_in_source === false
                                ? "No current source account"
                                : "Not recorded")}
                          </td>
                          <td>
                            {r.comparative_source_snapshot_id ??
                              (r.comparative_account_in_source === false
                                ? "No comparative source account"
                                : "Not recorded")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <ul>
                  {detail.data.body.limitations.map((text) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
                <Link
                  className="button"
                  href={`/intelligence/${eid}/lead?event=${selected}`}
                >
                  Independent review, working papers and exports
                </Link>
                <Link className="button" href="/reports/statutory">
                  Compose controlled reporting package
                </Link>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
