"use client";

import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

const metrics = ["inventory", "revenue", "cost_of_sales"] as const;
type Metric = (typeof metrics)[number];
type Scope = {
  account_ids: string[];
  expected_accounts: string;
  expected_amount: string;
  assessment: string;
  nil_inventory_assessment: string;
};
type Period = { snapshot_id: string } & Record<Metric, Scope>;
type Row = Record<string, unknown>;
const emptyScope = (): Scope => ({
  account_ids: [],
  expected_accounts: "",
  expected_amount: "",
  assessment: "",
  nil_inventory_assessment: "",
});
const emptyPeriod = (): Period => ({
  snapshot_id: "",
  inventory: emptyScope(),
  revenue: emptyScope(),
  cost_of_sales: emptyScope(),
});
const decimal = (value: string) => /^-?\d+(?:\.\d{1,8})?$/.test(value);

function MetricPicker({
  prefix,
  side,
  metric,
  snapshot,
  value,
  change,
}: {
  prefix: string;
  side: string;
  metric: Metric;
  snapshot: string;
  value: Scope;
  change: (value: Scope) => void;
}) {
  const [search, setSearch] = useState("");
  const accounts = useAPI<{
    items: { id: string; code: string; name: string }[];
    truncated?: boolean;
  }>(
    `${prefix}/accounts?snapshot_id=${snapshot}&comparative=${side === "prior"}&search=${encodeURIComponent(search)}`,
    !!snapshot,
  );
  const label = `${side} ${metric.replaceAll("_", " ")}`;
  const options = accounts.data?.items || [];
  return (
    <fieldset>
      <legend>{label}</legend>
      <ErrorState error={accounts.error} />
      <p>
        {metric === "inventory"
          ? "Debit-normal closing balance."
          : metric === "revenue"
            ? "Credits less debits, excluding opening balances."
            : "Debits less credits, excluding opening balances."}{" "}
        Assess account classification and complete scope explicitly.
      </p>
      <label>
        Find {label} accounts
        <input value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      {accounts.data?.truncated && (
        <p>
          Only the first 1,000 matching accounts are shown. Narrow the search.
          Previous selections remain retained.
        </p>
      )}
      <label>
        {label} accounts
        <select
          multiple
          size={4}
          value={value.account_ids}
          disabled={!snapshot || accounts.isFetching}
          onChange={(e) => {
            const visible = new Set(options.map((row) => row.id));
            change({
              ...value,
              account_ids: [
                ...value.account_ids.filter((id) => !visible.has(id)),
                ...Array.from(
                  e.target.selectedOptions,
                  (option) => option.value,
                ),
              ],
            });
          }}
        >
          {options.map((row) => (
            <option key={row.id} value={row.id}>
              {row.code} · {row.name}
            </option>
          ))}
        </select>
      </label>
      <p>
        {value.account_ids.length} selected, including selections outside the
        current search.
      </p>
      <Button
        disabled={!value.account_ids.length}
        onClick={() => change({ ...value, account_ids: [] })}
      >
        Clear {label} accounts
      </Button>
      <label>
        Independent {label} account count
        <input
          inputMode="numeric"
          value={value.expected_accounts}
          onChange={(e) =>
            change({ ...value, expected_accounts: e.target.value })
          }
        />
      </label>
      <label>
        Independent {label} amount
        <input
          inputMode="decimal"
          value={value.expected_amount}
          onChange={(e) =>
            change({ ...value, expected_amount: e.target.value })
          }
        />
      </label>
      <label>
        {label} account scope assessment
        <textarea
          value={value.assessment}
          onChange={(e) => change({ ...value, assessment: e.target.value })}
        />
      </label>
      {metric === "inventory" && (
        <label>
          {side} zero inventory assessment (required for zero)
          <textarea
            value={value.nil_inventory_assessment}
            onChange={(e) =>
              change({ ...value, nil_inventory_assessment: e.target.value })
            }
          />
        </label>
      )}
    </fieldset>
  );
}

