"use client";
import Link from "next/link";
import { SoDImport, MLFeedback, BoardDownloads } from "./grc-actions";
import { ControlGraph } from "./grc-graph";
import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, Empty, ErrorState } from "@/components/ui/primitives";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import type { Engagement, Page, RecordRow } from "@/types/models";
import { PageHeader } from "./shared";
import { PaperEditor, label, type Paper, type Schema } from "./grc-forms";

export const grcAreas = [
  ["command", "Internal Audit Command Center", ""],
  ["universe", "Audit Universe Explorer", "universe"],
  ["plan", "Risk-Based Annual Audit Plan", "plan"],
  ["engagement", "Internal Audit Engagement Workspace", "engagement"],
  ["testing", "Internal Audit Testing Studio", "test"],
  ["reports", "Internal Audit Report Designer", "report"],
  ["risks", "Enterprise Risk Register", "risk"],
  ["heatmap", "Risk Heatmap & Assessment Studio", "assessment"],
  ["kris", "Key Risk Indicator Dashboard", "kri"],
  ["controls", "Process & Control Library", "control"],
  ["rcm", "Risk Control Matrix Workbench", "link"],
  ["effectiveness", "Control Design & Effectiveness Testing", "test"],
  ["sod", "Segregation of Duties Analyzer", "sod-access"],
  ["rules", "Continuous Monitoring Rules Studio", "monitor-rule"],
  ["executions", "Continuous Monitoring Execution Dashboard", ""],
  ["alerts", "Intelligent Alert Investigation", "alert-decision"],
  ["deficiencies", "Control Deficiency Register", "deficiency"],
  ["remediation", "Remediation Action Tracker", "remediation"],
  ["obligations", "Compliance Obligation Center", "obligation"],
  ["policies", "Policy & Procedure Library", "policy"],
  ["third-parties", "Third-Party Risk Studio", "third-party"],
  ["copilot", "AI GRC Copilot", ""],
  ["board", "Audit Committee & Board Portal", "board"],
  ["quality", "Internal Audit Quality Assurance Studio", "qaip"],
] as const;
type Workspace = {
  permissions: string[];
  schemas: Record<string, Schema>;
  kind_permissions: Record<string, [string, string]>;
};
type Dashboard = {
  counts: Record<string, number>;
  approved_workpapers: number;
  closed_actions: number;
  overdue_actions: RecordRow[];
  heatmap: {
    id: string;
    risk_id: string;
    risk_reference: string;
    assessment_reference: string;
    scoring_id: string;
    scoring_reference: string;
    matrix_size: number;
    stale_source: boolean;
    residual_likelihood: number;
    residual_impact: number;
    inherent: string;
    residual: string;
    appetite_breach: boolean;
  }[];
};
type Run = RecordRow & {
  kind: string;
  created_at: string;
  inputs: Record<string, unknown>;
  results: Record<string, unknown>;
};
type Alert = RecordRow & {
  rule_key: string;
  source_id: string;
  run_id: string;
  signals: {
    deterministic?: Record<string, unknown>;
    ml?: Record<string, unknown>;
  };
};

