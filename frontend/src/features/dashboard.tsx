"use client";
import { Badge, Empty, QueryState, Status } from "@/components/ui/primitives";
import { useAPI } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { useScope } from "@/stores/workspace";
import type { RecordRow } from "@/types/models";
import {
  ArrowUpRight,
  Briefcase,
  CalendarClock,
  Clock3,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "./shared";
type Dashboard = {
  clients: number;
  active_engagements: number | null;
  findings: number | null;
  engagements: RecordRow[];
  activity: { action: string; created_at: string }[];
};
export function Dashboard() {
  const scope = useScope();
  const [status, setStatus] = useState("");
  const q = useAPI<Dashboard>(
    "workspace/dashboard?" +
      qs({ client_id: scope.client, period_id: scope.period, status }),
  );
  return (
    <>
      <PageHeader
        eyebrow="Firm overview"
        title="Executive Dashboard"
        description="Your authorized portfolio, financial exceptions and recent firm activity."
        actions={<Badge tone="blue">Live backend records</Badge>}
      />
      <div className="page-body dashboard">
        <div className="toolbar">
          <span>Portfolio overview</span>
          <span className="spacer" />
          <select
            aria-label="Engagement status filter"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All engagement statuses</option>
            {["draft", "active", "completed", "cancelled"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </div>
        <QueryState query={q}>
          <div className="kpi-grid">
            {[
              {
                label: "Total Clients",
                value: q.data?.clients,
                icon: Users,
                href: "/clients",
                tone: "blue",
              },
              {
                label: "Active Engagements",
                value: q.data?.active_engagements,
                icon: Briefcase,
                href: "/engagements",
                tone: "teal",
              },
              {
                label: "Stored Review Findings",
                value: q.data?.findings,
                icon: ShieldAlert,
                href: "/audit/risk-intelligence",
                tone: "red",
              },
              {
                label: "Compliance Deadlines",
                value: null,
                icon: CalendarClock,
                href: "/compliance",
                tone: "amber",
              },
            ].map((k) => (
              <Link
                className={"card kpi " + k.tone}
                href={k.href}
                key={k.label}
              >
                <span className="kpi-icon">
                  <k.icon size={20} />
                </span>
                <div>
                  <small>{k.label}</small>
                  <strong>
                    {k.value === null || k.value === undefined
                      ? "Not configured"
                      : k.value.toLocaleString()}
                  </strong>
                </div>
                <ArrowUpRight size={15} />
              </Link>
            ))}
          </div>
          <div className="dashboard-primary">
            <section className="card">
              <div className="section-heading">
                <h3>Engagement Overview</h3>
                <Link href="/engagements">
                  View all <ArrowUpRight size={12} />
                </Link>
              </div>
              {q.data?.engagements.length ? (
                <div className="engagement-list">
                  {q.data.engagements.map((e) => (
                    <Link href={"/engagements/" + e.id} key={e.id}>
                      <span className="entity-symbol">
                        <Briefcase size={17} />
                      </span>
                      <div>
                        <strong>{String(e.name)}</strong>
                        <small>{String(e.engagement_type)}</small>
                      </div>
                      <Status value={e.status} />
                      <ArrowUpRight size={14} />
                    </Link>
                  ))}
                </div>
              ) : (
                <Empty title="No engagements in this context" />
              )}
              <p className="subtle">
                Professional audit program progress is available in Phase 4.
              </p>
            </section>
            <section className="card insights">
              <h3>
                <Sparkles size={17} /> Financial Intelligence
              </h3>
              <Link href="/audit/risk-intelligence">
                <span className="insight-dot red" />
                <div>
                  <strong>Investigate deterministic findings</strong>
                  <p>
                    {q.data?.findings ?? "No authorized count"} stored rule
                    exceptions across runs. Repeated runs may flag the same
                    item.
                  </p>
                </div>
                <ArrowUpRight size={14} />
              </Link>
              <Link href="/financials/reconciliation">
                <span className="insight-dot teal" />
                <div>
                  <strong>Verify financial completeness</strong>
                  <p>
                    Inspect source controls, balance checks and independent
                    reconciliation evidence.
                  </p>
                </div>
                <ArrowUpRight size={14} />
              </Link>
              <Link href="/ai-copilot">
                <span className="insight-dot purple" />
                <div>
                  <strong>Request contextual AI support</strong>
                  <p>
                    Structured, cited suggestions using the approved AI gateway.
                  </p>
                </div>
                <ArrowUpRight size={14} />
              </Link>
            </section>
          </div>
          <div className="dashboard-secondary">
            <section className="card">
              <h3>Recent Firm Activity</h3>
              {q.data?.activity.length ? (
                <div className="activity-list">
                  {q.data.activity.map((a, i) => (
                    <div key={i}>
                      <Clock3 size={15} />
                      <strong>{a.action.replaceAll(".", " · ")}</strong>
                      <small>{new Date(a.created_at).toLocaleString()}</small>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty title="No activity available">
                  Firm activity is shown to firm administrators in firm-wide
                  context.
                </Empty>
              )}
            </section>
            <section className="card">
              <h3>Compliance Status</h3>
              <Empty title="Not yet configured">
                Corporate Tax, VAT, Transfer Pricing and Pillar Two services are
                available in Phase 5. No deadlines or compliance ratings are
                inferred.
              </Empty>
              <Link className="button" href="/compliance">
                Open Compliance Command Center <ArrowUpRight size={13} />
              </Link>
            </section>
          </div>
        </QueryState>
      </div>
    </>
  );
}