export function InventoryPerformance({
  eid,
  onCreated,
}: {
  eid: string;
  onCreated: (id: string) => void;
}) {
  const prefix = `intelligence/engagements/${eid}`;
  const options = useAPI<{
    currency: string;
    current: { id: string; label: string }[];
    prior: { id: string; label: string }[];
    truncated: Record<string, boolean>;
  }>(`${prefix}/inventory-performance-options`);
  const [current, setCurrent] = useState(emptyPeriod);
  const [prior, setPrior] = useState(emptyPeriod);
  const [comparable, setComparable] = useState("");
  const [assessment, setAssessment] = useState("");
  const [stockThreshold, setStockThreshold] = useState("");
  const [gpThreshold, setGPThreshold] = useState("");
  const [places, setPlaces] = useState("");
  const [rounding, setRounding] = useState("");
  const [label, setLabel] = useState("");
  const [rationale, setRationale] = useState("");
  const action = useAction<{ id: string }>();
  const scopeValid = (period: Period) =>
    !!period.snapshot_id &&
    metrics.every((metric) => {
      const scope = period[metric];
      return (
        scope.account_ids.length > 0 &&
        scope.account_ids.length <= 100 &&
        /^\d+$/.test(scope.expected_accounts) &&
        Number(scope.expected_accounts) === scope.account_ids.length &&
        decimal(scope.expected_amount) &&
        scope.assessment.trim().length >= 10 &&
        (metric !== "inventory" ||
          !/^-?0+(?:\.0+)?$/.test(scope.expected_amount) ||
          scope.nil_inventory_assessment.trim().length >= 10)
      );
    });
  function payloadPeriod(period: Period) {
    return {
      snapshot_id: period.snapshot_id,
      ...Object.fromEntries(
        metrics.map((metric) => [
          metric,
          {
            ...period[metric],
            expected_accounts: Number(period[metric].expected_accounts),
          },
        ]),
      ),
    };
  }
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>
        Review stock and gross-profit trends from committed accounts
      </summary>
      <p>
        Select current and earlier snapshots of this entity. This review uses
        the functional currency ({options.data?.currency || "not loaded"}),
        retains signed account values and requires independent controls. Stock
        existence, complete classification and reasons for changes require
        separate evidence. It issues no audit opinion.
      </p>
      <ErrorState error={options.error || action.error} />
      {(
        [
          ["current", current, setCurrent],
          ["prior", prior, setPrior],
        ] as const
      ).map(([side, period, setPeriod]) => (
        <fieldset key={side}>
          <legend>{side} committed source</legend>
          <label>
            {side} stock/GP snapshot
            <select
              value={period.snapshot_id}
              onChange={(e) =>
                setPeriod({ ...emptyPeriod(), snapshot_id: e.target.value })
              }
            >
              <option value="">
                Select committed GL/journal or trial balance
              </option>
              {options.data?.[side]?.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.label}
                </option>
              ))}
            </select>
          </label>
          {options.data?.truncated?.[side] && (
            <p>
              The latest 100 eligible snapshots are shown; this list is bounded.
            </p>
          )}
          {metrics.map((metric) => (
            <MetricPicker
              key={`${period.snapshot_id}:${metric}`}
              prefix={prefix}
              side={side}
              metric={metric}
              snapshot={period.snapshot_id}
              value={period[metric]}
              change={(scope) =>
                setPeriod((previous) => ({ ...previous, [metric]: scope }))
              }
            />
          ))}
        </fieldset>
      ))}
      <label>
        Stock/GP periods assessed comparable
        <select
          value={comparable}
          onChange={(e) => setComparable(e.target.value)}
        >
          <option value="">Select an assessment</option>
          <option value="yes">Assessed comparable</option>
          <option value="no">Not assessed comparable — block approval</option>
        </select>
      </label>
      <label>
        Stock/GP period comparability assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <label>
        Stock-change review threshold (%)
        <input
          inputMode="decimal"
          value={stockThreshold}
          onChange={(e) => setStockThreshold(e.target.value)}
        />
      </label>
      <label>
        Gross-profit margin change threshold (percentage points)
        <input
          inputMode="decimal"
          value={gpThreshold}
          onChange={(e) => setGPThreshold(e.target.value)}
        />
      </label>
      <label>
        Stock/GP display decimal places
        <input
          inputMode="numeric"
          value={places}
          onChange={(e) => setPlaces(e.target.value)}
        />
      </label>
      <label>
        Stock/GP display rounding
        <select value={rounding} onChange={(e) => setRounding(e.target.value)}>
          <option value="">Select rounding</option>
          <option value="HALF_UP">Half up</option>
          <option value="HALF_EVEN">Half even</option>
        </select>
      </label>
      <label>
        Stock/GP review title
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <label>
        Stock/GP source rationale
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
      </label>
      <Button
        disabled={
          action.isPending ||
          !scopeValid(current) ||
          !scopeValid(prior) ||
          current.snapshot_id === prior.snapshot_id ||
          !comparable ||
          assessment.trim().length < 10 ||
          !/^\d$/.test(places) ||
          Number(places) > 8 ||
          !rounding ||
          !decimal(stockThreshold) ||
          stockThreshold.startsWith("-") ||
          !decimal(gpThreshold) ||
          gpThreshold.startsWith("-") ||
          label.trim().length < 3 ||
          rationale.trim().length < 10 ||
          !options.data?.currency
        }
        onClick={async () => {
          const created = await action
            .mutateAsync({
              path: `${prefix}/inventory-performance`,
              body: {
                current: payloadPeriod(current),
                prior: payloadPeriod(prior),
                currency: options.data!.currency,
                periods_comparable: comparable === "yes",
                comparability_assessment: assessment,
                stock_change_threshold_percent: stockThreshold,
                gp_change_threshold_pp: gpThreshold,
                rounding_places: Number(places),
                rounding_method: rounding,
                label,
                rationale,
              },
            })
            .catch(() => null);
          if (created) onCreated(created.id);
        }}
      >
        Prepare stock and GP review
      </Button>
    </details>
  );
}

