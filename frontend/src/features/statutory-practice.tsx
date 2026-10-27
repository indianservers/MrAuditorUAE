"use client";
import { useState } from "react";
import Link from "next/link";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { PageHeader } from "./shared";
import type { Page, RecordRow } from "@/types/models";

const areas = {
  "companies-act": "Companies Act checklist",
  caro: "CARO clause review",
  "india-tax-audit": "India tax audit",
  "india-disclosures": "Schedule III / Ind AS disclosure review",
  "uae-disclosures": "UAE IFRS disclosure review",
  "qfzp-assessment": "QFZP evidence assessment",
  "dmtt-applicability": "DMTT scope assessment",
  "group-audit": "Group audit component review",
};
type Item = {
  clause: string;
  rule_id: string;
  state: string;
  facts: string;
  fact_sources: string;
  procedure: string;
  conclusion: string;
  management_response: string;
  evidence_ids: string[];
};
type Case = {
  id: string;
  version: number;
  freshness: string;
  body: {
    area: string;
    title: string;
    review_status: string;
    items: Record<string, unknown>[];
  };
};
export function StatutoryPractice({
  area = "companies-act",
}: {
  area?: string;
}) {
  const [eid, setEid] = useState("");
  const [rule, setRule] = useState("");
  const [clause, setClause] = useState("");
  const [facts, setFacts] = useState('{"entity_type":"company"}');
  const [factSources, setFactSources] = useState("{}");
  const [procedure, setProcedure] = useState("");
  const [conclusion, setConclusion] = useState("");
  const [response, setResponse] = useState("");
  const [state, setState] = useState("PENDING");
  const [evidenceIds, setEvidence] = useState<string[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [comments, setComments] = useState("");
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const country = useScope((s) => s.country);
  const engagements = useAPI<Page<RecordRow>>("engagements?limit=100");
  const rules = useAPI<{
    items: {
      id: string;
      rule_key: string;
      version: number;
      state: string;
      body: {
        effective_from: string;
        effective_to?: string;
        framework: string;
      };
    }[];
  }>(`regulatory/rules?country=${country}&limit=100`);
  const evidence = useAPI<{ items: RecordRow[] }>(
    `engagements/${eid}/audit/evidence?limit=100`,
    !!eid,
  );
  const papers = useAPI<{ items: RecordRow[] }>(
    `engagements/${eid}/audit/working-papers?limit=100`,
    !!eid,
  );
  const cases = useAPI<{
    items: { id: string; label: string; review_status: string }[];
  }>(
    `intelligence/engagements/${eid}/events?kind=statutory-checklist&limit=100`,
    !!eid,
  );
  const detail = useAPI<Case>(
    `intelligence/engagements/${eid}/events/${selected}`,
    !!eid && !!selected,
  );
  const action = useAction<Case>();
  const title = areas[area as keyof typeof areas] || areas["companies-act"];
  async function save() {
    setError(null);
    try {
      const result = await action.mutateAsync({
        path: `regulatory/engagements/${eid}/checklists`,
        body: {
          area,
          title,
          rationale: comments,
          items: items.map((i) => ({
            ...i,
            facts: JSON.parse(i.facts),
            fact_sources: JSON.parse(i.fact_sources),
          })),
          ...(detail.data
            ? {
                prior_id: detail.data.id,
                expected_version: detail.data.version,
              }
            : {}),
        },
      });
      setSelected(result.id);
    } catch (e) {
      setError(e as Error);
    }
  }
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="Country compliance"
        title={title}
        description="Record entity-specific applicability, actual procedures, evidence, management responses and independent reviewer conclusions."
      />
      <div className="toolbar" style={{ padding: 16, flexWrap: "wrap" }}>
        <label>
          Engagement
          <select
            value={eid}
            onChange={(e) => {
              setEid(e.target.value);
              setSelected("");
              setItems([]);
            }}
          >
            <option value="">Select engagement</option>
            {engagements.data?.items.map((e) => (
              <option key={e.id} value={e.id}>
                {String(e.name)}
              </option>
            ))}
          </select>
        </label>
        <Link className="button" href="/settings/regulatory-rules">
          Regulatory library
        </Link>
        <Link className="button" href="/settings">
          Working country: {country}
        </Link>
        {eid && (
          <Link className="button" href={`/engagements/${eid}/lifecycle`}>
            Source relationship graph
          </Link>
        )}
      </div>
      <ErrorState
        error={
          engagements.error ||
          rules.error ||
          evidence.error ||
          papers.error ||
          detail.error ||
          action.error ||
          error
        }
      />
      {eid && (
        <>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Clause register</h2>
            <p>
              Use a professionally validated, published rule for the actual
              period and framework. A pending provision cannot be treated as
              compliant. Country incorporation alone does not establish
              applicability.
            </p>
            <label>
              Clause or checklist reference
              <input
                value={clause}
                onChange={(e) => setClause(e.target.value)}
              />
            </label>
            <label>
              Published rule version
              <select value={rule} onChange={(e) => setRule(e.target.value)}>
                <option value="">Select effective-dated rule</option>
                {rules.data?.items
                  .filter((r) => r.state === "PUBLISHED")
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.rule_key} • v{r.version} • {r.body.framework} •{" "}
                      {r.body.effective_from}–{r.body.effective_to || "open"}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Entity applicability facts (JSON)
              <textarea
                value={facts}
                onChange={(e) => setFacts(e.target.value)}
              />
            </label>
            <label>
              Fact source bindings (JSON)
              <textarea
                value={factSources}
                onChange={(e) => setFactSources(e.target.value)}
                placeholder='{"turnover":{"kind":"intelligence","id":"reviewed-event-uuid","path":["totals","closing"]}}'
              />
            </label>
            <p>
              Use comparison: "exact" for retained dates, form identifiers and
              Boolean facts. Amounts use numeric comparison by default.
            </p>
            <label>
              Clause disposition
              <select value={state} onChange={(e) => setState(e.target.value)}>
                {[
                  "PENDING",
                  "APPLICABLE",
                  "NOT_APPLICABLE",
                  "EVIDENCE_REQUIRED",
                  "EXCEPTION_IDENTIFIED",
                  "PREPARED",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              Procedures actually performed
              <textarea
                value={procedure}
                onChange={(e) => setProcedure(e.target.value)}
              />
            </label>
            <label>
              Auditor conclusion
              <textarea
                value={conclusion}
                onChange={(e) => setConclusion(e.target.value)}
              />
            </label>
            <label>
              Management response
              <textarea
                value={response}
                onChange={(e) => setResponse(e.target.value)}
              />
            </label>
            <label>
              Existing evidence and working papers
              <select
                multiple
                size={5}
                value={evidenceIds}
                onChange={(e) =>
                  setEvidence(
                    Array.from(e.target.selectedOptions, (o) => o.value),
                  )
                }
              >
                {[
                  ...(evidence.data?.items || []),
                  ...(papers.data?.items || []),
                ].map((r) => (
                  <option key={r.id} value={r.id}>
                    {String(r.reference)} • {String(r.title)} •{" "}
                    {String(r.status)}
                  </option>
                ))}
              </select>
            </label>
            <Button
              disabled={!clause || !rule}
              onClick={() => {
                setItems([
                  ...items.filter((i) => i.clause !== clause),
                  {
                    clause,
                    rule_id: rule,
                    facts,
                    fact_sources: factSources,
                    procedure,
                    conclusion,
                    management_response: response,
                    state,
                    evidence_ids: evidenceIds,
                  },
                ]);
                setClause("");
              }}
            >
              Add or replace clause
            </Button>
            <table>
              <thead>
                <tr>
                  <th>Clause</th>
                  <th>Disposition</th>
                  <th>Evidence references</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.clause}>
                    <td>{i.clause}</td>
                    <td>
                      <Status value={i.state} />
                    </td>
                    <td>{i.evidence_ids.length}</td>
                    <td>
                      <Button
                        onClick={() =>
                          setItems(
                            items.filter((other) => other.clause !== i.clause),
                          )
                        }
                      >
                        Remove from new draft
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <label>
              Version / decision rationale
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
              />
            </label>
            <Button
              primary
              disabled={action.isPending || !items.length}
              onClick={save}
            >
              Save immutable checklist version
            </Button>
          </section>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Preserved reviews and drafts</h2>
            <label>
              Checklist version
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Select saved case</option>
                {cases.data?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label} • {c.review_status}
                  </option>
                ))}
              </select>
            </label>
            {detail.data && (
              <>
                <Status value={detail.data.body.review_status} />
                <Status value={detail.data.freshness} />
                <p>
                  Version {detail.data.version} • {detail.data.body.title}
                </p>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    maxHeight: 500,
                    overflow: "auto",
                  }}
                >
                  {JSON.stringify(detail.data.body.items, null, 2)}
                </pre>
                <div className="toolbar">
                  <Button
                    onClick={() => {
                      setItems(
                        detail.data!.body.items.map((i) => ({
                          clause: String(i.clause),
                          rule_id: String(i.rule_id),
                          facts: JSON.stringify(i.facts),
                          fact_sources: JSON.stringify(i.fact_sources || {}),
                          procedure: String(i.procedure),
                          conclusion: String(i.conclusion),
                          management_response: String(i.management_response),
                          state: String(i.state),
                          evidence_ids: i.evidence_ids as string[],
                        })),
                      );
                    }}
                  >
                    Copy retained clauses into new revision
                  </Button>
                  {["approve", "reject"].map((value) => (
                    <Button
                      key={value}
                      disabled={action.isPending}
                      onClick={async () => {
                        const updated = await action
                          .mutateAsync({
                            path: `intelligence/engagements/${eid}/events/${selected}/review`,
                            body: {
                              action: value,
                              expected_version: detail.data!.version,
                              comments,
                            },
                          })
                          .catch(() => null);
                        if (updated) setSelected(updated.id);
                      }}
                    >
                      {value === "approve"
                        ? "Record independent clause review"
                        : "Reject draft"}
                    </Button>
                  ))}
                  <Link
                    className="button"
                    href={`/intelligence/${eid}/lead?event=${selected}`}
                  >
                    Generate reviewed paper / export
                  </Link>
                </div>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
