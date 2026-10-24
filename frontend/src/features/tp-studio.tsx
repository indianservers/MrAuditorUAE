"use client";
import { TaxExecutionNotice } from "./tax-execution-notice";
import { useState } from "react";
import Link from "next/link";
import { AuditStudio } from "./audit-studio";
import { TPGraph, TPRangeChart } from "./tp-visuals";
import { TPObservations, TPCandidates } from "./tp-observations";
import { TPTaxBridge } from "./tp-tax-bridge";
import { PageHeader } from "./shared";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import {
  Button,
  Empty,
  ErrorState,
  Facts,
  Status,
} from "@/components/ui/primitives";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import type { Page, Engagement, RecordRow } from "@/types/models";

export const tpAreas = [
  ["dashboard", "TP Executive Dashboard", "profile"],
  ["relationships", "Related Party Intelligence", "relationship"],
  ["transactions", "Controlled Transactions", "transaction"],
  ["segmentation", "Financial Segmentation", "segmentation"],
  ["far", "Functional Analysis", "far"],
  ["methods", "Method Selection", "method"],
  ["datasets", "Comparable Data Imports", "dataset"],
  ["screening", "Comparable Screening", "screening"],
  ["benchmarking", "Benchmarking Statistics", "study"],
  ["loans", "Intercompany Loan Analysis", "loan"],
  ["credit", "Credit Assessment", "credit"],
  ["remuneration", "Connected Person Remuneration", "remuneration"],
  ["services", "Intercompany Services", "service"],
  ["intangibles", "Royalties & Guarantees", "royalty"],
  ["disclosure", "TP Disclosure", "disclosure"],
  ["localfile", "Local File Builder", "localfile"],
  ["masterfile", "Master File & APA", "masterfile"],
  ["ai", "AI TP Copilot", "judgment"],
] as const;
type Run = RecordRow & {
  results: Record<string, unknown>;
  dependencies_current: boolean;
  row_counts: Record<string, number>;
};

export function TPStudio({
  id,
  area = "dashboard",
}: {
  id?: string;
  area?: string;
}) {
  const directory = useAPI<Page<Engagement>>("engagements?limit=100", !id);
  const entry = tpAreas.find((x) => x[0] === area);
  if (!id)
    return (
      <>
        <PageHeader
          eyebrow="Transfer Pricing"
          title="Transfer Pricing"
          description="Source reconciliations, economic analysis and independently reviewed documentation."
        />
        <section className="workbench-body">
          {directory.error && <ErrorState error={directory.error} />}
          {directory.data?.items.map((e) => (
            <p key={e.id}>
              <Link href={`/tp/${e.id}/dashboard`}>{e.name}</Link>{" "}
              <Status value={e.status} />
            </p>
          ))}
        </section>
      </>
    );
  if (!entry)
    return <Empty title="Unknown TP workspace">Choose a TP workspace.</Empty>;
  return (
    <>
      <PageHeader
        eyebrow="Transfer Pricing / reviewed economic analysis"
        title={entry[1]}
        description="Approved financial sources · Versioned calculations · Independent professional judgment"
      />
      <nav className="audit-tabs" aria-label="TP workspaces">
        {tpAreas.map(([key, title]) => (
          <Link
            key={key}
            href={`/tp/${id}/${key}`}
            aria-current={area === key ? "page" : undefined}
          >
            {title}
          </Link>
        ))}
      </nav>
      <TPWorkspace key={area} id={id} area={area} initialKind={entry[2]} />
    </>
  );
}

