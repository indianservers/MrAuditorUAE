"use client";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  Database,
  Scale,
  ListChecks,
  ScanSearch,
  Files,
  ShieldCheck,
  FileText,
  AlertTriangle,
  Network,
  Users,
} from "lucide-react";
import type { Workspace } from "./global-workspace";

export function AuditJourney({ data, eid }: { data: Workspace; eid: string }) {
  const [attention, setAttention] = useState(false);
  const stages = [
    {
      title: "Accounting sources",
      kind: "",
      icon: Database,
      url: `/intelligence/${eid}/lead`,
      description: "Inspect committed balances and source schedules",
    },
    {
      title: "Planning & materiality",
      kind: "materiality",
      icon: Scale,
      url: `/engagements/${eid}/planning`,
      description: "Set scope, risks and reviewed materiality",
    },
    {
      title: "Risk assessment",
      kind: "risks",
      icon: ScanSearch,
      url: `/engagements/${eid}/risks`,
      description: "Connect identified risks to procedures",
    },
    {
      title: "Tests & evidence",
      kind: "testing",
      icon: ListChecks,
      url: `/engagements/${eid}/testing`,
      description: "Execute procedures and retain supporting evidence",
    },
    {
      title: "Working papers",
      kind: "working-papers",
      icon: Files,
      url: `/engagements/${eid}/working-papers`,
      description: "Review source-linked conclusions",
    },
    {
      title: "Findings & resolution",
      kind: "findings",
      icon: AlertTriangle,
      url: `/engagements/${eid}/findings`,
      description: "Resolve exceptions and management responses",
    },
    {
      title: "Independent review",
      kind: "review-notes",
      icon: ShieldCheck,
      url: `/engagements/${eid}/review-notes`,
      description: "Clear reviewer notes and approval gates",
    },
    {
      title: "Reporting",
      kind: "completion",
      icon: FileText,
      url: "/reports/statutory",
      description: "Compose reports from approved source versions",
    },
  ].map((stage) => {
    const records = data.records.filter((r) => r.kind === stage.kind);
    const stale = records.filter((r) => r.freshness !== "CURRENT").length;
    const reviewed = records.filter(
      (r) =>
        ["APPROVED", "LOCKED", "CLOSED", "RESOLVED", "CLEARED"].includes(
          r.status,
        ) && r.freshness === "CURRENT",
    ).length;
    const state = !stage.kind
      ? "Inspect sources"
      : stale
        ? "Source review needed"
        : !records.length
          ? "No records in view"
          : reviewed === records.length
            ? "Reviewed records"
            : "Work in progress";
    return { ...stage, records, reviewed, state, stale };
  });
  const next = data.blockers.find((b) => b.url);
  return (
    <section className="audit-command" aria-label="Audit command center">
      <div className="audit-command-heading">
        <div>
          <span className="eyebrow">ENGAGEMENT CONTROL CENTER</span>
          <h2>A clear path from source to opinion</h2>
          <p>
            Open any stage to work. Review states follow your retained records
            and source freshness.
          </p>
        </div>
        <Link className="button" href={`/engagements/${eid}/lifecycle`}>
          <Network size={16} /> Dependency graph
        </Link>
      </div>
      <div className="audit-command-body">
        <div>
          <div className="journey-toolbar">
            <strong>Audit journey</strong>
            <button
              type="button"
              aria-pressed={attention}
              onClick={() => setAttention(!attention)}
            >
              {attention ? "Show all stages" : "Focus on attention"}
            </button>
          </div>
          <div className="audit-journey-grid">
            {stages
              .filter((s) => !attention || s.state !== "Reviewed records")
              .map((stage, index) => {
                const Icon = stage.icon;
                return (
                  <Link
                    key={stage.title}
                    href={stage.url}
                    className={`audit-stage ${stage.stale ? "attention" : stage.state === "Reviewed records" ? "reviewed" : ""}`}
                  >
                    <div className="audit-stage-top">
                      <span className="audit-stage-icon">
                        <Icon size={21} />
                      </span>
                      <span className="audit-stage-index">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                    </div>
                    <h3>{stage.title}</h3>
                    <p>{stage.description}</p>
                    <div className="audit-stage-bottom">
                      <span>{stage.state}</span>
                      <ArrowRight size={15} />
                    </div>
                    {stage.records.length > 0 && (
                      <small>
                        {stage.reviewed} / {stage.records.length} current
                        reviewed records
                      </small>
                    )}
                  </Link>
                );
              })}
          </div>
        </div>
        <aside className="audit-next-action">
          <span className="eyebrow">NEXT BEST ACTION</span>
          <h3>{next?.label || "Inspect your engagement scope"}</h3>
          <p>
            {next?.reason.replaceAll("_", " ").toLowerCase() ||
              "Review the approved reporting context, team and source completeness before progressing."}
          </p>
          <Link
            href={next?.url || `/engagements/${eid}/planning`}
            className="button primary"
          >
            {next ? "Resolve blocker" : "Open planning"}
            <ArrowRight size={15} />
          </Link>
          <div className="audit-next-meta">
            <span>{data.blockers.length} readiness blockers</span>
            <span>
              {
                data.source_freshness.filter((s) => s.freshness !== "CURRENT")
                  .length
              }{" "}
              source items need review
            </span>
          </div>
          <Link href={`/engagements/${eid}/team`}>
            <Users size={15} /> Manage team & review assignments
          </Link>
          <p className="audit-scope-note">
            {data.truncated
              ? "Bounded view: additional records may exist. "
              : ""}
            Reviewed records do not indicate a signed opinion.
          </p>
        </aside>
      </div>
    </section>
  );
}
