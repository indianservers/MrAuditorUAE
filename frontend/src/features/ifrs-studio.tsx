"use client";
import { useState } from "react";
import Link from "next/link";
import { AuditStudio } from "./audit-studio";
import { FinancialReview } from "./financial-review";
import { GroupSourceLineage } from "./group-source-lineage";
import { ReportingRecordSelect } from "./reporting-record-select";
import { AccountingScheduleResults } from "./accounting-schedule-results";
import { AccountingExecutionNotice } from "./accounting-execution-notice";
import { money } from "@/lib/formatting/money";
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
import type { Page, RecordRow, Engagement } from "@/types/models";

export const ifrsAreas = [
  ["dashboard", "IFRS Reporting Dashboard", "profile"],
  ["designer", "Financial Statement Designer", "mapping"],
  ["trial-balance", "Adjusted Trial Balance", "profile"],
  ["adjustments", "IFRS Adjustment Workbench", "adjustment"],
  ["cash-flow", "Cash Flow Statement Studio", "cash-flow"],
  ["notes", "Financial Statement Notes Editor", "note"],
  ["ecl", "IFRS 9 ECL Studio", "ecl"],
  ["revenue", "IFRS 15 Revenue Recognition Studio", "revenue"],
  ["leases", "IFRS 16 Lease Accounting Studio", "lease"],
  ["deferred-tax", "IAS 12 Deferred Tax Studio", "deferred-tax"],
  ["fixed-assets", "Fixed Asset & Depreciation Studio", "fixed-assets"],
  ["inventory", "Inventory Costing & NRV", "inventory"],
  [
    "employee-benefits",
    "Payroll & Benefit Accounting Bridge",
    "employee-benefits",
  ],
  ["policies", "Accounting Policies & Judgments", "accounting-policy"],
  ["impairment", "Impairment & Provisions Studio", "impairment"],
  ["consolidation", "Group Consolidation Studio", "consolidation"],
  ["intercompany", "Intercompany Reconciliation", "consolidation"],
  ["disclosures", "IFRS Disclosure Compliance Center", "disclosure"],
  ["ai", "AI IFRS Technical Review Studio", "ai"],
] as const;
export function IFRSStudio({
  id,
  area = "dashboard",
}: {
  id?: string;
  area?: string;
}) {
  const tenant = useScope((s) => s.tenant);
  const engagements = useAPI<Page<Engagement>>("engagements?limit=100", !id);
  const selected = ifrsAreas.find((a) => a[0] === area);
  const [subkind, setSubkind] = useState<{
    engagement: string;
    area: string;
    kind: string;
  } | null>(null);
  if (!id)
    return (
      <>
        <PageHeader
          title="IFRS Reporting"
          eyebrow="Financial reporting"
          description="Choose an engagement to prepare sourced, versioned financial statements."
        />
        <div className="workbench-body">
          {engagements.error && <ErrorState error={engagements.error} />}
          {engagements.data?.items.map((e) => (
            <p key={e.id}>
              <Link href={`/ifrs/${e.id}/dashboard`}>{e.name}</Link>{" "}
              <Status value={e.status} />
            </p>
          ))}
          {!engagements.data?.items.length && (
            <Empty title="Select a reporting engagement">
              Create an engagement from its legal entity to begin.
            </Empty>
          )}
        </div>
      </>
    );
  if (!selected)
    return (
      <Empty title="Unknown reporting workspace">
        Choose a reporting workspace.
      </Empty>
    );
  const kind =
    subkind?.engagement === id && subkind.area === area
      ? subkind.kind
      : selected[2];
  const selectSubkind = (kind: string) =>
    setSubkind({ engagement: id, area, kind });
  return (
    <>
      <PageHeader
        title={selected[1]}
        eyebrow="IFRS / Financial reporting"
        description="Approved assumptions · Deterministic calculations · Independent professional review"
      />
      <nav className="audit-tabs" aria-label="IFRS workspaces">
        {ifrsAreas.map(([key, name]) => (
          <Link
            key={key}
            href={`/ifrs/${id}/${key}`}
            aria-current={area === key ? "page" : undefined}
          >
            {name}
          </Link>
        ))}
      </nav>
      <ReportingRuns key={`${tenant}:${id}:${area}:${kind}`} id={id} area={area} kind={kind} />
      {area === "impairment" && (
        <div className="toolbar">
          <label>
            Calculation type{" "}
            <select value={kind} onChange={(e) => selectSubkind(e.target.value)}>
              <option value="impairment">Impairment</option>
              <option value="provision">Provisions</option>
            </select>
          </label>
        </div>
      )}
      {area === "ecl" && (
        <div className="toolbar">
          <label>
            Instrument workbench{" "}
            <select value={kind} onChange={(e) => selectSubkind(e.target.value)}>
              <option value="ecl">Expected credit losses</option>
              <option value="instrument">
                Effective interest / amortised cost
              </option>
            </select>
          </label>
        </div>
      )}
      {area === "designer" && (
        <div className="toolbar">
          <label>
            Reporting workflow{" "}
            <select value={kind} onChange={(e) => selectSubkind(e.target.value)}>
              <option value="mapping">Account mapping</option>
              <option value="financials">Financial package approval</option>
            </select>
          </label>
        </div>
      )}
      {area === "disclosures" && <Standards />}
      {area === "ai" ? (
        <IFRSAI id={id} />
      ) : (
        <AuditStudio key={kind} id={id} area={`ifrs-${kind}`} ifrs />
      )}
    </>
  );
}
function Standards() {
  const q = useAPI<{ items: RecordRow[] }>("ifrs/standards");
  return (
    <details className="workbench-body">
      <summary>
        Versioned standards registry — original metadata, no licensed full text
      </summary>
      <FinancialDataGrid
        rows={q.data?.items || []}
        loading={q.isLoading}
        columns={[
          column("code", "Standard"),
          column("title", "Title", 200, { flex: 2 }),
          column("rule_version", "Version"),
          column("effective_date", "Effective"),
          column("support_status", "Support"),
        ]}
      />
    </details>
  );
}
type Run = RecordRow & {
  id: string;
  kind: string;
  results: Record<string, unknown>;
  dependencies_current: boolean;
  sha256: string;
};
function ReportingRuns({
  id,
  area,
  kind,
}: {
  id: string;
  area: string;
  kind: string;
}) {
  const base = `ifrs/engagements/${id}`;
  const [profile, setProfile] = useState("");
  const [record, setRecord] = useState("");
  const [rid, setRid] = useState("");
  const [line, setLine] = useState<RecordRow | null>(null);
  const [section, setSection] = useState("assets");
  const result = useAPI<Run>(`${base}/runs/${rid}`, !!rid);
  const atb = useAPI<{ lines: RecordRow[] }>(
    `${base}/adjusted-trial-balance/${profile}`,
    area === "trial-balance" && !!profile,
  );
  const action = useAction<Run>();
  const tenant = useScope((s) => s.tenant);
  const [downloadError, setDownloadError] = useState("");
  async function download(format: string) {
    setDownloadError("");
    try {
      const response = await fetch(
        `/api/backend/${base}/runs/${rid}/export/${format}`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download =
        response.headers
          .get("Content-Disposition")
          ?.match(/filename="([^"]+)"/)?.[1] ||
        `AuditOS-${rid}-draft.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError(String(e));
    }
  }
  const data = result.data?.results;
  const usesPresentation = !!data?.presentation_lines;
  const lines: RecordRow[] = (
    (data?.presentation_lines || data?.lines || []) as RecordRow[]
  ).map((line) => ({
    ...line,
    id: String(line.line_code || line.code || line.id),
  }));
  const checks = (
    data?.validation as { checks?: { code: string; passed: boolean }[] }
  )?.checks;
  return (
    <section
      className="workbench-body ifrs-report"
      aria-label="Reporting calculations"
    >
      <div className="toolbar">
        <ReportingRecordSelect
          path={`${base}/records/profile`}
          label="Reporting profile"
          value={profile}
          onChange={setProfile}
        />
        <Button
          disabled={!profile || action.isPending}
          onClick={async () => {
            const r = await action.mutateAsync({
              path: `${base}/financial-statements/${profile}`,
            });
            setRid(r.id);
          }}
        >
          Generate statements
        </Button>
        <ReportingRecordSelect
          path={`${base}/records/${kind}`}
          label="Approved assumptions"
          value={record}
          onChange={setRecord}
        />
        <Button
          disabled={
            !record ||
            action.isPending ||
            ![
              "lease",
              "ecl",
              "instrument",
              "revenue",
              "deferred-tax",
              "fixed-assets",
              "inventory",
              "employee-benefits",
              "impairment",
              "provision",
              "consolidation",
            ].includes(kind)
          }
          onClick={async () => {
            const r = await action.mutateAsync({
              path: `${base}/${["consolidation", "intercompany"].includes(area) ? "consolidation" : "calculate"}/${record}`,
            });
            setRid(r.id);
          }}
        >
          Calculate approved inputs
        </Button>
        <ReportingRecordSelect
            path={`${base}/runs`}
            label="Immutable version"
            value={rid}
            onChange={(id) => {
              setRid(id);
              setLine(null);
            }}
            runs
        />
      </div>
      {action.error && <ErrorState error={action.error} />}
      {result.error && <ErrorState error={result.error} />}
      {atb.error && <ErrorState error={atb.error} />}
      {area === "trial-balance" && (
        <FinancialDataGrid
          rows={atb.data?.lines || []}
          loading={atb.isLoading}
          columns={[
            column("code", "Account"),
            column("name", "Name", 200, { flex: 2 }),
            amount("original", "Source"),
            amount("adjustment", "Approved overlay"),
            amount("adjusted", "Adjusted"),
          ]}
        />
      )}
      {data && (
        <>
          <AccountingExecutionNotice
            receipt={
              data.execution as Parameters<
                typeof AccountingExecutionNotice
              >[0]["receipt"]
            }
          />
          {[
            "lease",
            "ecl",
            "fixed-assets",
            "inventory",
            "impairment",
            "employee-benefits",
            "deferred-tax",
          ].includes(result.data?.kind || "") && (
            <JournalProposer
              key={rid}
              base={base}
              rid={rid}
              profile={profile}
              kind={result.data?.kind || ""}
            />
          )}
          <div className="toolbar">
            <strong>
              {String(data.entity || result.data?.kind)} ·{" "}
              {String(data.currency || "")}
            </strong>
            <Status
              value={result.data?.dependencies_current ? "CURRENT" : "STALE"}
            />
            <Button onClick={() => result.refetch()}>
              Validate current dependencies
            </Button>
            {["pdf", "xlsx", "docx", "json"].map((f) => (
              <Button key={f} onClick={() => download(f)}>
                Export {f.toUpperCase()}
              </Button>
            ))}
          </div>
          {downloadError && <p role="alert">{downloadError}</p>}
          {data.comparative_status ===
            "PRIOR_REPORTED_GROUP_AMOUNTS_RETAINED" && (
            <section
              aria-label="Prior group comparative source"
              className="group-comparative-source"
            >
              <h3>Prior reported group figures</h3>
              <p>
                These figures retain the selected prior group calculation and
                its original translation. They do not establish an audited
                comparative or complete group report. Membership, ownership,
                currency and chart classification must remain compatible.
              </p>
              <Facts data={data.comparative as RecordRow} />
            </section>
          )}
          {result.data?.kind === "financials" && (
            <FinancialReview
              key={rid}
              base={base}
              rid={rid}
              precision={Number(data.precision ?? 2)}
            />
          )}
          {lines.length > 0 ? (
            <div className="ifrs-designer">
              <nav aria-label="Statement sections">
                {[
                  "assets",
                  "liabilities",
                  "equity",
                  "income",
                  "expenses",
                  "oci",
                ].map((s) => (
                  <Button key={s} onClick={() => setSection(s)}>
                    {s.toUpperCase()}
                  </Button>
                ))}
                <p>
                  {usesPresentation
                    ? "Figures use the approved presentation precision and credit-section signs. Select a line to trace its unrounded source values."
                    : "Figures use debit-positive source signs. Presentation exports convert credit sections."}
                </p>
                <Facts data={(data.totals || {}) as RecordRow} />
              </nav>
              <article>
                <h2>{String(data.entity)}</h2>
                <p>
                  {String(data.period_start)} – {String(data.period_end)} ·{" "}
                  {String(data.presentation)}
                </p>
                <FinancialDataGrid
                  rows={lines.filter((l) => l.section === section)}
                  columns={[
                    column("label", "Financial statement line", 200, {
                      flex: 2,
                    }),
                    {
                      ...amount(
                        usesPresentation ? "display_current" : "current",
                        "Current",
                        String(data.currency || ""),
                      ),
                      valueFormatter: (p) =>
                        money(p.value, Number(data.precision ?? 2)),
                    },
                    data.comparative
                      ? {
                          ...amount(
                            usesPresentation
                              ? "display_comparative"
                              : "comparative",
                            "Comparative",
                            String(data.currency || ""),
                          ),
                          valueFormatter: (p) =>
                            money(p.value, Number(data.precision ?? 2)),
                        }
                      : column("comparative", "Comparative", 140, {
                          valueFormatter: () => "Not supplied",
                        }),
                    column("note", "Note"),
                  ]}
                  onSelect={setLine}
                />
                <details>
                  <summary>Notes and supporting schedules</summary>
                  <Facts data={{ notes: data.notes || [] }} />
                </details>
              </article>
              <aside>
                <h3>Validation & source trace</h3>
                {checks?.map((c) => (
                  <p key={c.code}>
                    {c.passed ? "✓" : "!"} {c.code.replaceAll("_", " ")}
                  </p>
                ))}
                {line ? (
                  <Facts
                    data={
                      result.data?.kind === "consolidation"
                        ? Object.fromEntries(
                            Object.entries(line).filter(
                              ([key]) =>
                                key !== "source_accounts" &&
                                key !== "comparative_source_accounts",
                            ),
                          )
                        : line
                    }
                  />
                ) : (
                  <p>
                    Select a financial line to trace mapped source accounts.
                  </p>
                )}
              </aside>
            </div>
          ) : ["inventory", "employee-benefits"].includes(result.data?.kind || "") ? (
            <AccountingScheduleResults
              key={rid}
              kind={result.data?.kind || ""}
              data={data}
            />
          ) : (
            <Facts data={data} />
          )}
          {result.data?.kind === "consolidation" && line && (
            <GroupSourceLineage
              key={`${rid}:${String(line.line_code)}`}
              current={line.source_accounts}
              comparative={line.comparative_source_accounts}
              currency={String(data.currency || "")}
            />
          )}
          <p className="ifrs-run-id">
            Run {rid} · SHA-256 {result.data?.sha256}
          </p>
        </>
      )}
      {!data && area !== "trial-balance" && (
        <Empty title="Source-linked reporting">
          Prepare and independently approve a profile, mapping and assumptions
          below. Generate an immutable reporting run to review statements,
          schedules and validation findings.
        </Empty>
      )}
    </section>
  );
}
function JournalProposer({
  base,
  rid,
  profile,
  kind,
}: {
  base: string;
  rid: string;
  profile: string;
  kind: string;
}) {
  const [debit, setDebit] = useState(""),
    [credit, setCredit] = useState(""),
    [date, setDate] = useState(""),
    [reason, setReason] = useState(""),
    [reference, setReference] = useState(""),
    [allowance, setAllowance] = useState("0");
  const [component, setComponent] = useState("primary");
  const chart = useAPI<{ lines: RecordRow[] }>(
    `${base}/adjusted-trial-balance/${profile}`,
    !!profile,
  );
  const action = useAction<RecordRow>();
  return (
    <details>
      <summary>Prepare controlled calculation journal</summary>
      <p>
        The amount comes from the immutable run. Lease proposals cover initial
        liability recognition; ECL proposals deduct the existing allowance.
        Human-selected accounts and independent approval are required.
      </p>
      <div className="toolbar">
        <label>
          Journal reference
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        </label>
        {["deferred-tax", "employee-benefits"].includes(kind) && (
          <label>
            Journal movement
            <select
              value={component}
              onChange={(e) => setComponent(e.target.value)}
            >
              <option value="primary">Profit or loss</option>
              <option value="oci">Other comprehensive income</option>
              {kind === "deferred-tax" && (
                <option value="current_tax">Approved current tax</option>
              )}
            </select>
          </label>
        )}
        <label>
          Debit account
          <select value={debit} onChange={(e) => setDebit(e.target.value)}>
            <option value="">Choose account</option>
            {chart.data?.lines.map((r) => (
              <option key={String(r.code)} value={String(r.code)}>
                {String(r.code)} · {String(r.name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Credit account
          <select value={credit} onChange={(e) => setCredit(e.target.value)}>
            <option value="">Choose account</option>
            {chart.data?.lines.map((r) => (
              <option key={String(r.code)} value={String(r.code)}>
                {String(r.code)} · {String(r.name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Adjustment date
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        {kind === "ecl" && (
          <label>
            Existing ECL allowance
            <input
              value={allowance}
              onChange={(e) => setAllowance(e.target.value)}
              inputMode="decimal"
            />
          </label>
        )}
        <label>
          Accounting rationale
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <Button
          disabled={
            !profile ||
            !debit ||
            !credit ||
            !date ||
            !reference ||
            !reason ||
            action.isPending
          }
          onClick={() =>
            action.mutate({
              path: `${base}/runs/${rid}/propose-journal`,
              body: {
                profile_id: profile,
                reference,
                debit_account: debit,
                credit_account: credit,
                adjustment_date: date,
                rationale: reason,
                existing_allowance: allowance,
                component,
              },
            })
          }
        >
          Prepare proposed journal
        </Button>
      </div>
      {action.error && <ErrorState error={action.error} />}{" "}
      {action.data && <Facts data={action.data} />}
    </details>
  );
}
function IFRSAI({ id }: { id: string }) {
  const base = `ifrs/engagements/${id}`;
  const w = useAPI<{ ai_tasks: string[] }>(base + "/workspace");
  const sources = useAPI<Page<RecordRow>>(
    `engagements/${id}/audit/ifrs-note?limit=100`,
  );
  const [task, setTask] = useState("disclosure_gaps"),
    [source, setSource] = useState("");
  const action = useAction<RecordRow>();
  const decisions = useAction<RecordRow>();
  const suggestions = useAPI<Page<RecordRow>>(base + "/records/ai");
  const [comments, setComments] = useState("");
  const [model, setModel] = useState("mock-diagnostic");
  return (
    <section className="workbench-body">
      <h2>Source-grounded technical assistance</h2>
      <p>
        The diagnostic provider verifies the workflow. Professional
        interpretations require an approved provider and source review. Licensed
        IFRS text is not included.
      </p>
      <div className="toolbar">
        <label>
          Approved model name
          <input value={model} onChange={(e) => setModel(e.target.value)} />
        </label>
        <label>
          Task{" "}
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            {w.data?.ai_tasks.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Note source{" "}
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">Choose source note</option>
            {sources.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {String(s.reference)}
              </option>
            ))}
          </select>
        </label>
        <Button
          disabled={!source || action.isPending}
          onClick={() =>
            action.mutate({
              path: base + "/ai-actions",
              body: { task, model, sources: [{ kind: "record", id: source }] },
            })
          }
        >
          Request technical draft
        </Button>
      </div>
      {action.error && <ErrorState error={action.error} />}
      {action.data && <Facts data={action.data} />}
      <label>
        Reviewer decision rationale
        <input value={comments} onChange={(e) => setComments(e.target.value)} />
      </label>
      {decisions.error && <ErrorState error={decisions.error} />}
      {suggestions.data?.items.map((s) => (
        <details key={s.id}>
          <summary>
            {String(s.title)} · {String(s.status)}
          </summary>
          <Facts data={s} />
          {["approve", "return"].map((action) => (
            <Button
              key={action}
              disabled={
                !comments ||
                s.status !== "REVIEW_REQUIRED" ||
                decisions.isPending
              }
              onClick={() =>
                decisions.mutate({
                  path: `engagements/${id}/audit/records/${s.id}/actions`,
                  body: { action, version: s.version, comments },
                })
              }
            >
              {action === "approve"
                ? "Approve reviewed suggestion"
                : "Return suggestion"}
            </Button>
          ))}
        </details>
      ))}
    </section>
  );
}
