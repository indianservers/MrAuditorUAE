"use client";
import {
  CompletionControls,
  type CompletionCheck,
} from "./completion-controls";
import { NonresidentAuditRevenueEditor } from "./nonresident-audit-revenue";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  FileCheck2,
  GitBranch,
  History,
  Plus,
  Save,
  ShieldCheck,
} from "lucide-react";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Button,
  Empty,
  ErrorState,
  Facts,
  Pagination,
  Status,
} from "@/components/ui/primitives";
import { useAPI, useAction, useDebounced } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { useScope } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import { PageHeader } from "./shared";

export const auditAreas = [
  ["acceptance", "Engagement Acceptance"],
  ["independence", "Independence & Ethics"],
  ["planning", "Audit Planning Studio"],
  ["materiality", "Materiality Calculator"],
  ["risks", "Risk & Assertions Matrix"],
  ["programs", "Audit Program Builder"],
  ["procedures", "Procedure Assignments"],
  ["testing", "Audit Testing Workbench"],
  ["working-papers", "Working Paper Editor"],
  ["evidence", "Evidence Review Studio"],
  ["findings", "Findings & Misstatements"],
  ["review-notes", "Reviewer Command Center"],
  ["completion", "Engagement Completion"],
  ["requests", "Client Document Requests"],
  ["ai", "Engagement AI Assistant"],
  ["team", "Engagement Team"],
] as const;
type AuditRecord = RecordRow & {
  id: string;
  reference: string;
  title: string;
  status: string;
  version: number;
  kind: string;
  body: Record<string, unknown>;
};
type FieldSchema = {
  type?: string;
  title?: string;
  default?: unknown;
  enum?: string[];
  format?: string;
  anyOf?: FieldSchema[];
  $ref?: string;
};
type Schema = {
  properties: Record<string, FieldSchema>;
  required?: string[];
  $defs?: Record<string, FieldSchema>;
};
type Workspace = {
  engagement: { name: string; status: string; version: number };
  permissions: string[];
  roles: string[];
  transitions: string[];
  schemas: Record<string, Schema>;
  counts: { kind: string; status: string; count: number }[];
  ai_tasks: string[];
  policy: RecordRow;
};
const serverFields = new Set([
  "calculation",
  "review_stage",
  "review_cycle",
  "review_approvers",
  "assessment_flags",
]);
const tpPermissions: Record<string, [string, string]> = {
  "tp-rule": ["tp.rules.manage", "tp.rules.approve"],
  "tp-profile": ["tp.relationship.manage", "tp.review"],
  "tp-party": ["tp.relationship.manage", "tp.review"],
  "tp-relationship": ["tp.relationship.manage", "tp.review"],
  "tp-transaction": ["tp.transaction.classify", "tp.review"],
  "tp-segmentation": ["tp.segmentation.prepare", "tp.segmentation.approve"],
  "tp-far": ["tp.far.prepare", "tp.far.review"],
  "tp-method": ["tp.method.select", "tp.review"],
  "tp-dataset": ["tp.benchmark.import", "tp.benchmark.approve"],
  "tp-study": ["tp.benchmark.import", "tp.benchmark.approve"],
  "tp-screening": ["tp.benchmark.screen", "tp.benchmark.approve"],
  "tp-loan": ["tp.loan.analyze", "tp.review"],
  "tp-credit": ["tp.loan.analyze", "tp.review"],
  "tp-remuneration": ["tp.remuneration.review", "tp.review"],
  "tp-service": ["tp.segmentation.prepare", "tp.segmentation.approve"],
  "tp-royalty": ["tp.method.select", "tp.review"],
  "tp-guarantee": ["tp.loan.analyze", "tp.review"],
  "tp-comparability": ["tp.benchmark.screen", "tp.benchmark.approve"],
  "tp-disclosure": ["tp.disclosure.prepare", "tp.disclosure.approve"],
  "tp-localfile": ["tp.localfile.prepare", "tp.localfile.approve"],
  "tp-masterfile": ["tp.masterfile.prepare", "tp.masterfile.approve"],
  "tp-apa": ["tp.localfile.prepare", "tp.review"],
  "tp-judgment": ["tp.method.select", "tp.benchmark.approve"],
  "tp-release": ["tp.localfile.prepare", "tp.localfile.approve"],
};
const vatPreparePermissions: Record<string, string> = {
  "vat-rule": "vat.rules.manage",
  "vat-profile": "vat.profile.write",
  "vat-invoice": "vat.invoice.prepare",
  "vat-adjustment": "vat.adjustment.prepare",
  "vat-recovery": "vat.recovery.prepare",
  "vat-einvoicing": "einvoice.prepare",
  "vat-return": "vat.return.prepare",
};
function label(value: string) {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}
export function AuditStudio({
  id,
  area = "planning",
  ifrs = false,
  children,
  defaults,
}: {
  id: string;
  area?: string;
  ifrs?: boolean;
  children?: React.ReactNode;
  defaults?: Record<string, unknown>;
}) {
  const requestedRecord = useSearchParams().get("record");
  const base = `engagements/${id}/audit`;
  const workspace = useAPI<Workspace>(base + "/workspace", true, true);
  const [search, setSearch] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [offset, setOffset] = useState(0);
  const value = useDebounced(search);
  const records = useAPI<Page<AuditRecord>>(
    `${base}/${area}?${qs({ search: value, offset, limit: 50, status: lifecycle })}`,
    area !== "team",
    true,
  );
  const [selected, setSelected] = useState<AuditRecord | null>(null);
  const [creating, setCreating] = useState(false);
  const [history, setHistory] = useState(false);
  useEffect(() => {
    setSelected(null);
    setCreating(false);
    setHistory(false);
  }, [requestedRecord]);
  const detail = useAPI<AuditRecord>(
    `${base}/records/${selected?.id || requestedRecord}`,
    !!(selected?.id || requestedRecord),
  );
  const current =
    detail.data ||
    records.data?.items.find((r) => r.id === selected?.id) ||
    selected;
  const w = workspace.data;
  const canPrepare = area.startsWith("tp-")
    ? !!w?.permissions.includes(tpPermissions[area]?.[0])
    : !area.startsWith("vat-") ||
      !!w?.permissions.includes(vatPreparePermissions[area]);
  const title = ifrs
    ? (area.startsWith("tp-")
        ? "Transfer Pricing records / "
        : area.startsWith("vat-")
          ? "VAT records / "
          : area.startsWith("tax-")
            ? "Tax records / "
            : "Reporting records / ") +
      label(
        area
          .replace("ifrs-", "")
          .replace("tax-", "")
          .replace("vat-", "")
          .replace("tp-", ""),
      )
    : auditAreas.find((a) => a[0] === area)?.[1] || "Audit workspace";
  const action = useAction();
  const [reason, setReason] = useState("");
  if (workspace.error) return <ErrorState error={workspace.error} />;
  return (
    <>
      <PageHeader
        eyebrow="Engagement / External audit"
        title={title}
        description={w?.engagement.name || "Loading engagement…"}
        actions={
          <>
            <Status value={w?.engagement.status} />
            <Button
              disabled={!canPrepare}
              onClick={() => {
                setCreating(true);
                setSelected(null);
                setHistory(false);
              }}
            >
              <Plus size={14} /> New record
            </Button>
          </>
        }
      />
      <p>
        <Link href={`/engagements/${id}/workspace`}>Engagement workspace</Link>
        {" · "}
        <Link href={`/engagements/${id}/lifecycle`}>Audit lifecycle</Link>
        {" · "}
        <Link href={`/engagements/${id}/graph`}>
          Open working-paper dependency graph
        </Link>
      </p>
      <ErrorState error={detail.error} />
      {!ifrs && (
        <nav className="audit-tabs" aria-label="Engagement workspaces">
          {auditAreas.map(([key, name]) => (
            <Link
              key={key}
              href={`/engagements/${id}/${key}`}
              aria-current={key === area ? "page" : undefined}
            >
              {name}
            </Link>
          ))}
        </nav>
      )}
      {children}
      <label>
        Record lifecycle filter
        <select
          value={lifecycle}
          onChange={(e) => {
            setLifecycle(e.target.value);
            setOffset(0);
            setSelected(null);
          }}
        >
          <option value="">Current records</option>
          <option value="ARCHIVED">Archived drafts</option>
        </select>
      </label>
      <div className="audit-stage-bar">
        <span>
          <ShieldCheck size={15} /> Human review required
        </span>
        <span>
          {w?.counts.reduce((n, c) => n + c.count, 0) || 0} linked audit records
        </span>
        <span>Versioned • Tenant isolated • Source linked</span>
      </div>
      {area === "team" ? (
        <AuditTeam base={base} />
      ) : (
        <div className="audit-split">
          <section
            className="audit-register"
            aria-label="Audit record register"
          >
            <div className="toolbar">
              <input
                aria-label="Search audit records"
                placeholder="Search reference or title…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setOffset(0);
                }}
              />
              <span>{records.data?.total || 0} records</span>
              <Button onClick={() => records.refetch()}>Refresh</Button>
            </div>
            {area === "completion" && <Completion base={base} />}
            {area === "testing" && <SamplingWorkbench base={base} />}
            {area === "review-notes" && <ReviewQueue base={base} id={id} />}
            {area === "programs" && <InstantiateMethodology base={base} />}
            {area === "ai" && w && <AuditAI base={base} tasks={w.ai_tasks} />}
            <FinancialDataGrid
              exportable={!area.startsWith("tp-")}
              name={`audit-${area}`}
              rows={(records.data?.items || []).map((r) => ({
                ...r,
                audit_area: r.body.area,
                assertions: ((r.body.assertions as string[]) || []).join(", "),
                inherent_risk: r.body.inherent_risk,
                owner: r.body.owner_id,
              }))}
              loading={records.isLoading}
              error={records.error}
              columns={[
                column("reference", "Reference", 120, {
                  cellRenderer: (p: { data: AuditRecord; value: string }) => (
                    <button
                      className="text-button"
                      onClick={() => {
                        setSelected(p.data);
                        setCreating(false);
                        setHistory(false);
                      }}
                    >
                      {p.value}
                    </button>
                  ),
                }),
                column("title", "Audit record", 300),
                ...(area === "risks"
                  ? [
                      column("assertions", "Assertions", 240),
                      column("inherent_risk", "Inherent risk", 130),
                    ]
                  : []),
                ...(["procedures", "testing"].includes(area)
                  ? [column("owner", "Assigned auditor", 220)]
                  : []),
                column("status", "Review status", 160, {
                  cellRenderer: (p: { value: string }) => (
                    <Status value={p.value} />
                  ),
                }),
                column("version", "Version", 85),
                column("updated_at", "Last updated", 180),
              ]}
            />
            <Pagination
              offset={offset}
              total={records.data?.total || 0}
              limit={50}
              onChange={setOffset}
            />
            <details className="audit-lifecycle">
              <summary>
                <GitBranch size={14} /> Engagement lifecycle
              </summary>
              <label>
                Transition reason
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <div className="toolbar">
                {w?.transitions.map((to) => (
                  <Button
                    key={to}
                    disabled={!reason || action.isPending}
                    onClick={() =>
                      action.mutate({
                        path: base + "/transition",
                        body: {
                          version: w.engagement.version,
                          action: to,
                          comments: reason,
                        },
                      })
                    }
                  >
                    {label(to)}
                  </Button>
                ))}
              </div>
              <ErrorState error={action.error} />
            </details>
          </section>
          <aside className="audit-inspector" aria-label="Audit record editor">
            <div className="audit-inspector-heading">
              <FileCheck2 size={16} />
              <strong>
                {creating
                  ? "Prepare new record"
                  : current?.reference || "Record workspace"}
              </strong>
              {current && (
                <Button onClick={() => setHistory(!history)}>
                  <History size={14} /> History
                </Button>
              )}
            </div>
            {history && current ? (
              <AuditHistory base={base} record={current} />
            ) : (creating || current) && w?.schemas[area] ? (
              <AuditEditor
                key={`${current?.id || "new"}:${current?.version || 0}:${area}`}
                base={base}
                area={area}
                schema={w.schemas[area]}
                defaults={defaults}
                authorized={canPrepare}
                record={creating ? null : current}
                onSaved={() => setCreating(false)}
              />
            ) : current ? (
              <>
                <Facts data={current.body} />
                <RecordActions base={base} record={current} />
              </>
            ) : (
              <Empty title="Prepare, inspect and review">
                Select a reference from the register, or prepare a new record.
                Every edit preserves a version; approvals require an independent
                authorized reviewer.
              </Empty>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
function inputType(
  schema: FieldSchema,
  defs: Record<string, FieldSchema> = {},
) {
  const value = schema.anyOf?.find((s) => s.type !== "null") || schema;
  return value.$ref ? defs[value.$ref.split("/").at(-1) || ""] || value : value;
}
export function AuditEditor({
  base,
  area,
  schema,
  record,
  onSaved,
  defaults,
  authorized = true,
}: {
  base: string;
  area: string;
  schema: Schema;
  record: AuditRecord | null;
  onSaved: () => void;
  defaults?: Record<string, unknown>;
  authorized?: boolean;
}) {
  const [reference, setReference] = useState(record?.reference || "");
  const [title, setTitle] = useState(record?.title || "");
  const [body, setBody] = useState<Record<string, unknown>>(
    () =>
      record?.body || {
        ...Object.fromEntries(
          Object.entries(schema.properties)
            .filter(([, s]) => s.default !== undefined)
            .map(([k, s]) => [k, s.default]),
        ),
        ...defaults,
      },
  );
  const [parseError, setParseError] = useState("");
  const action = useAction<AuditRecord>();
  const set = (key: string, value: unknown) =>
    setBody((b) => ({ ...b, [key]: value }));
  const editable =
    authorized &&
    (!record ||
      [
        "IN_PROGRESS",
        "REVISED",
        "REVIEW_NOTES",
        "OPEN",
        "DRAFT",
        "MORE_INFORMATION_REQUIRED",
        "UNDER_REVIEW",
        "MANAGEMENT_RESPONSE_PENDING",
        "REMEDIATION_PENDING",
      ].includes(record.status));
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setParseError("");
    try {
      const clean: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(body)) {
        if (serverFields.has(key)) continue;
        const s = inputType(schema.properties[key] || {}, schema.$defs);
        clean[key] =
          (s.type === "array" || s.type === "object") &&
          typeof value === "string"
            ? JSON.parse(value)
            : value;
      }
      const saved = await action.mutateAsync({
        path: record ? `${base}/records/${record.id}` : `${base}/${area}`,
        method: record ? "PATCH" : "POST",
        body: {
          reference,
          title,
          body: clean,
          ...(record ? { version: record.version } : {}),
        },
      });
      setReference(saved.reference);
      onSaved();
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Unable to save");
    }
  }
  return (
    <div className="audit-editor">
      <form onSubmit={save}>
        <fieldset disabled={!editable || action.isPending}>
          <div className="audit-field-pair">
            <label>
              Reference
              <input
                required
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="e.g. PL-001"
              />
            </label>
            <label>
              Title
              <input
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
          </div>
          {Object.entries(schema.properties)
            .sort(
              ([a], [b]) =>
                Number(schema.required?.includes(b) || false) -
                Number(schema.required?.includes(a) || false),
            )
            .map(([key, raw]) => {
              const s = inputType(raw, schema.$defs),
                required = schema.required?.includes(key);
              const val = body[key];
              if (key === "nonresident_audit_revenue" && area === "tax-profile")
                return (
                  <NonresidentAuditRevenueEditor
                    key={`${base}:${record?.id || "new"}:${key}`}
                    base={base}
                    value={val}
                    onChange={(v) => set(key, v)}
                  />
                );
              return (
                <label key={key} className="audit-field">
                  <span>
                    {label(key)} {required && <b aria-label="required">*</b>}
                  </span>
                  {s.enum ? (
                    <select
                      value={String(val ?? "")}
                      required={required}
                      onChange={(e) => set(key, e.target.value)}
                    >
                      <option value="">Select…</option>
                      {s.enum.map((v) => (
                        <option key={v} value={v}>
                          {label(v)}
                        </option>
                      ))}
                    </select>
                  ) : s.type === "boolean" ? (
                    <select
                      value={String(val ?? "")}
                      required={required}
                      onChange={(e) => set(key, e.target.value === "true")}
                    >
                      <option value="">Select…</option>
                      <option value="false">No</option>
                      <option value="true">Yes</option>
                    </select>
                  ) : key === "sources" ? (
                    <SourceSelector
                      base={base}
                      value={val}
                      onChange={(v) => set(key, v)}
                    />
                  ) : key === "assertions" ? (
                    <AssertionSelector
                      value={val}
                      onChange={(v) => set(key, v)}
                    />
                  ) : key === "sections" && !area.startsWith("tp-") ? (
                    <Sections value={val} onChange={(v) => set(key, v)} />
                  ) : s.type === "array" || s.type === "object" ? (
                    <textarea
                      aria-label={label(key)}
                      rows={3}
                      placeholder={
                        key === "sources"
                          ? '[{"kind":"record","id":"source UUID"}]'
                          : "[]"
                      }
                      value={
                        typeof val === "string"
                          ? val
                          : JSON.stringify(
                              val ?? (s.type === "array" ? [] : {}),
                              null,
                              2,
                            )
                      }
                      onChange={(e) => set(key, e.target.value)}
                    />
                  ) : s.format === "date" ? (
                    <input
                      type="date"
                      required={required}
                      value={String(val ?? "")}
                      onChange={(e) => set(key, e.target.value)}
                    />
                  ) : s.format === "uuid" ? (
                    <input
                      required={required}
                      value={String(val ?? "")}
                      placeholder="UUID"
                      onChange={(e) => set(key, e.target.value || null)}
                    />
                  ) : s.type === "integer" ||
                    s.type === "number" ||
                    [
                      "benchmark_amount",
                      "selected_percentage",
                      "performance_percentage",
                      "trivial_percentage",
                      "specific_materiality",
                      "financial_impact",
                    ].includes(key) ? (
                    <input
                      type="number"
                      step="any"
                      required={required}
                      value={String(val ?? "")}
                      onChange={(e) =>
                        set(key, e.target.value === "" ? null : e.target.value)
                      }
                    />
                  ) : (
                    <textarea
                      rows={key === "narrative" || key === "conclusion" ? 4 : 2}
                      required={required}
                      value={String(val ?? "")}
                      onChange={(e) => set(key, e.target.value)}
                    />
                  )}
                </label>
              );
            })}
          {area === "materiality" && (
            <div className="audit-notice">
              Percentages are selected by the auditor. The server computes and
              stores the calculation and formula on save; these are not
              ISA-prescribed rates.
            </div>
          )}
          <Button primary type="submit">
            <Save size={14} /> Save version
          </Button>
        </fieldset>
      </form>
      {parseError && (
        <p role="alert" className="error">
          {parseError}
        </p>
      )}
      <ErrorState error={action.error} />
      {record?.body.calculation != null && (
        <Facts data={record.body.calculation as Record<string, unknown>} />
      )}
      {record && (
        <RecordActions base={base} record={record} busy={action.isPending} />
      )}
      {record && area === "evidence" && (
        <EvidenceFiles base={base} record={record} />
      )}
    </div>
  );
}
function Sections({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const sections = (
    Array.isArray(value)
      ? value
      : [{ heading: "Objective and work performed", text: "" }]
  ) as { heading: string; text: string }[];
  return (
    <div className="audit-sections">
      {sections.map((s, i) => (
        <div key={i}>
          <input
            aria-label={`Section ${i + 1} heading`}
            value={s.heading}
            onChange={(e) =>
              onChange(
                sections.map((x, n) =>
                  n === i ? { ...x, heading: e.target.value } : x,
                ),
              )
            }
          />
          <textarea
            aria-label={`Section ${i + 1} text`}
            rows={5}
            value={s.text}
            onChange={(e) =>
              onChange(
                sections.map((x, n) =>
                  n === i ? { ...x, text: e.target.value } : x,
                ),
              )
            }
          />
        </div>
      ))}
      <Button
        type="button"
        onClick={() =>
          onChange([...sections, { heading: "New section", text: "" }])
        }
      >
        Add section
      </Button>
    </div>
  );
}
function RecordActions({
  base,
  record,
  busy = false,
}: {
  base: string;
  record: AuditRecord;
  busy?: boolean;
}) {
  const access = useAPI<Workspace>(base + "/workspace");
  const canAct = (action: string) =>
    record.kind.startsWith("tp-")
      ? !!access.data?.permissions.includes(
          tpPermissions[record.kind]?.[action === "submit" ? 0 : 1],
        )
      : !record.kind.startsWith("vat-") ||
        !!access.data?.permissions.includes(
          ["submit", "archive", "restore"].includes(action)
            ? vatPreparePermissions[record.kind]
            : record.kind === "vat-rule"
              ? "vat.rules.approve"
              : record.kind === "vat-return"
                ? "vat.return.approve"
                : "vat.review",
        );
  const action = useAction();
  const [comments, setComments] = useState("");
  const lifecycleChoices =
    record.status === "ARCHIVED"
      ? ["restore"]
      : [
            "working-papers",
            "risks",
            "vat-invoice",
            "requests",
            "planning",
            "programs",
            "procedures",
          ].includes(record.kind) &&
          ["DRAFT", "IN_PROGRESS"].includes(record.status)
        ? ["archive"]
        : [];
  const choices =
    record.status === "ARCHIVED"
      ? lifecycleChoices
      : [
          ...lifecycleChoices,
          ...(record.kind === "findings"
            ? [
                "UNDER_REVIEW",
                "MANAGEMENT_RESPONSE_PENDING",
                "REMEDIATION_PENDING",
                "RESOLVED",
                "ACCEPTED_UNRESOLVED",
                "CLOSED",
              ]
            : record.kind === "requests"
              ? ["SENT", "ACCEPTED", "MORE_INFORMATION_REQUIRED", "CLOSED"]
              : record.kind === "review-notes"
                ? ["resolve", "clear"]
                : ["submit", "approve", "return", "lock", "reopen"]),
        ];
  return (
    <section className="audit-review-actions">
      <h3>Review & clearance</h3>
      <Status value={record.status} />
      <label>
        Decision comments
        <textarea
          rows={2}
          value={comments}
          onChange={(e) => setComments(e.target.value)}
          placeholder="Record the professional reason for this action"
        />
      </label>
      <div className="toolbar">
        {choices.map((a) => (
          <Button
            key={a}
            disabled={busy || !comments || action.isPending || !canAct(a)}
            onClick={() =>
              action.mutate({
                path: `${base}/records/${record.id}/actions`,
                body: { action: a, comments, version: record.version },
              })
            }
          >
            {label(a)}
          </Button>
        ))}
      </div>
      <ErrorState error={action.error} />
      <small>
        The backend validates permission, current state, version and separation
        of duties.
      </small>
    </section>
  );
}
function AuditHistory({ base, record }: { base: string; record: AuditRecord }) {
  const q = useAPI<{ versions: RecordRow[]; decisions: RecordRow[] }>(
    `${base}/records/${record.id}/history`,
  );
  return (
    <div className="audit-editor">
      <h3>Preserved versions</h3>
      {q.data?.versions.map((v) => (
        <details key={String(v.id)}>
          <summary>
            Version {String(v.version)} · {String(v.created_at)}
          </summary>
          <pre>{JSON.stringify(v.snapshot, null, 2)}</pre>
        </details>
      ))}
      <h3>Human decisions</h3>
      {q.data?.decisions.map((d) => (
        <Facts key={String(d.id)} data={d} />
      ))}
      <ErrorState error={q.error} />
    </div>
  );
}
function EvidenceFiles({
  base,
  record,
}: {
  base: string;
  record: AuditRecord;
}) {
  const tenant = useScope((s) => s.tenant);
  const [downloadError, setDownloadError] = useState("");
  const q = useAPI<{ items: RecordRow[] }>(
    `${base}/evidence-files/${record.id}`,
  );
  const action = useAction();
  return (
    <section>
      <h3>Private evidence versions</h3>
      <label>
        Upload supporting evidence
        <input
          type="file"
          accept=".pdf,.csv,.json,.xml,.txt,.ecr,.mt940,.sta,.sif,.xls,.xlsx,.docx,.png,.jpg,.jpeg,.tif,.tiff,.zip"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              const body = new FormData();
              body.append("file", f);
              action.mutate({
                path: `${base}/evidence-files/${record.id}`,
                body,
              });
            }
          }}
        />
      </label>
      <ErrorState error={action.error} />
      {q.data?.items.map((v) => (
        <div key={String(v.id)} className="audit-evidence-version">
          <strong>{String(v.filename)}</strong>
          <Status value={v.scan_status} />
          <small>
            Version {String(v.number)} · SHA-256 {String(v.sha256)}
          </small>
          {v.id === q.data?.items[0]?.id &&
            v.scan_status === "QUARANTINED" &&
            !["APPROVED", "LOCKED", "REVIEW_REQUIRED"].includes(
              record.status,
            ) && (
              <Button
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({
                    path: `${base}/evidence-files/${record.id}/${v.id}/rescan`,
                    body: {},
                  })
                }
              >
                Rescan retained original
              </Button>
            )}
          {v.scan_status === "CLEAN" && (
            <Button
              onClick={async () => {
                try {
                  const response = await fetch(
                    `/api/backend/${base}/evidence-files/${record.id}/${v.id}/download`,
                    { headers: { "X-Tenant-ID": tenant } },
                  );
                  if (!response.ok)
                    throw new Error("Evidence download denied or unavailable");
                  const url = URL.createObjectURL(await response.blob());
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = String(v.filename);
                  a.click();
                  setTimeout(() => URL.revokeObjectURL(url), 1000);
                } catch (e) {
                  setDownloadError(
                    e instanceof Error ? e.message : "Download failed",
                  );
                }
              }}
            >
              Download verified attachment
            </Button>
          )}
        </div>
      ))}
      {downloadError && <p role="alert">{downloadError}</p>}
      <p className="audit-notice">
        Files remain quarantined until the configured malware scanner reports
        clean. Document existence does not establish evidence sufficiency.
        Rescanning the latest quarantined original saves a new evidence version
        and preserves the previous scan result.
      </p>
    </section>
  );
}
function Completion({ base }: { base: string }) {
  const q = useAPI<{ checks: CompletionCheck[]; ready: boolean }>(
    base + "/completion-checks",
    true,
    true,
  );
  const eid = base.split("/")[1];
  return (
    <>
      <CompletionControls
        eid={eid}
        checks={q.data?.checks || []}
        ready={q.data?.ready}
      />
      <ErrorState error={q.error} />
    </>
  );
}
function AuditAI({ base, tasks }: { base: string; tasks: string[] }) {
  const [task, setTask] = useState(tasks[0]);
  const [sources, setSources] = useState("");
  const [model, setModel] = useState("mock-diagnostic");
  const action = useAction();
  const [error, setError] = useState("");
  return (
    <form
      className="audit-ai-form"
      onSubmit={(e) => {
        e.preventDefault();
        try {
          action.mutate({
            path: base + "/ai-actions",
            body: { task, model, sources: JSON.parse(sources) },
          });
          setError("");
        } catch {
          setError("Enter a valid source-reference array");
        }
      }}
    >
      <label>
        AI action
        <select value={task} onChange={(e) => setTask(e.target.value)}>
          {tasks.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label>
        Approved model
        <input value={model} onChange={(e) => setModel(e.target.value)} />
      </label>
      <label>
        Engagement source references
        <textarea
          required
          value={sources}
          onChange={(e) => setSources(e.target.value)}
          placeholder={'[{"kind":"record","id":"UUID"}]'}
        />
      </label>
      <Button primary disabled={action.isPending}>
        Draft for human review
      </Button>
      <p className="audit-notice">
        Mock diagnostic performs no semantic audit analysis. External providers
        require approved configuration. AI cannot approve records, determine
        evidence sufficiency or issue an opinion.
      </p>
      {error && <p role="alert">{error}</p>}
      <ErrorState error={action.error} />
    </form>
  );
}
function AuditTeam({ base }: { base: string }) {
  const q = useAPI<{ items: RecordRow[] }>(base + "/team");
  const users = useAPI<{ items: RecordRow[] }>(base + "/team-candidates");
  const roles = useAPI<{ items: RecordRow[] }>(
    base + "/team-candidates?kind=roles",
  );
  const action = useAction();
  const [member, setMember] = useState("");
  const [role, setRole] = useState("");
  return (
    <div className="workbench-body">
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate({
            path: base + "/team",
            body: { membership_id: member, role_id: role },
          });
        }}
      >
        <label>
          Team member
          <select
            required
            value={member}
            onChange={(e) => setMember(e.target.value)}
          >
            <option value="">Select member</option>
            {users.data?.items.map((u) => (
              <option key={String(u.id)} value={String(u.id)}>
                {String(u.email)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Engagement role
          <select
            required
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="">Select role</option>
            {roles.data?.items
              .filter(
                (r) =>
                  !String(r.name).startsWith("Client") &&
                  !String(r.name).startsWith("Platform"),
              )
              .map((r) => (
                <option key={String(r.id)} value={String(r.id)}>
                  {String(r.name)}
                </option>
              ))}
          </select>
        </label>
        <Button primary>Assign role</Button>
      </form>
      <ErrorState error={action.error} />
      <FinancialDataGrid
        name="audit-team"
        rows={q.data?.items || []}
        loading={q.isLoading}
        error={q.error}
        columns={[
          column("membership_id", "Membership", 300),
          column("role_id", "Role", 300),
          column("active", "Active", 100),
          column("expires_at", "Access expiry", 200),
        ]}
      />
    </div>
  );
}

function InstantiateMethodology({ base }: { base: string }) {
  const [version, setVersion] = useState("");
  const action = useAction();
  return (
    <form
      className="audit-ai-form"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate({ path: `${base}/methodology/${version}/instantiate` });
      }}
    >
      <label>
        Approved methodology version UUID
        <input
          required
          value={version}
          onChange={(e) => setVersion(e.target.value)}
        />
      </label>
      <Button>Instantiate approved procedures</Button>
      <ErrorState error={action.error} />
      <p className="audit-notice">
        A matching, independently approved reporting-period methodology is
        required. Procedures remain subject to engagement review.
      </p>
    </form>
  );
}

function ReviewQueue({ base, id }: { base: string; id: string }) {
  const q = useAPI<Page<AuditRecord>>(base + "/review-queue", true, true);
  return (
    <section className="audit-completion">
      <h3>Documents awaiting human review</h3>
      <ErrorState error={q.error} />
      {q.data?.items.map((r) => (
        <div key={r.id}>
          <FileCheck2 size={14} />
          <Link href={`/engagements/${id}/${r.kind}`}>
            {r.reference} · {r.title}
          </Link>
          <Status value={r.status} />
        </div>
      ))}
      {!q.data?.items.length && (
        <p>No accessible review documents in this engagement.</p>
      )}
    </section>
  );
}

function SourceSelector({
  base,
  value,
  onChange,
}: {
  base: string;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const q = useAPI<{ items: { id: string; kind: string; label: string }[] }>(
    base + "/linkable-sources",
  );
  const selected = (Array.isArray(value) ? value : []) as {
    id: string;
    kind: string;
  }[];
  return (
    <div>
      <select
        aria-label="Link source record"
        value=""
        onChange={(e) => {
          const source = q.data?.items.find((r) => r.id === e.target.value);
          if (source && !selected.some((s) => s.id === source.id))
            onChange([...selected, { kind: source.kind, id: source.id }]);
        }}
      >
        <option value="">Choose engagement source…</option>
        {q.data?.items.map((r) => (
          <option key={r.id} value={r.id}>
            {r.label}
          </option>
        ))}
      </select>
      {selected.map((source) => (
        <div className="audit-source-link" key={source.id}>
          <span>
            {q.data?.items.find((r) => r.id === source.id)?.label ||
              source.kind + " reference"}
          </span>
          <Button
            type="button"
            aria-label="Remove source link"
            onClick={() => onChange(selected.filter((s) => s.id !== source.id))}
          >
            ×
          </Button>
        </div>
      ))}
      <details>
        <summary>Advanced source references</summary>
        <textarea
          aria-label="sources"
          rows={3}
          value={
            typeof value === "string"
              ? value
              : JSON.stringify(selected, null, 2)
          }
          onChange={(e) => onChange(e.target.value)}
        />
      </details>
    </div>
  );
}
function AssertionSelector({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const selected = (Array.isArray(value) ? value : []) as string[];
  return (
    <div className="audit-assertions">
      {[
        "existence",
        "completeness",
        "accuracy",
        "valuation",
        "rights_and_obligations",
        "occurrence",
        "cut_off",
        "classification",
        "presentation",
      ].map((a) => (
        <span key={a}>
          <input
            aria-label={label(a)}
            type="checkbox"
            checked={selected.includes(a)}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...selected, a]
                  : selected.filter((s) => s !== a),
              )
            }
          />
          {label(a)}
        </span>
      ))}
    </div>
  );
}

