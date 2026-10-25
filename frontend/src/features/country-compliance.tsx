"use client";
import Link from "next/link";
import { useAPI, useAccess } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
import type { Page, RecordRow } from "@/types/models";
import { useState } from "react";
import { RegulatoryAssessmentPanel } from "./regulatory-assessment";

export function CountryCompliance() {
  const homeCountry = useScope((s) => s.country);
  const access = useAccess();
  const [eid, setEid] = useState("");
  const engagementCountry = useAPI<{ country: string }>(
    `intelligence/engagements/${eid}/country-workflows`,
    !!eid,
  );
  const country = eid ? engagementCountry.data?.country : homeCountry;
  const engagements = useAPI<Page<RecordRow>>("engagements?limit=100");
  const rules = useAPI<{ items: { id: string; state: string }[] }>(
    `regulatory/rules?country=${country}&limit=100`,
    !!country,
  );
  const workspace = useAPI<{
    reporting_context: { framework: string; version: number };
    record_statuses: Record<string, number>;
    blockers: { id: string; label: string; reason: string; url?: string }[];
    metrics_scope: string;
    truncated: boolean;
  }>(`jurisdictions/engagements/${eid}/workspace`, !!eid);
  const india = [
    [
      "Statutory audit planning",
      "/audit/india/statutory",
      "audit.read",
      "Source-linked checklist workflow",
    ],
    [
      "CARO clause review",
      "/audit/india/caro",
      "audit.read",
      "Requires validated period-specific rule content",
    ],
    [
      "Schedule III source reconciliation",
      "/audit/india/financial-reporting",
      "accounting.read",
      "Reviewed-source draft balances; full disclosure qualification pending",
    ],
    [
      "AS / Ind AS disclosure review",
      "/audit/india/disclosures",
      "audit.read",
      "Separate country/framework applicability",
    ],
    [
      "Tax audit clause review",
      "/audit/india/tax-audit",
      "audit.read",
      "Confirm the applicable legal regime and forms for the period",
    ],
  ];
  const uae = [
    [
      "IFRS financial reporting",
      "/ifrs",
      "ifrs.read",
      "Existing reviewed financial statements, notes, leases/ECL and source schedules",
    ],
    [
      "Corporate Tax and QFZP",
      "/tax",
      "tax.profile.read",
      "Existing period-specific computation, elections and evidence review",
    ],
    [
      "VAT review",
      "/vat",
      "vat.read",
      "Existing classified transactions, source evidence and return preparation",
    ],
    [
      "Transfer pricing and benchmarking",
      "/tp",
      "tp.read",
      "Existing actual comparable observations and controlled documentation",
    ],
    [
      "DMTT / Pillar Two",
      "/pillar-two",
      "dmtt.read",
      "Existing applicability, jurisdiction calculations and elections",
    ],
  ];
  const common = [
    [
      "Group relationships",
      "/groups",
      "entities.read",
      "Recorded cross-border ownership relationships",
    ],
    [
      "Internal audit and remediation",
      "/grc",
      "grc.read",
      "Existing universe, control testing, findings and remediation",
    ],
    [
      "Statutory report designer",
      "/reports/statutory",
      "audit.read",
      "Ordered source-backed blocks and controlled draft exports",
    ],
    [
      "Regulatory rule library",
      "/settings/regulatory-rules",
      "audit.read",
      "Independent validation, publication and historical version comparison",
    ],
  ];
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="Country compliance"
        title={`${country || "Engagement"} Compliance Workspace`}
        description="One global audit engine with country-specific content, source-linked calculations and professional review. Availability is separate from legal qualification."
      />
      <ErrorState
        error={
          engagementCountry.error ||
          engagements.error ||
          rules.error ||
          workspace.error
        }
      />
      <section className="main-panel" style={{ padding: 20 }}>
        <div className="toolbar">
          <Link className="button" href="/settings">
            Switch country in Settings
          </Link>
          <label>
            Engagement
            <select
              aria-label="Compliance engagement"
              value={eid}
              onChange={(e) => setEid(e.target.value)}
            >
              <option value="">Select authorized engagement</option>
              {engagements.data?.items.map((e) => (
                <option key={e.id} value={e.id}>
                  {String(e.name)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p>
          Library view: {rules.data?.items.length ?? 0} rule versions;{" "}
          {rules.data?.items.filter((r) => r.state === "PUBLISHED").length ?? 0}{" "}
          published versions in the first 100 returned. This is not a
          completeness or compliance certification.
        </p>
        {workspace.data && (
          <>
            <p>
              Approved context: {workspace.data.reporting_context.framework} •
              version {workspace.data.reporting_context.version}
            </p>
            <div className="toolbar">
              {Object.entries(workspace.data.record_statuses).map(
                ([status, count]) => (
                  <span key={status}>
                    <Status value={status} /> {count}
                  </span>
                ),
              )}
            </div>
            <h3>Actual engagement blockers</h3>
            {workspace.data.blockers.map((b) => (
              <p key={b.id}>
                {b.url ? <Link href={b.url}>{b.label}</Link> : b.label}:{" "}
                {b.reason}
              </p>
            ))}
            <p>
              {workspace.data.metrics_scope}
              {workspace.data.truncated ? " • Bounded view is truncated" : ""}
            </p>
            <Link className="button" href={`/engagements/${eid}/workspace`}>
              Open engagement workspace
            </Link>
          </>
        )}
      </section>
      <section className="main-panel" style={{ padding: 20 }}>
        <h2>Specialist workflows</h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(270px,1fr))",
            gap: 16,
          }}
        >
          {[
            ...(country === "IN" ? india : country === "AE" ? uae : []),
            ...common,
          ]
            .filter(([, , permission]) =>
              access.data?.permissions.includes(permission),
            )
            .map(([title, url, , description]) => (
              <article
                key={url}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: 16,
                }}
              >
                <h3>{title}</h3>
                <p>{description}</p>
                <Link className="button" href={url}>
                  Open workflow
                </Link>
              </article>
            ))}
        </div>
        {country === "IN" && (
          <p>
            India GST/TDS/TCS statutory adapters and a complete income-tax
            computation pack are not yet qualified. The accounting match engine
            and rule assessment service do not imply a live portal connection or
            legally complete tax computation.
          </p>
        )}
        {country && !["IN", "AE"].includes(country) && (
          <p>
            This country currently uses the global base profile. Local statutory
            and tax content must be validated before enabling a regulatory
            workflow.
          </p>
        )}
        <Button
          onClick={() => {
            rules.refetch();
            if (eid) workspace.refetch();
          }}
        >
          Refresh actual source and review states
        </Button>
      </section>
      {eid && (
        <section className="main-panel" style={{ padding: 20 }}>
          <h2>Connected evidence workflows</h2>
          <p>
            Bank reconciliation, payroll settlement, statutory dues and document
            comparison operate on reviewed source tables. These checks do not
            determine legal tax liability.
          </p>
          <Link
            className="button"
            href={`/intelligence/${eid}/country-workflow`}
          >
            Open country evidence workflows
          </Link>{" "}
          <Link className="button" href="/client-collaboration">
            Open client collaboration
          </Link>
        </section>
      )}
      {eid && <RegulatoryAssessmentPanel eid={eid} />}
    </div>
  );
}
