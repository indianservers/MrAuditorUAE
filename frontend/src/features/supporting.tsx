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
  Tabs,
} from "@/components/ui/primitives";
import { useAPI, useCan } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { useScope, useUI } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import {
  CalendarDays,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
  Scale,
  Settings2,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ContextGate, Future, PageHeader } from "./shared";
export function Compliance({ tax = false }: { tax?: boolean }) {
  const [tab, setTab] = useState("All");
  const categories = [
    "Corporate Tax",
    "VAT",
    "Transfer Pricing",
    "Pillar Two / DMTT",
  ];
  return (
    <>
      <PageHeader
        eyebrow="Regulatory workspace"
        title={tax ? "Tax Workspace" : "Compliance Command Center"}
        description="A unified view of obligations, regulatory references and configured services."
        actions={<Badge tone="warning">Phase 5 services not configured</Badge>}
      />
      <div className="page-body compliance">
        <Tabs items={["All", ...categories]} value={tab} onChange={setTab} />
        <div className="compliance-kpis">
          {(tab === "All" ? categories : [tab]).map((c, i) => (
            <section className="card" key={c}>
              <span className={"compliance-icon c" + i}>
                <Scale size={20} />
              </span>
              <h3>{c}</h3>
              <Badge>Not yet configured</Badge>
              <p className="subtle">No calculated outcome or filing status.</p>
            </section>
          ))}
        </div>
        <div className="compliance-panels">
          <section className="card">
            <h3>
              <CalendarDays size={17} /> Compliance calendar
            </h3>
            <Empty title="No configured obligations">
              Authoritative deadlines and filing workflows will be supplied by
              Phase 5. No dates are inferred from a selected financial year.
            </Empty>
          </section>
          <section className="card">
            <h3>
              <FileCheck2 size={17} /> Regulatory references
            </h3>
            <p className="subtle">
              Official reference portals. These links do not represent a
              compliance determination.
            </p>
            <a
              href="https://tax.gov.ae/"
              target="_blank"
              rel="noopener noreferrer"
              className="regulatory-link"
            >
              <span>
                Federal Tax Authority
                <small>UAE tax guidance and public notices</small>
              </span>
              <ExternalLink size={16} />
            </a>
            <a
              href="https://mof.gov.ae/"
              target="_blank"
              rel="noopener noreferrer"
              className="regulatory-link"
            >
              <span>
                UAE Ministry of Finance
                <small>Legislation and policy resources</small>
              </span>
              <ExternalLink size={16} />
            </a>
            <Future
              title="Regulatory monitoring"
              phase={5}
              description="Automated updates and client obligation matching are unavailable."
            />
          </section>
        </div>
        <section className="card">
          <h3>Client compliance status</h3>
          <Empty title="Available in Phase 5">
            No client has been classified as compliant, overdue or high risk by
            this frontend.
          </Empty>
        </section>
      </div>
    </>
  );
}
export function Supporting({ route }: { route: string }) {
  const ui = useUI();
  const scope = useScope();
  const aiRead = useCan("ai.read");
  const health = useAPI<RecordRow>(
    "ai/health",
    aiRead && route === "/settings",
  );
  const evidence = useAPI<Page<RecordRow>>(
    "accounting/imports?" +
      qs({
        entity_id: scope.entity,
        period_id: scope.period,
        limit: 100,
        sort: "-created_at",
      }),
    route === "/evidence" && !!scope.period,
  );
  if (route === "/settings")
    return (
      <>
        <PageHeader
          eyebrow="Workspace"
          title="Settings"
          description="Personal layout preferences and read-only system capabilities."
        />
        <div className="page-body settings-grid">
          <section className="card">
            <h3>
              <Settings2 size={17} /> Workspace preferences
            </h3>
            <label>
              Financial grid density
              <select
                value={ui.density}
                onChange={(e) =>
                  ui.setDensity(e.target.value as "compact" | "comfortable")
                }
              >
                <option value="compact">Compact · 35px</option>
                <option value="comfortable">Comfortable · 42px</option>
              </select>
            </label>
            <Button onClick={ui.toggleTheme}>
              Use {ui.dark ? "light" : "dark"} sidebar
            </Button>
            <p className="subtle">
              Only layout preferences are stored on this device. Session
              credentials and financial records are not stored in localStorage.
            </p>
          </section>
          <section className="card">
            <h3>AI gateway status</h3>
            <ErrorState error={health.error} />
            {health.data ? (
              <Facts data={health.data} />
            ) : (
              <Empty title="Provider status unavailable" />
            )}
            <p className="subtle">
              Real-provider connectivity is not probed by this status endpoint.
            </p>
          </section>
          <Future
            title="Firm administration"
            description="Manage server configuration through the documented deployment tooling. Membership and role mutation screens are not available."
          />
        </div>
      </>
    );
  if (route === "/evidence")
    return (
      <>
        <PageHeader
          eyebrow="Financial sources"
          title="Evidence & Source Register"
          description="Preserved import batches and immutable source references."
        />
        <ContextGate>
          <div className="workbench-body">
            <FinancialDataGrid
              name="evidence"
              rows={evidence.data?.items || []}
              loading={evidence.isLoading}
              error={evidence.error}
              columns={[
                column("id", "Source import", 300),
                column("source_system", "Source", 140),
                column("kind", "Kind", 100),
                column("status", "Status", 150),
                column("created_at", "Preserved at", 200),
              ]}
            />
            <p className="subtle">
              First 100 source batches. Use Integrations for paginated history.
              Source documents are private; drill down from a ledger line for
              record lineage.
            </p>
            <Link className="button" href="/integrations">
              Open Integrations
            </Link>
          </div>
        </ContextGate>
      </>
    );
  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Reports"
        description="Export supported financial views or open a source workbench."
      />
      <div className="page-body">
        <div className="report-grid">
          {[
            ["Trial Balance", "/financials/trial-balance"],
            ["General Ledger", "/financials/general-ledger"],
            ["Audit Findings", "/audit/risk-intelligence"],
            ["Reconciliation Exceptions", "/financials/reconciliation"],
          ].map(([label, href]) => (
            <Link className="card report-link" href={href} key={href}>
              <FileSpreadsheet size={24} />
              <h3>{label}</h3>
              <span>
                Open workbench and export loaded page <ExternalLink size={14} />
              </span>
            </Link>
          ))}
        </div>
        <Future
          title="Professional audit reporting"
          description="Full reports, opinion drafting, sign-offs and working-paper exports belong to future phases."
        />
      </div>
    </>
  );
}
