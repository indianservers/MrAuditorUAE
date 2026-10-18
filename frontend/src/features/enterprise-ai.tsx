"use client";
import Link from "next/link";
import { useState } from "react";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, Empty, ErrorState } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
import type { Engagement, Page } from "@/types/models";
import { useScope } from "@/stores/workspace";

export const aiAreas = [
  ["command-center", "AI Command Center"],
  ["agents", "Specialist Agent Library"],
  ["investigations", "Cross-Module Investigation Studio"],
  ["designer", "AI Workflow Designer"],
  ["monitor", "Workflow Execution Monitor"],
  ["approvals", "Human Approval Inbox"],
  ["documents", "Document Intelligence Studio"],
  ["matching", "Document-to-Ledger Matching"],
  ["knowledge", "Enterprise Knowledge Library"],
  ["research", "Regulatory Research Center"],
  ["citations", "AI Source & Citation Explorer"],
  ["evaluations", "AI Evaluation Dashboard"],
  ["providers", "Model & Provider Administration"],
  ["usage", "AI Usage & Cost Analytics"],
  ["security", "AI Security & Audit Trail"],
  ["schedules", "AI Automation Scheduler"],
] as const;
type Item = Record<string, unknown>;
type Agent = {
  id: string;
  description: string;
  allowed_tools: string[];
  required_permissions: string[];
  max_tool_calls: number;
  prompt_version: string;
};
type Registry = { items: Agent[]; templates: Record<string, string[]> };
type Run = {
  id: string;
  task: string;
  state: string;
  version: number;
  plan: string[];
  outputs: Item;
  events: { id: string; kind: string; body: Item; created_at: string }[];
};
type Proposal = {
  id: string;
  state: string;
  version: number;
  payload_hash: string;
  payload?: { after: { title: string; narrative: string } };
  decision?: Item;
  result?: Item;
};
function label(s: string) {
  return s.replaceAll(/[-_]/g, " ");
}
function Facts({ value }: { value: unknown }) {
  if (value === null || value === undefined)
    return <span className="ai-muted">Unavailable</span>;
  if (Array.isArray(value))
    return (
      <div className="ai-fact-list">
        {value.slice(0, 50).map((v, i) => (
          <div className="ai-fact" key={i}>
            <Facts value={v} />
          </div>
        ))}
        {value.length > 50 && <p>First 50 results shown.</p>}
      </div>
    );
  if (typeof value === "object")
    return (
      <dl className="ai-facts">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <dt>{label(k)}</dt>
            <dd>
              {typeof v === "object" ? (
                <details>
                  <summary>Inspect source values</summary>
                  <Facts value={v} />
                </details>
              ) : (
                <Facts value={v} />
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  return typeof value === "string" && /^https:\/\/[^\s<>]+$/.test(value) ? (
    <a href={value} target="_blank" rel="noreferrer">
      Open source publication
    </a>
  ) : (
    <span>{String(value)}</span>
  );
}

function ActiveContext({ eid }: { eid: string }) {
  const data = useAPI<Item>(`ai/engagements/${eid}/workspace`, !!eid);
  return (
    <details>
      <summary>Active permissions and engagement scope</summary>
      <Facts value={data.data} />
      {data.error && <ErrorState error={data.error} />}
    </details>
  );
}

function ExportDraft({ base, id }: { base: string; id: string }) {
  const tenant = useScope((s) => s.tenant);
  const [error, setError] = useState<Error>();
  async function download(kind: string) {
    try {
      const r = await fetch(
        `/api/backend/${base}/investigations/${id}/export/${kind}`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!r.ok)
        throw new Error(
          "Export unavailable; refresh and verify source access.",
        );
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `investigation-${id}.${kind}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Export failed"));
    }
  }
  return (
    <>
      <Button onClick={() => download("pdf")}>Export draft PDF</Button>
      <Button onClick={() => download("docx")}>Export draft DOCX</Button>
      {error && <ErrorState error={error} />}
    </>
  );
}
export function EnterpriseAI({ area = "command-center" }: { area?: string }) {
  const engagements = useAPI<Page<Engagement>>(
    "engagements?limit=100",
    area !== "providers",
  );
  const registry = useAPI<Registry>("ai/agents", area !== "providers");
  const [eid, setEid] = useState("");
  const [selected, setSelected] = useState("");
  const [left, setLeft] = useState(true);
  const [right, setRight] = useState(true);
  const title = aiAreas.find((a) => a[0] === area)?.[1];
  if (!title)
    return (
      <Empty title="Unknown AI workspace">
        Choose a workspace from the AI library.
      </Empty>
    );
  return (
    <div className="ai-shell">
      <PageHeader
        eyebrow="Intelligence / Professional assistance"
        title={title}
        description="Investigate with authorized sources. Prepare decisions for independent professional review."
      />
      <div className="ai-context">
        <label>
          Engagement
          <select
            aria-label="AI engagement"
            value={eid}
            onChange={(e) => {
              setEid(e.target.value);
              setSelected("");
            }}
          >
            <option value="">Select authorized engagement</option>
            {engagements.data?.items.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <span className="ai-chip">
          Source-bound · No autonomous financial changes
        </span>
        <Button onClick={() => setLeft(!left)}>
          {left ? "Hide" : "Show"} library
        </Button>
        <Button onClick={() => setRight(!right)}>
          {right ? "Hide" : "Show"} context
        </Button>
      </div>
      {registry.error && <ErrorState error={registry.error} />}
      <div
        className={`ai-layout ${left ? "" : "no-left"} ${right ? "" : "no-right"}`}
      >
        {left && (
          <aside className="ai-library">
            <small>WORKSPACES</small>
            <nav>
              {aiAreas.map((a) => (
                <Link
                  aria-current={area === a[0] ? "page" : undefined}
                  key={a[0]}
                  href={`/ai/${a[0]}`}
                >
                  {a[1]}
                </Link>
              ))}
            </nav>
            <small>REVIEWED RECIPES</small>
            {Object.keys(registry.data?.templates || {}).map((k) => (
              <span className="ai-recipe" key={k}>
                {label(k)}
              </span>
            ))}
          </aside>
        )}
        <main className="ai-main">
          {area === "providers" ? (
            <RemoteFacts path="ai/providers" title="Approved model inventory" />
          ) : eid ? (
            <Workspace
              key={`${eid}:${area}`}
              area={area}
              eid={eid}
              registry={registry.data}
              selected={selected}
              select={setSelected}
            />
          ) : area === "agents" ? (
            <AgentLibrary registry={registry.data} />
          ) : (
            <Empty title="Choose an engagement">
              Client, entity and period are resolved by the backend from the
              authorized engagement.
            </Empty>
          )}
        </main>
        {right && (
          <aside className="ai-context-panel">
            <small>CONTROL CONTEXT</small>
            <h3>Evidence before conclusions</h3>
            <p>Every tool rechecks engagement and specialist permissions.</p>
            <dl>
              <dt>Scope</dt>
              <dd>
                {engagements.data?.items.find((e) => e.id === eid)?.name ||
                  "No engagement selected"}
              </dd>
              <dt>Model activity</dt>
              <dd>
                Tools are deterministic. Draft generation is an explicit
                separate action.
              </dd>
              <dt>Approval</dt>
              <dd>
                Exact proposal payload + current source versions + independent
                reviewer.
              </dd>
              <dt>Retrieval</dt>
              <dd>
                Keyword index. Semantic retrieval and OCR are not configured.
              </dd>
            </dl>
            <p className="ai-warning">
              Anomaly scores are investigation signals. They do not establish
              fraud or an auditor conclusion.
            </p>
            {eid && <ActiveContext eid={eid} />}
          </aside>
        )}
      </div>
      <footer className="ai-status">
        <span>● Private evidence repository</span>
        <span>Durable workflow receipts</span>
        <span>Professional review required</span>
      </footer>
    </div>
  );
}
function AgentLibrary({ registry }: { registry?: Registry }) {
  return (
    <div className="ai-card-grid">
      {registry?.items.map((a) => (
        <article key={a.id} className="ai-card">
          <small>
            {a.id.toUpperCase()} · {a.prompt_version}
          </small>
          <h3>{a.description}</h3>
          <p>
            {a.allowed_tools.length} allowlisted tools · {a.max_tool_calls}{" "}
            calls maximum
          </p>
          <details>
            <summary>Tool and permission contract</summary>
            <Facts
              value={{
                tools: a.allowed_tools,
                permissions: a.required_permissions,
              }}
            />
          </details>
        </article>
      ))}
    </div>
  );
}
function Workspace({
  area,
  eid,
  registry,
  selected,
  select,
}: {
  area: string;
  eid: string;
  registry?: Registry;
  selected: string;
  select: (s: string) => void;
}) {
  const base = `ai/engagements/${eid}`;
  const runs = useAPI<{ items: Run[] }>(`${base}/investigations`, true, true);
  const run = useAPI<Run>(
    `${base}/investigations/${selected}`,
    !!selected,
    !!selected,
  );
  const action = useAction<Run>();
  const [task, setTask] = useState("audit-planning");
  const [prompt, setPrompt] = useState("");
  const [query, setQuery] = useState("");
  const [showPlan, setShowPlan] = useState(false);
  const [failure, setFailure] = useState<Error>();
  async function create() {
    try {
      const data = await action.mutateAsync({
        path: "ai/command",
        body: {
          engagement_id: eid,
          task,
          prompt:
            prompt || `Review ${label(task)} using current authorized evidence`,
          idempotency_key: crypto.randomUUID(),
          inputs: { query, limit: 20 },
        },
      });
      select(data.id);
    } catch (e) {
      setFailure(e instanceof Error ? e : new Error("Request failed"));
    }
  }
  const send = async (suffix: string, body?: unknown) => {
    try {
      await action.mutateAsync({
        path: `${base}/investigations/${selected}/${suffix}`,
        body,
      });
    } catch (e) {
      setFailure(e instanceof Error ? e : new Error("Request failed"));
    }
  };
  const error = failure || action.error || run.error || runs.error;
  if (area === "agents") return <AgentLibrary registry={registry} />;
  if (area === "designer") return <Designer registry={registry} base={base} />;
  if (area === "approvals") return <ApprovalInbox base={base} run={run.data} />;
  if (area === "documents" || area === "matching")
    return <Documents base={base} matching={area === "matching"} />;
  if (area === "citations") return <CitationExplorer base={base} />;
  if (["knowledge", "research"].includes(area))
    return <Knowledge base={base} research={area === "research"} />;
  if (area === "providers")
    return <RemoteFacts path="ai/providers" title="Approved model inventory" />;
  if (area === "usage")
    return <RemoteFacts path={`${base}/usage`} title="Workflow tool usage" />;
  if (area === "security")
    return (
      <RemoteFacts
        path={`${base}/security-events`}
        title="Immutable event receipts"
      />
    );
  if (area === "schedules")
    return <Schedules base={base} registry={registry} />;
  return (
    <>
      {error && <ErrorState error={error} />}
      <div className="ai-toolbar">
        <label>
          Saved investigation
          <select
            aria-label="Saved investigation"
            value={selected}
            onChange={(e) => select(e.target.value)}
          >
            <option value="">Select investigation</option>
            {runs.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {label(r.task)} · {r.state} · {r.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        {run.data && <span className="ai-chip">{run.data.state}</span>}
      </div>
      {["command-center", "investigations"].includes(area) && (
        <section className="ai-compose">
          <div className="ai-section-heading">
            <span>01 / REVIEW A TASK PLAN</span>
            <span>Typed delegation · depth 1</span>
          </div>
          <label>
            Investigation request
            <textarea
              placeholder="Review the available evidence and identify missing information…"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </label>
          <div className="ai-two-col">
            <label>
              Reviewed task
              <select value={task} onChange={(e) => setTask(e.target.value)}>
                {Object.keys(registry?.templates || {}).map((k) => (
                  <option key={k} value={k}>
                    {label(k)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Targeted evidence / GL search
              <input
                value={query}
                maxLength={200}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Optional bounded search"
              />
            </label>
          </div>
          <div className="ai-toolbar">
            <Button onClick={() => setShowPlan(!showPlan)}>Review plan</Button>
            <Button primary disabled={action.isPending} onClick={create}>
              Create investigation
            </Button>
          </div>
          {showPlan && (
            <ol className="ai-plan">
              {[
                ...(registry?.templates[task] || []),
                "quality.validate_sources",
              ].map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ol>
          )}
        </section>
      )}
      {run.data && (
        <>
          <section className="ai-execution">
            <div className="ai-section-heading">
              <span>02 / EXECUTION TIMELINE</span>
              <span>
                {run.data.events.filter((e) => e.kind === "step").length}/
                {run.data.plan.length} steps recorded
              </span>
            </div>
            <div className="ai-toolbar">
              <Button
                disabled={action.isPending}
                onClick={() => send("dispatch")}
              >
                Run / resume worker
              </Button>
              <Button disabled={action.isPending} onClick={() => send("step")}>
                Execute next step
              </Button>
              {![
                "COMPLETED",
                "PARTIALLY_COMPLETED",
                "FAILED",
                "CANCELLED",
              ].includes(run.data.state) && (
                <>
                  <Button
                    onClick={() =>
                      send("control", {
                        version: run.data!.version,
                        action:
                          run.data!.state === "PAUSED" ? "resume" : "pause",
                      })
                    }
                  >
                    {run.data.state === "PAUSED" ? "Resume" : "Pause"}
                  </Button>
                  <Button
                    onClick={() =>
                      send("control", {
                        version: run.data!.version,
                        action: "cancel",
                      })
                    }
                  >
                    Cancel
                  </Button>
                </>
              )}
              <Button onClick={() => send("draft")}>Draft narrative</Button>
              {area === "evaluations" && (
                <Button onClick={() => send("evaluate")}>
                  Run labeled evaluation
                </Button>
              )}
            </div>
            <ol className="ai-timeline">
              {run.data.plan.map((tool, i) => {
                const event = run.data!.events.find(
                  (e) => e.kind === "step" && Number(e.body.index) === i,
                );
                const result = event?.body.result as Item | undefined;
                return (
                  <li key={tool}>
                    <div className="ai-step-index">
                      {String(i + 1).padStart(2, "0")}
                    </div>
                    <div>
                      <strong>{tool}</strong>
                      <p>
                        {result
                          ? String(result.status)
                          : "Pending · no tool activity recorded"}
                      </p>
                      {result && (
                        <details>
                          <summary>Sources, signals & limitations</summary>
                          <Facts value={result} />
                        </details>
                      )}
                    </div>
                    <small>
                      {event ? `${event.body.duration_ms} ms` : "—"}
                    </small>
                  </li>
                );
              })}
            </ol>
          </section>
          <section className="ai-card">
            <h3>Structured outcome</h3>
            <div className="ai-toolbar">
              <ExportDraft base={base} id={selected} />
            </div>
            <Facts value={run.data.outputs} />
            {run.data.events
              .filter((e) => ["narrative", "evaluation"].includes(e.kind))
              .map((e) => (
                <div key={e.id}>
                  <h3>{label(e.kind)}</h3>
                  <Facts value={e.body} />
                </div>
              ))}
          </section>
          <ProposalEditor base={base} run={run.data} />
        </>
      )}
      {!run.data && (
        <Empty
          title={
            area === "evaluations"
              ? "Select a run to evaluate"
              : "No execution selected"
          }
        >
          Saved investigations retain their actual tool receipts and
          missing-source status.
        </Empty>
      )}
    </>
  );
}
function RemoteFacts({ path, title }: { path: string; title: string }) {
  const data = useAPI<{ items?: unknown }>(path);
  return (
    <section className="ai-card">
      <h2>{title}</h2>
      {data.error && <ErrorState error={data.error} />}
      <Facts value={data.data} />
    </section>
  );
}
function ProposalEditor({ base, run }: { base: string; run: Run }) {
  const action = useAction();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [ids, setIds] = useState<string[]>([]);
  const sources = Array.from(
    new Set(
      run.events.flatMap((e) => {
        const r = e.body.result as
          { sources?: { id: string; type?: string }[] } | undefined;
        return (
          r?.sources?.filter((s) => s.type === "record").map((s) => s.id) || []
        );
      }),
    ),
  );
  return (
    <section className="ai-card">
      <h3>Propose a draft evidence review workpaper</h3>
      <p>
        Independent approval authorizes draft creation. The existing workpaper
        review remains required.
      </p>
      <label>
        Draft title
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
        />
      </label>
      <label>
        Editable recommendation
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={4000}
        />
      </label>
      <fieldset>
        <legend>Supporting collected records</legend>
        {sources.map((id) => (
          <label className="ai-checkbox" key={id}>
            <input
              type="checkbox"
              checked={ids.includes(id)}
              onChange={(e) =>
                setIds(
                  e.target.checked ? [...ids, id] : ids.filter((x) => x !== id),
                )
              }
            />
            {id}
          </label>
        ))}
      </fieldset>
      <Button
        disabled={!title || text.length < 10 || !ids.length || action.isPending}
        onClick={() =>
          action.mutate({
            path: `${base}/approvals`,
            body: { run_id: run.id, title, narrative: text, record_ids: ids },
          })
        }
      >
        Request independent approval
      </Button>
      {action.error && <ErrorState error={action.error} />}
    </section>
  );
}
function ApprovalInbox({ base }: { base: string; run?: Run }) {
  const data = useAPI<{ items: Proposal[] }>(`${base}/approvals`);
  const action = useAction();
  const [comments, setComments] = useState("");
  return (
    <>
      <h2>Exact payload approval inbox</h2>
      <label>
        Reviewer comments
        <textarea
          value={comments}
          onChange={(e) => setComments(e.target.value)}
        />
      </label>
      {data.error && <ErrorState error={data.error} />}{" "}
      {action.error && <ErrorState error={action.error} />}{" "}
      {data.data?.items.map((p) => (
        <article className="ai-card" key={p.id}>
          <span className="ai-chip">{p.state}</span>
          <h3>{p.payload?.after.title || "Source unavailable"}</h3>
          <p>{p.payload?.after.narrative}</p>
          <small>Payload SHA-256: {p.payload_hash}</small>
          <Facts value={{ decision: p.decision, result: p.result }} />
          <div className="ai-toolbar">
            {p.state === "AWAITING_APPROVAL" &&
              ["approve", "reject"].map((d) => (
                <Button
                  key={d}
                  disabled={comments.length < 10 || action.isPending}
                  onClick={() =>
                    action.mutate({
                      path: `${base}/approvals/${p.id}/decision`,
                      body: {
                        version: p.version,
                        payload_hash: p.payload_hash,
                        decision: d,
                        comments,
                      },
                    })
                  }
                >
                  {label(d)}
                </Button>
              ))}
            {["APPROVED", "RECORDED"].includes(p.state) && (
              <Button
                onClick={() =>
                  action.mutate({ path: `${base}/approvals/${p.id}/execute` })
                }
              >
                Execute / verify draft
              </Button>
            )}
          </div>
        </article>
      ))}
      {data.data?.items.length === 0 && (
        <Empty title="No proposals">
          Create an evidence-linked recommendation from a completed
          investigation.
        </Empty>
      )}
    </>
  );
}
function Documents({ base, matching }: { base: string; matching: boolean }) {
  const data = useAPI<{ items: Item[] }>(`${base}/documents`);
  const action = useAction();
  const [rid, setRid] = useState("");
  const [kind, setKind] = useState("invoice");
  const [ext, setExt] = useState("");
  const [reason, setReason] = useState("");
  const [corrected, setCorrected] = useState("");
  const matches = useAPI<{ items: Item[] }>(
    `${base}/documents/${ext}/matches`,
    !!ext && matching,
  );
  return (
    <>
      <h2>
        {matching
          ? "Evidence matching candidates"
          : "Current clean evidence extraction"}
      </h2>
      <p>
        Upload through the existing evidence workspace, obtain clean scan and
        independent approval, then index that evidence record here.
      </p>
      {!matching && (
        <section className="ai-card">
          <label>
            Approved evidence record ID
            <input value={rid} onChange={(e) => setRid(e.target.value)} />
          </label>
          <label>
            Classification
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {[
                "invoice",
                "loan",
                "lease",
                "bank-statement",
                "financial-statement",
                "contract",
                "policy",
                "other",
              ].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <Button
            disabled={!rid || action.isPending}
            onClick={() =>
              action.mutate({
                path: `${base}/documents`,
                body: {
                  record_id: rid,
                  classification: kind,
                  confidentiality: "confidential",
                },
              })
            }
          >
            Extract & index
          </Button>
        </section>
      )}
      {(data.error || action.error || matches.error) && (
        <ErrorState error={data.error || action.error || matches.error} />
      )}
      <label>
        Extraction
        <select value={ext} onChange={(e) => setExt(e.target.value)}>
          <option value="">Select extraction</option>
          {data.data?.items.map((x) => (
            <option key={String(x.id)} value={String(x.id)}>
              {String(x.classification)} · {String(x.record_id).slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {matching ? (
        <>
          <label>
            Auditor match decision rationale
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          {matches.data?.items.map((row) => (
            <article className="ai-card" key={String(row.journal_id)}>
              <Facts value={row} />
              <div className="ai-toolbar">
                {["accept", "reject"].map((decision) => (
                  <Button
                    key={decision}
                    disabled={reason.length < 10 || action.isPending}
                    onClick={() =>
                      action.mutate({
                        path: `${base}/documents/${ext}/matches`,
                        body: {
                          journal_id: row.journal_id,
                          signals_hash: row.signals_hash,
                          decision,
                          reason,
                        },
                      })
                    }
                  >
                    {label(decision)} candidate
                  </Button>
                ))}
              </div>
            </article>
          ))}
        </>
      ) : (
        <>
          <Facts value={data.data?.items.find((x) => x.id === ext)} />
          {ext && (
            <section className="ai-card">
              <h3>Correct extracted amount</h3>
              <label>
                Amount from original evidence
                <input
                  value={corrected}
                  onChange={(e) => setCorrected(e.target.value)}
                />
              </label>
              <label>
                Correction reason
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <Button
                disabled={!corrected || reason.length < 10 || action.isPending}
                onClick={() =>
                  action.mutate({
                    path: `${base}/documents/${ext}/corrections`,
                    body: { fields: { amount: corrected }, reason },
                  })
                }
              >
                Save new extraction version
              </Button>
            </section>
          )}
        </>
      )}
    </>
  );
}
function Knowledge({ base, research }: { base: string; research: boolean }) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const data = useAPI<{ items: Item[] }>(
    `${base}/knowledge/search?query=${encodeURIComponent(query)}`,
    !!query,
  );
  return (
    <>
      <h2>
        {research
          ? "Dated technical evidence research"
          : "Authorized source retrieval"}
      </h2>
      {research && (
        <p className="ai-warning">
          No official or licensed technical corpus has been ingested. Client
          documents cannot establish current law. Verify source type, applicable
          period and authority before professional use.
        </p>
      )}
      {research && (
        <RemoteFacts
          path="ai/knowledge/sources"
          title="Official publications and licensed content availability"
        />
      )}
      <form
        className="ai-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(text);
        }}
      >
        <label>
          Search indexed evidence
          <input
            value={text}
            maxLength={200}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <Button disabled={!text}>Search authorized chunks</Button>
      </form>
      {data.error && <ErrorState error={data.error} />}
      <Facts value={data.data} />
    </>
  );
}
function CitationExplorer({ base }: { base: string }) {
  const action = useAction();
  const [id, setId] = useState("");
  const [kind, setKind] = useState("record");
  const [version, setVersion] = useState("");
  return (
    <>
      <h2>Verify and open an original source</h2>
      <p>
        Each open rechecks scope, permissions, approval and current source
        versions. Copy a cited ID from a tool receipt.
      </p>
      <label>
        Source type
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {[
            "record",
            "journal",
            "snapshot",
            "chunk",
            "ml",
            "ifrs",
            "tax",
            "vat",
            "tp",
          ].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </label>
      <label>
        Source ID
        <input value={id} onChange={(e) => setId(e.target.value)} />
      </label>
      <label>
        Expected workpaper version
        <input
          type="number"
          min={1}
          value={version}
          onChange={(e) => setVersion(e.target.value)}
        />
      </label>
      <Button
        disabled={!id || action.isPending}
        onClick={() =>
          action.mutate({
            path: `${base}/citations/verify`,
            body: {
              kind,
              id,
              ...(version ? { version: Number(version) } : {}),
            },
          })
        }
      >
        Verify & open source
      </Button>
      {action.error && <ErrorState error={action.error} />}
      <Facts value={action.data} />
    </>
  );
}

function Designer({ registry, base }: { registry?: Registry; base: string }) {
  const [recipe, setRecipe] = useState("audit-planning");
  const action = useAction<Run>();
  const [configured, setConfigured] = useState<string[] | null>(null);
  const [added, setAdded] = useState("documents.search");
  const [title, setTitle] = useState("Evidence review workflow");
  const templates = useAPI<{ items: Run[] }>(`${base}/workflows`);
  const tools = configured || [
    ...(registry?.templates[recipe] || []),
    "quality.validate_sources",
  ];
  return (
    <>
      <h2>Reviewed workflow graph</h2>
      <label>
        Template
        <select
          value={recipe}
          onChange={(e) => {
            setRecipe(e.target.value);
            setConfigured(null);
          }}
        >
          {Object.keys(registry?.templates || {}).map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </label>
      <div className="ai-toolbar">
        <label>
          Allowed tool
          <select value={added} onChange={(e) => setAdded(e.target.value)}>
            {Array.from(
              new Set(registry?.items.flatMap((a) => a.allowed_tools) || []),
            ).map((tool) => (
              <option key={tool}>{tool}</option>
            ))}
          </select>
        </label>
        <Button
          disabled={tools.includes(added) || tools.length >= 12}
          onClick={() => setConfigured([...tools, added])}
        >
          Add tool
        </Button>
      </div>
      <ol className="ai-plan">
        {tools.map((tool, i) => (
          <li key={tool}>
            {tool}{" "}
            <Button
              disabled={i === 0}
              onClick={() => {
                const next = [...tools];
                [next[i - 1], next[i]] = [next[i], next[i - 1]];
                setConfigured(next);
              }}
            >
              Move up
            </Button>{" "}
            <Button
              disabled={tools.length === 1}
              onClick={() => setConfigured(tools.filter((_, n) => n !== i))}
            >
              Remove
            </Button>
          </li>
        ))}
      </ol>
      <div className="ai-flow">
        <ReactFlow
          key={tools.join(":")}
          defaultNodes={tools.map((t, i) => ({
            id: String(i),
            position: { x: 60 + (i % 2) * 300, y: 40 + i * 110 },
            data: { label: t },
            style: { width: 270, fontSize: 12 },
          }))}
          defaultEdges={tools.slice(1).map((_, i) => ({
            id: `e${i}`,
            source: String(i),
            target: String(i + 1),
          }))}
          fitView
          nodesConnectable={false}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <Button
        onClick={() =>
          action.mutate({
            path: `${base}/workflows/validate`,
            body: {
              nodes: tools,
              edges: tools.slice(1).map((_, i) => [i, i + 1]),
            },
          })
        }
      >
        Validate graph & permissions
      </Button>
      {action.error && <ErrorState error={action.error} />}
      <Facts value={action.data} />
      <label>
        Workflow version title
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
        />
      </label>
      <Button
        disabled={!title || action.isPending}
        onClick={() =>
          action.mutate({
            path: `${base}/workflows`,
            body: {
              title,
              nodes: tools,
              edges: tools.slice(1).map((_, i) => [i, i + 1]),
              idempotency_key: crypto.randomUUID(),
            },
          })
        }
      >
        Save & activate read-only graph
      </Button>
      <p>
        Only allowlisted retrieval tools can run. Graph versions are immutable.
        Every execution rechecks current source permissions.
      </p>
      {templates.data?.items.map((template) => (
        <article className="ai-card" key={template.id}>
          <h3>
            {label(template.task)} · {template.id.slice(0, 8)}
          </h3>
          <Facts value={template.plan} />
          <Button
            onClick={() =>
              action.mutate({
                path: "ai/command",
                body: {
                  engagement_id: base.split("/")[2],
                  template_id: template.id,
                  prompt: "Explicitly run configured read-only workflow",
                  idempotency_key: crypto.randomUUID(),
                  inputs: { limit: 10 },
                },
              })
            }
          >
            Create run from this version
          </Button>
        </article>
      ))}
    </>
  );
}
function Schedules({ base, registry }: { base: string; registry?: Registry }) {
  const data = useAPI<{ items: Item[] }>(`${base}/schedules`);
  const action = useAction();
  const [task, setTask] = useState("audit-planning");
  const [frequency, setFrequency] = useState("weekly");
  const [date, setDate] = useState("");
  const [active, setActive] = useState(false);
  return (
    <>
      <h2>Authorized scheduled investigations</h2>
      <section className="ai-card">
        <label>
          Task
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            {Object.keys(registry?.templates || {}).map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
        <label>
          Frequency
          <select
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
          >
            {["daily", "weekly", "monthly"].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
        <label>
          Next execution (local time)
          <input
            type="datetime-local"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label className="ai-checkbox">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          Explicitly authorize recurring processing
        </label>
        <Button
          disabled={!date || action.isPending}
          onClick={() =>
            action.mutate({
              path: `${base}/schedules`,
              body: {
                task,
                frequency,
                next_due: new Date(date).toISOString(),
                active,
                inputs: { limit: 20 },
              },
            })
          }
        >
          Save schedule
        </Button>
      </section>
      {(data.error || action.error) && (
        <ErrorState error={data.error || action.error} />
      )}
      <Facts value={data.data} />
      {data.data?.items.map((row) => (
        <Button
          key={String(row.id)}
          disabled={row.active !== true || action.isPending}
          onClick={() =>
            action.mutate({ path: `${base}/schedules/${row.id}/pause` })
          }
        >
          Pause {String(row.task)}
        </Button>
      ))}
    </>
  );
}
