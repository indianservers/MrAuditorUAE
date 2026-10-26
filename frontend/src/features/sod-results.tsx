"use client";
/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- Named scroll regions need keyboard focus for horizontal evidence-table navigation. */

import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState } from "@/components/ui/primitives";

const collections = {
  conflicts: "Conflicts",
  conflict_intervals: "Conflict intervals",
  assignment_pair_links: "Assignment links",
  assignments: "Original assignments",
  scope_mappings: "Scope mappings",
  permission_pairs: "Permission pairs",
  retained_source_receipts: "Source receipts",
  dependencies: "Record dependencies",
};
type Collection = keyof typeof collections;
type Run = {
  id: string;
  created_at: string;
  results: { sod_contract?: string };
};
type State = { record_versions_status: string; implementation_status?: string };
type Summary = State & {
  id: string;
  frozen_at: string;
  snapshot_sha256: string;
  results: {
    analysis_from: string;
    analysis_through: string;
    analysis_mode: string;
    population_basis: string;
    source_binding_status: string;
    population_control_status: string;
    population_completeness: string;
    collection_totals: Record<Collection, number>;
    policy_pairs_retained: boolean;
    limitations: string[];
  };
};
type RowPage = State & {
  items: Record<string, string | number | boolean | null>[];
  total: number;
};
const text = (value: unknown) =>
  value == null ? "Not supplied" : String(value);
const label = (value: string) => value.replaceAll("_", " ");

