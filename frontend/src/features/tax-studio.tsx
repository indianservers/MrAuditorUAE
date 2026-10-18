"use client";
import { useState } from "react";
import Link from "next/link";
import { AuditStudio } from "./audit-studio";
import { PageHeader } from "./shared";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import {
  FinancialDataGrid,
  column,
  amount,
} from "@/components/grids/financial-data-grid";
import {
  Button,
  Empty,
  ErrorState,
  Facts,
  Status,
} from "@/components/ui/primitives";
import type { Page, RecordRow, Engagement } from "@/types/models";

export const taxAreas = [
  ["dashboard", "Corporate Tax Executive Dashboard", "profile"],
  ["taxpayers", "Taxpayer & Tax Period Management", "profile"],
  ["computation", "Corporate Tax Computation Studio", "computation"],
  ["adjustments", "Tax Adjustment Workbench", "adjustment"],
  ["reliefs", "Exempt Income & Reliefs", "exemption"],
  ["small-business", "Small Business Relief Assessment", "sbr"],
  ["qfzp", "QFZP Qualification Studio", "qfzp"],
  ["income-segmentation", "QFZP Income Segmentation", "qfzp"],
  ["de-minimis", "De Minimis Calculator", "qfzp"],
  ["free-zone-compliance", "Free Zone Compliance Matrix", "qfzp"],
  ["interest", "Interest Deduction Calculator", "interest"],
  ["losses", "Tax Loss Tracking", "loss"],
  ["tax-groups", "Corporate Tax Group Studio", "group"],
  ["restructuring", "Restructuring & Group Relief", "restructuring"],
  ["transitional", "Transitional Rules & Elections", "transitional"],
  [
    "related-parties",
    "Related-Party & Connected-Person Review",
    "related-party",
  ],
  ["returns", "Corporate Tax Return Preparation", "return"],
  ["calendar", "Tax Compliance Calendar", "deadline"],
  ["ai", "AI Corporate Tax Research & Review", "ai"],
  ["rules", "Tax Rules & Technical Administration", "rule"],
] as const;
type TaxRun = RecordRow & {
  id: string;
  kind: string;
  results: Record<string, unknown>;
  dependencies_current: boolean;
  sha256: string;
};

