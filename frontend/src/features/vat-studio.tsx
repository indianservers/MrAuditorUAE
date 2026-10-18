"use client";
import { useState } from "react";
import Link from "next/link";
import { AuditStudio } from "./audit-studio";
import { TaxSuggestion } from "./tax-studio";
import { PageHeader } from "./shared";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import {
  Button,
  Empty,
  ErrorState,
  Facts,
  Status,
} from "@/components/ui/primitives";
import {
  FinancialDataGrid,
  column,
  amount,
} from "@/components/grids/financial-data-grid";
import type { Page, Engagement, RecordRow } from "@/types/models";

export const vatAreas = [
  ["dashboard", "VAT Executive Dashboard", "profile"],
  ["profiles", "VAT Taxpayer Profiles", "profile"],
  ["sales", "Sales & Output VAT Studio", "invoice"],
  ["purchases", "Purchases & Input VAT Studio", "invoice"],
  ["transactions", "VAT Transaction Explorer", "invoice"],
  ["reconciliation", "VAT Reconciliation Workbench", "invoice"],
  ["returns", "VAT Return Preparation", "return"],
  ["invoices", "Tax Invoice Validator", "invoice"],
  ["imports", "Reverse Charge & Imports Studio", "invoice"],
  ["exceptions", "VAT Exceptions & Findings", "adjustment"],
  ["einvoicing", "E-Invoicing Readiness Dashboard", "einvoicing"],
  ["asp", "E-Invoice Validation & ASP Center", "invoice"],
  ["ai", "AI VAT Copilot", "invoice"],
  ["rules", "VAT Technical Rules Administration", "rule"],
] as const;
type Run = RecordRow & {
  results: Record<string, unknown>;
  dependencies_current: boolean;
  rows_total: number;
  kind: string;
};

export function VATStudio({
  id,
  area = "dashboard",
}: {
  id?: string;
  area?: string;
}) {
  const directory = useAPI<Page<Engagement>>("engagements?limit=100", !id);
  const entry = vatAreas.find((x) => x[0] === area);
  if (!id)
    return (
      <>
        <PageHeader
          eyebrow="UAE VAT / e-invoicing"
          title="VAT & E-Invoicing"
          description="Reconcile source transactions, prepare VAT201 and assess structured e-invoice readiness."
        />
        <section className="workbench-body">
          {directory.error && <ErrorState error={directory.error} />}{" "}
          {directory.data?.items.map((e) => (
            <p key={e.id}>
              <Link href={`/vat/${e.id}/dashboard`}>{e.name}</Link>{" "}
              <Status value={e.status} />
            </p>
          ))}
        </section>
      </>
    );
  if (!entry)
    return <Empty title="Unknown VAT workspace">Select a VAT workspace.</Empty>;
  return (
    <>
      <PageHeader
        eyebrow="UAE VAT / source-linked compliance"
        title={entry[1]}
        description="Reviewed tax points and legal rules · Exact ledger reconciliation · Independent approval"
      />
      <nav className="audit-tabs" aria-label="VAT workspaces">
        {vatAreas.map(([key, title]) => (
          <Link
            key={key}
            href={`/vat/${id}/${key}`}
            aria-current={area === key ? "page" : undefined}
          >
            {title}
          </Link>
        ))}
      </nav>
      <VATWorkspace key={area} id={id} area={area} initialKind={entry[2]} />
    </>
  );
}

