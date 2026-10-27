"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status, Empty } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
import { RegulatorySources, bindRetainedSource } from "./regulatory-sources";
import { RuleFixtureEditor, type FixtureReceipt } from "./rule-fixture-editor";

type Rule = {
  id: string;
  rule_key: string;
  country: string;
  version: number;
  sha256: string;
  body: Record<string, unknown>;
  current_sequence: number;
  state:
    | string
    | {
        state: string;
        body?: { comments?: string; fixture_validation?: FixtureReceipt };
        created_by?: string;
        created_at?: string;
      };
  validation_blockers?: string[];
  fixture_validation?: {
    status: string;
    case_count: number;
    receipt_sha256: string | null;
  };
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
  const [fixtureDraft, setFixtureDraft] = useState({ key: "", json: "[]" });
  const fixtureKey = `${tenant}:${id}`;
  const fixtures = fixtureDraft.key === fixtureKey ? fixtureDraft.json : "[]";
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
  const currentState =
    typeof detail.data?.state === "string"
      ? detail.data.state
      : detail.data?.state.state;
  const currentDecision =
    typeof detail.data?.state === "object" ? detail.data.state : null;
  const action = useAction<Rule>();
  function recordDecision(value: string) {
    setError(null);
    try {
      const cases: unknown =
        value === "approve" ? JSON.parse(fixtures) : undefined;
      if (value === "approve" && !Array.isArray(cases))
        throw new Error("Validation fixtures must be a JSON array");
      action.mutate({
        path: `regulatory/rules/${id}/decisions`,
        body: {
          action: value,
          expected_sequence: detail.data!.current_sequence,
          comments,
          ...(value === "approve" ? { validation_cases: cases } : {}),
        },
      });
    } catch (failure) {
      setError(failure as Error);
    }
  }
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
        {country === "AE" && (
          <Button
            onClick={() =>
              setEditor(
                JSON.stringify(
                  {
                    rule_key: "AE-",
                    country: "AE",
                    title: "",
                    description: "",
                    framework: "IFRS",
                    period_basis: "transaction_date",
                    effective_from: "",
                    effective_to: null,
                    citations: [
                      {
                        authority: "",
                        legislation: "",
                        url: "",
                        paragraph: "",
                        retrieval_status: "AWAITING_VALIDATION",
                        source_document_id: null,
                        document_sha256: null,
                        retrieved_on: null,
                      },
                    ],
                    input_requirements: ["reviewed_employee_population"],
                    output_requirements: ["employee_benefit"],
                    applicability: [],
                    exceptions_and_elections: [],
                    method: "benefit_profile",
                    benefit_parameters: {
                      regime: "",
                      cohort: "",
                      work_model: "full-time",
                      minimum_service_years: null,
                      year_days: null,
                      salary_divisor: null,
                      first_tier_years: null,
                      first_tier_days: null,
                      later_tier_days: null,
                      maximum_salary_months: null,
                    },
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
            Propose UAE benefit profile
          </Button>
        )}
        {country === "AE" && (
          <Button
            onClick={() =>
              setEditor(
                JSON.stringify(
                  {
                    rule_key: "AE-",
                    country: "AE",
                    title: "",
                    description: "",
                    framework: "IFRS",
                    period_basis: "transaction_date",
                    effective_from: "",
                    effective_to: null,
                    citations: [
                      {
                        authority: "",
                        legislation: "",
                        url: "",
                        paragraph: "",
                        retrieval_status: "AWAITING_VALIDATION",
                        source_document_id: null,
                        document_sha256: null,
                        retrieved_on: null,
                      },
                    ],
                    input_requirements: ["reviewed_assessed_pension_bases"],
                    output_requirements: ["pension_contributions"],
                    applicability: [],
                    exceptions_and_elections: [],
                    method: "pension_profile",
                    pension_parameters: {
                      authority: "",
                      scheme: "",
                      membership_cohort: "",
                      pension_country: "",
                      nationality: "",
                      employment_sector: "",
                      jurisdiction: "",
                      component: "",
                      minimum_basis: null,
                      salary_cap: null,
                      exclusive_eligibility_ceiling: null,
                      formula: "rate",
                      rate: null,
                      fixed_amount: null,
                      rounding: "",
                    },
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
            Propose UAE pension profile
          </Button>
        )}
        {country === "IN" && (
          <Button
            onClick={() =>
              setEditor(
                JSON.stringify(
                  {
                    rule_key: "IN-",
                    country: "IN",
                    title: "",
                    description: "",
                    framework: "Ind AS",
                    period_basis: "transaction_date",
                    effective_from: "",
                    effective_to: null,
                    citations: [
                      {
                        authority: "",
                        legislation: "",
                        url: "",
                        paragraph: "",
                        retrieval_status: "AWAITING_VALIDATION",
                        source_document_id: null,
                        document_sha256: null,
                        retrieved_on: null,
                      },
                    ],
                    input_requirements: ["reviewed_assessed_wage_bases"],
                    output_requirements: ["payroll_contributions"],
                    applicability: [],
                    exceptions_and_elections: [],
                    method: "payroll_profile",
                    payroll_parameters: {
                      rule_group: "",
                      component: "",
                      jurisdiction: "",
                      threshold_from: null,
                      threshold_to: null,
                      salary_cap: null,
                      formula: "rate",
                      rate: null,
                      fixed_amount: null,
                      rounding: "",
                    },
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
            Propose India payroll profile
          </Button>
        )}
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
          {detail.data.body.method === "pension_profile" && (
            <p>
              A salary cap limits the contribution base. An exclusive
              eligibility ceiling makes the expected contribution zero at or
              above the assessed salary limit, before any cap is applied. When
              configured, approval requires independently checked salary cases
              below, exactly at and above that limit.
            </p>
          )}
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
          {currentState === "DRAFT" && (
            <RuleFixtureEditor
              key={fixtureKey}
              id={id}
              value={fixtures}
              onChange={(json) => setFixtureDraft({ key: fixtureKey, json })}
            />
          )}
          <p>
            Recorded fixture validation:{" "}
            {detail.data.fixture_validation?.status || "NOT_RECORDED"} ·{" "}
            {detail.data.fixture_validation?.case_count || 0} cases
          </p>
          {currentDecision?.body?.fixture_validation && (
            <>
              {currentDecision.body.fixture_validation.support ===
                "BLOCKING_ONLY_NO_COMPLETE_WAGE_MONTH" && (
                <p>
                  Recorded fixtures verify refusal of split-month calculation.
                  They do not demonstrate a whole-month calculation.
                </p>
              )}
              <details>
                <summary>Recorded fixture outcomes</summary>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {JSON.stringify(
                    currentDecision.body.fixture_validation,
                    null,
                    2,
                  )}
                </pre>
              </details>
            </>
          )}
          <div className="toolbar">
            {["approve", "reject", "publish"]
              .filter((value) =>
                value === "publish"
                  ? currentState === "APPROVED"
                  : currentState === "DRAFT",
              )
              .map((value) => (
                <Button
                  key={value}
                  disabled={action.isPending}
                  onClick={() => recordDecision(value)}
                >
                  {value === "publish"
                    ? "Publish approved version"
                    : value === "approve"
                      ? "Record independent approval"
                      : "Reject proposal"}
                </Button>
              ))}
            <Button onClick={() => proposal()}>Propose amendment</Button>
            {currentState === "PUBLISHED" && (
              <Button
                disabled={action.isPending || comments.trim().length < 10}
                onClick={() =>
                  action.mutate({
                    path: `regulatory/rules/${id}/decisions`,
                    body: {
                      action: "withdraw",
                      expected_sequence: detail.data!.current_sequence,
                      comments,
                    },
                  })
                }
              >
                Withdraw published version
              </Button>
            )}
            <Button onClick={() => proposal(true)}>
              Propose controlled revert
            </Button>
          </div>
          {currentState === "WITHDRAWN" && (
            <section aria-label="Recorded rule withdrawal">
              <p>
                This version is withdrawn. Existing work remains available for
                history and shows stale where affected. Prepare an amendment or
                controlled revert, then obtain independent approval and publish
                a replacement before reuse.
              </p>
              <dl>
                <dt>Recorded withdrawal reason</dt>
                <dd>
                  {currentDecision?.body?.comments || "Reason unavailable"}
                </dd>
                <dt>Recorded by</dt>
                <dd>{currentDecision?.created_by || "Actor unavailable"}</dd>
                <dt>Recorded at</dt>
                <dd>{currentDecision?.created_at || "Time unavailable"}</dd>
              </dl>
            </section>
          )}
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