function TPWorkspace({
  id,
  area,
  initialKind,
}: {
  id: string;
  area: string;
  initialKind: string;
}) {
  const base = `tp/engagements/${id}`;
  const workspace = useAPI<{
    permissions: string[];
    ai_tasks: string[];
    record_counts: Record<string, Record<string, number>>;
  }>(base + "/workspace");
  const profiles = useAPI<Page<RecordRow>>(base + "/records/profile");
  const [profile, setProfile] = useState("");
  const [draftDefaults, setDraftDefaults] = useState<Record<string, unknown>>(
    {},
  );
  const [kind, setKind] = useState(initialKind);
  const [offset, setOffset] = useState(0);
  const [runOffset, setRunOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [rid, setRid] = useState("");
  const [dataset, setDataset] = useState("");
  const [error, setError] = useState("");
  const [on, setOn] = useState("");
  const [task, setTask] = useState("related_party_candidates");
  const [source, setSource] = useState("");
  const [suggestion, setSuggestion] = useState<RecordRow | null>(null);
  const [reviewReason, setReviewReason] = useState("");
  const [background, setBackground] = useState(false);
  const [jobId, setJobId] = useState("");
  const job = useAPI<RecordRow>(`jobs/${jobId}`, !!jobId, true);
  const suggestions = useAPI<Page<RecordRow>>(
    base + "/records/ai",
    area === "ai",
  );
  const records = useAPI<Page<RecordRow>>(
    `${base}/records/${kind}?limit=50&offset=${offset}&search=${encodeURIComponent(search)}`,
  );
  const datasets = useAPI<Page<RecordRow>>(
    base + "/records/dataset",
    area === "datasets",
  );
  const runs = useAPI<Page<RecordRow>>(base + "/runs");
  const run = useAPI<Run>(
    `${base}/runs/${rid}?offset=${runOffset}&limit=50`,
    !!rid,
  );
  const action = useAction();
  const tenant = useScope((s) => s.tenant);
  const can = (p: string) => !!workspace.data?.permissions.includes(p);
  async function calculate(path: string) {
    try {
      const queued = background && path.includes("/calculate/");
      const r = await action.mutateAsync({
        path: path + (queued ? "?background=true" : ""),
      });
      if (queued) setJobId(r.id);
      else setRid(r.id);
      setRunOffset(0);
      setOffset(0);
    } catch {
      /* mutation displays error */
    }
  }
  async function download(format: string) {
    setError("");
    try {
      const r = await fetch(
        `/api/backend/${base}/runs/${rid}/export/${format}`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!r.ok) throw new Error(await r.text());
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `tp-${rid}.${format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <>
      <section className="workbench-body tp-workspace">
        {workspace.error && <ErrorState error={workspace.error} />}
        {action.error && <ErrorState error={action.error} />}
        {error && <ErrorState error={new Error(error)} />}
        <div className="source-strip">
          Statistical results require professional review. Synthetic benchmarks
          support software testing only.
        </div>
        {area === "dashboard" && (
          <section>
            <h2>Engagement TP overview</h2>
            <div className="toolbar">
              {[
                ["Transaction workpapers", "transaction"],
                ["Loan workpapers", "loan"],
                ["Benchmark studies", "study"],
                ["Local File versions", "localfile"],
                ["Master File versions", "masterfile"],
                ["Release workpapers", "release"],
              ].map(([title, key]) => (
                <article className="kpi" key={key}>
                  <small>{title}</small>
                  <strong>
                    {workspace.data?.record_counts
                      ? Object.values(
                          workspace.data.record_counts[`tp-${key}`] || {},
                        ).reduce((sum, n) => sum + n, 0)
                      : "—"}
                  </strong>
                </article>
              ))}
            </div>
            <p>
              Counts cover all review states in this engagement. Review approval
              and source freshness before using a calculation.
            </p>
          </section>
        )}
        {["datasets", "screening"].includes(area) && (
          <TPObservations
            base={base}
            profile={profile}
            canScreen={can("tp.benchmark.screen")}
          />
        )}
        {["transactions", "relationships"].includes(area) && (
          <TPCandidates
            key={profile}
            base={base}
            profile={profile}
            onSelect={(row) => {
              setKind("transaction");
              setDraftDefaults({
                journal_line_ids: [row.id],
                transaction_date: row.posting_date,
                source_amount: row.source_amount,
                source_currency: row.source_currency,
                base_amount: row.base_amount,
                base_currency: row.currency,
                exchange_rate: row.exchange_rate,
                economic_key: `SOURCE-${row.id}`,
              });
            }}
          />
        )}
        {area === "relationships" && (
          <>
            <label>
              Relationship date
              <input
                type="date"
                value={on}
                onChange={(e) => setOn(e.target.value)}
              />
            </label>
            <TPGraph base={base} profile={profile} on={on} />
          </>
        )}
        {area === "ai" && (
          <section>
            <h2>Reviewed source assistance</h2>
            <div className="toolbar">
              <label>
                AI task
                <select value={task} onChange={(e) => setTask(e.target.value)}>
                  {workspace.data?.ai_tasks.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label>
                Source workpaper UUID
                <input
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                />
              </label>
              <Button
                disabled={
                  !profile ||
                  !source ||
                  !can("tp.ai.execute") ||
                  action.isPending
                }
                onClick={async () => {
                  try {
                    setSuggestion(
                      await action.mutateAsync({
                        path: base + "/ai",
                        body: {
                          profile_id: profile,
                          source_id: source,
                          task,
                          ...(rid ? { run_id: rid } : {}),
                        },
                      }),
                    );
                  } catch {}
                }}
              >
                Generate reviewable suggestion
              </Button>
            </div>
            <label>
              Saved AI suggestion
              <select
                aria-label="Saved AI suggestion"
                value={suggestion?.id || ""}
                onChange={(e) =>
                  setSuggestion(
                    suggestions.data?.items.find(
                      (x) => x.id === e.target.value,
                    ) || null,
                  )
                }
              >
                <option value="">Choose suggestion</option>
                {suggestions.data?.items.map((x) => (
                  <option key={x.id} value={x.id}>
                    {String(x.reference)} · {String(x.status)}
                  </option>
                ))}
              </select>
            </label>
            {suggestion && (
              <>
                <Facts data={suggestion} />
                <label>
                  Independent review rationale
                  <textarea
                    value={reviewReason}
                    onChange={(e) => setReviewReason(e.target.value)}
                  />
                </label>
                <div className="toolbar">
                  {["UNDER_REVIEW", "ACCEPTED", "REJECTED"].map((decision) => (
                    <Button
                      key={decision}
                      disabled={
                        !can("tp.review") || !reviewReason || action.isPending
                      }
                      onClick={async () => {
                        try {
                          setSuggestion(
                            await action.mutateAsync({
                              path: `${base}/ai/${suggestion.id}/decision`,
                              body: {
                                version: Number(suggestion.version),
                                decision,
                                rationale: reviewReason,
                              },
                            }),
                          );
                        } catch {}
                      }}
                    >
                      {decision.replaceAll("_", " ")}
                    </Button>
                  ))}
                </div>
              </>
            )}
            <p>
              AI output remains a suggestion. Approve conclusions through the
              independent workpaper review.
            </p>
          </section>
        )}
        <div className="toolbar">
          <label>
            TP profile
            <select
              aria-label="TP profile"
              value={profile}
              onChange={(e) => {
                setProfile(e.target.value);
                setDraftDefaults({});
              }}
            >
              <option value="">Choose approved profile</option>
              {profiles.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {String(p.reference)} · {String(p.status)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Record type
            <select
              aria-label="Record type"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setDraftDefaults({});
                setOffset(0);
              }}
            >
              {[
                "rule",
                "profile",
                "party",
                "relationship",
                "transaction",
                "segmentation",
                "far",
                "method",
                "dataset",
                "study",
                "screening",
                "loan",
                "credit",
                "remuneration",
                "service",
                "royalty",
                "guarantee",
                "comparability",
                "disclosure",
                "localfile",
                "masterfile",
                "apa",
                "judgment",
                "release",
              ].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <Button
            disabled={!profile || !can("tp.calculate") || action.isPending}
            onClick={() => calculate(`${base}/matrix/${profile}`)}
          >
            Reconcile controlled transaction matrix
          </Button>
          <label>
            Immutable calculation
            <select
              aria-label="Immutable calculation"
              value={rid}
              onChange={(e) => {
                setRid(e.target.value);
                setRunOffset(0);
              }}
            >
              <option value="">Choose calculation</option>
              {runs.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {String(r.kind)} · {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {area === "datasets" && (
          <div className="toolbar">
            <label>
              Approved dataset
              <select
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
              >
                <option value="">Choose licensed or synthetic dataset</option>
                {datasets.data?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {String(d.reference)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Import CSV / XLSX
              <input
                type="file"
                accept=".csv,.xlsx"
                disabled={
                  !dataset || !can("tp.benchmark.import") || action.isPending
                }
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const body = new FormData();
                  body.append("file", file);
                  try {
                    await action.mutateAsync({
                      path: `${base}/datasets/${dataset}/import`,
                      body,
                    });
                  } catch {}
                }}
              />
            </label>
          </div>
        )}
        <label>
          Search records
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={background}
            onChange={(e) => setBackground(e.target.checked)}
          />
          Queue workpaper calculations
        </label>
        {job.error && <ErrorState error={job.error} />}
        {job.data && (
          <>
            <Facts data={job.data} />
            {["pending", "failed"].includes(String(job.data.status)) && (
              <Button
                disabled={!can("tp.calculate") || action.isPending}
                onClick={async () => {
                  try {
                    await action.mutateAsync({
                      path: `${base}/jobs/${jobId}/${job.data?.status === "failed" ? "retry" : "cancel"}`,
                    });
                  } catch {}
                }}
              >
                {job.data.status === "failed"
                  ? "Retry TP calculation"
                  : "Cancel pending TP calculation"}
              </Button>
            )}
            {job.data.status === "completed" && (
              <Button
                onClick={() => {
                  setRid(
                    String(
                      (job.data?.result as { resource_id?: string })
                        ?.resource_id || "",
                    ),
                  );
                  setRunOffset(0);
                }}
              >
                Open completed calculation
              </Button>
            )}
          </>
        )}
        {records.error && <ErrorState error={records.error} />}
        <FinancialDataGrid
          exportable={false}
          name={`tp-${kind}`}
          rows={records.data?.items || []}
          columns={[
            column("reference", "Reference", 210),
            column("title", "Workpaper", 360),
            column("status", "Review status", 160),
          ]}
          onSelect={(r) => {
            if (
              can("tp.calculate") &&
              r.status === "APPROVED" &&
              [
                "segmentation",
                "study",
                "loan",
                "credit",
                "remuneration",
                "service",
                "royalty",
                "guarantee",
                "comparability",
                "disclosure",
                "far",
                "method",
                "localfile",
                "masterfile",
                "apa",
              ].includes(kind)
            )
              void calculate(`${base}/calculate/${r.id}`);
          }}
        />
        <p>
          Select an approved workpaper to calculate. Prepare and review records
          below.
        </p>
        <div className="toolbar">
          <Button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </Button>
          <span>
            Rows {offset + 1}–{Math.min(offset + 50, records.data?.total || 0)}{" "}
            of {records.data?.total || 0}
          </span>
          <Button
            disabled={offset + 50 >= (records.data?.total || 0)}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </Button>
        </div>
        {run.error && <ErrorState error={run.error} />}
        {run.data && (
          <>
            <Status
              value={run.data.dependencies_current ? "CURRENT" : "STALE"}
            />
            <TPRangeChart result={run.data.results} />
            <TaxExecutionNotice result={run.data.results} />
            <TPTaxBridge
              base={base}
              runId={rid}
              authorized={can("tp.review") && can("tax.adjustment.propose")}
            />
            <Facts
              data={
                Object.fromEntries(
                  Object.entries(run.data.results).filter(
                    ([, v]) =>
                      !Array.isArray(v) &&
                      (v === null || typeof v !== "object"),
                  ),
                ) as RecordRow
              }
            />
            {Object.entries(run.data.results)
              .filter(([, v]) => Array.isArray(v))
              .map(([key, value]) => {
                const rows = (value as unknown[]).map((v, i) => ({
                  ...(v && typeof v === "object" ? v : { value: v }),
                  id: `${key}-${runOffset + i}`,
                })) as RecordRow[];
                const keys = Array.from(
                  new Set(rows.flatMap((r) => Object.keys(r))),
                ).filter((k) => k !== "id");
                return (
                  <section key={key}>
                    <h2>{key.replaceAll("_", " ")}</h2>
                    <FinancialDataGrid
                      exportable={false}
                      name={`tp-run-${key}`}
                      rows={rows}
                      columns={keys.map((k) =>
                        column(k, k.replaceAll("_", " "), 190),
                      )}
                    />
                  </section>
                );
              })}
            <div className="toolbar">
              <Button
                disabled={!runOffset}
                onClick={() => setRunOffset(Math.max(0, runOffset - 50))}
              >
                Previous calculation rows
              </Button>
              <span>Calculation rows from {runOffset + 1}</span>
              <Button
                disabled={
                  runOffset + 50 >=
                  Math.max(0, ...Object.values(run.data.row_counts))
                }
                onClick={() => setRunOffset(runOffset + 50)}
              >
                Next calculation rows
              </Button>
            </div>
            <div className="toolbar">
              {["json", "xlsx", "pdf", "docx"].map((f) => (
                <Button
                  key={f}
                  disabled={
                    !can("tp.report.export") || !run.data?.dependencies_current
                  }
                  onClick={() => download(f)}
                >
                  Export {f.toUpperCase()}
                </Button>
              ))}
            </div>
          </>
        )}
      </section>
      <AuditStudio
        key={`${kind}:${profile}:${String(draftDefaults.economic_key || "")}`}
        id={id}
        area={`tp-${kind}`}
        ifrs
        defaults={
          profile && !["profile", "rule"].includes(kind)
            ? { profile_id: profile, ...draftDefaults }
            : {}
        }
      />
    </>
  );
}
