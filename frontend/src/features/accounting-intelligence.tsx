"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";
import { useScope } from "@/stores/workspace";
import {
  Badge,
  Button,
  Empty,
  ErrorState,
  Status,
} from "@/components/ui/primitives";
import { PageHeader, LineageDetail } from "./shared";
import { ReactFlow, Background, Controls, MiniMap } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Page, RecordRow } from "@/types/models";
import { CountryWorkflows } from "./country-workflows";
import { PDFGridEditor, buildPDFGrid, emptyPDFGrid } from "./pdf-grid-editor";

type Choice = { id: string; label: string; scan_status?: string };
type Result = {
  id: string;
  kind: string;
  version: number;
  sha256: string;
  freshness: string;
  provenance_status?: string;
  label: string;
  review_status: string;
  body: Record<string, unknown>;
  collection_totals?: Record<string, number>;
};
type Job = {
  id: string;
  operation: string;
  status: string;
  version: number;
  result_id?: string;
  attempts: number;
  error_details?: { message: string };
};
const areas = {
  "foundation-validation": "Foundation validation",
  ocr: "Document extraction",
  "source-table": "Supporting tables",
  mapping: "Mapping proposals",
  lead: "Lead schedules",
  ageing: "Open-item ageing",
  reconciliation: "Transaction reconciliation",
  vouching: "Sample vouching",
  flow: "Transaction investigation",
};
type Area = keyof typeof areas;
const val = (value: unknown): string =>
  value == null
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);

export function AccountingIntelligence({
  eid,
  area,
}: {
  eid?: string;
  area?: string;
}) {
  const engagements = useAPI<Page<RecordRow>>("engagements?limit=100");
  const selectedArea: Area = area && area in areas ? (area as Area) : "lead";
  if (!eid)
    return (
      <>
        <PageHeader
          eyebrow="Accounting intelligence"
          title="Connected audit execution"
          description="Select an engagement to work from committed accounting sources and retained evidence."
        />
        <ErrorState error={engagements.error} />
        <div className="toolbar">
          {engagements.data?.items.map((e) => (
            <Link
              className="button"
              key={e.id}
              href={`/intelligence/${e.id}/lead`}
            >
              {String(e.name || e.id)}
            </Link>
          ))}
        </div>
      </>
    );
  if (area === "workflow-source" || area === "country-workflow")
    return <CountryWorkflows key={`${eid}:${area}`} eid={eid} mode={area} />;
  return (
    <IntelligenceBody
      key={`${eid}:${selectedArea}`}
      eid={eid}
      area={selectedArea}
    />
  );
}