export function SoDInputAssignments({
  assignments,
}: {
  assignments: unknown[];
}) {
  const [offset, setOffset] = useState(0);
  const values = assignments.slice(offset, offset + 50) as Record<
    string,
    unknown
  >[];
  const fields = ["principal", "permission", "scope", "valid_from", "valid_to"];
  return (
    <details className="sod-input">
      <summary>
        Imported assignment population ({assignments.length} rows)
      </summary>
      <p>
        Original assignment indices are one-based. This is the workpaper
        population, before any frozen conflict analysis.
      </p>
      <div className="grc-toolbar">
        <Button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
          aria-label="Previous input assignments"
        >
          Previous
        </Button>
        <Button
          disabled={offset + 50 >= assignments.length}
          onClick={() => setOffset(offset + 50)}
          aria-label="Next input assignments"
        >
          Next
        </Button>
      </div>
      <div
        style={{ overflow: "auto", maxHeight: 480 }}
        role="region"
        aria-label="Imported assignment rows"
        tabIndex={0}
      >
        <table>
          <caption>
            Input assignments · page {Math.floor(offset / 50) + 1}
          </caption>
          <thead>
            <tr>
              <th scope="col">Assignment index</th>
              {fields.map((field) => (
                <th scope="col" key={field}>
                  {label(field)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {values.map((row, index) => (
              <tr key={offset + index}>
                <td>{offset + index + 1}</td>
                {fields.map((field) => (
                  <td key={field}>{text(row[field])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function Rows({
  base,
  run,
  collection,
}: {
  base: string;
  run: string;
  collection: Collection;
}) {
  const title = collections[collection];
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(collection === "conflicts");
  const query = useAPI<RowPage>(
    `${base}/runs/${run}/sod/rows/${collection.replaceAll("_", "-")}?offset=${offset}&limit=50`,
    open,
  );
  const headers = [
    ...new Set(query.data?.items.flatMap((item) => Object.keys(item)) || []),
  ];
  return (
    <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{title}</summary>
      {open && (
        <>
          {query.error && <ErrorState error={query.error} />}
          {query.isPending && <p>Loading {title.toLowerCase()}…</p>}
          {query.data && (
            <>
              <p>
                {query.data.total} retained rows · page{" "}
                {Math.floor(offset / 50) + 1}
              </p>
              {query.data.record_versions_status ===
                "STALE_HISTORICAL_SNAPSHOT" && (
                <p role="status">
                  These rows belong to a stale historical snapshot.
                </p>
              )}
              <div className="grc-toolbar">
                <Button
                  disabled={!offset || query.isFetching}
                  onClick={() => setOffset(Math.max(0, offset - 50))}
                  aria-label={`Previous ${title}`}
                >
                  Previous
                </Button>
                <Button
                  disabled={offset + 50 >= query.data.total || query.isFetching}
                  onClick={() => setOffset(offset + 50)}
                  aria-label={`Next ${title}`}
                >
                  Next
                </Button>
              </div>
              {query.data.items.length ? (
                <div
                  style={{ overflow: "auto", maxHeight: 480 }}
                  role="region"
                  aria-label={`${title} rows`}
                  tabIndex={0}
                >
                  <table>
                    <caption>{title} — original frozen rows</caption>
                    <thead>
                      <tr>
                        {headers.map((key) => (
                          <th scope="col" key={key}>
                            {label(key)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {query.data.items.map((item, i) => (
                        <tr key={offset + i}>
                          {headers.map((key) => (
                            <td
                              style={{
                                minWidth: 130,
                                maxWidth: 360,
                                overflowWrap: "anywhere",
                              }}
                              key={key}
                            >
                              {text(item[key])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>No retained {title.toLowerCase()} rows.</p>
              )}
            </>
          )}
        </>
      )}
    </details>
  );
}

export function SoDResults({ base, run }: { base: string; run: string }) {
  const query = useAPI<Summary>(`${base}/runs/${run}/sod`);
  const tenant = useScope((s) => s.tenant);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/${base.replace(/^\//, "")}/runs/${run}/sod/export`,
        { headers: { "X-Tenant-ID": tenant }, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          "SoD workbook unavailable; verify your engagement access and selected snapshot.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `sod-${run}.xlsx`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }
  if (query.error) return <ErrorState error={query.error} />;
  if (!query.data) return <p>Loading SoD snapshot…</p>;
  const data = query.data;
  return (
    <section className="sod-results" aria-label="Frozen SoD results">
      <h3>Frozen SoD results</h3>
      <p>
        {data.results.analysis_from} through {data.results.analysis_through} ·{" "}
        {data.results.analysis_mode} · {data.results.population_basis}
      </p>
      <p role="status">
        Record versions: {data.record_versions_status}. Calculation:{" "}
        {data.implementation_status}.
      </p>
      <p>
        Source checks were recorded when this calculation was frozen. Reading or
        exporting it does not recheck current original-file bytes or establish
        population completeness.
      </p>
      <dl>
        <dt>Source binding at freeze</dt>
        <dd>{data.results.source_binding_status}</dd>
        <dt>Population controls at freeze</dt>
        <dd>{data.results.population_control_status}</dd>
        <dt>Population completeness</dt>
        <dd>{data.results.population_completeness}</dd>
        <dt>Frozen at</dt>
        <dd>{data.frozen_at}</dd>
        <dt>Snapshot SHA-256</dt>
        <dd style={{ overflowWrap: "anywhere" }}>{data.snapshot_sha256}</dd>
      </dl>
      <p>
        {data.results.collection_totals.conflicts} conflicts ·{" "}
        {data.results.collection_totals.assignments} original assignments ·{" "}
        {data.results.collection_totals.assignment_pair_links} assignment links
      </p>
      {!data.results.policy_pairs_retained && (
        <p>
          This older snapshot did not retain the complete permission-pair
          definition. Freeze a new reviewed calculation to retain it.
        </p>
      )}
      <Button disabled={busy} onClick={download}>
        Download complete SoD workbook
      </Button>
      {error && <p role="alert">{error}</p>}
      <p>
        The workbook includes all retained rows across every page. Permission
        combinations remain review candidates; compensating controls and SOX/IFC
        conclusions are not inferred.
      </p>
      {(Object.keys(collections) as Collection[]).map((collection) => (
        <Rows
          key={`${run}:${collection}`}
          base={base}
          run={run}
          collection={collection}
        />
      ))}
      <details>
        <summary>Analysis limitations</summary>
        <ul>
          {data.results.limitations.map((value, i) => (
            <li key={i}>{value}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

export function SoDCalculation({
  base,
  paper,
  canCalculate = true,
}: {
  base: string;
  paper: string;
  canCalculate?: boolean;
}) {
  const action = useAction<Run>();
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const saved = useAPI<{ items: Run[]; total: number }>(
    `${base}/runs?kind=sod-access&record_id=${paper}&compact_sod=true&limit=20&offset=${offset}`,
  );
  const active = selected || action.data?.id || saved.data?.items[0]?.id;
  return (
    <>
      {canCalculate && (
        <Button
          disabled={action.isPending}
          onClick={() => {
            setSelected("");
            action.mutate({
              path: `${base}/records/${paper}/calculate?compact_sod=true`,
            });
          }}
        >
          Freeze reviewed calculation
        </Button>
      )}
      {action.error && <ErrorState error={action.error} />}
      {saved.error && <ErrorState error={saved.error} />}
      {saved.data && (
        <>
          <label>
            Saved SoD snapshot
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Newly frozen or first on this page</option>
              {saved.data.items.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.created_at} · {run.id}
                </option>
              ))}
            </select>
          </label>
          <div className="grc-toolbar">
            <Button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Newer snapshots
            </Button>
            <Button
              disabled={offset + 20 >= saved.data.total}
              onClick={() => setOffset(offset + 20)}
            >
              Older snapshots
            </Button>
          </div>
        </>
      )}
      {active ? (
        <SoDResults key={active} base={base} run={active} />
      ) : (
        <p>No frozen SoD calculation selected.</p>
      )}
    </>
  );
}