function VATWorkspace({
  id,
  area,
  initialKind,
}: {
  id: string;
  area: string;
  initialKind: string;
}) {
  const base = `vat/engagements/${id}`;
  const workspace = useAPI<{
    permissions: string[];
    ai_tasks: string[];
    engagement: Engagement;
  }>(base + "/workspace");
  const demo = useAPI<{ items: RecordRow[] }>("vat/demo-status");
  const profiles = useAPI<Page<RecordRow>>(base + "/records/profile");
  const rules = useAPI<Page<RecordRow>>(base + "/records/rule");
  const sources = useAPI<{ items: RecordRow[] }>(
    "vat/legislation",
    area === "rules",
  );
  const [profile, setProfile] = useState("");
  const [kind, setKind] = useState(initialKind);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const invoices = useAPI<Page<RecordRow>>(
    `${base}/records/invoice?offset=${offset}&limit=50&search=${encodeURIComponent(search)}${area === "sales" ? "&direction=sale" : area === "purchases" ? "&direction=purchase" : ""}`,
  );
  const assessments = useAPI<Page<RecordRow>>(base + "/records/" + kind);
  const runs = useAPI<Page<RecordRow>>(base + "/runs");
  const [rid, setRid] = useState("");
  const [rowOffset, setRowOffset] = useState(0);
  const result = useAPI<Run>(
    `${base}/runs/${rid}?offset=${rowOffset}&limit=50`,
    !!rid,
  );
  const [comparison, setComparison] = useState("");
  const prior = useAPI<Run>(`${base}/runs/${comparison}`, !!comparison);
  const action = useAction<RecordRow>();
  const validation = useAction<RecordRow>();
  const [error, setError] = useState("");
  const [documentId, setDocumentId] = useState("");
  const { tenant } = useScope();
  const permissions = workspace.data?.permissions || [];
  const can = (permission: string) => permissions.includes(permission);
  async function calculate(path: string) {
    try {
      const run = await action.mutateAsync({ path });
      setRid(run.id);
      setRowOffset(0);
    } catch {}
  }
  async function download() {
    try {
      const r = await fetch(`/api/backend/${base}/runs/${rid}/export/json`, {
        headers: { "X-Tenant-ID": tenant },
      });
      if (!r.ok) throw new Error(`Export rejected (${r.status})`);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `AuditOS-VAT-${rid}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    }
  }
  const rows: RecordRow[] =
    invoices.data?.items.map((row) => ({
      id: row.id,
      status: row.status,
      ...(row.body as Record<string, unknown>),
    })) || [];
  const data = result.data?.results;
  const selectedInvoice = selected?.id
    ? invoices.data?.items.find((x) => x.id === selected.id)
    : undefined;
  const [assessment, setAssessment] = useState("");
  return (
    <>
      <section className="workbench-body vat-workspace">
        {demo.data?.items.length ? (
          <div className="source-strip">
            <strong>SYNTHETIC DEMO · Nonproduction data</strong>
            <span>
              Versioned fixtures in an isolated tenant. No real TRNs or client
              documents.
            </span>
          </div>
        ) : null}
        {workspace.error && <ErrorState error={workspace.error} />}
        <div className="toolbar">
          <label>
            VAT profile
            <select
              aria-label="VAT profile"
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
            >
              <option value="">Choose approved profile</option>
              {profiles.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {String(p.reference)} · {String(p.status)}
                </option>
              ))}
            </select>
          </label>
          <Button
            disabled={!profile || !can("vat.calculate") || action.isPending}
            onClick={() => calculate(`${base}/computations/${profile}`)}
          >
            Prepare VAT reconciliation
          </Button>
          <label>
            VAT run
            <select
              aria-label="VAT run"
              value={rid}
              onChange={(e) => setRid(e.target.value)}
            >
              <option value="">Choose immutable run</option>
              {runs.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {String(r.kind)} · {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Compare period
            <select
              value={comparison}
              onChange={(e) => setComparison(e.target.value)}
            >
              <option value="">No comparison</option>
              {runs.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {action.error && <ErrorState error={action.error} />}{" "}
        {error && <ErrorState error={new Error(error)} />}
        {data ? (
          <>
            <div className="toolbar">
              <strong>
                {String(data.period_start || "")} –{" "}
                {String(data.period_end || "")}
              </strong>
              <Status
                value={result.data?.dependencies_current ? "CURRENT" : "STALE"}
              />
              <Button disabled={!can("vat.export")} onClick={download}>
                Export VAT JSON
              </Button>
              <span>
                Mapping:{" "}
                {String(data.mapping_version || "Specialist assessment")}
              </span>
            </div>
            {Array.isArray(data.boxes) ? (
              <>
                <h2>VAT201 preparation</h2>
                <div className="vat-grid">
                  <FinancialDataGrid
                    name="vat201-boxes"
                    rows={(data.boxes as RecordRow[]).map((x) => ({
                      ...x,
                      previous: (
                        prior.data?.results.boxes as RecordRow[] | undefined
                      )?.find((y) => y.box === x.box)?.vat,
                    }))}
                    columns={[
                      column("box", "Box", 95),
                      column("label", "Official return mapping", 330),
                      amount("net", "Taxable value", "AED"),
                      amount("vat", "VAT", "AED"),
                      amount("previous", "Compared period", "AED"),
                    ]}
                    onSelect={setSelected}
                  />
                </div>
              </>
            ) : (
              <Facts data={data as RecordRow} />
            )}
            <div className="tax-computation-layout">
              <article>
                <h2>Invoice to ledger reconciliation</h2>
                <FinancialDataGrid
                  name="vat-reconciliation"
                  rows={(data.reconciliations || []) as RecordRow[]}
                  columns={[
                    column("reference", "Source invoice", 180),
                    amount("source_amount", "Source", "AED"),
                    amount("calculated_vat", "Calculated VAT", "AED"),
                    amount("ledger_output", "Ledger output", "AED"),
                    amount("ledger_input", "Ledger input", "AED"),
                    amount("difference", "Difference", "AED"),
                    column("exception_status", "Status", 190),
                  ]}
                  onSelect={setSelected}
                />
                <div className="toolbar">
                  <Button
                    disabled={rowOffset === 0}
                    onClick={() => setRowOffset((x) => Math.max(0, x - 50))}
                  >
                    Previous reconciliation rows
                  </Button>
                  <span>
                    {rowOffset + 1}–
                    {Math.min(rowOffset + 50, result.data?.rows_total || 0)} of{" "}
                    {result.data?.rows_total || 0}
                  </span>
                  <Button
                    disabled={rowOffset + 50 >= (result.data?.rows_total || 0)}
                    onClick={() => setRowOffset((x) => x + 50)}
                  >
                    Next reconciliation rows
                  </Button>
                </div>
              </article>
              <aside>
                <h3>Source, rule & review trace</h3>
                {selected ? (
                  <Facts data={selected} />
                ) : (
                  <p>Select a row to inspect its linked sources.</p>
                )}
                <details open>
                  <summary>Exceptions and controls</summary>
                  <Facts
                    data={{
                      exceptions: data.exceptions,
                      control_accounts: data.control_accounts,
                      validation: data.validation,
                      filing_due: data.filing_due,
                      scope: data.scope,
                    }}
                  />
                </details>
                <details>
                  <summary>Applied legal versions</summary>
                  <Facts data={(data.rules || {}) as RecordRow} />
                </details>
              </aside>
            </div>
          </>
        ) : (
          <Empty title="Prepare from approved invoice sources">
            Select a VAT profile and reconcile its reviewed invoices to the
            ledger. Missing facts and differences remain visible exceptions.
          </Empty>
        )}
        {!["rules", "profiles", "returns", "einvoicing"].includes(area) && (
          <>
            <h2>Source invoices</h2>
            <div className="toolbar">
              <label>
                Search invoices
                <input
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setOffset(0);
                  }}
                />
              </label>
              <Button
                disabled={!selectedInvoice || validation.isPending}
                onClick={() =>
                  validation.mutate({
                    path: `${base}/invoices/${selectedInvoice?.id}/validate`,
                  })
                }
              >
                Validate selected invoice
              </Button>
            </div>
            <div className="vat-grid">
              <FinancialDataGrid
                name="vat-invoices"
                rows={rows
                  .filter((row) => area !== "sales" || row.direction === "sale")
                  .filter(
                    (row) =>
                      area !== "purchases" || row.direction === "purchase",
                  )}
                columns={[
                  column("invoice_number", "Invoice", 180),
                  column("direction", "Direction"),
                  column("treatment", "Tax treatment", 160),
                  amount("declared_net", "Net", "AED"),
                  amount("declared_tax", "Tax", "AED"),
                  amount("declared_gross", "Gross", "AED"),
                  column("status", "Review status", 180),
                ]}
                onSelect={setSelected}
              />
            </div>
            <div className="toolbar">
              <Button
                disabled={offset === 0}
                onClick={() => setOffset((x) => Math.max(0, x - 50))}
              >
                Previous invoices
              </Button>
              <span>
                {offset + 1}–{Math.min(offset + 50, invoices.data?.total || 0)}{" "}
                of {invoices.data?.total || 0}
              </span>
              <Button
                disabled={offset + 50 >= (invoices.data?.total || 0)}
                onClick={() => setOffset((x) => x + 50)}
              >
                Next invoices
              </Button>
            </div>
            {validation.error && <ErrorState error={validation.error} />}{" "}
            {validation.data && <Facts data={validation.data} />}
          </>
        )}
        {area === "rules" && (
          <>
            <h2>Official VAT & e-invoicing sources</h2>
            <div className="vat-grid">
              <FinancialDataGrid
                name="vat-rules"
                rows={sources.data?.items || []}
                columns={[
                  column("id", "Source", 160),
                  column("title", "Legislation", 450),
                  column("earliest", "Commencement / reference date", 200),
                  column("url", "Official publication", 450),
                ]}
              />
            </div>
            <details>
              <summary>Approved rule IDs for profile selection</summary>
              {rules.data?.items.map((r) => (
                <p key={r.id}>
                  {String(r.reference)} · {r.id} · {String(r.status)}
                </p>
              ))}
            </details>
          </>
        )}
        {["einvoicing", "purchases"].includes(area) && (
          <div className="toolbar">
            <label>
              Assessment type
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  setAssessment("");
                }}
              >
                {(area === "purchases"
                  ? ["invoice", "recovery"]
                  : ["einvoicing"]
                ).map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
            <label>
              Approved assessment
              <select
                aria-label="VAT assessment"
                value={assessment}
                onChange={(e) => setAssessment(e.target.value)}
              >
                <option value="">Choose assessment</option>
                {assessments.data?.items.map((r) => (
                  <option key={r.id} value={r.id}>
                    {String(r.reference)}
                  </option>
                ))}
              </select>
            </label>
            <Button
              disabled={
                !assessment || kind === "invoice" || !can("vat.calculate")
              }
              onClick={() => calculate(`${base}/assessments/${assessment}`)}
            >
              Calculate VAT assessment
            </Button>
          </div>
        )}
        {area === "asp" && (
          <ASPPanel
            base={base}
            invoice={selectedInvoice?.id || ""}
            enabled={can("einvoice.sandbox")}
          />
        )}
        {area === "ai" && (
          <VATAI
            base={base}
            profile={profile}
            source={selectedInvoice?.id || ""}
            tasks={workspace.data?.ai_tasks || []}
            enabled={can("vat.ai.execute")}
            canReview={can("vat.review")}
          />
        )}
      </section>
      {area !== "ai" && (
        <AuditStudio
          key={`${kind}:${profile}:${rid}`}
          id={id}
          area={`vat-${kind}`}
          ifrs
          defaults={{
            ...(profile && kind !== "profile" ? { profile_id: profile } : {}),
            ...(rid && kind === "return" ? { run_id: rid } : {}),
          }}
        />
      )}
      {area === "invoices" && (
        <section>
          <h2>Text PDF extraction</h2>
          <p>
            Requires linked, independently reviewed PDF evidence with a clean
            scan. Extracted fields remain unverified; scanned-image OCR is not
            configured.
          </p>
          <div className="toolbar">
            <label>
              Linked PDF evidence ID
              <input
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
              />
            </label>
            <Button
              disabled={
                !selectedInvoice ||
                !documentId ||
                !can("vat.invoice.prepare") ||
                validation.isPending
              }
              onClick={() =>
                validation.mutate({
                  path: `${base}/invoices/${selectedInvoice?.id}/extract/${documentId}`,
                })
              }
            >
              Extract text PDF
            </Button>
          </div>
        </section>
      )}
    </>
  );
}

function ASPPanel({
  base,
  invoice,
  enabled,
}: {
  base: string;
  invoice: string;
  enabled: boolean;
}) {
  const action = useAction<RecordRow>();
  const [buyer, setBuyer] = useState("");
  const [supplier, setSupplier] = useState("");
  const [simulate, setSimulate] = useState("accept");
  return (
    <section>
      <h2>Local ASP sandbox · no external transmission</h2>
      <p>
        Validates a documented semantic subset. Full PINT-AE XSD/Schematron
        validation and live ASP connectivity require an accredited provider
        specification.
      </p>
      <div className="toolbar">
        <label>
          Buyer endpoint ID
          <input value={buyer} onChange={(e) => setBuyer(e.target.value)} />
        </label>
        <label>
          Supplier endpoint ID
          <input
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
          />
        </label>
        <label>
          Sandbox outcome
          <select
            value={simulate}
            onChange={(e) => setSimulate(e.target.value)}
          >
            {["accept", "reject", "timeout"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <Button
          disabled={
            !enabled || !invoice || !buyer || !supplier || action.isPending
          }
          onClick={() =>
            action.mutate({
              path: base + "/sandbox",
              body: {
                invoice_id: invoice,
                idempotency_key: crypto.randomUUID(),
                buyer_endpoint_id: buyer,
                supplier_endpoint_id: supplier,
                schema_version: "auditos-pint-ae-subset/1.0",
                simulate,
              },
            })
          }
        >
          Run local ASP sandbox
        </Button>
      </div>
      {action.error && <ErrorState error={action.error} />}{" "}
      {action.data && <Facts data={action.data} />}
    </section>
  );
}

function VATAI({
  base,
  profile,
  source,
  tasks,
  enabled,
  canReview,
}: {
  base: string;
  profile: string;
  source: string;
  tasks: string[];
  enabled: boolean;
  canReview: boolean;
}) {
  const [task, setTask] = useState("transaction_classification");
  const [model, setModel] = useState("mock-diagnostic");
  const [reason, setReason] = useState("");
  const action = useAction<RecordRow>();
  const decision = useAction<RecordRow>();
  const suggestions = useAPI<Page<RecordRow>>(base + "/records/ai");
  return (
    <section>
      <h2>Source-grounded VAT assistance</h2>
      <p>
        Choose a source invoice above. Diagnostic mock tests transport and
        grounding; it performs no semantic legal research or visual OCR.
      </p>
      <div className="toolbar">
        <label>
          VAT AI task
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            {tasks.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Approved VAT model
          <input value={model} onChange={(e) => setModel(e.target.value)} />
        </label>
        <Button
          disabled={!enabled || !profile || !source || action.isPending}
          onClick={() =>
            action.mutate({
              path: base + "/ai",
              body: { profile_id: profile, source_id: source, task, model },
            })
          }
        >
          Request VAT analysis
        </Button>
      </div>
      {action.error && <ErrorState error={action.error} />}{" "}
      {action.data && <TaxSuggestion row={action.data} />}
      <label>
        VAT reviewer rationale
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {decision.error && <ErrorState error={decision.error} />}{" "}
      {suggestions.data?.items.map((row) => (
        <details key={row.id}>
          <summary>
            {String(row.title)} · {String(row.status)}
          </summary>
          <TaxSuggestion row={row} />
          {["UNDER_REVIEW", "ACCEPTED", "REJECTED"].map((value) => (
            <Button
              key={value}
              disabled={
                !canReview ||
                !reason ||
                !["SUGGESTED", "UNDER_REVIEW"].includes(String(row.status)) ||
                decision.isPending
              }
              onClick={() =>
                decision.mutate({
                  path: `${base}/ai/${row.id}/decision`,
                  body: {
                    version: row.version,
                    decision: value,
                    rationale: reason,
                  },
                })
              }
            >
              {value.replaceAll("_", " ")}
            </Button>
          ))}
        </details>
      ))}
    </section>
  );
}
