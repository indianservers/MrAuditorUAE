"use client";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Badge,
  Button,
  Empty,
  ErrorState,
  Facts,
  Pagination,
  QueryState,
  Status,
  Tabs,
} from "@/components/ui/primitives";
import { useAPI, useAction, useCan, useDebounced } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { Engagement, Page, RecordRow } from "@/types/models";
import { Briefcase, Flag } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Future, PageHeader } from "./shared";
export function Engagements({ id }: { id?: string }) {
  return id ? <EngagementDetail key={id} id={id} /> : <EngagementList />;
}
function EngagementList() {
  const [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0);
  const value = useDebounced(search);
  const q = useAPI<Page<Engagement>>(
    "engagements?" + qs({ search: value, offset, limit: 50 }),
  );
  return (
    <>
      <PageHeader
        eyebrow="Audit workspace"
        title="Engagements"
        description="Open a real engagement to review its scope, financial context and available records."
      />
      <div className="workbench-body">
        <div className="toolbar">
          <input
            aria-label="Search engagements"
            placeholder="Search engagements…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
          <small>
            Create engagements from the client legal-entity details.
          </small>
        </div>
        <FinancialDataGrid
          name="engagements"
          rows={(q.data?.items || []) as unknown as RecordRow[]}
          loading={q.isLoading}
          error={q.error}
          columns={[
            column("name", "Engagement", 350, {
              cellRenderer: (p: { data: Engagement; value: string }) => (
                <Link href={"/engagements/" + p.data.id}>{p.value}</Link>
              ),
            }),
            column("engagement_type", "Type", 170),
            column("status", "Status", 130, {
              cellRenderer: (p: { value: string }) => (
                <Status value={p.value} />
              ),
            }),
            column("updated_at", "Updated", 200),
          ]}
        />
        <Pagination
          offset={offset}
          total={q.data?.total || 0}
          limit={50}
          onChange={setOffset}
        />
      </div>
    </>
  );
}
function EngagementDetail({ id }: { id: string }) {
  const q = useAPI<Engagement>("engagements/" + id);
  const [tab, setTab] = useState("Overview"),
    [name, setName] = useState(""),
    [status, setStatus] = useState("");
  const action = useAction();
  const can = useCan("engagements.write");
  const analyticsRead = useCan("analytics.read");
  const scope = useScope();
  const entity = useAPI<RecordRow>("entities/" + q.data?.entity_id, !!q.data);
  const findings = useAPI<Page<RecordRow>>(
    "analytics/findings?" +
      qs({
        entity_id: q.data?.entity_id,
        period_id: q.data?.period_id,
        limit: 10,
      }),
    !!q.data && analyticsRead,
  );
  return (
    <>
      <PageHeader
        eyebrow="Audit › Engagements"
        title="Audit Engagement Workspace"
        description={q.data?.name || "Engagement scope and evidence overview"}
      />
      <div className="page-body engagement-workspace">
        <QueryState query={q}>
          {q.data && (
            <>
              <div className="engagement-banner">
                <span className="entity-symbol">
                  <Briefcase size={22} />
                </span>
                <div>
                  <h2>{q.data.name}</h2>
                  <p>
                    {q.data.engagement_type} · {textValue(entity.data?.name)}
                  </p>
                </div>
                <Status value={q.data.status} />
                <span className="spacer" />
                <Button
                  onClick={() => {
                    if (entity.data) {
                      scope.setClient(String(entity.data.client_id));
                      scope.setEntity(q.data!.entity_id);
                      if (q.data!.period_id) scope.setPeriod(q.data!.period_id);
                    }
                  }}
                >
                  Use engagement context
                </Button>
              </div>
              <Tabs
                items={[
                  "Overview",
                  "Planning",
                  "Risk Assessment",
                  "Testing",
                  "Findings",
                  "Team",
                  "Timeline",
                  "Documents",
                ]}
                value={tab}
                onChange={setTab}
              />
              {tab === "Overview" ? (
                <>
                  <div className="engagement-columns">
                    <section className="card">
                      <h3>Engagement lifecycle</h3>
                      <div className="lifecycle">
                        {[
                          "Planning",
                          "Risk Assessment",
                          "Fieldwork",
                          "Review",
                          "Completion",
                        ].map((v, i) => (
                          <div key={v}>
                            <span>{i + 1}</span>
                            <strong>{v}</strong>
                            <Badge>Phase 4 workflow</Badge>
                          </div>
                        ))}
                      </div>
                      <small className="subtle">
                        Engagement status does not represent completed audit
                        procedures.
                      </small>
                    </section>
                    <section className="card">
                      <h3>Scope & responsibilities</h3>
                      <Facts
                        data={{
                          engagement_type: q.data.engagement_type,
                          entity: entity.data?.name,
                          period_id: q.data.period_id || "Not assigned",
                          created_at: q.data.created_at,
                          version: q.data.version,
                          assigned_team: "Not exposed by current API",
                        }}
                      />
                      {can && (
                        <form
                          className="resource-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            action.mutate({
                              path: "engagements/" + id,
                              method: "PATCH",
                              body: {
                                name: name || q.data!.name,
                                status: status || q.data!.status,
                                version: q.data!.version,
                              },
                            });
                          }}
                        >
                          <label>
                            Engagement name
                            <input
                              value={name || q.data.name}
                              onChange={(e) => setName(e.target.value)}
                              maxLength={200}
                            />
                          </label>
                          <label>
                            Status
                            <select
                              value={status || q.data.status}
                              onChange={(e) => setStatus(e.target.value)}
                            >
                              {[
                                "draft",
                                "active",
                                "completed",
                                "cancelled",
                              ].map((s) => (
                                <option key={s}>{s}</option>
                              ))}
                            </select>
                          </label>
                          <Button primary disabled={action.isPending}>
                            Save engagement
                          </Button>
                          <ErrorState error={action.error} />
                          {action.isSuccess && (
                            <Badge tone="success">Saved</Badge>
                          )}
                        </form>
                      )}
                    </section>
                  </div>
                  <section className="card">
                    <h3>Available risk findings</h3>
                    {findings.data?.items.length ? (
                      findings.data.items.map((f) => (
                        <Link
                          className="list-link"
                          key={f.id}
                          href="/audit/risk-intelligence"
                        >
                          <Flag size={14} />
                          {textValue(f.rule_id)}
                          <Status value={f.status} />
                        </Link>
                      ))
                    ) : (
                      <Empty title="No accessible findings in this engagement context" />
                    )}
                  </section>
                </>
              ) : tab === "Findings" || tab === "Risk Assessment" ? (
                <section className="card">
                  <h3>Financial risk records</h3>
                  <p>
                    Use the engagement context, then open the risk studio to
                    inspect source-linked findings.
                  </p>
                  <Link href="/audit/risk-intelligence" className="button">
                    Open Risk Investigation
                  </Link>
                </section>
              ) : (
                <Future
                  title={tab + " workspace"}
                  description="The visual workspace is ready. Audit programs, team responsibilities, sign-offs, document review and timeline workflows arrive in Phase 4."
                />
              )}
            </>
          )}
        </QueryState>
      </div>
    </>
  );
}
