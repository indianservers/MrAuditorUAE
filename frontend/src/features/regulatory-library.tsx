"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status, Empty } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
import { RegulatorySources, bindRetainedSource } from "./regulatory-sources";

type Rule = {
  id: string;
  rule_key: string;
  country: string;
  version: number;
  sha256: string;
  body: Record<string, unknown>;
  current_sequence: number;
  state: string | { state: string };
  validation_blockers?: string[];
};

export function RegulatoryLibrary() {
  const country = useScope((s) => s.country);
  const tenant = useScope((s) => s.tenant);
  const params = useSearchParams();
  const [id, setId] = useState(params.get("rule") || "");
  const [search, setSearch] = useState("");
  const [authority, setAuthority] = useState("");
  const [effective, setEffective] = useState("");
  const [offset, setOffset] = useState(0);
  const [compare, setCompare] = useState("");
  const [editor, setEditor] = useState("");
  const [comments, setComments] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const list = useAPI<{ items: Rule[] }>(
    `regulatory/rules?country=${country}&search=${encodeURIComponent(search)}&authority=${encodeURIComponent(authority)}&offset=${offset}${effective ? `&effective_on=${effective}` : ""}`,
  );
  const detail = useAPI<Rule>(`regulatory/rules/${id}`, !!id);
  const diff = useAPI<{
    changes: { field: string; left: unknown; right: unknown }[];
  }>(`regulatory/rules/${id}/compare/${compare}`, !!id && !!compare);
  const impact = useAPI<{
    items: {
      engagement_id: string;
      result_id: string;
      freshness: string;
      review_status: string;
    }[];
  }>(`regulatory/rules/${id}/impact`, !!id);
  const action = useAction<Rule>();
  function proposal(revert = false) {
    if (!detail.data) return;
    setEditor(
      JSON.stringify(
        {
          ...detail.data.body,
          expected_sequence: detail.data.current_sequence,
          amendment_reason: "",
          reverts_version_id: revert ? detail.data.id : null,
        },
        null,
        2,
      ),
    );
  }
  async function save() {
    setError(null);
    try {
      const body = JSON.parse(editor);
      const result = await action.mutateAsync({
        path: "regulatory/rules",
        body,
      });
      setId(result.id);
      setEditor("");
    } catch (e) {
      setError(e as Error);
    }
  }
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="Settings"
        title="Regulatory Rule Library"
        description="Period-specific rules, official sources and controlled publication. Publication is not a government approval or audit conclusion."
      />
      <div className="toolbar" style={{ flexWrap: "wrap", padding: 16 }}>
        <label>
          Search rule identifier
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Authority (exact registered name)
          <input
            value={authority}
            onChange={(e) => {
              setAuthority(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Effective on
          <input
            type="date"
            value={effective}
            onChange={(e) => {
              setEffective(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <span>Country: {country}</span>
        <Button
          onClick={() =>
            setEditor(
              JSON.stringify(
                {
                  rule_key: `${country}-`,
                  country,
                  title: "",
                  description: "",
                  framework: country === "AE" ? "IFRS" : "Ind AS",
                  period_basis: "period_start",
                  effective_from: "",
                  effective_to: null,
                  citations: [
                    {
                      authority: "",
                      legislation: "",
                      url: "",
                      paragraph: "",
                      retrieval_status: "AWAITING_VALIDATION",
                      document_sha256: null,
                      source_document_id: null,
                      retrieved_on: null,
                    },
                  ],
                  input_requirements: ["entity_type"],
                  output_requirements: ["reviewed_conclusion"],
                  applicability: [],
                  exceptions_and_elections: [],
                  method: "checklist",
                  rate: null,
                  calculation_currency: null,
                  validation_status: "AWAITING_VALIDATION",
                  professional_review_status: "PENDING",
                  last_reviewed: null,
                  amendment_reason: "",
                  expected_sequence: 0,
                },
                null,
                2,
              ),
            )
          }
        >
          Propose new rule
        </Button>
      </div>
      <ErrorState
        error={
          list.error ||
          detail.error ||
          diff.error ||
          impact.error ||
          action.error ||
          error
        }
      />
      <RegulatorySources
        key={`${tenant}:${country}`}
        country={country}
        editor={editor}
        onAttach={(source, citationNumber) => {
          try {
            setEditor(bindRetainedSource(editor, source, citationNumber));
            setError(null);
          } catch (failure) {
            setError(failure as Error);
          }
        }}
      />
      <section className="main-panel" style={{ padding: 20 }}>
        <h2>Versions and publication status</h2>
        {!list.data?.items.length && (
          <Empty title="No tenant rules in this view">
            Create an explicit proposal with authoritative citations. No tax
            rates or applicability conclusions are assumed.
          </Empty>
        )}
        <table>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Version</th>
              <th>State</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.data?.items.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.rule_key}
                  <br />
                  {String(r.body.title)}
                </td>
                <td>{r.version}</td>
                <td>
                  <Status value={r.state} />
                </td>
                <td>
                  <Button
                    onClick={() => {
                      setId(r.id);
                      setCompare("");
                    }}
                  >
                    Inspect
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="toolbar">
          <Button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous 50
          </Button>
          <Button
            disabled={list.data?.items.length !== 50}
            onClick={() => setOffset(offset + 50)}
          >
            Next 50
          </Button>
        </div>
      </section>
      {detail.data && (
        <section className="main-panel" style={{ padding: 20 }}>
          <h2>
            {detail.data.rule_key} • v{detail.data.version}
          </h2>
          <Status
            value={
              typeof detail.data.state === "string"
                ? detail.data.state
                : detail.data.state.state
            }
          />
          <p>SHA-256: {detail.data.sha256}</p>
          {(
            detail.data.body.citations as {
              url: string;
              authority: string;
              paragraph: string;
            }[]
          ).map((c, i) => (
            <p key={i}>
              <a href={c.url} target="_blank" rel="noreferrer">
                {c.authority} • {c.paragraph}
              </a>
            </p>
          ))}
          <p>
            Publication blockers:{" "}
            {detail.data.validation_blockers?.join("; ") ||
              "No metadata blockers. Independent professional review still applies."}
          </p>
          <details>
            <summary>Full effective-dated rule and provenance</summary>
            <pre style={{ whiteSpace: "pre-wrap" }}>
              {JSON.stringify(detail.data.body, null, 2)}
            </pre>
          </details>
          <label>
            Decision rationale
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
            />
          </label>
          <div className="toolbar">
            {["approve", "reject", "publish"].map((value) => (
              <Button
                key={value}
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({
                    path: `regulatory/rules/${id}/decisions`,
                    body: {
                      action: value,
                      expected_sequence: detail.data!.current_sequence,
                      comments,
                    },
                  })
                }
              >
                {value === "publish"
                  ? "Publish approved version"
                  : value === "approve"
                    ? "Record independent approval"
                    : "Reject proposal"}
              </Button>
            ))}
            <Button onClick={() => proposal()}>Propose amendment</Button>
            <Button onClick={() => proposal(true)}>
              Propose controlled revert
            </Button>
          </div>
          <label>
            Compare with version
            <select
              value={compare}
              onChange={(e) => setCompare(e.target.value)}
            >
              <option value="">Select historical version</option>
              {list.data?.items
                .filter(
                  (r) => r.rule_key === detail.data!.rule_key && r.id !== id,
                )
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    Version {r.version}
                  </option>
                ))}
            </select>
          </label>
          {diff.data && (
            <pre style={{ whiteSpace: "pre-wrap" }}>
              {JSON.stringify(diff.data.changes, null, 2)}
            </pre>
          )}
          <h3>Affected accessible engagements</h3>
          {impact.data?.items.map((r) => (
            <p key={r.result_id}>
              <Link
                href={`/intelligence/${r.engagement_id}/lead?event=${r.result_id}`}
              >
                {r.engagement_id} • {r.freshness} • {r.review_status}
              </Link>
            </p>
          ))}
          <p className="subtle">
            Publishing a rule does not recalculate or overwrite historical
            outputs.
          </p>
        </section>
      )}
      {editor && (
        <section className="main-panel" style={{ padding: 20 }}>
          <h2>Rule proposal</h2>
          <p>
            For a rate-based rule, set calculation_currency to the ISO currency
            of the tax base. Assessment requires a reviewed source in that
            currency; no currency conversion is inferred.
          </p>
          <p>
            Enter the exact legal regime, period, applicability predicates and
            citation provenance. Attach a retained firm reference copy to each
            citation before approval. Retrieval details remain professional
            attestations; file integrity does not authenticate an official
            source. Executable formulas are prohibited.
          </p>
          <label>
            Versioned rule configuration
            <textarea
              rows={25}
              value={editor}
              onChange={(e) => setEditor(e.target.value)}
              spellCheck={false}
            />
          </label>
          <Button disabled={action.isPending} onClick={save}>
            Save immutable proposal
          </Button>
        </section>
      )}
    </div>
  );
}