function IntelligenceBody({ eid, area }: { eid: string; area: Area }) {
  const prefix = `intelligence/engagements/${eid}`;
  const scope = useScope();
  const query = useSearchParams();
  const [selected, setSelected] = useState(query.get("event") || "");
  const [showAllJobs, setShowAllJobs] = useState(false);
  const [offset, setOffset] = useState(0);
  const [snapshot, setSnapshot] = useState("");
  const [evidence, setEvidence] = useState("");
  const [source, setSource] = useState("");
  const [assessments, setAssessments] = useState<string[]>([]);
  const [documentLinks, setDocumentLinks] = useState<Record<string, string>>(
    {},
  );
  const [sample, setSample] = useState("");
  const [accountIds, setAccounts] = useState<string[]>([]);
  const [extractions, setExtractions] = useState<string[]>([]);
  const [section, setSection] = useState("Cash & Bank");
  const [comments, setComments] = useState("");
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [tolerance, setTolerance] = useState("0");
  const [dateTolerance, setDateTolerance] = useState("0");
  const [asOf, setAsOf] = useState("");
  const [fallback, setFallback] = useState(false);
  const [dateFormat, setDateFormat] = useState("iso");
  const [decimalSeparator, setDecimalSeparator] = useState(".");
  const [zipMember, setZipMember] = useState("");
  const [tableKind, setTableKind] = useState("bank");
  const [worksheet, setWorksheet] = useState("");
  const [pdfMode, setPDFMode] = useState(false);
  const [pdfGrid, setPDFGrid] = useState(emptyPDFGrid);
  const [localError, setLocalError] = useState<Error | null>(null);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const inputs = useAPI<{
    snapshots: Choice[];
    evidence: Choice[];
    samples: Choice[];
  }>(`${prefix}/inputs`);
  const capabilities = useAPI<{ lead_sections: string[] }>(
    "intelligence/capabilities",
  );
  const records = useEventHistory<Result>(prefix);
  const jobs = useAPI<{ items: Job[] }>(`${prefix}/jobs`, true, true);
  const foundation = useAPI<{
    runtime: string;
    professional_correctness: string;
    period: { state: string; version: number };
    job_counts: Record<string, number>;
  }>(`${prefix}/foundation-status`, area === "foundation-validation", true);
  const journalLines = useAPI<{
    items: {
      id: string;
      description: string;
      posting_date: string;
      debit: string;
      credit: string;
    }[];
    total: number;
  }>(
    `accounting/ledger?snapshot_id=${snapshot}&limit=500`,
    area === "foundation-validation" && !!snapshot,
  );
  const detail = useAPI<Result>(
    `${prefix}/events/${selected}?offset=${offset}&limit=100`,
    !!selected,
  );
  const accounts = useAPI<{
    items: { id: string; code: string; name: string }[];
  }>(`${prefix}/accounts?snapshot_id=${snapshot}`, !!snapshot);
  const action = useAction<Result>();
  const body = detail.data?.body;
  const boxScope = body?.box_comparison_scope;
  const selectedVATScope =
    boxScope &&
    typeof boxScope === "object" &&
    "mode" in boxScope &&
    boxScope.mode === "SELECTED_REQUIRED_BOXES"
      ? (boxScope as Record<string, unknown>)
      : null;
  const choices = records.data?.items || [];
  const choose = (id: string) => {
    setSelected(id);
    setOffset(0);
    setCorrections({});
  };
  async function run() {
    setLocalError(null);
    let pdfLayout;
    if (area === "source-table" && pdfMode) {
      try {
        pdfLayout = buildPDFGrid(pdfGrid);
      } catch (error) {
        setLocalError(error as Error);
        return;
      }
    }
    const payload: Record<string, unknown> = {};
    if (
      [
        "lead",
        "mapping",
        "flow",
        "reconciliation",
        "foundation-validation",
      ].includes(area)
    )
      payload.snapshot_id = snapshot;
    if (area === "foundation-validation")
      Object.assign(payload, {
        extraction_ids: extractions,
        assessment_ids: assessments,
        rationale: comments,
        document_links: extractions
          .filter((id) => documentLinks[id])
          .map((id) => ({
            extraction_id: id,
            journal_line_id: documentLinks[id],
          })),
      });
    if (["lead", "mapping", "reconciliation"].includes(area))
      payload.account_ids = accountIds;
    if (area === "lead")
      Object.assign(payload, { section, rationale: comments });
    if (area === "flow")
      Object.assign(payload, {
        title: "Financial transaction investigation",
        note: comments,
        max_journals: 1000,
      });
    if (area === "ocr" || area === "source-table")
      Object.assign(payload, {
        evidence_version_id: evidence,
        date_format: dateFormat,
        decimal_separator: decimalSeparator,
        ...(zipMember ? { zip_member: zipMember } : {}),
        ...(area === "source-table"
          ? {
              table_kind: tableKind,
              ...(pdfMode
                ? { pdf_layout: pdfLayout }
                : worksheet
                  ? { worksheet }
                  : {}),
            }
          : {}),
      });
    if (area === "ageing")
      Object.assign(payload, {
        source_id: source,
        as_of: asOf,
        use_document_date_when_due_missing: fallback,
      });
    if (area === "reconciliation")
      Object.assign(payload, {
        statement_source_id: source,
        tolerance,
        date_tolerance: Number(dateTolerance),
        reconciliation_type: "bank",
      });
    if (area === "vouching")
      Object.assign(payload, {
        sample_id: sample,
        extraction_ids: extractions,
        amount_tolerance: tolerance,
        date_tolerance: Number(dateTolerance),
      });
    await action
      .mutateAsync({
        path: `${prefix}/jobs`,
        body: { operation: area, payload },
        headers: { "Idempotency-Key": crypto.randomUUID() },
      })
      .catch(() => undefined);
  }
  async function decide(
    decision: string,
    itemId?: string,
    candidateId?: string,
  ) {
    if (!detail.data) return;
    const result = await action
      .mutateAsync({
        path: `${prefix}/events/${selected}/review`,
        body: {
          expected_version: detail.data.version,
          action: decision,
          comments,
          ...(itemId ? { item_id: itemId } : {}),
          ...(candidateId ? { candidate_id: candidateId } : {}),
        },
      })
      .catch(() => null);
    if (result?.id) choose(result.id);
  }
  async function exportFile(format: string) {
    setDownloadBusy(true);
    setLocalError(null);
    try {
      const response = await fetch(
        `/api/backend/${prefix}/events/${selected}/export?format=${format}`,
        { headers: { "X-Tenant-ID": scope.tenant } },
      );
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${area}-${selected}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setLocalError(error as Error);
    } finally {
      setDownloadBusy(false);
    }
  }
  const sourceChoices = choices.filter(
    (r) => r.kind === "source-table" && r.freshness === "CURRENT",
  );
  const financial = [
    "lead",
    "mapping",
    "flow",
    "reconciliation",
    "foundation-validation",
  ].includes(area);
  const tableRows =
    body &&
    [
      "rows",
      "items",
      "suggestions",
      "matches",
      "unmatched_left",
      "unmatched_right",
    ].filter((key) => Array.isArray(body[key]));
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="Accounting intelligence"
        title={areas[area]}
        description="Immutable source versions, deterministic calculations and independent human review."
        actions={
          <Link className="button" href={`/engagements/${eid}/lifecycle`}>
            View dependency graph
          </Link>
        }
      />
      <nav className="toolbar" aria-label="Accounting workflows">
        <Link className="button" href={`/intelligence/${eid}/country-workflow`}>
          Country workflows
        </Link>
        {Object.entries(areas).map(([key, label]) => (
          <Link
            className="button"
            aria-current={area === key ? "page" : undefined}
            key={key}
            href={`/intelligence/${eid}/${key}`}
          >
            {label}
          </Link>
        ))}
        <Link className="button" href="/integrations">
          Import accounting data
        </Link>
        <Link className="button" href="/audit/sampling">
          Select samples
        </Link>
        <Link className="button" href={`/engagements/${eid}/evidence`}>
          Upload evidence
        </Link>
      </nav>
      <ErrorState
        error={
          inputs.error ||
          records.error ||
          detail.error ||
          action.error ||
          localError
        }
      />
      <section className="main-panel" style={{ padding: 20 }}>
        <h2>Generate from retained sources</h2>
        <div
          className="toolbar"
          style={{ alignItems: "start", flexWrap: "wrap" }}
        >
          {financial && (
            <label>
              Committed snapshot
              <select
                value={snapshot}
                onChange={(e) => {
                  setSnapshot(e.target.value);
                  setAccounts([]);
                }}
              >
                <option value="">Select snapshot</option>
                {inputs.data?.snapshots.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {financial && area !== "flow" && area !== "foundation-validation" && (
            <label>
              Explicit account selection (first 1,000)
              <select
                multiple
                size={5}
                value={accountIds}
                onChange={(e) =>
                  setAccounts(
                    Array.from(e.target.selectedOptions, (o) => o.value),
                  )
                }
              >
                {accounts.data?.items.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.code} — {a.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {area === "foundation-validation" && (
            <>
              <label>
                Reviewed document extractions
                <select
                  multiple
                  value={extractions}
                  onChange={(e) =>
                    setExtractions(
                      Array.from(e.target.selectedOptions, (o) => o.value),
                    )
                  }
                >
                  {choices
                    .filter((c) => c.kind === "ocr")
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label} · {c.review_status} · {c.freshness}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Reviewed rule assessments
                <select
                  multiple
                  value={assessments}
                  onChange={(e) =>
                    setAssessments(
                      Array.from(e.target.selectedOptions, (o) => o.value),
                    )
                  }
                >
                  {choices
                    .filter((c) => c.kind === "regulatory-assessment")
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label} · {c.review_status} · {c.freshness}
                      </option>
                    ))}
                </select>
              </label>
              {extractions.map((id) => (
                <label key={id}>
                  Supporting transaction for{" "}
                  {choices.find((c) => c.id === id)?.label || id}
                  <select
                    value={documentLinks[id] || ""}
                    onChange={(e) =>
                      setDocumentLinks({
                        ...documentLinks,
                        [id]: e.target.value,
                      })
                    }
                  >
                    <option value="">Select retained journal line</option>
                    {journalLines.data?.items.map((line) => (
                      <option key={line.id} value={line.id}>
                        {line.posting_date} · {line.description} · debit{" "}
                        {line.debit} / credit {line.credit}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              {(journalLines.data?.total || 0) > 500 && (
                <p>
                  First 500 journal lines shown. Use the API for larger
                  selections.
                </p>
              )}
              <ErrorState error={journalLines.error} />
              <Link href="/compliance/country">Resolve applicable rules</Link>
            </>
          )}
          {(area === "ocr" || area === "source-table") && (
            <>
              <label>
                Evidence version
                <select
                  value={evidence}
                  onChange={(e) => setEvidence(e.target.value)}
                >
                  <option value="">Select retained file</option>
                  {inputs.data?.evidence.map((c) => (
                    <option
                      disabled={c.scan_status !== "CLEAN"}
                      key={c.id}
                      value={c.id}
                    >
                      {c.label} — {c.scan_status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Date convention
                <select
                  value={dateFormat}
                  onChange={(e) => setDateFormat(e.target.value)}
                >
                  <option value="iso">YYYY-MM-DD</option>
                  <option value="dmy">DD/MM/YYYY</option>
                  <option value="mdy">MM/DD/YYYY</option>
                </select>
              </label>
              <label>
                Decimal separator
                <select
                  value={decimalSeparator}
                  onChange={(e) => setDecimalSeparator(e.target.value)}
                >
                  <option value=".">Point</option>
                  <option value=",">Comma</option>
                </select>
              </label>
              {area === "ocr" && (
                <label>
                  ZIP member (optional)
                  <input
                    value={zipMember}
                    onChange={(e) => setZipMember(e.target.value)}
                  />
                </label>
              )}
              {area === "source-table" && (
                <>
                  <label>
                    Table type
                    <select
                      value={tableKind}
                      onChange={(e) => {
                        setTableKind(e.target.value);
                        setPDFMode(false);
                      }}
                    >
                      <option value="bank">Bank transactions</option>
                      <option value="open-items">
                        Authoritative open items
                      </option>
                    </select>
                    {tableKind === "open-items" && (
                      <small>
                        To reuse this table in Country workflows, include
                        explicit document_type (invoice, credit-note or
                        debit-note), counterparty, document_date and due_date.
                        Optional balance_date must agree to the reporting scope;
                        segment is retained for ECL assessment.
                      </small>
                    )}
                  </label>
                  {tableKind === "bank" && (
                    <label
                      style={{
                        display: "flex",
                        flexDirection: "row",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <input
                        type="checkbox"
                        style={{ width: 16, height: 16, minHeight: 0 }}
                        checked={pdfMode}
                        onChange={(event) => {
                          setPDFMode(event.target.checked);
                          setWorksheet("");
                        }}
                      />
                      Map a PDF bank text grid
                    </label>
                  )}
                  {!pdfMode && (
                    <label>
                      Worksheet name (required for multi-sheet XLSX)
                      <input
                        value={worksheet}
                        maxLength={128}
                        onChange={(event) => setWorksheet(event.target.value)}
                      />
                    </label>
                  )}
                  {!pdfMode && (
                    <p>
                      CSV or macro-free XLSX values only. All selected-sheet
                      rows, including hidden rows, are included. Formula cells,
                      macros and external links are rejected. Numeric amounts
                      use original spreadsheet XML values; text dates and
                      amounts follow the selected conventions. Keep identifiers
                      requiring display formatting as text.
                    </p>
                  )}
                  {pdfMode && (
                    <PDFGridEditor
                      key={evidence}
                      draft={pdfGrid}
                      onChange={setPDFGrid}
                      eid={eid}
                      evidence={evidence}
                      tenant={scope.tenant}
                    />
                  )}
                </>
              )}
            </>
          )}
          {area === "lead" && (
            <label>
              Schedule section
              <select
                value={section}
                onChange={(e) => setSection(e.target.value)}
              >
                {capabilities.data?.lead_sections.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
          )}
          {(area === "ageing" || area === "reconciliation") && (
            <label>
              Supporting table
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="">Select source</option>
                {sourceChoices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label} • v{c.version}
                  </option>
                ))}
              </select>
            </label>
          )}
          {area === "ageing" && (
            <>
              <label>
                As of
                <input
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={fallback}
                  onChange={(e) => setFallback(e.target.checked)}
                />
                Explicitly allow document-date fallback
              </label>
            </>
          )}
          {area === "vouching" && (
            <>
              <label>
                Actual selected sample
                <select
                  value={sample}
                  onChange={(e) => setSample(e.target.value)}
                >
                  <option value="">Select sample</option>
                  {inputs.data?.samples.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Current document extractions
                <select
                  multiple
                  size={4}
                  value={extractions}
                  onChange={(e) =>
                    setExtractions(
                      Array.from(e.target.selectedOptions, (o) => o.value),
                    )
                  }
                >
                  {choices
                    .filter(
                      (c) => c.kind === "ocr" && c.freshness === "CURRENT",
                    )
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label} • v{c.version} • {c.review_status}
                      </option>
                    ))}
                </select>
              </label>
            </>
          )}
          {["vouching", "reconciliation"].includes(area) && (
            <>
              <label>
                Amount tolerance
                <input
                  value={tolerance}
                  onChange={(e) => setTolerance(e.target.value)}
                />
              </label>
              <label>
                Date tolerance (days)
                <input
                  type="number"
                  min="0"
                  max="90"
                  value={dateTolerance}
                  onChange={(e) => setDateTolerance(e.target.value)}
                />
              </label>
            </>
          )}
        </div>
        <label>
          Auditor rationale / review comments
          <textarea
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            maxLength={4000}
          />
        </label>
        <Button primary disabled={action.isPending} onClick={run}>
          Queue {areas[area].toLowerCase()}
        </Button>
        <p className="subtle">
          Quarantined evidence is unavailable until a functioning malware
          scanner clears it. CSV/XLSX supporting tables and mapped PDF bank
          grids require explicit columns and conventions. Generated results
          never post entries or approve audit work.
        </p>
      </section>
      <section className="main-panel" style={{ padding: 20 }}>
        <h2>Execution queue</h2>
        {(jobs.data?.items.length || 0) > 5 && (
          <Button onClick={() => setShowAllJobs(!showAllJobs)}>
            {showAllJobs
              ? "Show latest five jobs"
              : "Show full recent job history"}
          </Button>
        )}
        <ErrorState error={jobs.error} />
        {jobs.data?.items.slice(0, showAllJobs ? undefined : 5).map((j) => (
          <div className="toolbar" key={j.id}>
            <span>
              {j.operation} • attempt {j.attempts}
            </span>
            <Status value={j.status} />
            {j.error_details && <span>{j.error_details.message}</span>}
            {j.result_id && (
              <Button onClick={() => choose(j.result_id!)}>Open result</Button>
            )}
            {["pending", "running", "failed"].includes(j.status) && (
              <Button
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({
                    path: `${prefix}/jobs/${j.id}/actions`,
                    body: {
                      version: j.version,
                      action: j.status === "failed" ? "retry" : "cancel",
                    },
                  })
                }
              >
                {j.status === "failed" ? "Retry" : "Cancel publication"}
              </Button>
            )}
          </div>
        ))}
      </section>
      <section className="main-panel" style={{ padding: 20 }}>
        <h2>Results and preserved history</h2>
        {area === "foundation-validation" && foundation.data && (
          <aside>
            <p>
              Runtime: {foundation.data.runtime}. Professional correctness: not
              assessed by health checks. Period: {foundation.data.period.state}.
            </p>
            <p>
              Jobs:{" "}
              {Object.entries(foundation.data.job_counts)
                .map(([state, count]) => `${state}: ${count}`)
                .join(" · ") || "No jobs submitted"}
            </p>
            <Button
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  path: `${prefix}/period-actions`,
                  body: {
                    action:
                      foundation.data!.period.state === "OPEN"
                        ? "lock"
                        : "reopen",
                    expected_version: foundation.data!.period.version,
                    reason: comments,
                  },
                })
              }
            >
              {foundation.data.period.state === "OPEN"
                ? "Lock period"
                : "Reopen period with recorded reason"}
            </Button>
            <ErrorState error={foundation.error} />
          </aside>
        )}
        <label>
          Result version
          <select value={selected} onChange={(e) => choose(e.target.value)}>
            <option value="">Select result</option>
            {choices.map((c) => (
              <option key={c.id} value={c.id}>
                {c.kind} • {c.label} • v{c.version} • {c.freshness}
              </option>
            ))}
          </select>
        </label>
        {records.hasOlder && (
          <Button disabled={records.loadingOlder} onClick={records.loadOlder}>
            Load older sources and results
          </Button>
        )}
        {!detail.data ? (
          <Empty title="Select a result">
            Completed runs and human decisions retain their original source
            receipts.
          </Empty>
        ) : (
          <>
            {selectedVATScope && (
              <aside aria-label="Selected VAT201 comparison coverage">
                <strong>
                  Selected VAT201 boxes only:{" "}
                  {Array.isArray(selectedVATScope.required_boxes)
                    ? selectedVATScope.required_boxes.map(String).join(", ")
                    : ""}
                  .
                </strong>{" "}
                Whole-return completeness is not determined.
                <p>{val(selectedVATScope.assessment)}</p>
              </aside>
            )}
            {body?.table_metadata != null &&
              typeof body.table_metadata === "object" && (
                <details>
                  <summary>
                    Supporting table layout and worksheet controls
                  </summary>
                  <dl>
                    {Object.entries(
                      body.table_metadata as Record<string, unknown>,
                    ).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key.replaceAll("_", " ")}</dt>
                        <dd>{val(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            <div className="toolbar">
              {detail.data.kind === "foundation-validation" && (
                <Button
                  disabled={action.isPending}
                  onClick={() => decide("submit")}
                >
                  Submit foundation workpaper for review
                </Button>
              )}
              <Badge>{detail.data.freshness}</Badge>
              {detail.data.provenance_status ===
                "legacy provenance incomplete" && (
                <Badge>Legacy provenance incomplete</Badge>
              )}
              <Status value={body?.review_status} />
              <span>Version {detail.data.version}</span>
              {["xlsx", "pdf", "docx"].map((f) => (
                <Button
                  disabled={downloadBusy}
                  key={f}
                  onClick={() => exportFile(f)}
                >
                  Export {f.toUpperCase()}
                </Button>
              ))}
            </div>
            <p className="subtle">SHA-256: {detail.data.sha256}</p>
            {body?.fields && typeof body.fields === "object" ? (
              <div className="toolbar" style={{ alignItems: "start" }}>
                <div style={{ flex: 1 }}>
                  <h3>Extracted fields</h3>
                  {Object.entries(body.fields as Record<string, unknown>).map(
                    ([key, value]) => (
                      <label key={key} style={{ display: "block" }}>
                        {key}
                        <input
                          value={
                            corrections[key] ??
                            (value == null ? "" : String(value))
                          }
                          onChange={(e) =>
                            setCorrections({
                              ...corrections,
                              [key]: e.target.value,
                            })
                          }
                        />
                      </label>
                    ),
                  )}
                  <Button
                    disabled={
                      action.isPending || !Object.keys(corrections).length
                    }
                    onClick={async () => {
                      const result = await action
                        .mutateAsync({
                          path: `${prefix}/events/${selected}/corrections`,
                          body: {
                            expected_version: detail.data!.version,
                            fields: corrections,
                            reason: comments,
                          },
                        })
                        .catch(() => null);
                      if (result?.id) choose(result.id);
                    }}
                  >
                    Save correction as new version
                  </Button>
                </div>
                <div style={{ flex: 1 }}>
                  <h3>Original extraction text and locations</h3>
                  <p>{val(body.validation_messages)}</p>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      maxHeight: 600,
                      overflow: "auto",
                    }}
                  >
                    {JSON.stringify(body.pages, null, 2)}
                  </pre>
                  <p className="subtle">
                    Raw recognition scores are uncalibrated. Inspect the
                    retained original in Evidence before approving.
                  </p>
                </div>
              </div>
            ) : null}
            {detail.data.kind === "mapping" && (
              <MappingDecisions
                prefix={prefix}
                result={detail.data}
                comments={comments}
                onSaved={choose}
              />
            )}
            {detail.data.kind === "ocr" && body && (
              <EvidencePreview prefix={prefix} body={body} />
            )}
            {detail.data.kind === "foundation-validation" && body && (
              <section>
                <h3>Foundation controls</h3>
                <p>
                  Execution: {val(body.execution_status)} · Completeness:{" "}
                  {val(body.completeness)} · Review: {val(body.review_status)}
                </p>
                {(
                  (body.issues as {
                    code: string;
                    reason: string;
                    remediation: string;
                    url?: string;
                    blocking: boolean;
                  }[]) || []
                ).map((issue, index) => (
                  <article key={index}>
                    <strong>
                      {issue.blocking ? "Blocker" : "Warning"}: {issue.reason}
                    </strong>
                    <p>
                      {issue.remediation}{" "}
                      {issue.url && (
                        <Link href={issue.url}>Open affected workspace</Link>
                      )}
                    </p>
                  </article>
                ))}
              </section>
            )}
            {detail.data.kind === "flow" && body && (
              <TransactionGraph body={body} />
            )}
            {tableRows?.map((key) => (
              <ResultTable
                key={key}
                name={key}
                values={body![key] as unknown[]}
                decide={decide}
                preferredColumns={
                  area === "source-table" && key === "rows"
                    ? body?.table_kind === "bank"
                      ? [
                          "reference",
                          "date",
                          "account_code",
                          "currency",
                          "amount",
                          "counterparty",
                          "source_page",
                          "source_page_row",
                          "source_worksheet",
                        ]
                      : [
                          "reference",
                          "counterparty",
                          "account_code",
                          "currency",
                          "open_amount",
                          "document_type",
                          "document_date",
                          "due_date",
                          "balance_date",
                        ]
                    : undefined
                }
              />
            ))}
            {body && (
              <details>
                <summary>Source receipts, totals and execution details</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere",
                    maxHeight: 500,
                    overflow: "auto",
                  }}
                >
                  {JSON.stringify(
                    {
                      ...body,
                      rows: undefined,
                      items: undefined,
                      pages: undefined,
                      source_rows: undefined,
                      destination_rows: undefined,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            )}
            <div className="toolbar">
              <Button
                disabled={action.isPending || offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous 100
              </Button>
              <span>
                Rows {offset + 1}–{offset + 100}
              </span>
              <Button
                disabled={
                  action.isPending ||
                  !Object.entries(detail.data.collection_totals || {}).some(
                    ([collection, n]) =>
                      collection !== "excluded_box_rows" && n > offset + 100,
                  )
                }
                onClick={() => setOffset(offset + 100)}
              >
                Next 100
              </Button>
            </div>
            <div className="toolbar">
              <Button
                disabled={
                  action.isPending || detail.data.freshness !== "CURRENT"
                }
                onClick={() => decide("approve")}
              >
                Record independent approval
              </Button>
              <Button
                disabled={
                  action.isPending || detail.data.freshness !== "CURRENT"
                }
                onClick={() => decide("reject")}
              >
                Record rejection
              </Button>
              <Button
                disabled={
                  action.isPending || body?.review_status !== "REVIEWED"
                }
                onClick={async () => {
                  await action
                    .mutateAsync({
                      path: `${prefix}/events/${selected}/working-paper`,
                      body: {
                        reference: `INT-${crypto.randomUUID().slice(0, 8)}`,
                        title: areas[area],
                        objective: comments,
                        assertions: [],
                      },
                    })
                    .catch(() => null);
                }}
              >
                Create connected working-paper draft
              </Button>
              <Link
                className="button"
                href={`/engagements/${eid}/working-papers`}
              >
                Review working papers
              </Link>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function MappingDecisions({
  prefix,
  result,
  comments,
  onSaved,
}: {
  prefix: string;
  result: Result;
  comments: string;
  onSaved: (id: string) => void;
}) {
  const action = useAction<Result>();
  const [assignments, setAssignments] = useState<
    Record<string, { classification: string; statement_group: string }>
  >({});
  const suggestions = (result.body.suggestions || []) as {
    account_code: string;
    name: string;
    suggested_classification: string;
    statement_group: string;
  }[];
  return (
    <section>
      <h3>Human mapping decisions</h3>
      <ErrorState error={action.error} />
      <p>
        Choose each classification explicitly. Saving creates a new proposal
        version for an independent reviewer. Applying an approved version
        updates the existing accounting mapping service and makes dependent
        outputs stale.
      </p>
      {suggestions.map((row) => (
        <div className="toolbar" key={row.account_code}>
          <span>
            {row.account_code} — {row.name}
          </span>
          <label>
            Classification
            <select
              value={assignments[row.account_code]?.classification || ""}
              onChange={(e) =>
                setAssignments({
                  ...assignments,
                  [row.account_code]: {
                    classification: e.target.value,
                    statement_group: row.statement_group || "",
                  },
                })
              }
            >
              <option value="">No decision</option>
              {["Assets", "Liabilities", "Equity", "Income", "Expenses"].map(
                (c) => (
                  <option key={c}>{c}</option>
                ),
              )}
            </select>
          </label>
        </div>
      ))}
      <Button
        disabled={action.isPending || !Object.keys(assignments).length}
        onClick={async () => {
          const saved = await action
            .mutateAsync({
              path: `${prefix}/events/${result.id}/mapping-decisions`,
              body: {
                expected_version: result.version,
                assignments,
                reason: comments,
              },
            })
            .catch(() => null);
          if (saved) onSaved(saved.id);
        }}
      >
        Save human assignments for review
      </Button>
      <Button
        disabled={
          action.isPending ||
          result.body.review_status !== "REVIEWED" ||
          !result.body.human_assignments ||
          result.freshness !== "CURRENT"
        }
        onClick={() =>
          action.mutate({ path: `${prefix}/events/${result.id}/apply-mapping` })
        }
      >
        Apply independently reviewed mapping
      </Button>
    </section>
  );
}

function EvidencePreview({
  prefix,
  body,
}: {
  prefix: string;
  body: Record<string, unknown>;
}) {
  const tenant = useScope((s) => s.tenant);
  const [pageIndex, setPageIndex] = useState(0);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const pages =
    (body.pages as {
      page: number;
      width: number;
      height: number;
      source_page: number;
      source_file: string;
      blocks: { id: string; text: string; bbox?: number[][] }[];
    }[]) || [];
  const page = pages[pageIndex];
  const id = String(body.evidence_version_id || "");
  const member = page?.source_file === "original" ? "" : page?.source_file;
  useEffect(() => {
    const controller = new AbortController();
    let blobUrl = "";
    if (!id || !page) return;
    fetch(
      `/api/backend/${prefix}/evidence/${id}/preview?page=${page.source_page}${member ? `&member=${encodeURIComponent(member)}` : ""}`,
      { headers: { "X-Tenant-ID": tenant }, signal: controller.signal },
    )
      .then(async (r) => {
        if (!r.ok)
          throw new Error(`Document preview unavailable (${r.status})`);
        blobUrl = URL.createObjectURL(await r.blob());
        setUrl(blobUrl);
        setError(null);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e);
      });
    return () => {
      controller.abort();
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [prefix, id, page, member, tenant]);
  return (
    <section>
      <h3>Retained original — raster preview</h3>
      <ErrorState error={error} />
      <label>
        Source page
        <select
          value={pageIndex}
          onChange={(e) => {
            setUrl("");
            setPageIndex(Number(e.target.value));
          }}
        >
          {pages.map((p, i) => (
            <option key={p.page} value={i}>
              {p.source_file} • page {p.source_page}
            </option>
          ))}
        </select>
      </label>
      {url && page && (
        <svg
          role="img"
          aria-label="Original document with extracted text regions"
          viewBox={`0 0 ${page.width} ${page.height}`}
          style={{ width: "100%", maxHeight: 700, background: "white" }}
        >
          <image href={url} width={page.width} height={page.height} />
          {page.blocks
            .filter((b) => b.bbox)
            .map((b) => (
              <polygon
                key={b.id}
                points={b.bbox!.map((p) => p.join(",")).join(" ")}
                fill="rgba(37,99,235,0.08)"
                stroke="#2563eb"
                strokeWidth="1"
              >
                <title>{b.text}</title>
              </polygon>
            ))}
        </svg>
      )}
    </section>
  );
}

function TransactionGraph({ body }: { body: Record<string, unknown> }) {
  const [focus, setFocus] = useState("");
  const [line, setLine] = useState("");
  const allEdges = (Array.isArray(body.edges) ? body.edges : []) as {
    id: string;
    source: string;
    target: string;
    amount: string;
    currency: string;
    source_record_id: string;
  }[];
  const rawNodes = (Array.isArray(body.nodes) ? body.nodes : []) as {
    id: string;
    label: string;
    type: string;
  }[];
  const ids = new Set(rawNodes.slice(0, 100).map((n) => n.id));
  const edges = allEdges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const connected = new Set([
    focus,
    ...edges
      .filter((e) => e.source === focus || e.target === focus)
      .flatMap((e) => [e.source, e.target]),
  ]);
  return (
    <>
      <h3>Actual debit and credit relationships</h3>
      <p className="subtle">
        {String(body.meaning)}. View is bounded to 100 nodes and the current
        100-edge page. Select a node to focus its neighbors.
      </p>
      <div style={{ height: 500 }}>
        <ReactFlow
          fitView
          nodes={rawNodes.slice(0, 100).map((n, i) => ({
            id: n.id,
            position: { x: n.type === "account" ? 0 : 380, y: i * 100 },
            data: { label: n.label },
            className: "mr-audit-node",
            style: {
              width: 240,
              padding: 12,
              background: "var(--surface, #fff)",
              color: "var(--text, #172234)",
              opacity: focus && !connected.has(n.id) ? 0.3 : 1,
            },
          }))}
          edges={edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: `${e.amount} ${e.currency}`,
            animated: focus === e.source || focus === e.target,
          }))}
          onNodeClick={(_, node) => setFocus(node.id === focus ? "" : node.id)}
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
      <details>
        <summary>Source posting references</summary>
        {edges.map((e) => (
          <p key={e.id}>
            <Button onClick={() => setLine(e.id)}>
              {e.amount} {e.currency} • source {e.source_record_id}
            </Button>
          </p>
        ))}
      </details>
      {line && <LineageDetail id={line} />}
    </>
  );
}

function ResultTable({
  name,
  values,
  decide,
  preferredColumns,
}: {
  name: string;
  values: unknown[];
  decide: (action: string, item?: string, candidate?: string) => Promise<void>;
  preferredColumns?: string[];
}) {
  const [showAll, setShowAll] = useState(false);
  const rows = values.filter((v) => v && typeof v === "object") as Record<
    string,
    unknown
  >[];
  const allColumns = Array.from(new Set(rows.flatMap(Object.keys))).filter(
    (key) => key !== "candidates",
  );
  const columns = showAll
    ? allColumns
    : preferredColumns
      ? preferredColumns.filter((key) => allColumns.includes(key))
      : allColumns.slice(0, 12);
  return (
    <div style={{ overflowX: "auto" }}>
      <h3>{name.replaceAll("_", " ")}</h3>
      {(preferredColumns || allColumns.length > 12) && (
        <label
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            gap: 8,
          }}
        >
          <input
            type="checkbox"
            style={{ width: 16, height: 16, minHeight: 0 }}
            checked={showAll}
            onChange={(event) => setShowAll(event.target.checked)}
          />
          {preferredColumns
            ? "Show all supporting-table provenance"
            : "Show all result columns"}
        </label>
      )}
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
            {rows.some((r) => r.candidates) && <th>Auditor decision</th>}
            {(name === "matches" || name.startsWith("unmatched_")) && (
              <th>Auditor decision</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={String(r.id || i)}>
              {columns.map((c) => (
                <td key={c} style={{ maxWidth: 300, overflowWrap: "anywhere" }}>
                  {val(r[c])}
                </td>
              ))}
              {Array.isArray(r.candidates) && (
                <td>
                  {(r.candidates as Record<string, unknown>[]).map((c) => (
                    <Button
                      key={String(c.extraction_id)}
                      onClick={() =>
                        decide("accept", String(r.id), String(c.extraction_id))
                      }
                    >
                      Accept candidate {String(c.extraction_id).slice(0, 8)} •{" "}
                      {String(c.machine_status)}
                    </Button>
                  ))}
                  <Button
                    onClick={() => decide("request-evidence", String(r.id))}
                  >
                    Request evidence
                  </Button>
                  <Button onClick={() => decide("finding", String(r.id))}>
                    Record exception
                  </Button>
                </td>
              )}
              {name === "matches" && Array.isArray(r.left_ids) && (
                <td>
                  <Button
                    onClick={() =>
                      decide("accept", String((r.left_ids as unknown[])[0]))
                    }
                  >
                    Accept proposed match
                  </Button>
                </td>
              )}
              {name.startsWith("unmatched_") && (
                <td>
                  <Button onClick={() => decide("finding", String(r.id))}>
                    Record reconciliation exception
                  </Button>
                  <Button
                    onClick={() => decide("request-evidence", String(r.id))}
                  >
                    Request supporting evidence
                  </Button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