function SamplingWorkbench({ base }: { base: string }) {
  const sources = useAPI<{
    items: { id: string; kind: string; label: string }[];
  }>(base + "/linkable-sources");
  const [snapshot, setSnapshot] = useState("");
  const [method, setMethod] = useState("random");
  const [size, setSize] = useState("10");
  const [seed, setSeed] = useState("42");
  const [threshold, setThreshold] = useState("0");
  const [rationale, setRationale] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const action = useAction<RecordRow>();
  return (
    <form
      className="audit-ai-form"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate({
          path: base + "/select-sample",
          body: {
            snapshot_id: snapshot,
            method,
            size: Number(size),
            seed: Number(seed),
            threshold,
            selected_line_ids: chosen,
            selection_rationale: rationale,
          },
        });
      }}
    >
      <h3>Reproducible population selection</h3>
      <div className="audit-field-pair">
        <label>
          Committed population
          <select
            required
            value={snapshot}
            onChange={(e) => setSnapshot(e.target.value)}
          >
            <option value="">Choose snapshot…</option>
            {sources.data?.items
              .filter((r) => r.kind === "snapshot")
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
          </select>
        </label>
        <label>
          Selection method
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            {[
              "random",
              "systematic",
              "mus",
              "high_value",
              "judgmental",
              "full",
            ].map((m) => (
              <option key={m} value={m}>
                {label(m)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Human-selected sample size
          <input
            type="number"
            required
            min="1"
            max="1000000"
            value={size}
            onChange={(e) => setSize(e.target.value)}
          />
        </label>
        <label>
          Reproduction seed
          <input
            type="number"
            min="0"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
        <label>
          High-value threshold
          <input
            type="number"
            min="0"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
          />
        </label>
      </div>
      {method === "judgmental" && (
        <>
          <label>
            Selection rationale
            <textarea
              required
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
            />
          </label>
          <label>
            Explicit source transactions
            <select
              multiple
              required
              value={chosen}
              onChange={(e) =>
                setChosen(Array.from(e.target.selectedOptions, (o) => o.value))
              }
            >
              {sources.data?.items
                .filter((r) => r.kind === "journal")
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
            </select>
          </label>
        </>
      )}
      <Button primary disabled={action.isPending}>
        Select population items
      </Button>
      <ErrorState error={action.error} />
      {action.data && <Facts data={action.data} />}
      <p className="audit-notice">
        Record the selected run reference in the testing record. Sample size is
        a human methodology input; selection does not establish audit assurance.
      </p>
    </form>
  );
}