export function GRCStudio({
  eid,
  area = "command",
}: {
  eid?: string;
  area?: string;
}) {
  const directory = useAPI<Page<Engagement>>("engagements?limit=100");
  const [selected, setSelected] = useState(eid || "");
  const entry = grcAreas.find((x) => x[0] === area);
  return (
    <>
      <PageHeader
        eyebrow="Governance / Internal audit"
        title={entry?.[1] || "Internal Audit & GRC"}
        description="Evidence-linked workpapers · Independently reviewed conclusions · Separate rule and model signals"
      />
      <div className="grc-shell">
        <label className="grc-engagement">
          Engagement
          <select
            aria-label="GRC engagement"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Choose authorized engagement</option>
            {directory.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </label>
        {directory.error && <ErrorState error={directory.error} />}
        <nav className="grc-nav" aria-label="GRC workspaces">
          {grcAreas.map(([key, title]) => (
            <Link
              key={key}
              aria-current={key === area ? "page" : undefined}
              href={selected ? `/grc/${selected}/${key}` : "/grc"}
            >
              {title}
            </Link>
          ))}
        </nav>
        {selected && entry ? (
          <Panel
            key={selected + area}
            eid={selected}
            area={area}
            kind={entry[2]}
          />
        ) : (
          <Empty title="Choose an engagement">
            Workpapers follow your active engagement permissions.
          </Empty>
        )}
      </div>
    </>
  );
}

function Panel({
  eid,
  area,
  kind: defaultKind,
}: {
  eid: string;
  area: string;
  kind: string;
}) {
  const base = `grc/engagements/${eid}`;
  const workspace = useAPI<Workspace>(`${base}/workspace`);
  const dashboard = useAPI<Dashboard>(
    `${base}/dashboard`,
    area === "command" || area === "heatmap" || area === "remediation",
  );
  const [kind, setKind] = useState(defaultKind);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Paper>();
  const [editing, setEditing] = useState(false);
  const [newPaper, setNewPaper] = useState(false);
  const [filter, setFilter] = useState("");
  const records = useAPI<Page<Paper>>(
    `${base}/records/${kind}?limit=50&offset=${page * 50}&search=${encodeURIComponent(filter)}`,
    !!kind && !!workspace.data,
  );
  const action = useAction();
  const [reason, setReason] = useState("");
  const permissions = workspace.data?.permissions || [];
  const canPrepare = permissions.includes(
    workspace.data?.kind_permissions[kind]?.[0] || "",
  );
  const canReview = permissions.includes(
    workspace.data?.kind_permissions[kind]?.[1] || "",
  );
  if (workspace.error) return <ErrorState error={workspace.error} />;
  if (!workspace.data)
    return <p role="status">Loading authorized GRC workspace…</p>;
  const rows = records.data?.items || [];
  const detail = selected
    ? rows.find((x) => x.id === selected.id) || selected
    : undefined;
  const switchKind = (value: string) => {
    setKind(value);
    setSelected(undefined);
    setEditing(false);
    setPage(0);
  };
  return (
    <section className="grc-workspace">
      {area === "sod" && permissions.includes("grc.sod.analyze") && (
        <SoDImport base={base} />
      )}
      {area === "command" && dashboard.data && (
        <Command data={dashboard.data} eid={eid} />
      )}
      {area === "heatmap" && (
        <Heatmap data={dashboard.data} onSelect={(id) => setFilter(id)} />
      )}
      {area === "rcm" && <Matrix base={base} />}
      {area === "executions" && <Executions base={base} />}
      {area === "alerts" && (
        <Alerts
          base={base}
          onSelect={(id) => {
            setNewPaper(true);
            setEditing(true);
            setReason(`Investigation alert ${id}`);
          }}
        />
      )}
      {area === "copilot" && <Copilot base={base} />}
      {area === "board" && <BoardPackages base={base} />}
      {area === "remediation" && dashboard.data && (
        <div className="grc-overdue">
          <h2>Overdue actions awaiting verified closure</h2>
          {dashboard.data.overdue_actions.length ? (
            dashboard.data.overdue_actions.map((x) => (
              <button key={x.id} onClick={() => setFilter(String(x.reference))}>
                {String(x.reference)} · {String(x.days_overdue)} days overdue
              </button>
            ))
          ) : (
            <p>No reviewed overdue actions in the authorized scope.</p>
          )}
        </div>
      )}
      {kind && (
        <>
          <div className="grc-toolbar">
            <div>
              <h2>{label(kind)} workpapers</h2>
              <span>
                {records.data?.total || 0} records · page {page + 1}
              </span>
            </div>
            {area === "universe" && (
              <Button
                onClick={() =>
                  switchKind(kind === "framework" ? "universe" : "framework")
                }
              >
                {kind === "framework"
                  ? "Audit universe"
                  : "Applicable frameworks"}
              </Button>
            )}
            {(area === "plan" || area === "heatmap") && (
              <Button
                onClick={() =>
                  switchKind(kind === "scoring" ? defaultKind : "scoring")
                }
              >
                {kind === "scoring"
                  ? "Return to workpapers"
                  : "Scoring & appetite"}
              </Button>
            )}
            {area === "sod" && (
              <Button
                onClick={() =>
                  switchKind(kind === "sod-rule" ? "sod-access" : "sod-rule")
                }
              >
                {kind === "sod-rule"
                  ? "Permission populations"
                  : "Incompatible permission rules"}
              </Button>
            )}
            {area === "remediation" && (
              <Button
                onClick={() =>
                  switchKind(kind === "closure" ? "remediation" : "closure")
                }
              >
                {kind === "closure"
                  ? "Management actions"
                  : "Independent closure reviews"}
              </Button>
            )}
            {canPrepare && (
              <Button
                primary
                onClick={() => {
                  setSelected(undefined);
                  setNewPaper(true);
                  setEditing(true);
                }}
              >
                Prepare {label(kind)}
              </Button>
            )}
          </div>
          <div className="grc-toolbar">
            <label>
              Search references and titles
              <input
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPage(0);
                }}
              />
            </label>
            <Button disabled={!page} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button
              disabled={(page + 1) * 50 >= (records.data?.total || 0)}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
          {records.error && <ErrorState error={records.error} />}
          {area === "plan" && <PlanTimeline rows={rows} />}
          {area === "kris" && <KRITrend rows={rows} />}
          {area === "remediation" && (
            <ActionLanes rows={rows} onSelect={setSelected} />
          )}
          {area === "obligations" && <Calendar rows={rows} />}
          {area === "third-parties" && <VendorReview rows={rows} />}
          <div className="grc-split">
            <div className="grc-grid">
              <FinancialDataGrid
                name={`grc-${area}-${kind}`}
                rows={rows.map((x) => ({
                  ...x,
                  ...Object.fromEntries(
                    Object.entries(x.body).filter(
                      ([_k, v]) => !Array.isArray(v) && typeof v !== "object",
                    ),
                  ),
                  id: x.id,
                }))}
                columns={[
                  column("reference", "Reference", 180),
                  column("title", "Workpaper", 280),
                  column("status", "Review", 120),
                  ...fieldsFor(kind).map((x) => column(x, label(x), 165)),
                  column("version", "Version", 90),
                ]}
                onSelect={(x) => setSelected(rows.find((r) => r.id === x.id))}
                exportable={false}
              />
            </div>
            {detail && !editing && (
              <aside className="grc-detail">
                <div className="grc-toolbar">
                  <h2>{detail.reference}</h2>
                  <Button onClick={() => setSelected(undefined)}>Close</Button>
                </div>
                <p>{detail.title}</p>
                <span className="grc-status">
                  {detail.status} · v{detail.version}
                </span>
                <Narrative value={detail.body} />
                {area === "engagement" && (
                  <StageTimeline
                    base={base}
                    paper={detail}
                    permissions={permissions}
                  />
                )}
                {area === "testing" && <SampleSelector base={base} />}
                {area === "rules" &&
                  permissions.includes("monitor.job.execute") && (
                    <MonitorRun base={base} paper={detail} />
                  )}
                {area === "rules" &&
                  permissions.includes("monitor.schedule.manage") && (
                    <Schedule base={base} paper={detail} />
                  )}
                {area === "board" &&
                  detail.status === "APPROVED" &&
                  permissions.includes("governance.report.prepare") && (
                    <Button
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({
                          path: `${base}/board/${detail.id}/publish`,
                        })
                      }
                    >
                      Publish reviewed package
                    </Button>
                  )}
                {area === "policies" &&
                  permissions.includes("policy.acknowledge") && (
                    <Button
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({
                          path: `${base}/policies/${detail.id}/acknowledgments`,
                        })
                      }
                    >
                      Acknowledge this policy version
                    </Button>
                  )}
                {canPrepare &&
                  ["IN_PROGRESS", "REVISED", "REVIEW_NOTES"].includes(
                    detail.status,
                  ) && (
                    <Button
                      onClick={() => {
                        setNewPaper(false);
                        setEditing(true);
                      }}
                    >
                      Edit draft
                    </Button>
                  )}
                <label>
                  Review rationale
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <div className="grc-toolbar">
                  {(detail.status === "IN_PROGRESS" ||
                    detail.status === "REVIEW_NOTES" ||
                    detail.status === "REVISED") &&
                    canPrepare && (
                      <Button
                        disabled={!reason || action.isPending}
                        onClick={() =>
                          action.mutate({
                            path: `${base}/records/${detail.id}/actions`,
                            body: {
                              version: detail.version,
                              action: "submit",
                              comments: reason,
                            },
                          })
                        }
                      >
                        Submit for review
                      </Button>
                    )}
                  {detail.status === "REVIEW_REQUIRED" && canReview && (
                    <Button
                      disabled={!reason || action.isPending}
                      onClick={() =>
                        action.mutate({
                          path: `${base}/records/${detail.id}/actions`,
                          body: {
                            version: detail.version,
                            action: "approve",
                            comments: reason,
                          },
                        })
                      }
                    >
                      Approve independently
                    </Button>
                  )}
                  {detail.status === "APPROVED" &&
                    permissions.includes("grc.calculate") &&
                    [
                      "assessment",
                      "plan",
                      "kri",
                      "sod-access",
                      "test",
                    ].includes(kind) && (
                      <Calculation base={base} paper={detail} />
                    )}
                </div>
                <History base={base} paper={detail} />
              </aside>
            )}
          </div>
          {editing && workspace.data.schemas[kind] && (
            <PaperEditor
              key={(newPaper ? "new" : detail?.id) + kind}
              base={base}
              kind={kind}
              schema={workspace.data.schemas[kind]}
              paper={newPaper ? undefined : detail}
              done={() => setEditing(false)}
            />
          )}
        </>
      )}
      {action.error && <ErrorState error={action.error} />}
      {dashboard.error && <ErrorState error={dashboard.error} />}
    </section>
  );
}