export function InventoryPerformanceEvidence({
  prefix,
  selected,
  initial,
  total,
  controls,
  scope,
  observation,
}: {
  prefix: string;
  selected: string;
  initial: Row[];
  total: number;
  controls: Row[];
  scope: Record<string, unknown>;
  observation?: string;
}) {
  const [offset, setOffset] = useState(0);
  const page = useAPI<{ body: { inventory_performance_links: Row[] } }>(
    `${prefix}/events/${selected}?limit=1&inventory_performance_offset=${offset}&inventory_performance_limit=20`,
    offset > 0,
  );
  const rows = offset
    ? page.data?.body.inventory_performance_links || []
    : initial;
  const periods = scope.periods as
    Record<string, { start: string; end: string; days: number }> | undefined;
  return (
    <section aria-label="Stock and gross-profit source evidence">
      <p>{observation}</p>
      {(["current", "prior"] as const).map((side) => {
        const statuses = scope.source_balance_status as
          | Record<
              string,
              { balanced: boolean; debit_credit_difference: string }
            >
          | undefined;
        const status = statuses?.[side];
        return (
          <p key={side}>
            {side} source balance:{" "}
            {status
              ? status.balanced
                ? "Balanced"
                : "Unbalanced — approval blocked"
              : "Not supplied"}
            . Debit/credit difference:{" "}
            {status?.debit_credit_difference ?? "Not supplied"}.
          </p>
        );
      })}
      <p>
        Currency: {String(scope.currency)}. GP change threshold:{" "}
        {String(scope.gp_change_threshold_pp)} percentage points. Stock change
        threshold: {String(scope.stock_change_threshold_percent)}%. Raw values
        remain retained; display rounding does not change controls.
      </p>
      <p>
        Current period: {periods?.current?.start} to {periods?.current?.end} (
        {periods?.current?.days} days). Prior period: {periods?.prior?.start} to{" "}
        {periods?.prior?.end} ({periods?.prior?.days} days).
      </p>
      <p>
        Comparability assessment: {String(scope.comparability_assessment)}.{" "}
        {scope.periods_comparable === true
          ? "Assessed comparable"
          : "Comparison not assessed comparable; approval blocked"}
        .
      </p>
      <details>
        <summary>Stock/GP independent controls · {controls.length}</summary>
        <div className="table-wrap">
          <table aria-label="Stock/GP independent controls">
            <thead>
              <tr>
                {[
                  "period_side",
                  "metric",
                  "expected_accounts",
                  "selected_accounts",
                  "expected_amount",
                  "calculated_amount",
                  "assessment",
                  "nil_inventory_assessment",
                ].map((key) => (
                  <th key={key}>{key.replaceAll("_", " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {controls.map((row, index) => (
                <tr key={index}>
                  {[
                    "period_side",
                    "metric",
                    "expected_accounts",
                    "selected_accounts",
                    "expected_amount",
                    "calculated_amount",
                    "assessment",
                    "nil_inventory_assessment",
                  ].map((key) => (
                    <td key={key}>
                      {row[key] == null ? "Not supplied" : String(row[key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details>
        <summary>Stock/GP account lineage · {total}</summary>
        <ErrorState error={page.error} />
        <div className="table-wrap">
          <table aria-label="Stock/GP account lineage">
            <caption>{`Rows ${offset + 1}–${offset + rows.length} of ${total}`}</caption>
            <thead>
              <tr>
                {[
                  "period_side",
                  "metric",
                  "account_code",
                  "account_name",
                  "measurement_basis",
                  "opening",
                  "debit",
                  "credit",
                  "closing",
                  "normalized_amount",
                  "snapshot_id",
                  "account_id",
                ].map((key) => (
                  <th key={key}>{key.replaceAll("_", " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {[
                    "period_side",
                    "metric",
                    "account_code",
                    "account_name",
                    "measurement_basis",
                    "opening",
                    "debit",
                    "credit",
                    "closing",
                    "normalized_amount",
                    "snapshot_id",
                    "account_id",
                  ].map((key) => (
                    <td key={key}>
                      {row[key] == null ? "Not supplied" : String(row[key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button
          disabled={!offset || page.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          Previous stock/GP account links
        </Button>
        <Button
          disabled={
            offset + 20 >= total || page.isFetching || Boolean(page.error)
          }
          onClick={() => setOffset(offset + 20)}
        >
          Next stock/GP account links
        </Button>
      </details>
    </section>
  );
}
