"use client";
import { useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import {
  Button,
  ErrorState,
  Status,
  Facts,
  Empty,
} from "@/components/ui/primitives";
import {
  Layers,
  ArrowUpRight,
  ShieldCheck,
  Globe2,
  FileCheck2,
  AlertTriangle,
} from "lucide-react";

export type ModuleItem = {
  id: string;
  category: string;
  name: string;
  description: string;
  availability: string;
  url: string | null;
  record_count: number | null;
  requires_engagement: boolean;
  kind: string | null;
};
export type Catalogue = {
  version: string;
  country: string;
  categories: { id: string; name: string }[];
  items: ModuleItem[];
};
export function ModuleDirectory({ eid }: { eid?: string }) {
  const params = useSearchParams();
  const [search, setSearch] = useState(params?.get("search") || ""),
    [category, setCategory] = useState("ALL");
  const country = useScope((s) => s.country);
  const q = useAPI<Catalogue>(
    `jurisdictions/modules?country=${country}${eid ? `&eid=${eid}` : ""}`,
  );
  return (
    <section className="global-page">
      <div className="global-heading">
        <div>
          <span className="eyebrow">
            Capability catalogue · {q.data?.country || country}
          </span>
          <h2>Audit modules</h2>
          <p>
            One global audit engine. Country-specific availability, real
            workflows and a clearly marked roadmap.
          </p>
        </div>
        <Layers size={30} />
      </div>
      <div className="global-filters">
        <input
          aria-label="Search modules"
          placeholder="Find a module or submodule…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Module category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="ALL">All 13 categories</option>
          {q.data?.categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <small>{q.data?.items.length || 0} registered submodules</small>
      </div>
      <ErrorState error={q.error} />
      <div className="module-grid">
        {q.data?.categories
          .filter((c) => category === "ALL" || category === c.id)
          .map((c) => {
            const items = q.data!.items.filter(
              (m) =>
                m.category === c.id &&
                m.name.toLowerCase().includes(search.toLowerCase()),
            );
            return items.length ? (
              <section className="module-category" key={c.id}>
                <h3>
                  <span>{c.id}</span>
                  {c.name}
                </h3>
                {items.map((m) => (
                  <article key={m.id} className="module-entry">
                    <div>
                      <strong>{m.name}</strong>
                      <p>{m.description}</p>
                      {m.record_count !== null && (
                        <small>{m.record_count} authorized records</small>
                      )}
                    </div>
                    <div>
                      <Status value={m.availability} />
                      {m.url ? (
                        <Link href={m.url} className="module-open">
                          Open workflow <ArrowUpRight size={13} />
                        </Link>
                      ) : (
                        <small>
                          {m.requires_engagement
                            ? "Select an engagement to open"
                            : "PLANNED" === m.availability
                              ? "Future phase · no engine available"
                              : "Unavailable in this context"}
                        </small>
                      )}
                    </div>
                  </article>
                ))}
              </section>
            ) : null;
          })}
      </div>
    </section>
  );
}

type RecordNode = {
  id: string;
  kind: string;
  label: string;
  status: string;
  freshness: string;
  url: string;
};
type Workspace = {
  team: { user_id: string; email: string; role: string }[];
  engagement: { id: string; name: string; status: string; updated_at: string };
  entity: {
    id: string;
    name: string;
    country: string;
    functional_currency: string;
    client_id: string;
  };
  client: { id: string; name: string };
  period: { id: string; start_date: string; end_date: string };
  package: { country: string; version: string };
  reporting_context: { version: number; framework: string };
  records: RecordNode[];
  record_statuses: Record<string, number>;
  blockers: { id: string; label: string; reason: string; url?: string }[];
  mapping: { total: number; mapped: number } | null;
  source_freshness: RecordNode[];
  truncated: boolean;
  metrics_scope: string;
};
export function EngagementWorkspace({ eid }: { eid: string }) {
  const q = useAPI<Workspace>(
    `jurisdictions/engagements/${eid}/workspace`,
    true,
    true,
  );
  const [tab, setTab] = useState("Overview");
  const scope = useScope();
  const data = q.data;
  const records = data?.records || [];
  const kinds = (kind: string) => records.filter((r) => r.kind === kind);
  const pending = records.filter((r) => r.status === "REVIEW_REQUIRED");
  const [configuration, setConfiguration] = useState(false);
  const context = () => {
    if (data) {
      scope.setClient(data.client.id);
      scope.setEntity(data.entity.id);
      scope.setPeriod(data.period.id);
    }
  };
  return (
    <section className="global-page">
      <ErrorState error={q.error} />
      {!data ? (
        <p>Loading authorized engagement…</p>
      ) : (
        <>
          <div className="global-heading">
            <div>
              <span className="eyebrow">Mr Auditor / {data.client.name}</span>
              <h1>{data.engagement.name}</h1>
              <p>
                {data.entity.name} · Incorporated {data.entity.country} ·
                Reporting {data.package.country} ·{" "}
                {data.entity.functional_currency}
              </p>
            </div>
            <div>
              <Status value={data.engagement.status} />
              <Link
                className="primary-link"
                href={`/engagements/${eid}/lifecycle`}
              >
                Explore lifecycle <ArrowUpRight size={15} />
              </Link>
            </div>
          </div>
          <div className="context-strip">
            <span>
              <Globe2 size={16} />
              {data.package.version}
            </span>
            <span>
              {data.period.start_date} — {data.period.end_date}
            </span>
            <span>{data.reporting_context.framework}</span>
            <button onClick={() => setConfiguration(!configuration)}>
              Review reporting context
            </button>
          </div>
          {configuration && <ReportingContext eid={eid} />}
          <nav className="workspace-sections" aria-label="Engagement sections">
            {[
              "Overview",
              "Planning",
              "Accounting Data",
              "Scrutiny",
              "Reconciliations",
              "Working Papers",
              "Risks",
              "Findings",
              "Tax",
              "Reporting",
              "Activity History",
            ].map((t) => (
              <button
                key={t}
                aria-current={tab === t ? "page" : undefined}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
            <Link href={`/engagements/${eid}/lifecycle`}>
              Audit Lifecycle Graph
            </Link>
          </nav>
          {tab === "Overview" ? (
            <>
              <div className="workspace-metrics">
                {[
                  [
                    "Working papers",
                    kinds("working-papers").length,
                    FileCheck2,
                  ],
                  ["Pending approvals", pending.length, ShieldCheck],
                  [
                    "Open findings",
                    kinds("findings").filter(
                      (r) =>
                        !["RESOLVED", "CLOSED", "ARCHIVED"].includes(r.status),
                    ).length,
                    AlertTriangle,
                  ],
                  [
                    "Source impact",
                    data.source_freshness.filter(
                      (r) => r.freshness !== "CURRENT",
                    ).length,
                    Layers,
                  ],
                ].map(([label, count, Icon]) => {
                  const I = Icon as typeof Layers;
                  return (
                    <article key={String(label)}>
                      <I size={19} />
                      <span>{String(label)}</span>
                      <strong>{String(count)}</strong>
                    </article>
                  );
                })}
              </div>
              <div className="workspace-columns">
                <section className="card">
                  <h3>Audit readiness blockers</h3>
                  <p className="subtle">
                    Professional review remains required. These checks are not
                    an audit opinion.
                  </p>
                  {data.blockers.map((b) => (
                    <p key={b.id} className="blocker-row">
                      <AlertTriangle size={14} />
                      {b.url ? <Link href={b.url}>{b.label}</Link> : b.label}
                      <Status value={b.reason} />
                    </p>
                  ))}
                  {!data.blockers.length && (
                    <p>No blockers detected within this projection.</p>
                  )}
                </section>
                <section className="card">
                  <h3>Work and evidence</h3>
                  <Facts data={data.record_statuses} />
                  <p>
                    Outstanding document requests:{" "}
                    {
                      kinds("requests").filter(
                        (r) =>
                          !["CLOSED", "APPROVED", "ARCHIVED"].includes(
                            r.status,
                          ),
                      ).length
                    }
                  </p>
                  <p>
                    Review notes:{" "}
                    {
                      kinds("review-notes").filter(
                        (r) =>
                          !["CLEARED", "RESOLVED", "ARCHIVED"].includes(
                            r.status,
                          ),
                      ).length
                    }
                  </p>
                  <p>
                    Materiality:{" "}
                    {kinds("materiality")
                      .map((r) => r.status)
                      .join(", ") || "Not started"}
                  </p>
                  <p>
                    Account mapping:{" "}
                    {data.mapping
                      ? `${data.mapping.mapped} of ${data.mapping.total} accounts classified`
                      : "Restricted or unavailable"}
                  </p>
                  <Link href={`/engagements/${eid}/team`}>
                    Team, reviewer and partner assignments
                  </Link>
                  {data.team?.map((member) => (
                    <p key={member.user_id + member.role}>
                      {member.email} · {member.role}
                    </p>
                  ))}
                  <p>Last updated: {data.engagement.updated_at}</p>
                </section>
              </div>
              <p className="subtle">
                {data.metrics_scope}
                {data.truncated && " · Incomplete bounded population"}
              </p>
            </>
          ) : tab === "Activity History" ? (
            <Activity eid={eid} />
          ) : tab === "Working Papers" ? (
            <Link
              className="primary-link"
              href={`/engagements/${eid}/working-papers`}
            >
              Open working-paper register
            </Link>
          ) : tab === "Risks" ? (
            <Link className="primary-link" href={`/engagements/${eid}/risks`}>
              Open risk register
            </Link>
          ) : tab === "Findings" ? (
            <Link
              className="primary-link"
              href={`/engagements/${eid}/findings`}
            >
              Open findings register
            </Link>
          ) : tab === "Accounting Data" ? (
            <section className="card">
              <h3>Accounting data</h3>
              <p>
                Use this engagement’s legal entity and financial period for
                source-data work.
              </p>
              <div className="actions">
                {["mapping", "trial-balance", "general-ledger"].map((k) => (
                  <Link key={k} onClick={context} href={`/financials/${k}`}>
                    {k.replaceAll("-", " ")}
                  </Link>
                ))}
              </div>
            </section>
          ) : (
            <ModuleDirectory eid={eid} />
          )}
        </>
      )}
    </section>
  );
}

type Profile = {
  country: string;
  name: string;
  version: string;
  status: string;
  currencies: string[];
  accounting_standards: string[];
  auditing_standards: string[];
  tax_categories: string[];
  reporting_requirements: string[];
  sources: { title: string; url: string }[];
  legal_effectivity: string;
};
type ContextEvent = {
  id: string;
  kind: string;
  created_by: string;
  body: {
    country: string;
    framework: string;
    request_id?: string;
    reason: string;
    version?: number;
  };
};
export function ReportingContext({ eid }: { eid: string }) {
  const q = useAPI<{
    current: {
      country: string;
      version: number;
      framework: string;
      as_of: string;
    };
    events: ContextEvent[];
    user_id: string;
  }>(`jurisdictions/engagements/${eid}/context`);
  const [selected, setSelected] = useState("");
  const country = selected || q.data?.current.country || "AE";
  const p = useAPI<Profile>(`jurisdictions/profiles/${country}`);
  const action = useAction();
  const canPlan = useCan("audit.plan"),
    canReview = useCan("workingpaper.review");
  const decided = new Set(
    q.data?.events
      .filter((e) => e.kind !== "REQUESTED")
      .map((e) => e.body.request_id),
  );
  return (
    <section className="card reporting-context">
      <h3>Versioned reporting context</h3>
      <p>
        Incorporation, currency and historical conclusions stay intact. Every
        reporting-context change needs an independent review. Completed
        engagements must use their governed reopening process first.
      </p>
      <p>
        Current version {q.data?.current.version} · {q.data?.current.framework}
      </p>
      {canPlan && q.data && (
        <form
          key={q.data.current.version}
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            action.mutate({
              path: `jurisdictions/engagements/${eid}/context`,
              body: {
                country,
                framework: f.get("framework"),
                entity_type: f.get("entity_type"),
                as_of: f.get("as_of"),
                reason: f.get("reason"),
                base_version: q.data!.current.version,
              },
            });
          }}
          className="context-form"
        >
          <label>
            Reporting country
            <select
              aria-label="Reporting country"
              value={country}
              onChange={(e) => setSelected(e.target.value)}
            >
              {["AE", "IN", "GB", "US", "SG", "SA", "AU"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Reporting framework
            <select
              key={country}
              name="framework"
              aria-label="Reporting framework"
            >
              {p.data?.accounting_standards.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Entity type
            <select name="entity_type">
              <option>company</option>
              <option>partnership</option>
              <option>branch</option>
              <option>other</option>
            </select>
          </label>
          <label>
            Legal as-of date
            <input
              name="as_of"
              type="date"
              required
              defaultValue={q.data.current.as_of}
            />
          </label>
          <label>
            Amendment / applicability rationale
            <input
              name="reason"
              aria-label="Context rationale"
              minLength={10}
              maxLength={4000}
              required
            />
          </label>
          <Button disabled={action.isPending}>
            Request independent review
          </Button>
        </form>
      )}
      {q.data?.events.map((event) => (
        <article key={event.id}>
          <Status value={event.kind} /> {event.body.country} ·{" "}
          {event.body.framework}
          <p>{event.body.reason}</p>
          {event.kind === "REQUESTED" &&
            !decided.has(event.id) &&
            canReview &&
            event.created_by !== q.data?.user_id && (
              <div className="actions">
                {[true, false].map((approve) => (
                  <Button
                    key={String(approve)}
                    onClick={() => {
                      const comments = window.prompt(
                        "Document the independent applicability review (minimum 10 characters)",
                      );
                      if (comments && comments.length >= 10)
                        action.mutate({
                          path: `jurisdictions/engagements/${eid}/context/decision`,
                          body: { request_id: event.id, approve, comments },
                        });
                    }}
                  >
                    {approve ? "Approve context" : "Reject context"}
                  </Button>
                ))}
              </div>
            )}
        </article>
      ))}
      <ErrorState error={q.error || p.error || action.error} />
    </section>
  );
}

function Activity({ eid }: { eid: string }) {
  const q = useAPI<{ items: Record<string, unknown>[] }>(
    `jurisdictions/engagements/${eid}/activity`,
  );
  return (
    <section className="card">
      <h3>Engagement activity</h3>
      <ErrorState error={q.error} />
      {q.data?.items.map((e, i) => (
        <Facts key={i} data={e} />
      ))}
    </section>
  );
}

type Group = {
  entities: {
    id: string;
    name: string;
    country: string;
    functional_currency: string;
  }[];
  relationships: {
    id: string;
    parent_id: string;
    child_id: string;
    status: string;
    version: number;
    body: { ownership_percent: string; effective_from: string; reason: string };
  }[];
};
export function GroupWorkspace() {
  const q = useAPI<Group>("jurisdictions/groups"),
    action = useAction();
  const create = useCan("entities.write"),
    review = useCan("tenant.manage");
  return (
    <section className="global-page">
      <div className="global-heading">
        <div>
          <span className="eyebrow">Group & multi-entity</span>
          <h1>Corporate group structure</h1>
          <p>
            Cross-country ownership with independent review. Currencies and
            legal jurisdictions remain entity-specific.
          </p>
        </div>
      </div>
      <ErrorState error={q.error || action.error} />
      {create && (
        <form
          className="context-form card"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            action.mutate({
              path: "jurisdictions/groups",
              body: {
                parent_id: f.get("parent"),
                child_id: f.get("child"),
                ownership_percent: f.get("share"),
                effective_from: f.get("date"),
                reason: f.get("reason"),
              },
            });
          }}
        >
          {["parent", "child"].map((key) => (
            <label key={key}>
              {key} entity
              <select aria-label={`${key} entity`} name={key}>
                {q.data?.entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} · {e.country} / {e.functional_currency}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label>
            Ownership %
            <input
              name="share"
              type="number"
              step="0.000001"
              min="0.000001"
              max="100"
              required
            />
          </label>
          <label>
            Effective from
            <input name="date" type="date" required />
          </label>
          <label>
            Ownership rationale
            <input name="reason" minLength={10} required />
          </label>
          <Button>Submit ownership relationship</Button>
        </form>
      )}
      {q.data && (
        <div
          style={{
            height: 400,
            border: "1px solid var(--border)",
            marginTop: 20,
          }}
          aria-label="Cross-country ownership graph"
        >
          <ReactFlow
            nodes={q.data.entities.slice(0, 300).map((e, i) => ({
              id: e.id,
              position: { x: (i % 3) * 330, y: Math.floor(i / 3) * 150 },
              sourcePosition: Position.Right,
              targetPosition: Position.Left,
              data: {
                label: `${e.name}\n${e.country} · ${e.functional_currency}`,
              },
              style: {
                width: 260,
                padding: 16,
                whiteSpace: "pre-wrap",
                borderRadius: 12,
                border: "2px solid #13847c",
              },
            }))}
            edges={q.data.relationships
              .filter(
                (r) =>
                  r.status !== "ARCHIVED" &&
                  r.status !== "REJECTED" &&
                  q
                    .data!.entities.slice(0, 300)
                    .some((e) => e.id === r.parent_id) &&
                  q
                    .data!.entities.slice(0, 300)
                    .some((e) => e.id === r.child_id),
              )
              .map((r) => ({
                id: r.id,
                source: r.parent_id,
                target: r.child_id,
                label: `${r.body.ownership_percent}% · ${r.status}`,
                markerEnd: { type: MarkerType.ArrowClosed },
                style: {
                  strokeDasharray: r.status === "APPROVED" ? undefined : "5 5",
                },
              }))}
            fitView
            maxZoom={1.1}
            nodesDraggable={false}
            nodesConnectable={false}
            onlyRenderVisibleElements
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
      )}
      {!q.data?.relationships.length && (
        <Empty title="No authorized group relationships" />
      )}
      <div
        className="group-structure"
        role="list"
        aria-label="Group relationships"
      >
        {q.data?.relationships.map((r) => (
          <article
            className="card"
            key={r.id}
            role="listitem"
            data-testid={`group-relationship-${r.id}`}
          >
            <div className="group-edge">
              <strong>
                {q.data?.entities.find((e) => e.id === r.parent_id)?.name} (
                {q.data?.entities.find((e) => e.id === r.parent_id)?.country})
              </strong>
              <span>→ {r.body.ownership_percent}% →</span>
              <strong>
                {q.data?.entities.find((e) => e.id === r.child_id)?.name} (
                {q.data?.entities.find((e) => e.id === r.child_id)?.country})
              </strong>
            </div>
            <Status value={r.status} />
            <p>
              Effective from {r.body.effective_from} · {r.body.reason}
            </p>
            {review &&
              ["IN_REVIEW", "APPROVED", "REJECTED"].includes(r.status) && (
                <div className="actions">
                  {(r.status === "IN_REVIEW"
                    ? ["approve", "reject"]
                    : ["archive"]
                  ).map((a) => (
                    <Button
                      key={a}
                      onClick={() => {
                        const reason = window.prompt(
                          "Independent review rationale (minimum 10 characters)",
                        );
                        if (reason && reason.length >= 10)
                          action.mutate({
                            path: `jurisdictions/groups/${r.id}`,
                            method: "PATCH",
                            body: { version: r.version, action: a, reason },
                          });
                      }}
                    >
                      {a}
                    </Button>
                  ))}
                </div>
              )}
          </article>
        ))}
      </div>
      <p className="subtle">
        Relationships do not automatically establish control, consolidation
        treatment or tax-group eligibility.
      </p>
    </section>
  );
}

export function RecordHub({ kind }: { kind: "working-papers" | "findings" }) {
  const [eid, setEid] = useState("");
  const engagements = useAPI<{ items: { id: string; name: string }[] }>(
    "engagements?limit=100",
  );
  const records = useAPI<{
    items: { id: string; reference: string; title: string; status: string }[];
  }>(`engagements/${eid}/audit/${kind}?limit=50`, !!eid);
  return (
    <section className="global-page">
      <div className="global-heading">
        <div>
          <span className="eyebrow">Authorized engagement records</span>
          <h1>{kind === "findings" ? "Findings" : "Working Papers"}</h1>
          <p>
            Select an engagement to inspect its saved records and review
            history.
          </p>
        </div>
      </div>
      <select
        aria-label="Record engagement"
        value={eid}
        onChange={(e) => setEid(e.target.value)}
      >
        <option value="">Select engagement</option>
        {engagements.data?.items.map((e) => (
          <option key={e.id} value={e.id}>
            {e.name}
          </option>
        ))}
      </select>
      <ErrorState error={records.error || engagements.error} />
      {eid && (
        <Link href={`/engagements/${eid}/${kind}`}>
          Open full register and available actions
        </Link>
      )}
      {records.data?.items.map((r) => (
        <article className="card" key={r.id}>
          <Link href={`/engagements/${eid}/${kind}?record=${r.id}`}>
            {r.reference}: {r.title}
          </Link>
          <Status value={r.status} />
        </article>
      ))}
    </section>
  );
}
