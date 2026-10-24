"use client";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Badge,
  Button,
  Drawer,
  ErrorState,
  Facts,
  Modal,
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
import { downloadCSV, textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import {
  ArrowRight,
  Check,
  CloudUpload,
  Download,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { ContextGate, JobProgress, PageHeader } from "./shared";
import { ReportPackageWizard } from "./report-import";
import { NativeConnection } from "./native-connection";
type Preview = {
  sheets: string[];
  selected_sheet: string;
  headers: string[];
  rows: string[][];
};
export function Integrations() {
  const [uploadProvider, setUploadProvider] = useState("file");
  const [connectionProvider, setConnectionProvider] = useState("zoho");
  const [packageUpload, setPackageUpload] = useState(false);
  const [upload, setUpload] = useState(false),
    [connect, setConnect] = useState(false),
    [selected, setSelected] = useState<RecordRow | null>(null),
    [tab, setTab] = useState("All connectors"),
    [offset, setOffset] = useState(0);
  const scope = useScope();
  const catalogue = useAPI<{
    items: { id: string; name: string; status: string }[];
  }>("connectors/catalogue");
  const canManage = useCan("connectors.manage"),
    canImport = useCan("accounting.import");
  const connections = useAPI<Page<RecordRow>>(
    "accounting/connections",
    canManage,
  );
  const imports = useAPI<Page<RecordRow>>(
    "accounting/imports?" +
      qs({
        client_id: scope.client,
        entity_id: scope.entity,
        period_id: scope.period,
        offset,
        limit: 50,
        sort: "-created_at",
      }),
  );
  return (
    <>
      <PageHeader
        eyebrow="Data connections"
        title="Accounting Integration Center"
        description="Connect accounting sources, validate imports and preserve financial lineage."
        actions={
          <>
            {canManage && (
              <Button onClick={() => setConnect(true)}>
                <Plus size={14} /> New connection
              </Button>
            )}
            {canImport && (
              <Button primary onClick={() => setUpload(true)}>
                <CloudUpload size={15} /> Import data
              </Button>
            )}
          </>
        }
      />
      <div className="page-body integration-page">
        <Tabs
          items={["All connectors", "Accounting", "File import"]}
          value={tab}
          onChange={setTab}
        />
        <ErrorState error={connections.error || catalogue.error} />
        <div className="connector-grid">
          {(catalogue.data?.items || [])
            .filter((p) =>
              tab === "File import"
                ? p.id === "file"
                : tab === "Accounting"
                  ? p.id !== "file"
                  : true,
            )
            .map(({ name, id: provider, status: qualification }, i) => {
              const connection = connections.data?.items.find(
                (c) =>
                  c.provider === provider &&
                  (!scope.entity || c.entity_id === scope.entity),
              );
              return (
                <section className="card connector" key={name}>
                  <div className="connector-title">
                    <span className={"provider-logo p" + i}>
                      {name === "Zoho Books"
                        ? "Z"
                        : name === "TallyPrime"
                          ? "▦"
                          : name === "Excel / CSV"
                            ? "X"
                            : name === "QuickBooks"
                              ? "qb"
                              : name
                                  .split(/\s+/)
                                  .map((word) => word[0])
                                  .join("")
                                  .slice(0, 2)}
                    </span>
                    <strong>{name}</strong>
                  </div>
                  <Status
                    value={
                      name === "Excel / CSV"
                        ? "File import available"
                        : connection?.status || qualification
                    }
                  />
                  <small>
                    {name === "TallyPrime"
                      ? "Local agent connectivity: not probed"
                      : name === "Zoho Books"
                        ? "Account transactions + source evidence"
                        : name === "Excel / CSV"
                          ? "CSV · XLSX · Tally export"
                          : ["busy", "marg"].includes(provider)
                            ? "Direct partner API + report import"
                            : "Direct vendor API + report import"}
                  </small>
                  {name === "Excel / CSV" ? (
                    <Button
                      disabled={!canImport}
                      onClick={() => setUpload(true)}
                    >
                      Upload file
                    </Button>
                  ) : (
                    <Button
                      disabled={!canManage}
                      onClick={() => {
                        if (connection) setSelected(connection);
                        else {
                          setConnectionProvider(provider);
                          setConnect(true);
                        }
                      }}
                    >
                      {connection ? "Connection details" : "Configure"}
                    </Button>
                  )}
                  <Button
                    disabled={!canImport}
                    onClick={() => {
                      setUploadProvider(provider);
                      setPackageUpload(true);
                    }}
                  >
                    Import complete report set
                  </Button>
                </section>
              );
            })}
        </div>
        <section className="card pipeline-card">
          <h3>Data Import & Validation Pipeline</h3>
          <div className="pipeline">
            {[
              "Source file",
              "Column mapping",
              "Validation",
              "Explicit activation",
              "Financial population",
            ].map((stage, i) => (
              <div key={stage}>
                <span className="pipeline-icon">{i + 1}</span>
                <strong>{stage}</strong>
                <small>
                  {
                    [
                      "Original preserved",
                      "Operator-selected",
                      "Backend checks",
                      "Review required",
                      "Available after commit",
                    ][i]
                  }
                </small>
                {i < 4 && <ArrowRight size={17} />}
              </div>
            ))}
          </div>
          <small className="subtle">
            Pipeline stages describe the workflow. Completion comes from each
            import record.
          </small>
        </section>
        <div className="section-heading">
          <h3>Recent Import Activity</h3>
          <span className="subtle">Authorized records • selected context</span>
        </div>
        <FinancialDataGrid
          name="imports"
          rows={imports.data?.items || []}
          loading={imports.isLoading}
          error={imports.error}
          onSelect={setSelected}
          columns={[
            column("source_system", "Source", 110),
            column("kind", "Population", 110),
            column("id", "Import batch", 250),
            column("row_count", "Source rows", 120),
            column("valid_count", "Valid rows", 120),
            column("status", "Status", 150, {
              cellRenderer: (p: { value: string }) => (
                <Status value={p.value} />
              ),
            }),
            column("created_at", "Started", 190),
          ]}
        />
        <Pagination
          offset={offset}
          total={imports.data?.total || 0}
          limit={50}
          onChange={setOffset}
        />
      </div>
      <Modal
        title="Import financial data"
        open={upload}
        onOpenChange={setUpload}
        wide
      >
        <ContextGate>
          <ImportWizard
            key={uploadProvider}
            provider={uploadProvider}
            onDone={() => setUpload(false)}
          />
        </ContextGate>
      </Modal>
      <Modal
        title="Configure accounting connection"
        open={connect}
        onOpenChange={setConnect}
      >
        <ContextGate>
          <ConnectionForm
            key={connectionProvider}
            initialProvider={connectionProvider}
            onDone={() => setConnect(false)}
          />
        </ContextGate>
      </Modal>
      <Modal
        title="Import accounting report set"
        open={packageUpload}
        onOpenChange={setPackageUpload}
      >
        <ContextGate>
          <ReportPackageWizard
            key={uploadProvider}
            provider={uploadProvider}
            renderBatch={(id) => <ImportDetail key={id} batchId={id} />}
          />
        </ContextGate>
      </Modal>
      <Drawer
        title={selected?.provider ? "Accounting connection" : "Import details"}
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
      >
        {selected &&
          (selected.provider ? (
            <ConnectionDetail key={selected.id} connection={selected} />
          ) : (
            <ImportDetail key={selected.id} batchId={selected.id} />
          ))}
      </Drawer>
    </>
  );
}
function ImportWizard({
  onDone,
  provider,
}: {
  onDone: () => void;
  provider: string;
}) {
  const catalogue = useAPI<{ items: { id: string; name: string }[] }>(
    "connectors/catalogue",
  );
  const [sourceSystem, setSourceSystem] = useState(provider);
  const [company, setCompany] = useState("");
  const [previewedFile, setPreviewedFile] = useState<File | null>(null);
  const currency = useCurrency();
  const scope = useScope();
  const inspect = useAction<Preview>();
  const action = useAction<RecordRow>();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null),
    [sheet, setSheet] = useState(""),
    [kind, setKind] = useState("gl"),
    [mapping, setMapping] = useState<Record<string, string>>({}),
    [batch, setBatch] = useState(""),
    [job, setJob] = useState(""),
    [error, setError] = useState(""),
    [supersedes, setSupersedes] = useState(""),
    [delimiter, setDelimiter] = useState(","),
    [encoding, setEncoding] = useState("utf-8-sig");
  const nativeTally =
    sourceSystem === "tally" && !!file && /\.(xml|json)$/i.test(file.name);
  const pop = usePopulation();
  const preview = (selected: File, sheetName = "") => {
    setPreviewedFile(null);
    const data = new FormData();
    data.append("file", selected);
    if (sheetName) data.append("sheet", sheetName);
    data.append("delimiter", delimiter);
    data.append("encoding", encoding);
    inspect.mutate(
      { path: "workspace/inspect-file", body: data },
      {
        onSuccess: (p) => {
          setPreviewedFile(selected);
          setSheet(p.selected_sheet || "");
          const initial: Record<string, string> = {};
          for (const h of p.headers) {
            const key = h.toLowerCase().trim().replaceAll(" ", "_");
            if (
              [
                "account_code",
                "account_name",
                "journal_ref",
                "posting_date",
                "debit",
                "credit",
                "description",
                "source_id",
                "opening_balance",
                "closing_balance",
              ].includes(key)
            )
              initial[key] = h;
          }
          setMapping(initial);
        },
      },
    );
  };
  function choose(selected?: File) {
    if (!selected) return;
    if (
      !(
        sourceSystem === "tally" ? /\.(csv|xlsx|xml|json)$/i : /\.(csv|xlsx)$/i
      ).test(selected.name) ||
      selected.size > 64 * 1024 * 1024
    ) {
      setError("Choose a supported accounting file up to 64 MiB.");
      return;
    }
    setError("");
    setFile(selected);
    if (!/\.(xml|json)$/i.test(selected.name)) preview(selected);
  }
  return (
    <div className="import-wizard">
      <div className="step-track">
        <Badge tone="blue">1 Source & mapping</Badge>
        <ArrowRight size={14} />
        <Badge>2 Preview & validate</Badge>
        <ArrowRight size={14} />
        <Badge>3 Review & activate</Badge>
      </div>
      {!batch ? (
        <>
          <div
            className="drop-zone"
            role="button"
            tabIndex={0}
            aria-label="Choose import file"
            onClick={() => input.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") input.current?.click();
            }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              choose(e.dataTransfer.files[0]);
            }}
          >
            <CloudUpload size={28} />
            <strong>{file?.name || "Drop your financial file here"}</strong>
            <small>
              CSV or XLSX · Tally also accepts XML/JSON · Maximum 64 MiB
            </small>
            <input
              ref={input}
              type="file"
              hidden
              accept={
                sourceSystem === "tally"
                  ? ".csv,.xlsx,.xml,.json"
                  : ".csv,.xlsx"
              }
              onChange={(e) => choose(e.target.files?.[0])}
            />
          </div>
          <div className="form-grid">
            <label>
              Source system
              <select
                value={sourceSystem}
                onChange={(e) => {
                  setSourceSystem(e.target.value);
                  setFile(null);
                }}
              >
                {catalogue.data?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            {sourceSystem === "tally" && (
              <label>
                Tally company name
                <input
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                />
              </label>
            )}
            <label>
              Population type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="gl">General ledger</option>
                <option value="journals">Journal entries</option>
                <option value="tb">Trial balance</option>
                <option value="coa">Chart of accounts</option>
              </select>
            </label>
            <label>
              Delimiter
              <select
                value={delimiter}
                onChange={(e) => setDelimiter(e.target.value)}
              >
                <option value=",">Comma</option>
                <option value=";">Semicolon</option>
                <option value={"\t"}>Tab</option>
              </select>
            </label>
            <label>
              Encoding
              <select
                value={encoding}
                onChange={(e) => setEncoding(e.target.value)}
              >
                {["utf-8-sig", "cp1252", "utf-16"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            {inspect.data?.sheets.length ? (
              <label>
                Worksheet
                <select
                  aria-label="Worksheet"
                  value={sheet}
                  onChange={(e) => {
                    setSheet(e.target.value);
                    if (file) preview(file, e.target.value);
                  }}
                >
                  {inspect.data.sheets.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label>
              Supersedes existing batch
              <select
                value={supersedes}
                onChange={(e) => setSupersedes(e.target.value)}
              >
                <option value="">New population</option>
                {pop.committed
                  .filter((b) => b.status === "active")
                  .map((b) => (
                    <option key={b.id} value={b.id}>
                      {String(b.kind)} · {b.id.slice(0, 8)}
                    </option>
                  ))}
              </select>
            </label>
            <Button
              disabled={!file || nativeTally || inspect.isPending}
              onClick={() => file && preview(file, sheet)}
            >
              Refresh preview
            </Button>
          </div>
          <ErrorState error={inspect.error} />
          {!nativeTally && file === previewedFile && inspect.data && (
            <>
              <h3>Column mapping</h3>
              <div className="mapping-fields">
                {[
                  "account_code",
                  "account_name",
                  "journal_ref",
                  "posting_date",
                  "debit",
                  "credit",
                  "description",
                  "source_id",
                  "opening_balance",
                  "closing_balance",
                ].map((key) => (
                  <label key={key}>
                    {key.replaceAll("_", " ")}
                    <select
                      aria-label={"Map " + key}
                      value={mapping[key] || ""}
                      onChange={(e) =>
                        setMapping((s) => ({ ...s, [key]: e.target.value }))
                      }
                    >
                      <option value="">Automatic / not supplied</option>
                      {inspect.data.headers.map((h) => (
                        <option key={h}>{h}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <h3>Source preview · first 20 rows</h3>
              <div className="source-preview">
                <table>
                  <thead>
                    <tr>
                      {inspect.data.headers.map((h, i) => (
                        <th key={i}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {inspect.data.rows.map((r, i) => (
                      <tr key={i}>
                        {r.map((v, j) => (
                          <td key={j}>{v}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="subtle">
                Dates: YYYY-MM-DD. Independent completeness controls are not
                asserted by this upload.
              </p>
            </>
          )}
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          <ErrorState error={action.error} />
          <Button
            primary
            disabled={
              !file ||
              (nativeTally
                ? !company
                : !inspect.data ||
                  file !== previewedFile ||
                  inspect.isPending) ||
              action.isPending
            }
            onClick={() => {
              if (!file) return;
              const data = new FormData();
              data.append("file", file);
              data.append(
                "options",
                JSON.stringify({
                  client_id: scope.client,
                  entity_id: scope.entity,
                  period_id: scope.period,
                  kind,
                  source_system: sourceSystem,
                  tally_company: nativeTally ? company : null,
                  currency,
                  sheet: sheet || null,
                  delimiter,
                  encoding,
                  mapping: nativeTally
                    ? {}
                    : Object.fromEntries(
                        Object.entries(mapping).filter(([, v]) => v),
                      ),
                  supersedes_id: supersedes || null,
                }),
              );
              action.mutate(
                { path: "accounting/imports", body: data },
                { onSuccess: (r) => setBatch(r.id) },
              );
            }}
          >
            Upload preserved source
          </Button>
        </>
      ) : (
        <>
          <ImportDetail batchId={batch} onJob={setJob} />
          {job && <JobProgress id={job} />}
          <Button onClick={onDone}>Return to integration center</Button>
        </>
      )}
    </div>
  );
}
function ImportDetail({
  batchId,
  onJob,
}: {
  batchId: string;
  onJob?: (id: string) => void;
}) {
  const q = useAPI<RecordRow>("accounting/imports/" + batchId, true, true);
  const preview = useAPI<{
    rows: { row_number: number; values: Record<string, string> }[];
  }>("accounting/imports/" + batchId + "/preview");
  const validations = useAPI<Page<RecordRow>>(
    "accounting/imports/" + batchId + "/validations?limit=100",
    true,
    true,
  );
  const action = useAction<RecordRow>();
  const [job, setJob] = useState(""),
    [confirm, setConfirm] = useState(false);
  const can = useCan("accounting.import");
  return (
    <>
      <QueryState query={q}>
        {q.data && (
          <>
            <Facts
              data={{
                batch_id: q.data.id,
                status: q.data.status,
                source_system: q.data.source_system,
                row_count: q.data.row_count,
                valid_count: q.data.valid_count,
                snapshot_id: q.data.snapshot_id,
              }}
            />
            <div className="actions">
              {q.data.status === "uploaded" && (
                <Button
                  primary
                  disabled={!can || action.isPending}
                  onClick={() =>
                    action.mutate(
                      {
                        path: `accounting/imports/${batchId}/validate?background=true`,
                      },
                      {
                        onSuccess: (r) => {
                          setJob(r.id);
                          onJob?.(r.id);
                        },
                      },
                    )
                  }
                >
                  Validate in background
                </Button>
              )}
              {q.data.status === "validated" && (
                <Button
                  primary
                  disabled={!can || action.isPending}
                  onClick={() => setConfirm(true)}
                >
                  <Check size={14} /> Review activation
                </Button>
              )}
              <Button
                disabled={!validations.data?.items.length}
                onClick={() =>
                  downloadCSV(
                    "import-validations-first-100.csv",
                    validations.data?.items || [],
                  )
                }
              >
                <Download size={14} /> Error / check report
              </Button>
            </div>
            <ErrorState error={action.error} />
            {job && (
              <JobProgress
                id={job}
                onDone={() => {
                  q.refetch();
                  validations.refetch();
                }}
              />
            )}
            <h3>Validation results · first 100</h3>
            <QueryState query={validations}>
              {validations.data?.items.map((v) => (
                <section className="check-row" key={v.id}>
                  <strong>{textValue(v.rule)}</strong>
                  <Status value={v.status} />
                  <div className="validation-message">
                    {v.row_number ? `Row ${textValue(v.row_number)}: ` : ""}
                    {textValue(v.message)}
                  </div>
                  <details>
                    <summary>Evidence</summary>
                    <Facts
                      data={(v.evidence || {}) as Record<string, unknown>}
                    />
                  </details>
                </section>
              ))}
            </QueryState>
            <details>
              <summary>Source preview</summary>
              <ErrorState error={preview.error} />
              {preview.data?.rows.map((r) => (
                <Facts key={r.row_number} data={r.values} />
              ))}
            </details>
          </>
        )}
      </QueryState>
      <Modal
        title="Activate financial population?"
        open={confirm}
        onOpenChange={setConfirm}
      >
        <p>
          Activation makes validated financial rows available to workbenches.
          Any explicitly superseded population remains preserved in source
          history.
        </p>
        <Button
          primary
          disabled={action.isPending}
          onClick={() =>
            action.mutate(
              { path: `accounting/imports/${batchId}/commit` },
              { onSuccess: () => setConfirm(false) },
            )
          }
        >
          Confirm activation
        </Button>
        <ErrorState error={action.error} />
      </Modal>
    </>
  );
}
function ConnectionForm({
  onDone,
  initialProvider,
}: {
  onDone: () => void;
  initialProvider: string;
}) {
  const scope = useScope();
  const catalogue = useAPI<{ items: { id: string; name: string }[] }>(
    "connectors/catalogue",
  );
  const [provider, setProvider] = useState(initialProvider),
    [name, setName] = useState(""),
    [clientId, setClientId] = useState(""),
    [secret, setSecret] = useState(""),
    [region, setRegion] = useState("ae");
  const action = useAction();
  return (
    <form
      className="resource-form"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate(
          {
            path: "accounting/connections",
            body: {
              client_id: scope.client,
              entity_id: scope.entity,
              period_id: scope.period,
              provider,
              name,
              region,
              credentials:
                provider === "zoho"
                  ? { client_id: clientId, client_secret: secret }
                  : {},
            },
          },
          {
            onSuccess: () => {
              setSecret("");
              onDone();
            },
          },
        );
      }}
    >
      <label>
        Provider
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {catalogue.data?.items
            .filter((p) => p.id !== "file")
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Connection name
        <input
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      {provider === "zoho" && (
        <>
          <label>
            Zoho region
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {[
                "ae",
                "com",
                "eu",
                "in",
                "com.au",
                "jp",
                "ca",
                "com.cn",
                "sa",
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            OAuth client ID
            <input
              autoComplete="off"
              required
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
            />
          </label>
          <label>
            OAuth client secret
            <input
              type="password"
              autoComplete="new-password"
              required
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </label>
          <small className="subtle">
            Stored encrypted by the backend. A configured redirect URI and
            server encryption key are required.
          </small>
        </>
      )}
      <ErrorState error={action.error} />
      <Button primary disabled={action.isPending}>
        Create connection
      </Button>
    </form>
  );
}
function ConnectionDetail({ connection: initial }: { connection: RecordRow }) {
  const current = useAPI<Page<RecordRow>>("accounting/connections");
  const connection =
    current.data?.items.find((c) => c.id === initial.id) || initial;
  const action = useAction<RecordRow>();
  const [redirect, setRedirect] = useState(
      typeof window !== "undefined"
        ? window.location.origin + "/integrations/zoho/callback"
        : "",
    ),
    [organization, setOrganization] = useState(""),
    [job, setJob] = useState(""),
    [code, setCode] = useState(""),
    [state, setState] = useState("");
  const orgs = useAPI<{ organizations: RecordRow[] }>(
    `connectors/zoho/${connection.id}/organizations`,
    connection.provider === "zoho" && connection.status === "authorized",
  );
  return (
    <>
      <Facts
        data={{
          name: connection.name,
          provider: connection.provider,
          status: connection.status,
          region: connection.region,
          organization_id: connection.organization_id,
        }}
      />
      {connection.provider === "tally" ? (
        <>
          <Badge tone="warning">Agent connectivity not probed</Badge>
          <p>
            Use the authorized Windows agent in{" "}
            <code>agents/tally_agent.py</code> with HTTPS AuditOS URL and local
            Tally XML export. Credentials belong in the Windows credential
            vault.
          </p>
          <p>
            Export CSV/XLSX reports for the file import workflow, or use the
            agent resumable package upload. Server registration alone does not
            establish a live connection.
          </p>
        </>
      ) : connection.provider !== "zoho" ? (
        <NativeConnection key={connection.id} connection={connection} />
      ) : (
        <>
          <label>
            Configured OAuth redirect URI
            <input
              value={redirect}
              onChange={(e) => setRedirect(e.target.value)}
            />
          </label>
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(
                {
                  path: `connectors/zoho/${connection.id}/authorize`,
                  body: { redirect_uri: redirect },
                },
                {
                  onSuccess: (r) => {
                    const url = new URL(String(r.authorization_url));
                    if (
                      url.protocol === "https:" &&
                      /^accounts\.zoho(cloud)?\./.test(url.hostname)
                    ) {
                      sessionStorage.setItem(
                        "auditos-zoho-connection",
                        connection.id,
                      );
                      window.location.assign(url.href);
                    }
                  },
                },
              )
            }
          >
            Authorize with Zoho
          </Button>
          <details>
            <summary>Complete authorized callback</summary>
            <p>
              The OAuth callback returns a code and state. Submit them only for
              this connection.
            </p>
            <label>
              Code
              <input value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <label>
              State
              <input value={state} onChange={(e) => setState(e.target.value)} />
            </label>
            <Button
              disabled={!code || !state || action.isPending}
              onClick={() =>
                action.mutate(
                  {
                    path: `connectors/zoho/${connection.id}/callback`,
                    body: { code, state },
                  },
                  {
                    onSuccess: () => {
                      setCode("");
                      setState("");
                    },
                  },
                )
              }
            >
              Complete authorization
            </Button>
          </details>
          <label>
            Organization
            <select
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
            >
              <option value="">Select accessible organization</option>
              {orgs.data?.organizations.map((o) => (
                <option
                  key={String(o.organization_id)}
                  value={String(o.organization_id)}
                >
                  {textValue(o.name)}
                </option>
              ))}
            </select>
          </label>
          <Button
            disabled={!organization || action.isPending}
            onClick={() =>
              action.mutate({
                path: `connectors/zoho/${connection.id}/organization`,
                body: { organization_id: organization },
              })
            }
          >
            Choose organization
          </Button>
          <Button
            primary
            disabled={action.isPending || !connection.organization_id}
            onClick={() =>
              action.mutate(
                { path: `connectors/zoho/${connection.id}/sync` },
                { onSuccess: (r) => setJob(r.id) },
              )
            }
          >
            <RefreshCw size={14} /> Start supported sync
          </Button>
          <p className="subtle">
            Extracts all supported account transaction types and preserves
            source evidence. Review the resulting GL and chart batches, and
            reconcile to an independent period trial balance. Live qualification
            and incremental sync remain pending.
          </p>
        </>
      )}
      <ErrorState error={action.error} />
      {action.data && (
        <Status value={action.data.status || "Request accepted"} />
      )}{" "}
      {job && <JobProgress id={job} />}
    </>
  );
}
export function ZohoCallback() {
  const params = useSearchParams();
  const native = params.get("native") === "1";
  const storageKey = native
    ? "auditos-native-connection"
    : "auditos-zoho-connection";
  const action = useAction<RecordRow>();
  const [connectionId, setConnectionId] = useState("");
  return (
    <>
      <PageHeader
        eyebrow="Integrations"
        title="Accounting authorization callback"
        description="Exchange the authorization code through the secure backend connector."
      />
      <div className="page-body">
        <Facts
          data={{
            code: params.get("code")
              ? "Received — copy from address bar"
              : "Missing",
            state: params.get("state")
              ? "Received — copy from address bar"
              : "Missing",
          }}
        />
        <label>
          Connection identifier
          <input
            value={connectionId}
            onChange={(e) => setConnectionId(e.target.value)}
            placeholder="Use original connection or enter its ID"
          />
        </label>
        <Button
          onClick={() =>
            setConnectionId(sessionStorage.getItem(storageKey) || "")
          }
        >
          Use original connection
        </Button>
        <Button
          primary
          disabled={
            !connectionId ||
            !params.get("code") ||
            !params.get("state") ||
            action.isPending ||
            action.isSuccess
          }
          onClick={() =>
            action.mutate(
              {
                path: `connectors/${native ? "native" : "zoho"}/${connectionId}/callback`,
                body: {
                  code: params.get("code"),
                  state: params.get("state"),
                  ...(native
                    ? { realm_id: params.get("realmId") || null }
                    : {}),
                },
              },
              {
                onSuccess: () => {
                  sessionStorage.removeItem(storageKey);
                  window.history.replaceState(
                    null,
                    "",
                    native
                      ? "/integrations/zoho/callback?native=1"
                      : "/integrations/zoho/callback",
                  );
                },
              },
            )
          }
        >
          Complete secure authorization
        </Button>
        <ErrorState error={action.error} />
        {action.data && <Status value={action.data.status} />}
        <p>
          OAuth state and redirect URI are verified by the backend. Return to
          Integrations to select an organization.
        </p>
      </div>
    </>
  );
}
