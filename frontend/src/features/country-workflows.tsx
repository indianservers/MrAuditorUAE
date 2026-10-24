"use client";

import Link from "next/link";
import { useState } from "react";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { PageHeader } from "./shared";

type Choice = {
  id: string;
  label: string;
  kind: string;
  version: number;
  freshness: string;
  review_status: string;
  table_type?: string;
  native_format?: string;
  table_kind?: string;
  evidence_version_id?: string;
};
type Workflow = {
  id: string;
  title: string;
  available: boolean;
  roles: Record<string, string>;
};
type Result = {
  id: string;
  version: number;
  kind: string;
  freshness: string;
  collection_totals?: Record<string, number>;
  body: {
    workflow?: string;
    expected_total?: string;
    reported_total?: string;
    expected_total_complete?: boolean;
    title: string;
    review_status: string;
    execution_mode?: string;
    language_model_dependency?: boolean;
    blocked?: boolean;
    exception_count?: number;
    table_type?: string;
    rows: Record<string, unknown>[];
    limitations?: string[];
    control_comparison?: Record<string, string>;
    native_metadata?: Record<string, unknown>;
    supporting_table_id?: string;
    supporting_scope_assessment?: string;
    supporting_side?: string;
    supporting_balance_date?: string;
    supporting_amount_sign?: string;
    csv_mapping?: {
      applied_columns: Record<string, string>;
      ignored_columns: string[];
      rationale: string;
      amount_derivation?: string;
      debit_column?: string | null;
      credit_column?: string | null;
    };
    country_guidance?: Record<string, unknown>;
    population_completeness: string;
    nil_population?: boolean;
    nil_declarations?: Record<string, string>;
    operations_execution?: {
      contract_version: string;
      population_completeness: string;
      execution_mode: string;
    };
    payment_proposals?: {
      order_id: string;
      vendor: string;
      currency: string;
      amount: string;
      state: string;
      holds: string[];
    }[];
  };
};
const text = (v: unknown) =>
  v == null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
const moneyTables = [
  "cash-payments",
  "item-allocations",
  "payroll-bases",
  "transactions",
  "tax-documents",
  "obligations",
  "return-boxes",
  "audit-open-items",
  "settlements",
  "balance-controls",
  "confirmations",
  "cutoff-documents",
  "purchase-lines",
  "expense-claims",
  "benefit-employees",
  "trade-lines",
  "excise-movements",
  "excise-returns",
  "escrow-entries",
  "billing-lines",
  "accounting-controls",
];

