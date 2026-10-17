"use client";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Badge,
  Button,
  Drawer,
  Empty,
  ErrorState,
  Facts,
  Pagination,
  Status,
} from "@/components/ui/primitives";
import { useAPI, useAction, useCan, usePopulation } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { downloadCSV, textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import { Download, RefreshCw, Scale, ShieldCheck } from "lucide-react";
import { useState } from "react";
import {
  ContextGate,
  JobProgress,
  PageHeader,
  PopulationPicker,
} from "./shared";
export function Reconciliation() {
  return (
    <>
      <PageHeader
        eyebrow="Financial Data › Reconciliation"
        title="Financial Reconciliation Studio"
        description="Verify source controls, financial balances and independent comparisons."
        actions={<Badge tone="blue">Evidence-driven checks</Badge>}
      />
      <ContextGate>
        <ReconciliationBody />
      </ContextGate>
    </>
  );
}
function ReconciliationBody() {
  const scope = useScope();
  const pop = usePopulation();
  const comparisons = useAPI<Page<RecordRow>>(
    "accounting/imports?" +
      qs({ entity_id: scope.entity, limit: 100, sort: "-created_at" }),
  );
  const [selectedRun, setSelectedRun] = useState(""),
    [comparison, setComparison] = useState(""),
    [tolerance, setTolerance] = useState("0"),
    [selected, setSelected] = useState<RecordRow | null>(null),
    [offset, setOffset] = useState(0),
    [job, setJob] = useState("");
  const runs = useAPI<Page<RecordRow>>(
    "reconciliation/runs?" +
      qs({
        entity_id: scope.entity,
        period_id: scope.period,
        sort: "-created_at",
        limit: 100,
      }),
  );
  const active =
    runs.data?.items.find(
      (r) => r.id === selectedRun && r.snapshot_id === pop.snapshot,
    ) || runs.data?.items.find((r) => r.snapshot_id === pop.snapshot);
  const exceptions = useAPI<Page<RecordRow>>(
    "reconciliation/exceptions?" +
      qs({ run_id: active?.id, offset, limit: 50 }),
    !!active,
  );
  const checks = ((active?.result as Record<string, unknown>)?.checks ||
    []) as RecordRow[];
  return (
    <div className="workbench-body reconciliation">
      <div className="toolbar wrap">
        <PopulationPicker />
        <label>
          Independent comparison
          <select
            aria-label="Comparison population"
            value={comparison}
            onChange={(e) => setComparison(e.target.value)}
          >
            <option value="">No independent snapshot</option>
            {comparisons.data?.items
              .filter(
                (b) =>
                  ["active", "superseded"].includes(String(b.status)) &&
                  ["gl", "journals", "tb"].includes(String(b.kind)),
              )
              .filter((b) => b.id !== pop.chosen?.id)
              .map((b) => (
                <option key={b.id} value={String(b.id)}>
                  {String(b.kind).toUpperCase()} ·{" "}
                  {String(b.created_at).slice(0, 10)} ·{" "}
                  {b.period_id === scope.period
                    ? "Selected period"
                    : "Other period"}
                </option>
              ))}
          </select>
        </label>
        <label>
          Tolerance
          <input
            aria-label="Reconciliation tolerance"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={tolerance}
            onChange={(e) => setTolerance(e.target.value)}
          />
        </label>
        <RunReconciliation
          snapshot={pop.snapshot}
          comparisonBatch={comparison}
          tolerance={tolerance}
          onJob={setJob}
        />
        <select
          aria-label="Reconciliation history"
          value={active?.id || ""}
          onChange={(e) => {
            setSelectedRun(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">Run history</option>
          {runs.data?.items
            .filter((r) => r.snapshot_id === pop.snapshot)
            .map((r) => (
              <option key={r.id} value={r.id}>
                {String(r.created_at).slice(0, 16)} · {String(r.status)}
              </option>
            ))}
        </select>
      </div>
      {job && <JobProgress id={job} onDone={() => runs.refetch()} />}
      <ErrorState error={runs.error} />
      <section className="card pipeline-card">
        <h3>Financial control checks</h3>
        <div className="pipeline">
          {checks.slice(0, 6).map((c) => (
            <div key={String(c.test)}>
              <span className="pipeline-icon">
                {c.status === "passed" ? (
                  <ShieldCheck size={20} />
                ) : (
                  <Scale size={20} />
                )}
              </span>
              <strong>{textValue(c.test).replaceAll("_", " ")}</strong>
              <Status value={c.status} />
            </div>
          ))}
        </div>
        {!checks.length && (
          <Empty title="No reconciliation run">
            Choose a committed population and run backend reconciliation.
          </Empty>
        )}
      </section>
      <div className="summary-strip">
        <div>
          <small>Reconciliation status</small>
          <Status value={active?.status || "Not run"} />
        </div>
        <div>
          <small>Independent comparison</small>
          <strong>
            {active?.comparison_snapshot_id ? "Selected" : "Not supplied"}
          </strong>
        </div>
        <div>
          <small>Exceptions in run</small>
          <strong>{exceptions.data?.total ?? "—"}</strong>
        </div>
        <div>
          <small>Adjustment posting</small>
          <span>Unavailable</span>
        </div>
      </div>
      <div className="recon-content">
        <div className="main-panel">
          <div className="section-heading">
            <h3>Reconciliation exceptions</h3>
            <Button
              disabled={!exceptions.data?.items.length}
              onClick={() =>
                downloadCSV(
                  "reconciliation-exceptions-page.csv",
                  exceptions.data?.items || [],
                )
              }
            >
              <Download size={13} /> Export page
            </Button>
          </div>
          <FinancialDataGrid
            name="reconciliation-exceptions"
            rows={exceptions.data?.items || []}
            loading={exceptions.isLoading}
            error={exceptions.error}
            onSelect={setSelected}
            columns={[
              column("account_code", "Affected account", 180),
              column("details", "Exception evidence", 650, {
                valueFormatter: (p) => textValue(p.value),
              }),
              column("created_at", "Created", 190),
            ]}
          />
          <Pagination
            offset={offset}
            total={exceptions.data?.total || 0}
            limit={50}
            onChange={setOffset}
          />
        </div>
        <aside className="card check-list">
          <h3>Run evidence</h3>
          {checks.map((c, i) => (
            <details key={i}>
              <summary>
                {textValue(c.test).replaceAll("_", " ")}{" "}
                <Status value={c.status} />
              </summary>
              <Facts data={c} />
            </details>
          ))}
          <p className="subtle">
            Balanced totals alone do not establish completeness. Missing
            controls remain insufficient evidence.
          </p>
        </aside>
      </div>
      <Drawer
        title="Reconciliation exception"
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
      >
        {selected && (
          <>
            <h3>Account {textValue(selected.account_code)}</h3>
            <Facts data={(selected.details || {}) as Record<string, unknown>} />
            <Facts
              data={{
                run_id: selected.run_id,
                entity_id: selected.entity_id,
                period_id: selected.period_id,
              }}
            />
            <p>
              Investigate source records before proposing adjustments.
              Adjustment posting and resolution tracking are unavailable.
            </p>
          </>
        )}
      </Drawer>
    </div>
  );
}
function RunReconciliation({
  snapshot,
  comparisonBatch,
  tolerance,
  onJob,
}: {
  snapshot?: string;
  comparisonBatch: string;
  tolerance: string;
  onJob: (id: string) => void;
}) {
  const comparison = useAPI<RecordRow>(
    "accounting/imports/" + comparisonBatch,
    !!comparisonBatch,
  );
  const action = useAction<RecordRow>();
  const can = useCan("analytics.run");
  return (
    <>
      <Button
        primary
        disabled={
          !can ||
          !snapshot ||
          action.isPending ||
          (!!comparisonBatch && !comparison.data)
        }
        onClick={() =>
          action.mutate(
            {
              path: "reconciliation/runs?background=true",
              body: {
                snapshot_id: snapshot,
                comparison_snapshot_id: comparison.data?.snapshot_id || null,
                tolerance,
              },
            },
            { onSuccess: (r) => onJob(r.id) },
          )
        }
      >
        <RefreshCw size={14} /> Run reconciliation
      </Button>
      <ErrorState error={action.error || comparison.error} />
    </>
  );
}
