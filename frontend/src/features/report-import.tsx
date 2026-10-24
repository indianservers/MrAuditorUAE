"use client";

import { useState, type ReactNode } from "react";
import { Button, ErrorState, Facts } from "@/components/ui/primitives";
import { useAPI, useAction, useCurrency, usePopulation } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { downloadCSV } from "@/lib/formatting/money";

const labels = {
  coa: "Chart of accounts",
  tb: "Trial balance",
  gl: "General ledger",
};
type Kind = keyof typeof labels;
type Preview = { headers: string[]; sheets: string[]; selected_sheet: string };

export function ReportPackageWizard({
  provider,
  renderBatch,
}: {
  provider: string;
  renderBatch: (id: string) => ReactNode;
}) {
  const scope = useScope();
  const currency = useCurrency();
  const population = usePopulation();
  const [supersedes, setSupersedes] = useState<Partial<Record<Kind, string>>>(
    {},
  );
  const [source, setSource] = useState(provider);
  const [files, setFiles] = useState<Partial<Record<Kind, File>>>({});
  const [mappings, setMappings] = useState<
    Partial<Record<Kind, Record<string, string>>>
  >({});
  const [previews, setPreviews] = useState<Partial<Record<Kind, Preview>>>({});
  const [error, setError] = useState("");
  const [inspecting, setInspecting] = useState<Kind | null>(null);
  const [dateFormat, setDateFormat] = useState("%Y-%m-%d");
  const action = useAction<{
    batch_ids: Record<Kind, string>;
    accounts_reconciled: number;
  }>();
  const inspect = useAction<Preview>();
  const catalogue = useAPI<{ items: { id: string; name: string }[] }>(
    "connectors/catalogue",
  );
  const contract = useAPI<{
    report_columns: Record<Kind, string[]>;
    live_testing_requirements: string[];
  }>(`connectors/${source}/requirements`);
  const [controls, setControls] = useState<
    Partial<Record<Kind, Record<string, string>>>
  >({});

  async function choose(kind: Kind, file?: File) {
    if (!file) return;
    setError("");
    setPreviews((v) => ({ ...v, [kind]: undefined }));
    setFiles((v) => ({ ...v, [kind]: undefined }));
    if (!/\.(csv|xlsx)$/i.test(file.name) || file.size > 64 * 1024 * 1024) {
      setError("Choose a CSV or XLSX report up to 64 MiB.");
      return;
    }
    setInspecting(kind);
    const body = new FormData();
    body.append("file", file);
    try {
      const preview = await inspect.mutateAsync({
        path: "workspace/inspect-file",
        body,
      });
      if (preview.sheets.length > 1) {
        setError("Export each report as a single-sheet XLSX or CSV file.");
        return;
      }
      setPreviews((v) => ({ ...v, [kind]: preview }));
      setFiles((v) => ({ ...v, [kind]: file }));
      setMappings((v) => ({ ...v, [kind]: {} }));
    } catch {
      setError("Report preview failed. Check the file and retry.");
    } finally {
      setInspecting(null);
    }
  }

  if (action.data) {
    return (
      <>
        <p>
          The three reports reconcile. Review validation and activation for each
          population below.
        </p>
        <Facts
          data={{
            accounts_reconciled: action.data.accounts_reconciled,
            source_system: source,
          }}
        />
        {(Object.keys(labels) as Kind[]).map((kind) => (
          <details key={kind}>
            <summary>{labels[kind]}</summary>
            {renderBatch(action.data!.batch_ids[kind])}
          </details>
        ))}
      </>
    );
  }
  return (
    <div className="import-wizard">
      <p>
        Upload a flat general ledger, chart of accounts, and trial balance with
        opening, period debit/credit movements, and closing balances. The
        combined limit is 64 MiB.
      </p>
      <div className="form-grid">
        <label>
          Accounting system
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {catalogue.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Date format
          <select
            value={dateFormat}
            onChange={(e) => setDateFormat(e.target.value)}
          >
            <option value="%Y-%m-%d">YYYY-MM-DD</option>
            <option value="%d/%m/%Y">DD/MM/YYYY</option>
            <option value="%m/%d/%Y">MM/DD/YYYY</option>
            <option value="%d-%m-%Y">DD-MM-YYYY</option>
            <option value="%d-%b-%Y">DD-Mon-YYYY</option>
          </select>
        </label>
      </div>
      <ErrorState
        error={
          catalogue.error || contract.error || inspect.error || action.error
        }
      />
      {(Object.keys(labels) as Kind[]).map((kind) => (
        <section className="card" key={kind}>
          <h3>{labels[kind]}</h3>
          <Button
            disabled={!contract.data}
            onClick={() =>
              downloadCSV(`${source}-${kind}-template.csv`, [
                Object.fromEntries(
                  (contract.data?.report_columns[kind] || []).map((key) => [
                    key,
                    "",
                  ]),
                ),
              ])
            }
          >
            Download column template
          </Button>
          <label>
            {labels[kind]} file
            <input
              type="file"
              accept=".csv,.xlsx"
              disabled={!!inspecting}
              onChange={(e) => void choose(kind, e.target.files?.[0])}
            />
          </label>
          {files[kind] && <p>{files[kind]?.name}</p>}
          <label>
            Replace active {labels[kind].toLowerCase()} population
            <select
              value={supersedes[kind] || ""}
              onChange={(e) =>
                setSupersedes((v) => ({
                  ...v,
                  [kind]: e.target.value,
                }))
              }
            >
              <option value="">New population</option>
              {population.committed
                .filter((b) => b.kind === kind && b.status === "active")
                .map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.id}
                  </option>
                ))}
            </select>
          </label>
          {previews[kind] && (
            <details>
              <summary>
                Map source columns (automatic matching is used for standard
                headings)
              </summary>
              <div className="mapping-fields">
                {contract.data?.report_columns[kind].map((field) => (
                  <label key={field}>
                    {field.replaceAll("_", " ")}
                    <select
                      value={mappings[kind]?.[field] || ""}
                      onChange={(e) =>
                        setMappings((v) => ({
                          ...v,
                          [kind]: { ...v[kind], [field]: e.target.value },
                        }))
                      }
                    >
                      <option value="">Automatic / not supplied</option>
                      {previews[kind]?.headers.map((h) => (
                        <option key={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </details>
          )}
          <details>
            <summary>Independent source controls (optional)</summary>
            <p>
              Use counts and functional-currency totals from an independently
              generated source report.
            </p>
            <div className="form-grid">
              {[
                "reference",
                "expected_rows",
                "expected_debit",
                "expected_credit",
              ].map((key) => (
                <label key={key}>
                  {key.replaceAll("_", " ")}
                  <input
                    value={controls[kind]?.[key] || ""}
                    onChange={(e) =>
                      setControls((v) => ({
                        ...v,
                        [kind]: { ...v[kind], [key]: e.target.value },
                      }))
                    }
                  />
                </label>
              ))}
            </div>
          </details>
        </section>
      ))}
      {error && <p role="alert">{error}</p>}
      <Button
        primary
        disabled={
          action.isPending ||
          !!inspecting ||
          !files.gl ||
          !files.tb ||
          !files.coa
        }
        onClick={() => {
          setError("");
          const chosen = Object.values(files).filter((f): f is File => !!f);
          if (chosen.reduce((n, f) => n + f.size, 0) > 64 * 1024 * 1024) {
            setError("Combined reports exceed 64 MiB.");
            return;
          }
          const suppliedControls: Record<string, unknown> = {};
          for (const [kind, control] of Object.entries(controls)) {
            if (!Object.values(control).some((v) => v.trim())) continue;
            if (
              ![
                "reference",
                "expected_rows",
                "expected_debit",
                "expected_credit",
              ].every((k) => control[k]?.trim()) ||
              !/^\d+$/.test(control.expected_rows)
            ) {
              setError(
                "Complete the reference, integer row count, debit total and credit total for each supplied control.",
              );
              return;
            }
            suppliedControls[kind] = {
              ...control,
              expected_rows: Number(control.expected_rows),
            };
          }
          const body = new FormData();
          for (const kind of Object.keys(labels) as Kind[])
            body.append(kind, files[kind]!);
          body.append(
            "options",
            JSON.stringify({
              client_id: scope.client,
              entity_id: scope.entity,
              period_id: scope.period,
              source_system: source,
              currency,
              date_format: dateFormat,
              mappings: Object.fromEntries(
                Object.entries(mappings).map(([k, v]) => [
                  k,
                  Object.fromEntries(
                    Object.entries(v).filter(([, val]) => val),
                  ),
                ]),
              ),
              controls: suppliedControls,
              supersedes_ids: Object.fromEntries(
                Object.entries(supersedes).filter(([, v]) => v),
              ),
            }),
          );
          action.mutate({ path: "connectors/report-packages", body });
        }}
      >
        Reconcile reports and create import batches
      </Button>
      <p className="subtle">
        Report uploads retain the selected source system. Direct API
        availability is shown separately in the integration center. Successful
        reconciliation still requires source review.
      </p>
    </div>
  );
}