export function CountryWorkflows({
  eid,
  mode,
}: {
  eid: string;
  mode: "workflow-source" | "country-workflow";
}) {
  const prefix = `intelligence/engagements/${eid}`;
  const tenant = useScope((s) => s.tenant);
  const canUseVAT = useCan("vat.read");
  const config = useAPI<{
    country: string;
    items: Workflow[];
    source_formats?: {
      id: string;
      label: string;
      available: boolean;
      table_type: string | null;
      description: string;
    }[];
    check_templates: Record<string, string[]>;
    scenarios: {
      id: string;
      title: string;
      workflow: string;
      country: string;
      expected: Record<string, unknown>;
    }[];
    source_contracts: Record<
      string,
      Record<string, { required: boolean; type: string }>
    >;
  }>(`${prefix}/country-workflows`);
  const inputs = useAPI<{
    evidence: { id: string; label: string; scan_status: string }[];
    snapshots: { id: string; label: string }[];
  }>(`${prefix}/inputs`);
  const results = useAPI<{ items: Choice[] }>(
    `${prefix}/events?limit=100&newest=true`,
    true,
    true,
  );
  const jobs = useAPI<{
    items: {
      id: string;
      operation: string;
      status: string;
      result_id?: string;
      error_details?: { message: string };
    }[];
  }>(`${prefix}/jobs`, true, true);
  const [selected, setSelected] = useState("");
  const [showAllJobs, setShowAllJobs] = useState(false);
  const [offset, setOffset] = useState(0);
  const detail = useAPI<Result>(
    `${prefix}/events/${selected}?offset=${offset}&limit=100`,
    !!selected,
  );
  const [workflow, setWorkflow] = useState("bank-brs");
  const [invoiceFaceAmounts, setInvoiceFaceAmounts] = useState(false);
  const [tableType, setTableType] = useState("transactions");
  const [sourceOrigin, setSourceOrigin] = useState("evidence");
  const [supportingTable, setSupportingTable] = useState("");
  const [supportingScope, setSupportingScope] = useState("");
  const [supportingSide, setSupportingSide] = useState("receivable");
  const [supportingBalanceDate, setSupportingBalanceDate] = useState("");
  const [supportingAmountSign, setSupportingAmountSign] =
    useState("as-reported");
  const [vatRun, setVATRun] = useState("");
  const vatRuns = useAPI<{ items: { id: string; label: string }[] }>(
    `${prefix}/vat-sources`,
    sourceOrigin === "vat" && canUseVAT,
  );
  const [sourceFormat, setSourceFormat] = useState("canonical-csv");
  const [customColumns, setCustomColumns] = useState(false);
  const [csvColumns, setCSVColumns] = useState<Record<string, string>>({});
  const [ignoredColumns, setIgnoredColumns] = useState("");
  const [mappingRationale, setMappingRationale] = useState("");
  const [csvDelimiter, setCSVDelimiter] = useState(",");
  const [amountDerivation, setAmountDerivation] = useState("none");
  const [debitColumn, setDebitColumn] = useState("");
  const [creditColumn, setCreditColumn] = useState("");
  const [statementIdentifier, setStatementIdentifier] = useState("");
  const [employerRegistration, setEmployerRegistration] = useState("");
  const [obligationDue, setObligationDue] = useState("");
  const [obligationPeriod, setObligationPeriod] = useState("");
  const [expectedMembers, setExpectedMembers] = useState("");
  const [expectedDocuments, setExpectedDocuments] = useState("");
  const [ruleDocument, setRuleDocument] = useState("");
  const [gstRegistration, setGSTRegistration] = useState("");
  const [gstDirection, setGSTDirection] = useState("purchase");
  const [gstPeriod, setGSTPeriod] = useState("");
  const [ledgerSnapshot, setLedgerSnapshot] = useState("");
  const [ledgerAccount, setLedgerAccount] = useState("");
  const [ledgerFrom, setLedgerFrom] = useState("");
  const [ledgerKind, setLedgerKind] = useState("transactions");
  const [balanceSide, setBalanceSide] = useState("receivable");
  const accounts = useAPI<{
    items: { id: string; code: string; name: string }[];
  }>(`${prefix}/accounts?snapshot_id=${ledgerSnapshot}`, !!ledgerSnapshot);
  const [evidence, setEvidence] = useState("");
  const [label, setLabel] = useState("");
  const [expectedRows, setExpectedRows] = useState("1");
  const [nilReason, setNilReason] = useState("");
  const [totals, setTotals] = useState("AED=0");
  const [sources, setSources] = useState<Record<string, string>>({});
  const [asOf, setAsOf] = useState("");
  const [reviewThrough, setReviewThrough] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [taxYear, setTaxYear] = useState("");
  const [requiredChecks, setRequiredChecks] = useState("");
  const [requiredBoxes, setRequiredBoxes] = useState("");
  const [subjects, setSubjects] = useState("");
  const [account, setAccount] = useState("");
  const [currency, setCurrency] = useState("AED");
  const [balances, setBalances] = useState<Record<string, string>>({});
  const [comments, setComments] = useState("");
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<Error | null>(null);
  const [showRuleProvenance, setShowRuleProvenance] = useState(false);
  const action = useAction<{ id: string }>();
  const available = config.data?.items.filter((w) => w.available) || [];
  const chosen = available.find((w) => w.id === workflow);
  const formatInfo = config.data?.source_formats?.find(
    (f) => f.id === sourceFormat,
  );
  const body = detail.data?.body;
  const rows = body?.rows || [];
  const allColumns = [
    ...new Set(rows.flatMap((row) => Object.keys(row))),
  ].filter((k) => !["auditor", "auditor_at"].includes(k));
  const columns =
    body?.workflow === "india-payroll-rules" && !showRuleProvenance
      ? [
          "subject",
          "period",
          "component",
          "currency",
          "assessed_base",
          "expected_amount",
          "reported_amount",
          "difference",
          "state",
        ].filter((key) => allColumns.includes(key))
      : ["india-gst", "uae-vat"].includes(body?.workflow || "") &&
          !showRuleProvenance
        ? [
            "counterparty",
            "reference",
            "document_type",
            "component",
            "currency",
            "books_tax",
            "return_tax",
            "tax_difference",
            "net_difference",
            "state",
            "source_review_reasons",
          ].filter((key) => allColumns.includes(key))
        : allColumns;
  async function run() {
    setLocalError(null);
    try {
      let payload: Record<string, unknown>;
      const operation =
        mode === "workflow-source" && sourceOrigin === "vat"
          ? "workflow-vat"
          : mode === "workflow-source" && sourceOrigin === "ledger"
            ? "workflow-ledger"
            : mode;
      if (
        operation === "workflow-source" &&
        sourceFormat === "canonical-csv" &&
        sourceOrigin === "evidence" &&
        customColumns &&
        mappingRationale.trim().length < 10
      ) {
        throw new Error(
          "Record a column mapping and exclusion assessment of at least ten characters.",
        );
      }
      if (operation === "workflow-vat") {
        payload = { run_id: vatRun, label };
      } else if (operation === "workflow-ledger") {
        payload = {
          ...(ledgerKind === "balance-controls"
            ? { source_kind: ledgerKind, balance_side: balanceSide }
            : {}),
          snapshot_id: ledgerSnapshot,
          account_ids: [ledgerAccount],
          bank_account: account,
          currency,
          label,
          as_of: asOf,
          ...(ledgerFrom && ledgerKind === "transactions"
            ? { from_date: ledgerFrom }
            : {}),
          ...(nilReason && ledgerKind === "transactions"
            ? { nil_reason: nilReason }
            : {}),
        };
      } else if (mode === "workflow-source") {
        const controls: Record<string, string> = {};
        if (moneyTables.includes(tableType)) {
          for (const pair of totals.split(",")) {
            const [code, value, extra] = pair.trim().split("=");
            if (
              !/^[A-Z]{3}$/.test(code || "") ||
              !value ||
              extra ||
              code in controls
            )
              throw new Error(
                "Enter unique currency totals, for example AED=1250.50,USD=200",
              );
            controls[code] = value;
          }
        }
        payload = ["supporting", "supporting-items"].includes(sourceOrigin)
          ? {
              supporting_table_id: supportingTable,
              evidence_version_id:
                results.data?.items.find((item) => item.id === supportingTable)
                  ?.evidence_version_id || "",
              supporting_scope_assessment: supportingScope,
              account_identifier: account,
              table_type:
                sourceOrigin === "supporting-items"
                  ? "audit-open-items"
                  : "transactions",
              ...(sourceOrigin === "supporting-items"
                ? {
                    supporting_side: supportingSide,
                    supporting_balance_date: supportingBalanceDate,
                    supporting_amount_sign: supportingAmountSign,
                  }
                : {}),
              file_format: "canonical-csv",
              label,
              expected_rows: Number(expectedRows),
              control_totals: controls,
            }
          : {
              evidence_version_id: evidence,
              file_format: sourceFormat,
              ...(sourceFormat === "canonical-csv" && customColumns
                ? {
                    column_mapping: Object.fromEntries(
                      Object.entries(csvColumns).filter(
                        ([field, value]) =>
                          value !== "" &&
                          !(
                            tableType === "transactions" &&
                            amountDerivation !== "none" &&
                            field === "amount"
                          ),
                      ),
                    ),
                    ignored_columns: ignoredColumns
                      .split("\n")
                      .filter((value) => value !== ""),
                    mapping_rationale: mappingRationale,
                    delimiter: csvDelimiter,
                    ...(tableType === "transactions" &&
                    amountDerivation !== "none"
                      ? {
                          amount_derivation: amountDerivation,
                          debit_column: debitColumn,
                          credit_column: creditColumn,
                        }
                      : {}),
                  }
                : {}),
              ...(["payroll-rules", "benefit-rules"].includes(tableType) &&
              ruleDocument
                ? { rule_document_version_id: ruleDocument }
                : {}),
              ...(sourceFormat === "india-inv01-json"
                ? {
                    gst_registration: gstRegistration,
                    gst_direction: gstDirection,
                    gst_period: gstPeriod,
                  }
                : {}),
              ...(sourceFormat === "india-gstr2b-json"
                ? {
                    gst_registration: gstRegistration,
                    gst_period: gstPeriod,
                    expected_documents: Number(expectedDocuments),
                  }
                : {}),
              ...(sourceFormat !== "canonical-csv" && account
                ? { account_identifier: account }
                : {}),
              ...(sourceFormat === "camt053" && statementIdentifier
                ? { statement_identifier: statementIdentifier }
                : {}),
              ...(["uae-wps-sif", "india-epfo-ecr"].includes(sourceFormat) &&
              employerRegistration
                ? { employer_registration: employerRegistration }
                : {}),
              ...(["uae-wps-sif", "india-epfo-ecr"].includes(sourceFormat) &&
              obligationDue
                ? { obligation_due_date: obligationDue }
                : {}),
              ...(sourceFormat === "india-epfo-ecr"
                ? {
                    obligation_period: obligationPeriod,
                    expected_members: Number(expectedMembers),
                  }
                : {}),
              table_type: tableType,
              label,
              expected_rows: Number(expectedRows),
              ...(Number(expectedRows) === 0 ? { nil_reason: nilReason } : {}),
              control_totals: controls,
            };
      } else {
        if (!chosen)
          throw new Error(
            "Select an available workflow for the engagement country",
          );
        if (workflow === "open-item-allocations" && !invoiceFaceAmounts)
          throw new Error(
            "Confirm that invoices contain face amounts before cash allocation.",
          );
        payload = {
          workflow,
          ...(workflow === "open-item-allocations"
            ? { allocation_basis: "invoice_face_amounts" }
            : {}),
          source_ids: sources,
          as_of: asOf,
          title: label,
          rationale: reason,
          currency: [
            "india-payroll-rules",
            "india-gst",
            "india-withholding",
          ].includes(workflow)
            ? "INR"
            : currency,
          ...([
            "subsequent-settlements",
            "balance-confirmations",
            "expense-cutoff",
            "going-concern-cash",
          ].includes(workflow)
            ? { review_through: reviewThrough }
            : {}),
          ...([
            "expense-cutoff",
            "excise-reconciliation",
            "gold-reconciliation",
            "asset-register-review",
          ].includes(workflow)
            ? { period_start: periodStart }
            : {}),
          ...(taxYear ? { tax_year_start: taxYear } : {}),
          ...(workflow === "bank-brs" ? { account, ...balances } : {}),
          required_checks: requiredChecks
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          required_boxes: requiredBoxes
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        };
        payload.subjects = subjects
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      }
      await action.mutateAsync({
        path: `${prefix}/jobs`,
        body: { operation, payload },
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
    } catch (error) {
      setLocalError(error as Error);
    }
  }
  async function decide(
    decision: "approve" | "reject" | "accept",
    itemId?: string,
  ) {
    if (!detail.data) return;
    const response = await action
      .mutateAsync({
        path: `${prefix}/events/${selected}/review`,
        body: {
          action: decision,
          expected_version: detail.data.version,
          comments,
          ...(itemId ? { item_id: itemId } : {}),
        },
      })
      .catch(() => null);
    if (response) setSelected(response.id);
  }
  function template() {
    const fields = Object.keys(config.data?.source_contracts[tableType] || {});
    const url = URL.createObjectURL(
      new Blob([fields.join(",") + "\r\n"], { type: "text/csv" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `${tableType}-headers.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function exportFile() {
    try {
      const response = await fetch(
        `/api/backend/${prefix}/events/${selected}/export?format=xlsx`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `country-workflow-${selected}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setLocalError(error as Error);
    }
  }
  return (
    <div>
      <PageHeader
        eyebrow={`${config.data?.country || "Engagement"} · Country workflows`}
        title={
          mode === "workflow-source"
            ? "Prepare controlled source tables"
            : "Reconcile and assess evidence"
        }
        description="Work from retained evidence, compare independent sources and document exceptions before review."
      />
      <nav className="toolbar" aria-label="Country workflow navigation">
        <Link className="button" href={`/intelligence/${eid}/workflow-source`}>
          Prepare sources
        </Link>
        <Link className="button" href={`/intelligence/${eid}/country-workflow`}>
          Run workflows
        </Link>
        <Link className="button" href={`/intelligence/${eid}/lead`}>
          Accounting intelligence
        </Link>
        <Link className="button" href={`/engagements/${eid}/evidence`}>
          Upload evidence
        </Link>
      </nav>
      <ErrorState
        error={
          config.error ||
          (sourceOrigin === "vat" ? vatRuns.error : null) ||
          accounts.error ||
          inputs.error ||
          results.error ||
          jobs.error ||
          detail.error ||
          action.error ||
          localError
        }
      />
      <details style={{ margin: "16px 0" }}>
        <summary>
          {config.data?.scenarios.length || 0} synthetic reference scenarios
          across country workflows
        </summary>
        <p>
          These scenarios test source comparisons and evidence controls. They do
          not establish complete statutory coverage or live registry
          integrations.
        </p>
        <ul>
          {config.data?.scenarios
            .filter((s) => s.workflow === workflow)
            .map((s) => (
              <li key={s.id}>
                {s.id} · {s.title}
              </li>
            ))}
        </ul>
      </details>
      <section className="main-panel" style={{ padding: 20 }}>
        <h2>
          {mode === "workflow-source" ? "Source controls" : "Workflow scope"}
        </h2>
        <p>
          Sources support controlled CSV and available native formats, up to
          5,000 rows each. File totals establish uploaded-file completeness;
          legal calculations and external registry verification require separate
          qualification.
        </p>
        <div
          className="toolbar"
          style={{ flexWrap: "wrap", alignItems: "start" }}
        >
          <label>
            Schedule title
            <input value={label} onChange={(e) => setLabel(e.target.value)} />
          </label>
          {mode === "workflow-source" ? (
            <>
              <label>
                Source origin
                <select
                  aria-label="Source origin"
                  value={sourceOrigin}
                  onChange={(e) => {
                    setSourceOrigin(e.target.value);
                    setTableType(
                      e.target.value === "supporting-items"
                        ? "audit-open-items"
                        : "transactions",
                    );
                    setSupportingTable("");
                  }}
                >
                  <option value="evidence">Retained source file</option>
                  <option value="ledger">Committed ledger</option>
                  <option value="supporting">
                    Reviewed supporting bank table
                  </option>
                  <option value="supporting-items">
                    Reviewed supporting open-item table
                  </option>
                  {config.data?.country === "AE" && canUseVAT && (
                    <option value="vat">Reconciled UAE VAT calculation</option>
                  )}
                </select>
              </label>
              {sourceOrigin === "vat" ? (
                <>
                  <label>
                    Current reconciled VAT201 run
                    <select
                      aria-label="Current reconciled VAT201 run"
                      value={vatRun}
                      onChange={(e) => setVATRun(e.target.value)}
                    >
                      <option value="">Select VAT calculation</option>
                      {vatRuns.data?.items.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p>
                    Reuse the VAT workbench's current, source-reconciled boxes.
                    Import the filed return separately.
                  </p>
                </>
              ) : ["supporting", "supporting-items"].includes(sourceOrigin) ? (
                <>
                  <label>
                    {sourceOrigin === "supporting-items"
                      ? "Reviewed supporting open-item table"
                      : "Reviewed supporting bank table"}
                    <select
                      aria-label={
                        sourceOrigin === "supporting-items"
                          ? "Reviewed supporting open-item table"
                          : "Reviewed supporting bank table"
                      }
                      value={supportingTable}
                      onChange={(event) =>
                        setSupportingTable(event.target.value)
                      }
                    >
                      <option value="">Select reviewed table</option>
                      {results.data?.items
                        .filter(
                          (item) =>
                            item.kind === "source-table" &&
                            item.table_kind ===
                              (sourceOrigin === "supporting-items"
                                ? "open-items"
                                : "bank") &&
                            item.review_status === "REVIEWED" &&
                            item.freshness === "CURRENT" &&
                            item.evidence_version_id,
                        )
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label} · v{item.version}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    {sourceOrigin === "supporting-items"
                      ? "Control account identifier"
                      : "Bank account identifier"}
                    <input
                      value={account}
                      onChange={(event) => setAccount(event.target.value)}
                    />
                  </label>
                  <label>
                    {sourceOrigin === "supporting-items"
                      ? "Supporting open-item scope assessment"
                      : "Supporting bank account scope assessment"}
                    <textarea
                      value={supportingScope}
                      maxLength={2000}
                      onChange={(event) =>
                        setSupportingScope(event.target.value)
                      }
                    />
                  </label>
                  {sourceOrigin === "supporting-items" && (
                    <>
                      <label>
                        Open-item subledger side
                        <select
                          value={supportingSide}
                          onChange={(event) =>
                            setSupportingSide(event.target.value)
                          }
                        >
                          <option value="receivable">Receivable</option>
                          <option value="payable">Payable</option>
                        </select>
                      </label>
                      <label>
                        Open-item balance date
                        <input
                          type="date"
                          value={supportingBalanceDate}
                          onChange={(event) =>
                            setSupportingBalanceDate(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        Open-item source sign
                        <select
                          value={supportingAmountSign}
                          onChange={(event) =>
                            setSupportingAmountSign(event.target.value)
                          }
                        >
                          <option value="as-reported">Use reported sign</option>
                          <option value="reverse-sign">
                            Reverse reported sign
                          </option>
                        </select>
                      </label>
                      <p>
                        Amounts must use the subledger's normal sign:
                        invoices/debit notes non-negative and credit notes
                        non-positive. Explicit document types, counterparties,
                        document dates and due dates are required in the
                        reviewed table.
                      </p>
                    </>
                  )}
                  <label>
                    Expected data rows
                    <input
                      type="number"
                      min={1}
                      max={5000}
                      value={expectedRows}
                      onChange={(event) => setExpectedRows(event.target.value)}
                    />
                  </label>
                  <label>
                    Independent totals by currency
                    <input
                      value={totals}
                      onChange={(event) => setTotals(event.target.value)}
                    />
                  </label>
                  <p>
                    Reuse all reviewed normalized rows and their original
                    evidence. Declare independent row/currency controls and
                    verify the account scope; no account ownership, PDF
                    extraction or value conversion is inferred. Open-item sign
                    changes require the explicit selection above.
                  </p>
                </>
              ) : sourceOrigin === "ledger" ? (
                <>
                  <label>
                    Ledger source type
                    <select
                      value={ledgerKind}
                      onChange={(e) => setLedgerKind(e.target.value)}
                    >
                      <option value="transactions">Bank movements</option>
                      <option value="balance-controls">
                        Period-end GL balance control
                      </option>
                    </select>
                  </label>
                  {ledgerKind === "balance-controls" && (
                    <label>
                      Subledger side
                      <select
                        value={balanceSide}
                        onChange={(e) => setBalanceSide(e.target.value)}
                      >
                        <option value="receivable">
                          Receivables (debit normal)
                        </option>
                        <option value="payable">
                          Payables (credit normal)
                        </option>
                      </select>
                    </label>
                  )}
                  <label>
                    Committed ledger snapshot
                    <select
                      aria-label="Committed ledger snapshot"
                      value={ledgerSnapshot}
                      onChange={(e) => {
                        setLedgerSnapshot(e.target.value);
                        setLedgerAccount("");
                      }}
                    >
                      <option value="">Select snapshot</option>
                      {inputs.data?.snapshots?.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Bank ledger account
                    <select
                      aria-label="Bank ledger account"
                      value={ledgerAccount}
                      onChange={(e) => setLedgerAccount(e.target.value)}
                    >
                      <option value="">Select one account</option>
                      {accounts.data?.items?.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.code} · {a.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Bank account identifier
                    <input
                      value={account}
                      onChange={(e) => setAccount(e.target.value)}
                    />
                  </label>
                  <label>
                    Ledger functional currency
                    <input
                      value={currency}
                      onChange={(e) =>
                        setCurrency(e.target.value.toUpperCase())
                      }
                    />
                  </label>
                  <label>
                    Ledger through date
                    <input
                      type="date"
                      value={asOf}
                      onChange={(e) => setAsOf(e.target.value)}
                    />
                  </label>
                  {ledgerKind === "transactions" && (
                    <label>
                      Ledger from date (optional)
                      <input
                        type="date"
                        value={ledgerFrom}
                        onChange={(e) => setLedgerFrom(e.target.value)}
                      />
                    </label>
                  )}
                  {ledgerKind === "transactions" && (
                    <label>
                      Nil rationale (only for an empty ledger)
                      <textarea
                        value={nilReason}
                        onChange={(e) => setNilReason(e.target.value)}
                      />
                    </label>
                  )}
                </>
              ) : (
                <>
                  <label>
                    Source file format
                    <select
                      aria-label="Source file format"
                      value={sourceFormat}
                      onChange={(e) => {
                        setSourceFormat(e.target.value);
                        const chosenFormat = config.data?.source_formats?.find(
                          (f) => f.id === e.target.value,
                        );
                        if (chosenFormat?.table_type)
                          setTableType(chosenFormat.table_type);
                      }}
                    >
                      {(
                        config.data?.source_formats || [
                          {
                            id: "canonical-csv",
                            label: "Controlled canonical CSV",
                            available: true,
                          },
                        ]
                      )
                        .filter((f) => f.available)
                        .map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.label}
                          </option>
                        ))}
                    </select>
                  </label>
                  {sourceFormat !== "canonical-csv" && (
                    <p>{formatInfo?.description}</p>
                  )}
                  <label>
                    Source table type
                    <select
                      disabled={sourceFormat !== "canonical-csv"}
                      value={tableType}
                      onChange={(e) => {
                        setTableType(e.target.value);
                        setCSVColumns({});
                        setAmountDerivation("none");
                      }}
                    >
                      {Object.keys(config.data?.source_contracts || {}).map(
                        (k) => (
                          <option key={k}>{k}</option>
                        ),
                      )}
                    </select>
                  </label>
                  {sourceFormat === "canonical-csv" && (
                    <>
                      <label>
                        <input
                          type="checkbox"
                          checked={customColumns}
                          onChange={(event) =>
                            setCustomColumns(event.target.checked)
                          }
                        />
                        Map original CSV columns
                      </label>
                      {customColumns && (
                        <fieldset>
                          <legend>Original export columns</legend>
                          <label>
                            CSV separator
                            <select
                              value={csvDelimiter}
                              onChange={(event) =>
                                setCSVDelimiter(event.target.value)
                              }
                            >
                              <option value=",">Comma</option>
                              <option value=";">Semicolon</option>
                              <option value={"\t"}>Tab</option>
                            </select>
                          </label>
                          {tableType === "transactions" && (
                            <>
                              <label>
                                Transaction amount columns
                                <select
                                  value={amountDerivation}
                                  onChange={(event) =>
                                    setAmountDerivation(event.target.value)
                                  }
                                >
                                  <option value="none">
                                    One signed amount column
                                  </option>
                                  <option value="debit-positive">
                                    Debit minus credit
                                  </option>
                                  <option value="credit-positive">
                                    Credit minus debit
                                  </option>
                                </select>
                              </label>
                              {amountDerivation !== "none" && (
                                <>
                                  <label>
                                    Original debit column
                                    <input
                                      value={debitColumn}
                                      maxLength={120}
                                      onChange={(event) =>
                                        setDebitColumn(event.target.value)
                                      }
                                    />
                                  </label>
                                  <label>
                                    Original credit column
                                    <input
                                      value={creditColumn}
                                      maxLength={120}
                                      onChange={(event) =>
                                        setCreditColumn(event.target.value)
                                      }
                                    />
                                  </label>
                                  <p>
                                    Choose the sign convention supported by this
                                    export. Values must be unsigned plain
                                    decimals; both sides nonzero or both blank
                                    are rejected. A blank side counts as zero
                                    only when the other side has a value.
                                  </p>
                                </>
                              )}
                            </>
                          )}
                          {Object.entries(
                            config.data?.source_contracts[tableType] || {},
                          )
                            .filter(
                              ([field]) =>
                                !(
                                  field === "amount" &&
                                  tableType === "transactions" &&
                                  amountDerivation !== "none"
                                ),
                            )
                            .map(([field, contract]) => (
                              <label key={field}>
                                CSV column for {field}
                                {contract.required ? " (required)" : ""}
                                <input
                                  aria-label={`CSV column for ${field}`}
                                  value={csvColumns[field] || ""}
                                  placeholder={field}
                                  maxLength={120}
                                  onChange={(event) =>
                                    setCSVColumns({
                                      ...csvColumns,
                                      [field]: event.target.value,
                                    })
                                  }
                                />
                              </label>
                            ))}
                          <label>
                            Excluded CSV columns, one exact heading per line
                            <textarea
                              value={ignoredColumns}
                              onChange={(event) =>
                                setIgnoredColumns(event.target.value)
                              }
                            />
                          </label>
                          <label>
                            Column mapping and exclusion assessment
                            <textarea
                              value={mappingRationale}
                              maxLength={2000}
                              onChange={(event) =>
                                setMappingRationale(event.target.value)
                              }
                            />
                          </label>
                          <p>
                            Enter exact original headings. A blank mapping uses
                            the standard field name. Every extra column must be
                            explicitly excluded and remains in the original
                            evidence. Dates, signed amounts, identifiers and
                            row/currency controls still use the displayed source
                            contract. Only an explicitly selected debit/credit
                            difference changes amount representation; dates and
                            currencies are not converted, and no bank or
                            government export is authenticated.
                          </p>
                        </fieldset>
                      )}
                    </>
                  )}
                  {tableType === "payroll-bases" && (
                    <p>
                      Payroll base controls sum assessed bases across component
                      rows. They are not gross payroll totals. Record each
                      membership or exemption decision and its evidence
                      reference explicitly.
                    </p>
                  )}
                  {["payroll-rules", "benefit-rules"].includes(tableType) && (
                    <>
                      <label>
                        {tableType === "benefit-rules" ? "Benefit" : "Payroll"}{" "}
                        rule source document (optional shared document)
                        <select
                          value={ruleDocument}
                          onChange={(e) => setRuleDocument(e.target.value)}
                        >
                          <option value="">
                            Use document references from the CSV
                          </option>
                          {inputs.data?.evidence
                            .filter((item) => item.scan_status === "CLEAN")
                            .map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.label}
                              </option>
                            ))}
                        </select>
                      </label>
                      <p>
                        Select a retained document to fill blank source-document
                        references and hashes in the CSV. Conflicting references
                        are rejected. Independently review this source before
                        calculating expected dues. Payroll rules must cover the
                        whole wage month; benefit rules must cover the
                        service-end date and assessed employment regime.
                      </p>
                    </>
                  )}
                  {["camt053", "swift-mt940"].includes(sourceFormat) && (
                    <label>
                      Statement account identifier (optional selection)
                      <input
                        value={account}
                        onChange={(e) => setAccount(e.target.value)}
                      />
                    </label>
                  )}
                  {sourceFormat === "camt053" && (
                    <label>
                      Statement identifier (required when selection is
                      ambiguous)
                      <input
                        value={statementIdentifier}
                        onChange={(e) => setStatementIdentifier(e.target.value)}
                      />
                    </label>
                  )}
                  {sourceFormat === "uae-wps-sif" && (
                    <>
                      <label>
                        Employer registration cross-check (optional)
                        <input
                          value={employerRegistration}
                          onChange={(e) =>
                            setEmployerRegistration(e.target.value)
                          }
                        />
                      </label>
                      <label>
                        Declared obligation due date (optional)
                        <input
                          type="date"
                          value={obligationDue}
                          onChange={(e) => setObligationDue(e.target.value)}
                        />
                      </label>
                      <p>
                        A SIF is an instruction file. Actual bank payment
                        evidence is required separately.
                      </p>
                    </>
                  )}
                  {sourceFormat === "india-inv01-json" && (
                    <>
                      <label>
                        Entity GSTIN
                        <input
                          value={gstRegistration}
                          onChange={(e) => setGSTRegistration(e.target.value)}
                        />
                      </label>
                      <label>
                        Invoice direction
                        <select
                          value={gstDirection}
                          onChange={(e) => setGSTDirection(e.target.value)}
                        >
                          <option value="purchase">
                            Purchase — entity is buyer
                          </option>
                          <option value="sale">Sale — entity is seller</option>
                        </select>
                      </label>
                      <label>
                        Reporting month
                        <input
                          type="month"
                          value={gstPeriod}
                          onChange={(e) => setGSTPeriod(e.target.value)}
                        />
                      </label>
                      <p>
                        Enter five data rows per invoice and an INR total of
                        signed tax across all components. This imports invoice
                        data; IRP authenticity, cancellation status and credit
                        eligibility require separate evidence.
                      </p>
                    </>
                  )}
                  {sourceFormat === "india-gstr2b-json" && (
                    <>
                      <label>
                        Recipient GSTIN
                        <input
                          value={gstRegistration}
                          onChange={(event) =>
                            setGSTRegistration(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        GSTR-2B return month
                        <input
                          type="month"
                          value={gstPeriod}
                          onChange={(event) => setGSTPeriod(event.target.value)}
                        />
                      </label>
                      <label>
                        Independent GSTR-2B document count
                        <input
                          type="number"
                          min={0}
                          max={1250}
                          value={expectedDocuments}
                          onChange={(event) => {
                            setExpectedDocuments(event.target.value);
                            setExpectedRows(
                              String(Number(event.target.value) * 4),
                            );
                          }}
                        />
                      </label>
                      <p>
                        Count each source document, including amendments and
                        reversal records. Four tax-component rows are imported
                        per document. INR controls sum signed document tax
                        fields; they do not represent eligible credit. Paged
                        downloads and unknown sections require a supported
                        complete profile.
                      </p>
                    </>
                  )}
                  {sourceFormat === "india-epfo-ecr" && (
                    <>
                      <label>
                        EPFO establishment registration
                        <input
                          value={employerRegistration}
                          onChange={(e) =>
                            setEmployerRegistration(e.target.value)
                          }
                        />
                      </label>
                      <label>
                        ECR wage month
                        <input
                          type="month"
                          value={obligationPeriod}
                          onChange={(e) => setObligationPeriod(e.target.value)}
                        />
                      </label>
                      <label>
                        Independent ECR member count
                        <input
                          type="number"
                          min={1}
                          max={1666}
                          value={expectedMembers}
                          onChange={(e) => setExpectedMembers(e.target.value)}
                        />
                      </label>
                      <label>
                        Declared obligation due date (optional)
                        <input
                          type="date"
                          value={obligationDue}
                          onChange={(e) => setObligationDue(e.target.value)}
                        />
                      </label>
                      <p>
                        Enter three contribution rows per member, plus one for
                        each non-zero advance refund. INR controls include those
                        contributions and refunds. Establishment and month are
                        declared separately from the text. Filing, payment,
                        rates, membership, insurance and administration charges
                        need separate evidence.
                      </p>
                    </>
                  )}
                  <label>
                    Clean retained evidence
                    <select
                      value={evidence}
                      onChange={(e) => setEvidence(e.target.value)}
                    >
                      <option value="">Select evidence</option>
                      {inputs.data?.evidence.map((e) => (
                        <option
                          key={e.id}
                          value={e.id}
                          disabled={e.scan_status !== "CLEAN"}
                        >
                          {e.label} · {e.scan_status}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Expected data rows
                    <input
                      type="number"
                      min={0}
                      max={5000}
                      value={expectedRows}
                      onChange={(e) => setExpectedRows(e.target.value)}
                    />
                  </label>
                  {Number(expectedRows) === 0 && (
                    <label>
                      Nil population rationale
                      <textarea
                        value={nilReason}
                        onChange={(e) => setNilReason(e.target.value)}
                      />
                    </label>
                  )}
                  {moneyTables.includes(tableType) && (
                    <label>
                      Independent totals by currency
                      <input
                        aria-label="Independent totals by currency"
                        value={totals}
                        onChange={(e) => setTotals(e.target.value)}
                      />
                      <small>
                        Signed amount totals; tax-document sources use tax
                        totals. Confirmation sources use requested amounts.
                      </small>
                    </label>
                  )}
                  {sourceFormat === "canonical-csv" && (
                    <Button onClick={template}>Download CSV headers</Button>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              <label>
                Workflow
                <select
                  value={workflow}
                  onChange={(e) => {
                    setWorkflow(e.target.value);
                    setSources({});
                    setRequiredChecks("");
                  }}
                >
                  {available.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Reconciliation date
                <input
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </label>
              {[
                "subsequent-settlements",
                "balance-confirmations",
                "expense-cutoff",
                "going-concern-cash",
              ].includes(workflow) && (
                <label>
                  Review through date
                  <input
                    type="date"
                    value={reviewThrough}
                    min={asOf}
                    onChange={(e) => setReviewThrough(e.target.value)}
                  />
                </label>
              )}
              {[
                "expense-cutoff",
                "excise-reconciliation",
                "gold-reconciliation",
                "asset-register-review",
              ].includes(workflow) && (
                <label>
                  Reporting period start
                  <input
                    type="date"
                    value={periodStart}
                    max={asOf}
                    onChange={(e) => setPeriodStart(e.target.value)}
                  />
                </label>
              )}
              {workflow === "ownership-lookthrough" && (
                <label>
                  Company subject IDs, comma separated
                  <input
                    value={subjects}
                    onChange={(e) => setSubjects(e.target.value)}
                  />
                </label>
              )}
              {config.data?.country === "IN" && (
                <label>
                  Tax-year start (for form guidance)
                  <input
                    type="date"
                    value={taxYear}
                    onChange={(e) => setTaxYear(e.target.value)}
                  />
                </label>
              )}
              {Object.entries(chosen?.roles || {}).map(([role, type]) => (
                <label key={role}>
                  {role} source
                  <select
                    aria-label={`${role} source`}
                    value={sources[role] || ""}
                    onChange={(e) =>
                      setSources({ ...sources, [role]: e.target.value })
                    }
                  >
                    <option value="">Select {type} source</option>
                    {results.data?.items
                      .filter(
                        (r) =>
                          r.kind === "workflow-source" &&
                          r.table_type === type &&
                          r.freshness === "CURRENT" &&
                          (!["uae-wps-sif", "india-epfo-ecr"].includes(
                            r.native_format || "",
                          ) ||
                            ["channel", "return", "reported"].includes(role)) &&
                          (![
                            "india-payroll-rules",
                            "uae-benefit-review",
                          ].includes(workflow) ||
                            role !== "rules" ||
                            r.review_status === "REVIEWED"),
                      )
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.label} · v{r.version} · {r.review_status}
                        </option>
                      ))}
                  </select>
                  {type === "obligations" &&
                    !["channel", "return", "reported"].includes(role) && (
                      <small>
                        Use independent payroll/dues or payment evidence. WPS
                        and ECR files establish a return/channel population
                        only.
                      </small>
                    )}
                </label>
              ))}
              {workflow === "uae-vat-return" && (
                <label>
                  Required VAT201 boxes, comma separated
                  <input
                    value={requiredBoxes}
                    onChange={(e) => setRequiredBoxes(e.target.value)}
                  />
                </label>
              )}
              {workflow === "bank-brs" && (
                <>
                  <label>
                    Bank account identifier
                    <input
                      value={account}
                      onChange={(e) => setAccount(e.target.value)}
                    />
                  </label>
                  <label>
                    Account currency
                    <input
                      value={currency}
                      onChange={(e) =>
                        setCurrency(e.target.value.toUpperCase())
                      }
                    />
                  </label>
                  {[
                    "book_opening",
                    "book_closing",
                    "statement_opening",
                    "statement_closing",
                  ].map((key) => (
                    <label key={key}>
                      {key.replaceAll("_", " ")}
                      <input
                        inputMode="decimal"
                        value={balances[key] || ""}
                        onChange={(e) =>
                          setBalances({ ...balances, [key]: e.target.value })
                        }
                      />
                    </label>
                  ))}
                </>
              )}
              {[
                "controls",
                "vendor-diligence",
                "nonprofit-diligence",
                "tax-close",
              ].includes(workflow) && (
                <>
                  <label>
                    Required check identifiers, comma separated
                    <input
                      value={requiredChecks}
                      onChange={(e) => setRequiredChecks(e.target.value)}
                    />
                  </label>
                  <Button
                    onClick={() =>
                      setRequiredChecks(
                        (config.data?.check_templates[workflow] || []).join(
                          ",",
                        ),
                      )
                    }
                  >
                    Use country starter checks
                  </Button>
                  <label>
                    Subject population, comma separated
                    <input
                      value={subjects}
                      onChange={(e) => setSubjects(e.target.value)}
                    />
                  </label>
                </>
              )}
              <label>
                Scope and source rationale
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              {workflow === "open-item-allocations" && (
                <label>
                  <input
                    type="checkbox"
                    checked={invoiceFaceAmounts}
                    onChange={(e) => setInvoiceFaceAmounts(e.target.checked)}
                  />
                  Invoice amounts are face amounts before cash allocations,
                  rather than already-net balances.
                </label>
              )}
            </>
          )}
          <Button disabled={action.isPending} onClick={run}>
            Queue calculation
          </Button>
        </div>
        {mode === "workflow-source" &&
          sourceOrigin === "evidence" &&
          sourceFormat === "canonical-csv" && (
            <details>
              <summary>CSV field contract</summary>
              <ul>
                {Object.entries(
                  config.data?.source_contracts[tableType] || {},
                ).map(([k, v]) => (
                  <li key={k}>
                    {k}
                    {v.required ? " · required" : " · optional"}
                  </li>
                ))}
              </ul>
              <p>
                Use ISO dates (YYYY-MM-DD), periods YYYY-MM, signed decimals
                without thousands separators, uppercase currency codes, unique
                row IDs and negative credit-note amounts. Blank optional fields
                are omitted. Unknown columns and duplicate domain keys are
                rejected.
              </p>
            </details>
          )}
      </section>
      <section className="main-panel" style={{ padding: 20, marginTop: 16 }}>
        <h2>Recent jobs</h2>
        {(jobs.data?.items.length || 0) > 5 && (
          <Button onClick={() => setShowAllJobs(!showAllJobs)}>
            {showAllJobs
              ? "Show latest five jobs"
              : "Show full recent job history"}
          </Button>
        )}
        {jobs.data?.items
          .filter((j) =>
            [
              "workflow-source",
              "workflow-ledger",
              "workflow-vat",
              "country-workflow",
            ].includes(j.operation),
          )
          .slice(0, showAllJobs ? undefined : 5)
          .map((j) => (
            <div className="toolbar" key={j.id}>
              <span>{j.operation}</span>
              <Status value={j.status} />
              {j.error_details && (
                <span role="alert">{j.error_details.message}</span>
              )}
              {j.result_id && (
                <Button onClick={() => setSelected(j.result_id!)}>
                  Open result
                </Button>
              )}
            </div>
          ))}
      </section>
      <label>
        Saved source or result (latest 100)
        <select
          aria-label="Saved source or result"
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">Select result</option>
          {results.data?.items
            .filter((r) =>
              ["workflow-source", "country-workflow"].includes(r.kind),
            )
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.label} · v{r.version} · {r.freshness}
              </option>
            ))}
        </select>
      </label>
      {detail.data && body && (
        <section className="main-panel" style={{ padding: 20, marginTop: 16 }}>
          <h2>{body.title}</h2>
          {body.operations_execution && (
            <p>
              Source scope:{" "}
              {body.operations_execution.population_completeness.replaceAll(
                "_",
                " ",
              )}
              . Reviewed comparisons do not establish an audit opinion. No
              payments or journals are executed.
            </p>
          )}
          {body.workflow === "open-item-allocations" &&
            body.review_status === "REVIEWED" &&
            !body.blocked && (
              <Button
                onClick={async () => {
                  const created = await action
                    .mutateAsync({
                      path: `${prefix}/events/${selected}/remaining-open-items`,
                      body: {},
                    })
                    .catch(() => null);
                  if (created) setSelected(created.id);
                }}
              >
                Prepare remaining open items for ageing and ECL review
              </Button>
            )}
          {!!body.payment_proposals?.length && (
            <details>
              <summary>Payment proposals — separate approval required</summary>
              <ul>
                {body.payment_proposals.map((proposal, index) => (
                  <li key={`${proposal.order_id}-${index}`}>
                    {proposal.vendor}: {proposal.currency} {proposal.amount} ·{" "}
                    {proposal.state.replaceAll("_", " ")}
                    {proposal.holds.length
                      ? ` · ${proposal.holds.join(", ")}`
                      : ""}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div className="toolbar">
            <Status value={body.review_status} />
            <Status value={detail.data.freshness} />
            <span>{body.exception_count ?? 0} exceptions</span>
            <Button onClick={exportFile}>Export XLSX</Button>
          </div>
          {body.blocked && (
            <p role="alert">
              Approval blocked: correct source controls or missing/expired
              evidence and regenerate.
            </p>
          )}
          {body.workflow === "india-payroll-rules" && (
            <>
              <p>
                {body.expected_total_complete === false
                  ? "Partial expected total"
                  : "Expected contributions"}
                : INR {body.expected_total}. Reported contributions: INR{" "}
                {body.reported_total}. Payment is not verified by this
                comparison.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={showRuleProvenance}
                  onChange={(event) =>
                    setShowRuleProvenance(event.target.checked)
                  }
                />
                Show rule provenance and source references
              </label>
            </>
          )}
          <p>
            Population basis: {body.population_completeness}. Calculations do
            not determine a statutory compliance conclusion.
          </p>
          {["india-gst", "uae-vat"].includes(body.workflow || "") && (
            <label>
              <input
                type="checkbox"
                checked={showRuleProvenance}
                onChange={(event) =>
                  setShowRuleProvenance(event.target.checked)
                }
              />
              Show source versions and review details
            </label>
          )}
          {body.execution_mode && (
            <p>
              Execution: {body.execution_mode.replaceAll("_", " ")}.
              {body.language_model_dependency === false
                ? " No language-model credentials required."
                : ""}
            </p>
          )}
          {body.nil_population && (
            <p>
              Declared nil population: independently review the source
              declarations before concluding that no activity exists.
            </p>
          )}
          {body.nil_declarations && (
            <dl>
              {Object.entries(body.nil_declarations).map(
                ([role, rationale]) => (
                  <div key={role}>
                    <dt>{role} nil declaration</dt>
                    <dd>{rationale}</dd>
                  </div>
                ),
              )}
            </dl>
          )}
          {body.control_comparison && (
            <dl>
              {Object.entries(body.control_comparison).map(([k, v]) => (
                <div key={k}>
                  <dt>{k.replaceAll("_", " ")}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          )}
          {body.native_metadata && (
            <details>
              <summary>Original source controls and calculation basis</summary>
              <dl>
                {Object.entries(body.native_metadata).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{text(value)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          {body.csv_mapping && (
            <details>
              <summary>Original CSV column mapping and exclusions</summary>
              <dl>
                {Object.entries(body.csv_mapping.applied_columns).map(
                  ([field, heading]) => (
                    <div key={field}>
                      <dt>{field.replaceAll("_", " ")}</dt>
                      <dd>{heading}</dd>
                    </div>
                  ),
                )}
              </dl>
              <p>
                Excluded columns:{" "}
                {body.csv_mapping.ignored_columns.join(", ") || "None"}
              </p>
              <p>{body.csv_mapping.rationale}</p>
              {body.csv_mapping.amount_derivation &&
                body.csv_mapping.amount_derivation !== "none" && (
                  <p>
                    Amount basis: {body.csv_mapping.amount_derivation}; debit
                    column: {body.csv_mapping.debit_column}; credit column:{" "}
                    {body.csv_mapping.credit_column}.
                  </p>
                )}
            </details>
          )}
          {body.supporting_table_id && (
            <div>
              <p>{body.supporting_scope_assessment}</p>
              {body.supporting_side && (
                <p>
                  Subledger: {body.supporting_side}; balance date:{" "}
                  {body.supporting_balance_date}; source sign:{" "}
                  {body.supporting_amount_sign}.
                </p>
              )}
              <Button
                onClick={() => {
                  setSelected(body.supporting_table_id!);
                  setOffset(0);
                }}
              >
                Open reviewed supporting table
              </Button>
            </div>
          )}
          {body.limitations && (
            <ul>
              {body.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          )}
          {body.country_guidance && (
            <details>
              <summary>Country-specific scope guidance</summary>
              <dl>
                {Object.entries(body.country_guidance).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{text(v)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          <label>
            Review / exception rationale
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
            />
          </label>
          <div className="toolbar">
            <Button
              disabled={
                action.isPending ||
                detail.data.freshness !== "CURRENT" ||
                !!body.blocked
              }
              onClick={() => decide("approve")}
            >
              Independent approval
            </Button>
            <Button
              disabled={action.isPending}
              onClick={() => decide("reject")}
            >
              Reject
            </Button>
            <Link
              className="button"
              href={`/intelligence/${eid}/lead?event=${selected}`}
            >
              Open working-paper actions
            </Link>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <caption>
                Source-linked schedule · rows {offset + 1}–
                {offset + rows.length}; XLSX contains the full result
              </caption>
              <thead>
                <tr>
                  {columns.map((k) => (
                    <th key={k} scope="col">
                      {k.replaceAll("_", " ")}
                    </th>
                  ))}
                  {detail.data.kind === "country-workflow" && (
                    <th scope="col">Disposition</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={String(row.id || i)}>
                    {columns.map((k) => (
                      <td key={k}>{text(row[k])}</td>
                    ))}
                    {detail.data?.kind === "country-workflow" && (
                      <td>
                        <Button
                          disabled={action.isPending}
                          onClick={() => decide("accept", String(row.id))}
                        >
                          Document exception
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="toolbar" aria-label="Schedule pages">
            <Button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              Previous rows
            </Button>
            <Button
              disabled={
                offset + rows.length >=
                (detail.data.collection_totals?.rows || rows.length)
              }
              onClick={() => setOffset(offset + 100)}
            >
              Next rows
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