export function TaxStudio({
  id,
  area = "dashboard",
}: {
  id?: string;
  area?: string;
}) {
  const directory = useAPI<Page<Engagement>>("engagements?limit=100", !id);
  const [subkind, setSubkind] = useState("");
  const [profile, setProfile] = useState("");
  const [financial, setFinancial] = useState("");
  const entry = taxAreas.find((x) => x[0] === area);
  if (!id)
    return (
      <>
        <PageHeader
          eyebrow="Tax / UAE Corporate Tax"
          title="Corporate Tax"
          description="Open an assigned engagement to reconcile approved financial statements to a professionally reviewed tax position."
        />
        <section className="workbench-body">
          {directory.error && <ErrorState error={directory.error} />}{" "}
          {directory.data?.items.map((e) => (
            <p key={e.id}>
              <Link href={`/tax/${e.id}/dashboard`}>{e.name}</Link>{" "}
              <Status value={e.status} />
            </p>
          ))}
          {!directory.data?.items.length && (
            <Empty title="Choose a tax reporting engagement">
              Create an engagement from the existing legal entity.
            </Empty>
          )}
        </section>
      </>
    );
  if (!entry)
    return <Empty title="Unknown tax workspace">Choose a tax workspace.</Empty>;
  const kind = subkind || entry[2];
  const choices: Record<string, string[]> = {
    taxpayers: ["profile", "foundation"],
    reliefs: ["exemption", "credit"],
    losses: ["loss", "loss-transfer"],
    transitional: ["transitional", "election"],
  };
  return (
    <>
      <PageHeader
        eyebrow="UAE Corporate Tax / Source-linked workpapers"
        title={entry[1]}
        description="Approved legislation · Accounting-to-tax reconciliation · Independent Tax Manager and Partner review"
      />
      <nav className="audit-tabs" aria-label="Corporate Tax workspaces">
        {taxAreas.map(([key, title]) => (
          <Link
            key={key}
            href={`/tax/${id}/${key}`}
            aria-current={area === key ? "page" : undefined}
          >
            {title}
          </Link>
        ))}
      </nav>
      <TaxWorkspace
        id={id}
        area={area}
        kind={kind}
        profile={profile}
        onProfile={setProfile}
        financial={financial}
        onFinancial={setFinancial}
      />
      {choices[area] && (
        <div className="toolbar">
          <label>
            Record type
            <select value={kind} onChange={(e) => setSubkind(e.target.value)}>
              {choices[area].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {area === "rules" && <LegalRegistry />}
      {area === "ai" ? (
        <TaxAI id={id} profile={profile} />
      ) : (
        <AuditStudio
          key={`${kind}:${profile}:${financial}`}
          id={id}
          area={`tax-${kind}`}
          ifrs
          defaults={{
            ...(kind !== "profile" && profile ? { profile_id: profile } : {}),
            ...(kind === "profile" && financial
              ? { financial_run_id: financial }
              : {}),
          }}
        />
      )}
    </>
  );
}

function TaxWorkspace({
  id,
  area,
  kind,
  profile,
  onProfile,
  financial,
  onFinancial,
}: {
  id: string;
  area: string;
  kind: string;
  profile: string;
  onProfile: (v: string) => void;
  financial: string;
  onFinancial: (v: string) => void;
}) {
  const base = `tax/engagements/${id}`;
  const profiles = useAPI<Page<RecordRow>>(base + "/records/profile");
  const records = useAPI<Page<RecordRow>>(base + "/records/" + kind);
  const runs = useAPI<Page<RecordRow>>(base + "/runs");
  const financials = useAPI<Page<RecordRow>>(
    `ifrs/engagements/${id}/runs?kind=financials`,
  );
  const rules = useAPI<Page<RecordRow>>(base + "/records/rule?limit=100");
  const [rid, setRid] = useState(""),
    [compare, setCompare] = useState(""),
    [assumption, setAssumption] = useState("");
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const run = useAPI<TaxRun>(`${base}/runs/${rid}`, !!rid);
  const previous = useAPI<TaxRun>(`${base}/runs/${compare}`, !!compare);
  const ledger = useAPI<{ items: RecordRow[] }>(
    `${base}/loss-ledger/${profile}`,
    area === "losses" && !!profile,
  );
  const action = useAction<TaxRun>();
  const tenant = useScope((s) => s.tenant);
  const [error, setError] = useState("");
  const data = run.data?.results;
  const allowed = [
    "qfzp",
    "sbr",
    "interest",
    "group",
    "restructuring",
    "transitional",
    "foundation",
    "loss-transfer",
  ].includes(kind);
  async function perform(path: string) {
    try {
      const r = await action.mutateAsync({ path });
      setRid(r.id);
      setSelected(null);
    } catch {}
  }
  async function download(format: string) {
    setError("");
    try {
      const r = await fetch(
        `/api/backend/${base}/runs/${rid}/export/${format}`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!r.ok) throw new Error(`Export rejected (${r.status})`);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `AuditOS-CT-${rid}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    }
  }
  const bridge = data
    ? [
        {
          id: "accounting_profit",
          label: "Accounting profit before tax",
          value: data.accounting_profit,
        },
        {
          id: "net_adjustments",
          label: "Approved net tax adjustments",
          value: data.net_adjustments,
        },
        {
          id: "before_loss",
          label: "Taxable income before losses",
          value: data.before_loss,
        },
        {
          id: "loss_utilised",
          label: "Losses utilized",
          value: data.loss_utilised,
        },
        {
          id: "taxable_income",
          label: "Taxable income",
          value: data.taxable_income,
        },
        {
          id: "gross_tax",
          label: "Gross Corporate Tax",
          value: data.gross_tax,
        },
        {
          id: "foreign_tax_credit",
          label: "Foreign tax credit",
          value: data.foreign_tax_credit,
        },
        {
          id: "current_tax",
          label: "Current Corporate Tax",
          value: data.current_tax,
        },
      ].filter((x) => x.value !== undefined)
    : [];
  const qfzp = (data?.qfzp ||
    (run.data?.kind === "qfzp" ? data : null)) as Record<
    string,
    unknown
  > | null;
  return (
    <section
      className="workbench-body tax-workspace"
      aria-label="Corporate Tax calculations"
    >
      <div className="toolbar">
        <label>
          Tax profile
          <select
            aria-label="Tax profile"
            value={profile}
            onChange={(e) => onProfile(e.target.value)}
          >
            <option value="">Choose approved profile</option>
            {profiles.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {String(p.reference)} · {String(p.status)}
              </option>
            ))}
          </select>
        </label>
        <Button
          disabled={!profile || action.isPending}
          onClick={() => perform(`${base}/computations/${profile}`)}
        >
          Calculate Corporate Tax
        </Button>
        <label>
          Approved assessment
          <select
            aria-label="Approved assessment"
            value={assumption}
            onChange={(e) => setAssumption(e.target.value)}
          >
            <option value="">Choose assessment</option>
            {records.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {String(r.reference)} · {String(r.status)}
              </option>
            ))}
          </select>
        </label>
        <Button
          disabled={!assumption || !allowed || action.isPending}
          onClick={() =>
            perform(
              kind === "loss-transfer"
                ? `${base}/loss-transfers/${assumption}/post`
                : `${base}/calculate/${assumption}`,
            )
          }
        >
          {kind === "loss-transfer"
            ? "Post approved loss transfer"
            : "Calculate assessment"}
        </Button>
        <label>
          Computation version
          <select
            aria-label="Computation version"
            value={rid}
            onChange={(e) => setRid(e.target.value)}
          >
            <option value="">Choose immutable version</option>
            {runs.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {String(r.kind)} · {r.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {area === "taxpayers" && (
        <div className="toolbar">
          <label>
            Approved IFRS source
            <select
              aria-label="Approved IFRS source"
              value={financial}
              onChange={(e) => onFinancial(e.target.value)}
            >
              <option value="">Choose financial run</option>
              {financials.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id}
                </option>
              ))}
            </select>
          </label>
          <p>
            Selected source prefills new profiles. Enter approved rule IDs from
            Technical Administration; monetary JSON values must be quoted
            decimal strings.
          </p>
        </div>
      )}
      {action.error && <ErrorState error={action.error} />}{" "}
      {run.error && <ErrorState error={run.error} />}{" "}
      {ledger.error && <ErrorState error={ledger.error} />}{" "}
      {error && <p role="alert">{error}</p>}
      {area === "losses" && profile && (
        <FinancialDataGrid
          name="tax-loss-ledger"
          rows={ledger.data?.items || []}
          columns={[
            column("id", "Approved loss lot", 300),
            amount("available", "Available", "AED"),
          ]}
        />
      )}
      {data ? (
        <>
          <div className="toolbar">
            <strong>
              {String(data.entity || run.data?.kind)} ·{" "}
              {String(data.period_start)} – {String(data.period_end)}
            </strong>
            <Status
              value={run.data?.dependencies_current ? "CURRENT" : "STALE"}
            />
            <Button onClick={() => run.refetch()}>Validate dependencies</Button>
            {["pdf", "xlsx", "json"].map((f) => (
              <Button key={f} onClick={() => download(f)}>
                Export {f.toUpperCase()}
              </Button>
            ))}
            <label>
              Compare version
              <select
                value={compare}
                onChange={(e) => setCompare(e.target.value)}
              >
                <option value="">No comparison</option>
                {runs.data?.items.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="tax-computation-layout">
            <article>
              {bridge.length > 0 && (
                <>
                  <h2>Accounting-to-tax reconciliation</h2>
                  <FinancialDataGrid
                    name="tax-bridge"
                    rows={bridge.map((row) => ({
                      ...row,
                      comparative: previous.data?.results[row.id],
                    }))}
                    columns={[
                      column("label", "Computation line", 320),
                      amount("value", "Current", "AED"),
                      amount("comparative", "Compared version", "AED"),
                    ]}
                    onSelect={setSelected}
                  />
                </>
              )}
              {qfzp && (
                <>
                  <div className="toolbar">
                    <h2>QFZP decision matrix</h2>
                    <Status
                      value={String(qfzp.assessment || "INSUFFICIENT_DATA")}
                    />
                  </div>
                  <FinancialDataGrid
                    name="qfzp-conditions"
                    rows={(qfzp.conditions || []) as RecordRow[]}
                    columns={[
                      column("requirement", "Requirement", 250),
                      column("assessment", "Assessment", 160),
                      column("rationale", "Professional assessment", 350),
                    ]}
                    onSelect={setSelected}
                  />
                  <details>
                    <summary>Income segmentation and de minimis</summary>
                    <Facts data={qfzp as RecordRow} />
                  </details>
                </>
              )}
              {((data.lines || []) as RecordRow[]).length > 0 && (
                <>
                  <h2>Approved tax adjustments</h2>
                  <FinancialDataGrid
                    name="tax-adjustments"
                    rows={data.lines as RecordRow[]}
                    columns={[
                      column("label", "Source / reference", 220),
                      amount("accounting_amount", "Accounting", "AED"),
                      amount("proposed_adjustment", "Proposed", "AED"),
                      amount("approved_adjustment", "Approved", "AED"),
                      column("rule_id", "Legal rule", 280),
                      column("status", "Status"),
                    ]}
                    onSelect={setSelected}
                  />
                </>
              )}
              {!bridge.length && !qfzp && <Facts data={data as RecordRow} />}
            </article>
            <aside>
              <h3>Legal reference & source trace</h3>
              {selected ? (
                <Facts data={selected} />
              ) : (
                <p>
                  Select a reconciliation line, adjustment or condition to
                  inspect its source.
                </p>
              )}
              <details open>
                <summary>Exceptions / professional review</summary>
                <Facts
                  data={{
                    exceptions: data.exceptions || data.unresolved || [],
                    validation: data.validation || {},
                    scope: data.scope,
                  }}
                />
              </details>
              <details>
                <summary>Applied legislation versions</summary>
                <Facts data={(data.rules || {}) as RecordRow} />
              </details>
              {previous.data && (
                <details>
                  <summary>Compared snapshot</summary>
                  <Facts data={previous.data.results as RecordRow} />
                </details>
              )}
            </aside>
          </div>
          <div className="audit-stage-bar">
            <span>Immutable run {rid}</span>
            <span>SHA-256 {run.data?.sha256}</span>
          </div>
        </>
      ) : (
        <Empty title="Reconcile before release">
          Prepare and independently review a taxpayer profile and rule versions.
          Calculations use approved IFRS statements and approved tax
          adjustments. Unsupported or incomplete legal treatments remain
          explicit exceptions.
        </Empty>
      )}
      {area === "rules" && (
        <details open>
          <summary>Engagement rule IDs and professional status</summary>
          {rules.data?.items.map((r) => (
            <p key={r.id}>
              <strong>{String(r.reference)}</strong> · {r.id} ·{" "}
              {String(r.status)}
            </p>
          ))}
        </details>
      )}
      {area === "calendar" && data && (
        <Facts
          data={{
            filing_deadline: data.filing_deadline,
            payment_deadline: data.payment_deadline,
            source: "Selected rule version plus approved deadline overrides",
          }}
        />
      )}
    </section>
  );
}

function LegalRegistry() {
  const sources = useAPI<{ items: RecordRow[] }>("tax/legislation");
  return (
    <details className="workbench-body" open>
      <summary>
        Official source register — inclusion does not approve a tax rule
      </summary>
      <FinancialDataGrid
        name="tax-sources"
        rows={sources.data?.items || []}
        columns={[
          column("id", "Source", 170),
          column("title", "Legislation / guidance", 450),
          column("coverage", "Coverage", 240),
          column("url", "Official source", 500, {
            cellRenderer: (p: { value: string }) => (
              <a href={p.value} target="_blank" rel="noreferrer">
                Open official publication
              </a>
            ),
          }),
        ]}
      />
    </details>
  );
}

function TaxAI({ id, profile }: { id: string; profile: string }) {
  const base = `tax/engagements/${id}`;
  const workspace = useAPI<{ ai_tasks: string[] }>(base + "/workspace");
  const sources = useAPI<Page<RecordRow>>(base + "/records/adjustment");
  const suggestions = useAPI<Page<RecordRow>>(base + "/records/ai");
  const [source, setSource] = useState(""),
    [task, setTask] = useState("deduction_review"),
    [reason, setReason] = useState(""),
    [model, setModel] = useState("mock-diagnostic");
  const action = useAction<RecordRow>();
  const decision = useAction<RecordRow>();
  return (
    <section className="workbench-body">
      <h2>Source-grounded tax research</h2>
      <p>
        Approved rule metadata and selected sources only. Diagnostic mode
        verifies transport and grounding; it does not provide a professional
        legal opinion. Accepted suggestions still require a separately approved
        tax adjustment.
      </p>
      <div className="toolbar">
        <label>
          Tax research task
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            {workspace.data?.ai_tasks.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Source adjustment
          <select
            aria-label="Source adjustment"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="">Choose source</option>
            {sources.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {String(r.reference)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Approved model
          <input value={model} onChange={(e) => setModel(e.target.value)} />
        </label>
        <Button
          disabled={!profile || !source || action.isPending}
          onClick={() =>
            action.mutate({
              path: base + "/ai",
              body: {
                profile_id: profile,
                task,
                model,
                sources: [{ kind: "record", id: source }],
              },
            })
          }
        >
          Request tax analysis
        </Button>
      </div>
      {action.error && <ErrorState error={action.error} />}{" "}
      {action.data && <TaxSuggestion row={action.data} />}
      <label>
        Independent reviewer rationale
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {decision.error && <ErrorState error={decision.error} />}{" "}
      {suggestions.data?.items.map((r) => (
        <details key={r.id}>
          <summary>
            {String(r.title)} · {String(r.status)}
          </summary>
          <TaxSuggestion row={r} />
          {["UNDER_REVIEW", "ACCEPTED", "REJECTED"].map((state) => (
            <Button
              key={state}
              disabled={
                !reason ||
                !["SUGGESTED", "UNDER_REVIEW"].includes(String(r.status)) ||
                decision.isPending
              }
              onClick={() =>
                decision.mutate({
                  path: `${base}/ai/${r.id}/decision`,
                  body: {
                    version: r.version,
                    decision: state,
                    rationale: reason,
                  },
                })
              }
            >
              {state.replaceAll("_", " ")}
            </Button>
          ))}
        </details>
      ))}
    </section>
  );
}

export function TaxSuggestion({ row }: { row: RecordRow }) {
  const body = row.body as Record<string, unknown>;
  const output = body?.output as Record<string, unknown> | undefined;
  if (!output) return <Facts data={row} />;
  return (
    <article className="tax-suggestion">
      <div className="toolbar">
        <h3>{String(output.issue)}</h3>
        <Status value={String(row.status)} />
      </div>
      <p>{String(output.analysis)}</p>
      <Facts
        data={{
          tax_period: output.tax_period,
          potential_treatment: output.potential_treatment,
          required_human_action: output.required_human_action,
          requires_human_review: output.requires_human_review,
          tax_position_approved: output.tax_position_approved,
        }}
      />
      {[
        ["Relevant facts", "relevant_facts"],
        ["Missing facts", "missing_facts"],
        ["Uncertainty", "uncertainties"],
      ].map(([label, key]) => (
        <section key={key}>
          <h4>{label}</h4>
          <ul>
            {((output[key] || []) as string[]).map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </section>
      ))}
      <h4>Applicable legislation</h4>
      <ul>
        {(
          (output.applicable_legislation || []) as Record<string, unknown>[]
        ).map((law, i) => (
          <li key={i}>
            {String(law.source_id)} · Article {String(law.article)} · rule
            version {String(law.rule_version)} · {String(law.rule_record_id)}
          </li>
        ))}
      </ul>
      <details>
        <summary>Source versions, model and review history</summary>
        <Facts data={row} />
      </details>
    </article>
  );
}