function fieldsFor(kind: string) {
  const fields: Record<string, string[]> = {
    risk: ["category", "treatment", "review_date"],
    control: ["control_type", "frequency", "approach"],
    deficiency: ["severity", "root_cause_method"],
    remediation: ["management_status", "target_date"],
    obligation: ["module", "deadline", "compliance_assessment"],
    policy: ["version_number", "effective_from", "review_date"],
    "third-party": ["criticality", "renewal_date"],
    qaip: ["assessment_type", "scheduled_on"],
    "monitor-rule": ["rule_code", "version_number", "input_kind"],
    test: ["test_type", "conclusion", "period_end"],
    universe: ["unit_type", "inherent_rating", "maturity"],
  };
  return fields[kind] || [];
}
function Narrative({ value }: { value: unknown }) {
  if (Array.isArray(value))
    return (
      <ol className="grc-values">
        {value.map((v, i) => (
          <li key={i}>
            <Narrative value={v} />
          </li>
        ))}
      </ol>
    );
  if (value && typeof value === "object")
    return (
      <dl className="grc-values">
        {Object.entries(value)
          .filter(
            ([k]) =>
              !["review_stage", "review_cycle", "review_approvers"].includes(k),
          )
          .map(([k, v]) => (
            <div key={k}>
              <dt>{label(k)}</dt>
              <dd>
                <Narrative value={v} />
              </dd>
            </div>
          ))}
      </dl>
    );
  return <span>{value == null ? "Not supplied" : String(value)}</span>;
}
function Command({ data, eid }: { data: Dashboard; eid: string }) {
  return (
    <>
      <div className="grc-command">
        <div>
          <small>Reviewed workpapers</small>
          <strong>{data.approved_workpapers}</strong>
        </div>
        <div>
          <small>Approved independent closures</small>
          <strong>{data.closed_actions}</strong>
        </div>
        <div>
          <small>Open overdue actions</small>
          <strong>{data.overdue_actions.length}</strong>
        </div>
        <div>
          <small>Assessed risk appetite breaches</small>
          <strong>
            {data.heatmap.filter((x) => x.appetite_breach).length}
          </strong>
        </div>
      </div>
      <div className="grc-coverage">
        <h2>Engagement coverage</h2>
        {Object.entries(data.counts).map(([k, v]) => (
          <div key={k}>
            <span>{label(k)}</span>
            <meter
              min="0"
              max={Math.max(...Object.values(data.counts), 1)}
              value={v}
            />
            <strong>{v}</strong>
          </div>
        ))}
      </div>
      <Link href={`/grc/${eid}/heatmap`}>Open assessed risk heatmap →</Link>
    </>
  );
}
function Heatmap({
  data,
  onSelect,
}: {
  data?: Dashboard;
  onSelect: (id: string) => void;
}) {
  const [cell, setCell] = useState<[number, number]>();
  const [model, setModel] = useState("");
  const models = [
    ...new Map((data?.heatmap || []).map((x) => [x.scoring_id, x])).values(),
  ];
  const chosen = model || models[0]?.scoring_id;
  const points = (data?.heatmap || []).filter((x) => x.scoring_id === chosen);
  const size = points[0]?.matrix_size || 5;
  const coordinates = Array.from({ length: size }, (_, i) => i + 1);
  return (
    <section className="grc-heat">
      <h2>Residual likelihood × impact</h2>
      <p>
        Only current independently approved assessments are plotted. Ordinal
        scores are not probabilities. Color shows breaches of the approved
        appetite.
      </p>
      <label>
        Approved scoring methodology
        <select
          value={chosen || ""}
          onChange={(e) => {
            setModel(e.target.value);
            setCell(undefined);
          }}
        >
          {models.map((x) => (
            <option key={x.scoring_id} value={x.scoring_id}>
              {x.scoring_reference} · {x.matrix_size} × {x.matrix_size}
            </option>
          ))}
        </select>
      </label>
      <div
        className="grc-matrix"
        style={{ gridTemplateColumns: `repeat(${size},minmax(50px,100px))` }}
        role="group"
        aria-label="Residual risk matrix"
      >
        {[...coordinates].reverse().flatMap((l) =>
          coordinates.map((i) => {
            const hits =
              points.filter(
                (x) => x.residual_likelihood === l && x.residual_impact === i,
              ) || [];
            return (
              <button
                key={`${l}:${i}`}
                className={hits.some((x) => x.appetite_breach) ? "high" : "low"}
                onClick={() => setCell([l, i])}
                aria-label={`Likelihood ${l}, impact ${i}, ${hits.length} risks`}
              >
                <small>
                  {l} × {i}
                </small>
                <strong>{hits.length}</strong>
              </button>
            );
          }),
        )}
      </div>
      {cell && (
        <ul>
          {points
            .filter(
              (x) =>
                x.residual_likelihood === cell[0] &&
                x.residual_impact === cell[1],
            )
            .map((x) => (
              <li key={x.id}>
                <Button onClick={() => onSelect(x.assessment_reference)}>
                  {x.risk_reference} · residual {x.residual}{" "}
                  {x.stale_source
                    ? "· source changed: reassessment required"
                    : ""}{" "}
                  {x.appetite_breach ? "· above appetite" : ""}
                </Button>
              </li>
            ))}
        </ul>
      )}
    </section>
  );
}
function PlanTimeline({ rows }: { rows: Paper[] }) {
  return (
    <section className="grc-plan">
      <h3>Annual plan commitments</h3>
      {rows.flatMap((p) =>
        ((p.body.items || []) as Record<string, unknown>[]).map((x, i) => (
          <div key={p.id + i}>
            <strong>{p.reference}</strong>
            <span>
              {String(x.starts)} — {String(x.ends)}
            </span>
            <span>
              {String(x.budget_hours)} budgeted hours / {String(x.actual_hours)}{" "}
              actual
            </span>
            <span>
              {x.deferred ? `Deferred: ${x.deferral_reason}` : "Scheduled"}
            </span>
          </div>
        )),
      )}
    </section>
  );
}
function KRITrend({ rows }: { rows: Paper[] }) {
  return (
    <section className="grc-kri">
      {rows.map((p) => {
        const observations = (p.body.observations || []) as {
          observed_on: string;
          value: string;
        }[];
        const max = Math.max(
          1,
          ...observations.map((x) => Math.abs(Number(x.value))),
        );
        return (
          <article key={p.id}>
            <h3>{p.title}</h3>
            <p>
              Threshold {String(p.body.threshold)} {String(p.body.unit)} ·
              breach {String(p.body.direction)}
            </p>
            <div className="grc-spark">
              {observations.map((x) => (
                <div key={x.observed_on} title={`${x.observed_on}: ${x.value}`}>
                  <span
                    style={{
                      height: `${(Math.abs(Number(x.value)) / max) * 80 + 4}px`,
                    }}
                  />
                  <small>{x.observed_on}</small>
                  <strong>{x.value}</strong>
                </div>
              ))}
            </div>
          </article>
        );
      })}
    </section>
  );
}
function ActionLanes({
  rows,
  onSelect,
}: {
  rows: Paper[];
  onSelect: (p: Paper) => void;
}) {
  return (
    <div className="grc-lanes">
      {["planned", "in_progress", "reported_complete"].map((status) => (
        <section key={status}>
          <h3>{label(status)}</h3>
          {rows
            .filter((x) => x.body.management_status === status)
            .map((x) => (
              <button key={x.id} onClick={() => onSelect(x)}>
                <strong>{x.reference}</strong>
                <span>{String(x.body.corrective_action)}</span>
                <small>
                  Due {String(x.body.target_date)} · {x.status}
                </small>
              </button>
            ))}
        </section>
      ))}
      <p>
        Management-reported completion remains subject to independently approved
        retesting and closure.
      </p>
    </div>
  );
}
function Calendar({ rows }: { rows: Paper[] }) {
  return (
    <ol className="grc-calendar">
      {[...rows]
        .sort((a, b) =>
          String(a.body.deadline).localeCompare(String(b.body.deadline)),
        )
        .map((x) => (
          <li key={x.id}>
            <time>{String(x.body.deadline)}</time>
            <strong>{x.title}</strong>
            <span>{label(String(x.body.module))}</span>
            <span>{label(String(x.body.compliance_assessment))}</span>
          </li>
        ))}
    </ol>
  );
}
function VendorReview({ rows }: { rows: Paper[] }) {
  return (
    <div className="grc-vendors">
      {["critical", "high", "moderate", "low"].map((level) => (
        <section key={level}>
          <h3>{label(level)} dependency</h3>
          {rows
            .filter((x) => x.body.criticality === level)
            .map((x) => (
              <p key={x.id}>
                <strong>{String(x.body.name)}</strong> ·{" "}
                {String(x.body.services)}
                <br />
                Renewal {String(x.body.renewal_date)} ·{" "}
                {String(x.body.geography)}
              </p>
            ))}
        </section>
      ))}
    </div>
  );
}
function Matrix({ base }: { base: string }) {
  const [graph, setGraph] = useState(false);
  const rows = useAPI<Page<RecordRow>>(`${base}/rcm?limit=500`);
  return (
    <>
      <h2>Risk / control relationship matrix</h2>
      <Button onClick={() => setGraph((v) => !v)}>
        {graph ? "Hide relationship graph" : "Inspect relationship graph"}
      </Button>
      {graph && (
        <ControlGraph
          rows={(rows.data?.items || []).map((x) => ({
            id: x.id,
            risk: x.risk as Paper,
            control: x.control as Paper,
            status: x.status,
          }))}
        />
      )}
      {rows.error && <ErrorState error={rows.error} />}
      <div className="grc-grid">
        <FinancialDataGrid
          name="grc-joined-rcm"
          rows={(rows.data?.items || []).map((x) => ({
            ...x,
            risk: (x.risk as Paper).title,
            control: (x.control as Paper).title,
            risk_status: (x.risk as Paper).status,
            control_status: (x.control as Paper).status,
          }))}
          columns={[
            column("reference", "Mapping"),
            column("risk", "Risk", 260),
            column("control", "Control", 260),
            column("risk_status", "Risk review"),
            column("control_status", "Control review"),
            column("rationale", "Mapping rationale", 350),
          ]}
          exportable={false}
        />
      </div>
    </>
  );
}
function Calculation({ base, paper }: { base: string; paper: Paper }) {
  const action = useAction<Run>();
  return (
    <>
      <Button
        disabled={action.isPending}
        onClick={() =>
          action.mutate({ path: `${base}/records/${paper.id}/calculate` })
        }
      >
        Freeze reviewed calculation
      </Button>
      {action.data && <Narrative value={action.data.results} />}{" "}
      {action.error && <ErrorState error={action.error} />}
    </>
  );
}
function History({ base, paper }: { base: string; paper: Paper }) {
  const query = useAPI<{ items: RecordRow[] }>(
    `${base}/records/${paper.id}/history`,
  );
  return (
    <details>
      <summary>Auditable revisions</summary>
      {query.data?.items.map((x) => (
        <p key={x.id}>
          Version {String(x.version)} · {String(x.created_at)} ·{" "}
          {String(x.status)}
        </p>
      ))}
      {query.error && <ErrorState error={query.error} />}
    </details>
  );
}
function StageTimeline({
  base,
  paper,
  permissions,
}: {
  base: string;
  paper: Paper;
  permissions: string[];
}) {
  const runs = useAPI<{ items: Run[] }>(
    `${base}/runs?kind=ia-transition&limit=100`,
  );
  const action = useAction();
  const [reason, setReason] = useState("");
  const [report, setReport] = useState("");
  const latest = runs.data?.items.find((x) => x.record_id === paper.id);
  const current = String(latest?.results.stage || "DRAFT");
  const allowed: Record<string, string[]> = {
    DRAFT: ["PLANNED"],
    PLANNED: ["APPROVED", "DRAFT"],
    APPROVED: ["FIELDWORK"],
    FIELDWORK: ["REVIEW"],
    REVIEW: ["REPORTING", "FIELDWORK"],
    REPORTING: ["ISSUED", "FIELDWORK"],
    ISSUED: ["FOLLOW_UP"],
    FOLLOW_UP: ["CLOSED", "FIELDWORK"],
    CLOSED: ["FOLLOW_UP"],
  };
  return (
    <section>
      <h3>Internal audit lifecycle · {current}</h3>
      <div className="grc-stages">
        {Object.keys(allowed).map((x) => (
          <span key={x} aria-current={x === current ? "step" : undefined}>
            {label(x)}
          </span>
        ))}
      </div>
      <label>
        Transition rationale
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {current === "REPORTING" && (
        <label>
          Approved report reference
          <input value={report} onChange={(e) => setReport(e.target.value)} />
        </label>
      )}
      <div className="grc-toolbar">
        {allowed[current]?.map((next) => (
          <Button
            key={next}
            disabled={
              !reason ||
              action.isPending ||
              !permissions.includes(
                next === "ISSUED"
                  ? "ia.report.approve"
                  : ["APPROVED", "REPORTING", "CLOSED"].includes(next)
                    ? "ia.engagement.review"
                    : "ia.engagement.execute",
              )
            }
            onClick={() =>
              action.mutate({
                path: `${base}/internal-audits/${paper.id}/transitions`,
                body: {
                  expected_stage: current,
                  next_stage: next,
                  rationale: reason,
                  ...(report ? { report_id: report } : {}),
                },
              })
            }
          >
            {label(next)}
          </Button>
        ))}
      </div>
      {action.error && <ErrorState error={action.error} />}
    </section>
  );
}
function SampleSelector({ base }: { base: string }) {
  const action = useAction<RecordRow>();
  const [snapshot, setSnapshot] = useState("");
  const [method, setMethod] = useState("random");
  const [size, setSize] = useState(10);
  const [seed, setSeed] = useState(17);
  return (
    <section>
      <h3>Freeze a test sample</h3>
      <label>
        Approved population snapshot
        <input value={snapshot} onChange={(e) => setSnapshot(e.target.value)} />
      </label>
      <label>
        Selection method
        <select value={method} onChange={(e) => setMethod(e.target.value)}>
          {["random", "systematic", "high_value", "mus"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </label>
      <label>
        Sample size
        <input
          type="number"
          min="1"
          max="1000"
          value={size}
          onChange={(e) => setSize(Number(e.target.value))}
        />
      </label>
      <label>
        Reproducible seed
        <input
          type="number"
          min="0"
          value={seed}
          onChange={(e) => setSeed(Number(e.target.value))}
        />
      </label>
      <Button
        disabled={!snapshot || action.isPending}
        onClick={() =>
          action.mutate({
            path: `${base}/samples`,
            body: { snapshot_id: snapshot, method, size, seed },
          })
        }
      >
        Select actual source items
      </Button>
      {action.data && <Narrative value={action.data} />}{" "}
      {action.error && <ErrorState error={action.error} />}
    </section>
  );
}
function MonitorRun({ base, paper }: { base: string; paper: Paper }) {
  const action = useAction<{ id: string; status: string }>();
  const job = useAPI<RecordRow>(
    `jobs/${action.data?.id}`,
    !!action.data?.id,
    true,
  );
  return (
    <section>
      <Button
        disabled={paper.status !== "APPROVED" || action.isPending}
        onClick={() =>
          action.mutate({ path: `${base}/monitoring/${paper.id}/execute` })
        }
      >
        Run approved monitoring rule
      </Button>
      {job.data && (
        <p role="status">
          Job {String(job.data.status)} · {String(job.data.progress)}% <br />
          {String(job.data.error_category || "")}
        </p>
      )}
      {job.error && <ErrorState error={job.error} />}{" "}
      {action.error && <ErrorState error={action.error} />}
    </section>
  );
}
function Schedule({ base, paper }: { base: string; paper: Paper }) {
  const action = useAction();
  const [frequency, setFrequency] = useState("daily");
  const [due, setDue] = useState("");
  return (
    <details>
      <summary>Schedule reviewed rule</summary>
      <label>
        Frequency
        <select
          value={frequency}
          onChange={(e) => setFrequency(e.target.value)}
        >
          {["daily", "weekly", "monthly", "quarterly"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </label>
      <label>
        Next execution in local time
        <input
          type="datetime-local"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </label>
      <Button
        disabled={!due || action.isPending || paper.status !== "APPROVED"}
        onClick={() =>
          action.mutate({
            path: `${base}/schedules`,
            body: {
              rule_id: paper.id,
              frequency,
              next_due: new Date(due).toISOString(),
            },
          })
        }
      >
        Create schedule
      </Button>
      {action.error && <ErrorState error={action.error} />}
    </details>
  );
}
function Executions({ base }: { base: string }) {
  const runs = useAPI<{ items: Run[] }>(
    `${base}/runs?kind=monitoring&limit=100`,
    true,
    true,
  );
  const schedules = useAPI<{ items: RecordRow[] }>(`${base}/schedules`);
  const [selected, setSelected] = useState<Run>();
  return (
    <section>
      <h2>Monitoring execution history</h2>
      <div className="grc-grid">
        <FinancialDataGrid
          name="grc-monitoring-runs"
          rows={(runs.data?.items || []).map((x) => ({ ...x, ...x.results }))}
          columns={[
            column("created_at", "Executed UTC", 200),
            column("status", "Result"),
            column("id", "Frozen run", 280),
          ]}
          onSelect={(x) =>
            setSelected(runs.data?.items.find((r) => r.id === x.id))
          }
          exportable={false}
        />
      </div>
      {selected && <Narrative value={selected.results} />}
      <h3>Configured schedules</h3>
      {schedules.data?.items.map((x) => (
        <p key={x.id}>
          {String(x.frequency)} · next {String(x.next_due)} ·{" "}
          {x.active ? "active" : "paused"} · reviewed rule v
          {String(x.rule_version)}
        </p>
      ))}
      {runs.error && <ErrorState error={runs.error} />}{" "}
      {schedules.error && <ErrorState error={schedules.error} />}
    </section>
  );
}
function Alerts({
  base,
  onSelect,
}: {
  base: string;
  onSelect: (id: string) => void;
}) {
  const [page, setPage] = useState(0);
  const alerts = useAPI<Page<Alert>>(
    `${base}/alerts?limit=50&offset=${page * 50}`,
  );
  const [selected, setSelected] = useState<Alert>();
  const source = useAPI<RecordRow>(
    `${base}/alerts/${selected?.id}/source`,
    !!selected,
  );
  return (
    <section>
      <div className="grc-toolbar">
        <h2>Review candidates · {alerts.data?.total || 0}</h2>
        <Button disabled={!page} onClick={() => setPage((x) => x - 1)}>
          Previous alerts
        </Button>
        <Button
          disabled={(page + 1) * 50 >= (alerts.data?.total || 0)}
          onClick={() => setPage((x) => x + 1)}
        >
          Next alerts
        </Button>
      </div>
      <div className="grc-split">
        <div className="grc-grid">
          <FinancialDataGrid
            name="grc-alerts"
            rows={alerts.data?.items || []}
            columns={[
              column("rule_key", "Rule", 210),
              column("id", "Alert reference", 280),
              column("source_id", "Source item", 280),
            ]}
            onSelect={(x) => setSelected(x as Alert)}
            exportable={false}
          />
        </div>
        {selected && (
          <aside className="grc-detail">
            <h3>Investigation {selected.id}</h3>
            {(selected.source_provenance as { synthetic?: boolean })
              ?.synthetic && (
              <p className="grc-status">SYNTHETIC SOFTWARE TEST DATA</p>
            )}
            <h4>Deterministic signal</h4>
            <Narrative
              value={
                selected.signals.deterministic ||
                "No deterministic rule matched"
              }
            />
            <h4>TensorFlow.js prediction</h4>
            <Narrative
              value={selected.signals.ml || "Not scored by a deployed model"}
            />
            <MLFeedback
              inference={selected.signals.ml?.inference_id}
              transaction={selected.source_id}
            />
            <h4>Original source</h4>
            <Narrative value={source.data} />
            <Button onClick={() => onSelect(selected.id)}>
              Prepare reviewer decision
            </Button>
            <p>
              A candidate signal does not establish fraud or a misstatement.
            </p>
          </aside>
        )}
      </div>
      {alerts.error && <ErrorState error={alerts.error} />}{" "}
      {source.error && <ErrorState error={source.error} />}
    </section>
  );
}
function Copilot({ base }: { base: string }) {
  const registry = useAPI<{ ai_tasks: string[] }>("grc/frameworks");
  const action = useAction<Run>();
  const [task, setTask] = useState("");
  const [sources, setSources] = useState("");
  return (
    <section className="grc-copilot">
      <h2>Source-linked suggestions</h2>
      <p>
        Suggestions require professional review. The configured diagnostic
        provider does not perform semantic audit analysis.
      </p>
      <label>
        Task
        <select value={task} onChange={(e) => setTask(e.target.value)}>
          <option value="">Choose task</option>
          {registry.data?.ai_tasks.map((x) => (
            <option key={x} value={x}>
              {label(x)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Approved workpaper references, one per line
        <textarea
          value={sources}
          onChange={(e) => setSources(e.target.value)}
          rows={5}
        />
      </label>
      <Button
        disabled={!task || !sources.trim() || action.isPending}
        onClick={() =>
          action.mutate({
            path: `${base}/ai`,
            body: { task, record_ids: sources.split(/\s+/).filter(Boolean) },
          })
        }
      >
        Request governed suggestion
      </Button>
      {action.data && <Narrative value={action.data.results} />}{" "}
      {action.error && <ErrorState error={action.error} />}
    </section>
  );
}
function BoardPackages({ base }: { base: string }) {
  const runs = useAPI<{ items: Run[] }>(`${base}/board/packages`);
  return (
    <section>
      <h2>Governance publication</h2>
      <p>
        Prepare a package from approved reports, obtain independent approval,
        then publish. Board recipients receive the frozen narrative package.
      </p>
      {runs.data?.items.map((x) => (
        <p key={x.id}>
          Package {x.id} · {x.created_at}
        </p>
      ))}
      {runs.error && <ErrorState error={runs.error} />}
    </section>
  );
}

export function BoardPortal() {
  const [eid, setEid] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [open, setOpen] = useState(false);
  const query = useAPI<{ report: Record<string, unknown>; sha256: string }>(
    `grc/engagements/${eid}/board/packages/${identifier}`,
    open,
  );
  return (
    <>
      <PageHeader
        eyebrow="Governance / restricted distribution"
        title="Audit Committee & Board Portal"
        description="Published, independently reviewed narrative packages"
      />
      <div className="grc-shell">
        <label>
          Engagement reference
          <input
            value={eid}
            onChange={(e) => {
              setOpen(false);
              setEid(e.target.value);
            }}
          />
        </label>
        <label>
          Published package reference
          <input
            value={identifier}
            onChange={(e) => {
              setOpen(false);
              setIdentifier(e.target.value);
            }}
          />
        </label>
        <Button disabled={!eid || !identifier} onClick={() => setOpen(true)}>
          Open authorized package
        </Button>
        {query.error && <ErrorState error={query.error} />}{" "}
        {query.data && (
          <article className="grc-board">
            <Narrative value={query.data.report} />
            <BoardDownloads eid={eid} identifier={identifier} />
            <p>Integrity SHA-256: {query.data.sha256}</p>
          </article>
        )}
      </div>
    </>
  );
}
