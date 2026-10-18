"use client";
import { Chart, Heatmap } from "@/components/charts";
import { MLSignals } from "./ml-signals";
import type { ChartDatum } from "@/components/charts/financial-chart";
import {
  FinancialDataGrid,
  amount,
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
  QueryState,
  Status,
  Tabs,
} from "@/components/ui/primitives";
import {
  useAPI,
  useAction,
  useCan,
  useCurrency,
  usePopulation,
} from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { money, textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import { Play, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import {
  AIRequest,
  ContextGate,
  JobProgress,
  LineageDetail,
  PageHeader,
  PopulationPicker,
} from "./shared";
type Summary = {
  risk: ChartDatum[];
  rules: ChartDatum[];
  timeline: ChartDatum[];
  distribution: ChartDatum[];
  concentration: ChartDatum[];
  groups: { group: string; rule: string; value: number }[];
};
export function Analytics() {
  return (
    <>
      <MLSignals />
      <PageHeader
        eyebrow="Audit Intelligence › Risk Investigation"
        title="AI Audit Risk Investigation Studio"
        description="Investigate anomalies, prioritize risks, and review AI-supported explanations."
        actions={
          <Badge tone="warning">
            Indicators require professional investigation
          </Badge>
        }
      />
      <ContextGate>
        <AnalyticsBody />
      </ContextGate>
    </>
  );
}
function AnalyticsBody() {
  const currency = useCurrency();
  const scope = useScope();
  const pop = usePopulation();
  const [materiality, setMateriality] = useState("100000"),
    [runId, setRunId] = useState(""),
    [job, setJob] = useState(""),
    [rule, setRule] = useState(""),
    [band, setBand] = useState(""),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<RecordRow | null>(null),
    [tab, setTab] = useState("Findings"),
    [chartView, setChartView] = useState("Transaction amounts");
  const can = useCan("analytics.run");
  const runs = useAPI<Page<RecordRow>>(
    "analytics/runs?" +
      qs({
        entity_id: scope.entity,
        period_id: scope.period,
        sort: "-created_at",
        limit: 100,
      }),
  );
  const available =
    runs.data?.items.filter(
      (r) => r.snapshot_id === pop.snapshot && r.status === "completed",
    ) || [];
  const active = available.find((r) => r.id === runId) || available[0];
  const run = useAPI<RecordRow>("analytics/runs/" + active?.id, !!active);
  const summary = useAPI<Summary>(
    "workspace/analytics/" +
      active?.id +
      "/summary?" +
      qs({ rule_id: rule, band }),
    !!active,
  );
  const findings = useAPI<Page<RecordRow>>(
    "workspace/findings?" +
      qs({ run_id: active?.id, rule_id: rule, band, offset, limit: 50 }),
    !!active,
  );
  const action = useAction<RecordRow>();
  useEffect(() => {
    setOffset(0);
    setSelected(null);
  }, [rule, band, active?.id]);
  const rules = (run.data?.rules || []) as RecordRow[];
  const rightData =
    chartView === "Transaction amounts"
      ? [...(summary.data?.distribution || [])].sort(
          (a, b) =>
            [
              "0–10K",
              "10–50K",
              "50–100K",
              "100–500K",
              "500K–1M",
              ">1M",
            ].indexOf(a.name) -
            [
              "0–10K",
              "10–50K",
              "50–100K",
              "100–500K",
              "500K–1M",
              ">1M",
            ].indexOf(b.name),
        )
      : chartView === "Risk severity"
        ? summary.data?.risk
        : chartView === "Account concentration"
          ? summary.data?.concentration
          : summary.data?.rules;
  return (
    <div className="workbench-body risk-workbench">
      <div className="toolbar wrap">
        <PopulationPicker />
        <label>
          Materiality threshold
          <input
            type="number"
            min="0.01"
            step="0.01"
            aria-label="Materiality threshold"
            value={materiality}
            onChange={(e) => setMateriality(e.target.value)}
          />
        </label>
        <select
          aria-label="Analytics run"
          value={active?.id || ""}
          onChange={(e) => setRunId(e.target.value)}
        >
          <option value="">Select analytics run</option>
          {available.map((r) => (
            <option key={r.id} value={r.id}>
              {String(r.created_at).slice(0, 16)} · {r.id.slice(0, 8)}
            </option>
          ))}
        </select>
        <select
          aria-label="Risk severity filter"
          value={band}
          onChange={(e) => setBand(e.target.value)}
        >
          <option value="">All risk bands</option>
          {["Low", "Moderate", "High", "Critical"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select
          aria-label="Rule filter"
          value={rule}
          onChange={(e) => setRule(e.target.value)}
        >
          <option value="">All rules</option>
          {rules.map((r) => (
            <option key={String(r.rule_id)} value={String(r.rule_id)}>
              {textValue(r.rule_id)} · {textValue(r.test_name)}
            </option>
          ))}
        </select>
        <Button
          primary
          disabled={
            !can || !pop.snapshot || !Number(materiality) || action.isPending
          }
          onClick={() =>
            action.mutate(
              {
                path: "analytics/runs?background=true",
                body: { snapshot_id: pop.snapshot, materiality },
              },
              { onSuccess: (r) => setJob(r.id) },
            )
          }
        >
          <Play size={14} /> Run analytics
        </Button>
        {rule && (
          <Button onClick={() => setRule("")}>Clear chart filter</Button>
        )}
      </div>
      <ErrorState error={action.error || runs.error || summary.error} />
      {job && <JobProgress id={job} onDone={() => runs.refetch()} />}
      <div className={"split-workbench" + (selected ? " has-inspector" : "")}>
        <div className="main-panel">
          <div className="risk-charts">
            <Heatmap data={summary.data?.groups || []} onSelect={setRule} />
            <div className="stacked-charts">
              <div className="chart-select">
                <select
                  aria-label="Chart view"
                  value={chartView}
                  onChange={(e) => setChartView(e.target.value)}
                >
                  {[
                    "Transaction amounts",
                    "Risk severity",
                    "Risk factors by rule",
                    "Account concentration",
                  ].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </div>
              <Chart
                title={chartView}
                data={rightData || []}
                type={chartView === "Risk severity" ? "donut" : "bar"}
                unit={
                  chartView === "Transaction amounts"
                    ? "flagged lines · functional currency buckets"
                    : "findings"
                }
                onSelect={
                  chartView === "Risk factors by rule" ? setRule : undefined
                }
              />
              <Chart
                title="Flagged entries over time"
                data={summary.data?.timeline || []}
                type="line"
                unit="findings"
              />
            </div>
          </div>
          <Tabs
            items={["Findings", "Rule performance", "Severity distribution"]}
            value={tab}
            onChange={setTab}
          />
          {tab === "Findings" ? (
            <>
              <FinancialDataGrid
                name="risk-findings"
                server
                rows={findings.data?.items || []}
                loading={findings.isLoading}
                error={findings.error}
                onSelect={setSelected}
                columns={[
                  column("score", "Risk Score", 110, {
                    cellRenderer: (p: { value: string }) => (
                      <Badge
                        tone={
                          Number(p.value) >= 75
                            ? "danger"
                            : Number(p.value) >= 50
                              ? "warning"
                              : "blue"
                        }
                      >
                        {p.value || "—"}
                      </Badge>
                    ),
                  }),
                  column("band", "Severity", 110),
                  column("rule_id", "Rule", 90),
                  column("voucher_number", "Voucher No.", 160),
                  column("posting_date", "Date", 125),
                  column("account_name", "Account", 210),
                  amount("base_debit", "Debit", currency),
                  amount("base_credit", "Credit", currency),
                  column("counterparty", "Counterparty", 175),
                  column("description", "Description", 260),
                  column("status", "Status", 150),
                ]}
              />
              <Pagination
                offset={offset}
                total={findings.data?.total || 0}
                limit={50}
                onChange={setOffset}
              />
            </>
          ) : tab === "Rule performance" ? (
            <FinancialDataGrid
              name="rules"
              rows={rules.map((r, i) => ({ ...r, id: String(r.rule_id || i) }))}
              columns={[
                column("rule_id", "Rule", 100),
                column("test_name", "Test", 320),
                column("status", "Test status", 160),
                column("population_count", "Population", 120),
                column("tested_count", "Tested", 120),
                column("flagged_count", "Flagged", 120),
                column("execution_ms", "Duration (ms)", 125),
              ]}
            />
          ) : (
            <Chart
              title="Risk severity distribution"
              data={summary.data?.risk || []}
              type="donut"
              onSelect={setBand}
              unit="flagged lines"
            />
          )}
          {!active && !runs.isLoading && (
            <Empty title="No completed analytics run">
              Choose a committed population and run supported rules. Missing
              prerequisites will be reported as not testable.
            </Empty>
          )}
        </div>
        {selected && (
          <aside className="inspector">
            <header>
              <h3>Investigation</h3>
              <button
                className="icon-button"
                aria-label="Close investigation"
                onClick={() => setSelected(null)}
              >
                ×
              </button>
            </header>
            <Status value={selected.band || "Population indicator"} />
            <h3>
              {textValue(
                rules.find((r) => r.rule_id === selected.rule_id)?.test_name ||
                  selected.rule_id,
              )}
            </h3>
            <div className="risk-score">
              <strong>{textValue(selected.score).replace(/\.0+$/, "")}</strong>
              <small> /100 · indicator</small>
            </div>
            <Facts
              data={{
                voucher: selected.voucher_number,
                date: selected.posting_date,
                account: selected.account_name,
                debit: money(selected.base_debit),
                credit: money(selected.base_credit),
              }}
            />
            <section className="card flag-card">
              <h4>
                <ShieldAlert size={15} /> Why flagged?
              </h4>
              <Facts
                data={(selected.evidence || {}) as Record<string, unknown>}
              />
            </section>
            <section className="card">
              <h4>Deterministic risk factors</h4>
              <Facts
                data={(selected.factors || {}) as Record<string, unknown>}
              />
            </section>
            {pop.snapshot && !!selected.line_id && (
              <AIRequest
                key={selected.id}
                task="anomaly-explanation"
                snapshot={pop.snapshot}
                lineId={String(selected.line_id)}
                runId={active?.id}
              />
            )}
            <p className="subtle">
              Reviewer notes and case disposition are reserved for Phase 4. A
              flag is not a finding of fraud.
            </p>
            {!!selected.line_id && (
              <details>
                <summary>Source evidence</summary>
                <LineageDetail id={String(selected.line_id)} />
              </details>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
export function Sampling() {
  const pop = usePopulation(),
    scope = useScope();
  const [method, setMethod] = useState("random"),
    [size, setSize] = useState("10"),
    [seed, setSeed] = useState("42"),
    [threshold, setThreshold] = useState("0"),
    [selected, setSelected] = useState(""),
    [offset, setOffset] = useState(0);
  const action = useAction<RecordRow>();
  const q = useAPI<Page<RecordRow>>(
    "sampling/runs?" +
      qs({
        entity_id: scope.entity,
        period_id: scope.period,
        limit: 100,
        sort: "-created_at",
      }),
    !!scope.period,
  );
  const detail = useAPI<RecordRow>(
    "sampling/runs/" + selected + "?" + qs({ offset, limit: 50 }),
    !!selected,
  );
  const can = useCan("sampling.run");
  const selection = detail.data?.selection as Page<RecordRow> | undefined;
  return (
    <>
      <PageHeader
        eyebrow="Audit Intelligence"
        title="Audit Sampling"
        description="Reproducible backend selection. Sampling does not establish audit assurance."
      />
      <ContextGate>
        <div className="workbench-body">
          <div className="toolbar wrap">
            <PopulationPicker />
            <label>
              Method
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                {["random", "systematic", "mus", "high_value", "full"].map(
                  (v) => (
                    <option key={v}>{v}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              Size
              <input
                type="number"
                min="1"
                max="1000000"
                value={size}
                onChange={(e) => setSize(e.target.value)}
              />
            </label>
            <label>
              Seed
              <input
                type="number"
                min="0"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </label>
            <label>
              Threshold
              <input
                type="number"
                min="0"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </label>
            <Button
              primary
              disabled={!can || !pop.snapshot || action.isPending}
              onClick={() =>
                action.mutate(
                  {
                    path: "sampling/runs",
                    body: {
                      snapshot_id: pop.snapshot,
                      method,
                      size: Number(size),
                      seed: Number(seed),
                      threshold,
                    },
                  },
                  { onSuccess: (r) => setSelected(r.id) },
                )
              }
            >
              Select sample
            </Button>
          </div>
          <ErrorState error={action.error} />
          <FinancialDataGrid
            name="sampling-runs"
            rows={q.data?.items || []}
            columns={[
              column("id", "Run", 280),
              column("method", "Method", 150),
              column("seed", "Seed", 100),
              column("status", "Status", 150),
              column("created_at", "Created", 190),
            ]}
            onSelect={(r) => {
              setSelected(r.id);
              setOffset(0);
            }}
          />
          <Drawer
            open={!!selected}
            onOpenChange={(v) => {
              if (!v) setSelected("");
            }}
            title="Sample selection"
          >
            <QueryState query={detail}>
              {detail.data && (
                <>
                  <Facts
                    data={(detail.data.result || {}) as Record<string, unknown>}
                  />
                  {selection?.items.map((s) => (
                    <details key={s.id}>
                      <summary>
                        {textValue(s.line_id)} · {textValue(s.hits)} hit(s)
                      </summary>
                      <LineageDetail id={String(s.line_id)} />
                    </details>
                  ))}
                  <Pagination
                    offset={offset}
                    limit={50}
                    total={selection?.total || 0}
                    onChange={setOffset}
                  />
                </>
              )}
            </QueryState>
          </Drawer>
        </div>
      </ContextGate>
    </>
  );
}
