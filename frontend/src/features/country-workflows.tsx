"use client";

import Link from "next/link";
import { useState } from "react";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
import { BankCarryforwardSource } from "./bank-carryforward-source";
import { ContributionObligationSource } from "./contribution-obligation-source";
import { PayrollPostingLinks } from "./payroll-posting-links";
import { InventoryEvidenceTable } from "./inventory-evidence-table";
import { VATCompositionSource } from "./vat-composition-source";
import {
  PublishedBenefitSource,
  PublishedPayrollSource,
  PublishedPensionSource,
} from "./published-benefit-source";

const WPS_VARIABLE_FIELDS = [
  "housing_allowance",
  "conveyance_allowance",
  "medical_allowance",
  "annual_passage_allowance",
  "overtime_allowance",
  "other_allowances",
  "leave_encashment",
] as const;

function ExcludedVATBoxes({
  prefix,
  selected,
  initial,
  total,
}: {
  prefix: string;
  selected: string;
  initial: Record<string, unknown>[];
  total: number;
}) {
  const [offset, setOffset] = useState(0);
  const page = useAPI<Result>(
    `${prefix}/events/${selected}?limit=1&excluded_offset=${offset}&excluded_limit=100`,
    offset > 0,
  );
  const rows = offset ? page.data?.body.excluded_box_rows || [] : initial;
  const columns = [
    "source_role",
    "source_row_id",
    "registration",
    "period_start",
    "period_end",
    "box",
    "currency",
    "taxable_amount",
    "tax",
    "adjustment",
  ];
  if (!total) return null;
  return (
    <details>
      <summary>Review {total} excluded VAT box rows</summary>
      <ErrorState error={page.error} />
      {page.error && (
        <Button onClick={() => void page.refetch()}>Retry excluded rows</Button>
      )}
      <p>
        {page.isFetching && offset > 0
          ? "Loading excluded rows…"
          : rows.length
            ? `Excluded rows ${offset + 1}–${offset + rows.length} of ${total}. This list has its own page controls.`
            : "Excluded rows are unavailable for this page."}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Excluded VAT box rows">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.source_role}:${row.source_row_id}:${index}`}>
                {columns.map((column) => (
                  <td key={column}>{text(row[column])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar" aria-label="Excluded VAT box pages">
        <Button
          disabled={!offset || page.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Previous excluded rows
        </Button>
        <Button
          disabled={
            offset + rows.length >= total || page.isFetching || !rows.length
          }
          onClick={() => setOffset(offset + 100)}
        >
          Next excluded rows
        </Button>
      </div>
    </details>
  );
}

type Choice = {
  id: string;
  label: string;
  kind: string;
  version: number;
  freshness: string;
  review_status: string;
  table_type?: string;
  native_format?: string;
  allowed_source_roles?: string[] | null;
  inventory_controls_verified?: boolean;
  obligation_populations?: string[] | null;
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
    currency?: string;
    expected_total?: string;
    reported_total?: string;
    role_totals?: Record<
      string,
      Record<
        string,
        {
          net: string | null;
          tax: string | null;
          selected_rows: number;
          complete_for_selected_population: boolean;
        }
      >
    >;
    expected_total_complete?: boolean;
    title: string;
    review_status: string;
    obligation_population_scope?: string;
    execution_mode?: string;
    language_model_dependency?: boolean;
    blocked?: boolean;
    exception_count?: number;
    table_type?: string;
    rows: Record<string, unknown>[];
    count_bridges?: Record<string, unknown>[];
    payroll_posting_links?: Record<string, unknown>[];
    inventory_quantity_controls?: Record<string, unknown>[];
    limitations?: string[];
    control_comparison?: Record<string, string>;
    allocation_controls?: Record<string, string>;
    payment_scope?: Record<string, string>;
    box_comparison_scope?: {
      mode: string;
      required_boxes: string[];
      assessment: string | null;
      excluded_rows: Record<string, number>;
      whole_return_completeness: string;
    };
    excluded_box_rows?: Record<string, unknown>[];
    excluded_box_controls?: Record<string, unknown>[];
    included_box_controls?: Record<string, unknown>[];
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
  "payroll-account-balances",
  "payroll-ledger-lines",
  "obligation-allocations",
  "cash-payments",
  "item-allocations",
  "credit-applications",
  "bank-outstanding",
  "bank-clearances",
  "withholding-records",
  "payroll-bases",
  "pension-bases",
  "pension-reported",
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
  "import-vat-lines",
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
  const results = useEventHistory<Choice>(prefix);
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
  const [payrollView, setPayrollView] = useState("accounts");
  const detail = useAPI<Result>(
    `${prefix}/events/${selected}?offset=${offset}&limit=100&payroll_view=${payrollView}`,
    !!selected,
  );
  const [workflow, setWorkflow] = useState("bank-brs");
  const [invoiceFaceAmounts, setInvoiceFaceAmounts] = useState(false);
  const [withholdingRole, setWithholdingRole] = useState("");
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
  const [inventoryControlsEnabled, setInventoryControlsEnabled] =
    useState(false);
  const [inventoryControls, setInventoryControls] = useState("[]");
  const [stockControlled, setStockControlled] = useState(false);
  const [stockCutoffAssessment, setStockCutoffAssessment] = useState("");
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
  const [ecrArrearControls, setECRArrearControls] = useState("{}");
  const [ecrArrearContext, setECRArrearContext] = useState("");
  const [ecrDisbursed, setECRDisbursed] = useState("");
  const [ecrArrearAssessment, setECRArrearAssessment] = useState("");
  const [arrearsOnly, setArrearsOnly] = useState(false);
  const [wpsVariableCount, setWPSVariableCount] = useState("");
  const [wpsVariableTotals, setWPSVariableTotals] = useState("{}");
  const [gstrBundle, setGSTRBundle] = useState(false);
  const [gstrFiles, setGSTRFiles] = useState("");
  const [gstrParts, setGSTRParts] = useState("[]");
  const [gstrAssessment, setGSTAssessment] = useState("");
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
  const [importBaseControl, setImportBaseControl] = useState("");
  const [importBridgeRole, setImportBridgeRole] = useState("");
  const [importBridgeLabel, setImportBridgeLabel] = useState("");
  const [importBridgeAssessment, setImportBridgeAssessment] = useState("");
  const [importBridgeBoxes, setImportBridgeBoxes] = useState({
    "6": true,
    "7": true,
  });
  const [importBridgeControls, setImportBridgeControls] = useState<
    Record<string, Record<string, string>>
  >({
    "6": { expected_rows: "", taxable_amount: "", tax: "" },
    "7": { expected_rows: "", taxable_amount: "", tax: "" },
  });
  const [sources, setSources] = useState<Record<string, string>>({});
  const [asOf, setAsOf] = useState("");
  const [reviewThrough, setReviewThrough] = useState("");
  const [obligationMonthStart, setObligationMonthStart] = useState("");
  const [obligationMonthEnd, setObligationMonthEnd] = useState("");
  const [settlementStart, setSettlementStart] = useState("");
  const [bankPaymentSign, setBankPaymentSign] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [taxYear, setTaxYear] = useState("");
  const [requiredChecks, setRequiredChecks] = useState("");
  const [requiredBoxes, setRequiredBoxes] = useState("");
  const [restrictBoxes, setRestrictBoxes] = useState(false);
  const [boxScopeAssessment, setBoxScopeAssessment] = useState("");
  const [subjects, setSubjects] = useState("");
  const [account, setAccount] = useState("");
  const [currency, setCurrency] = useState("AED");
  const [balances, setBalances] = useState<Record<string, string>>({});
  const [comments, setComments] = useState("");
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<Error | null>(null);
  const [showRuleProvenance, setShowRuleProvenance] = useState(false);
  const [outstandingSelections, setOutstandingSelections] = useState<
    Record<string, string[]>
  >({});
  const [outstandingLabel, setOutstandingLabel] = useState("");
  const [outstandingCount, setOutstandingCount] = useState("");
  const [outstandingTotal, setOutstandingTotal] = useState("");
  const [outstandingAssessment, setOutstandingAssessment] = useState("");
  const action = useAction<{ id: string }>();
  const available = config.data?.items.filter((w) => w.available) || [];
  const chosen = available.find((w) => w.id === workflow);
  const formatInfo = config.data?.source_formats?.find(
    (f) => f.id === sourceFormat,
  );
  const body = detail.data?.body;
  const compactVAT = body?.workflow === "uae-vat-return";
  const rows: Record<string, unknown>[] =
    body?.workflow === "obligation-bank-allocations" && !showRuleProvenance
      ? (body.rows || []).map((row) => ({
          ...row,
          subject: row.subject ?? row.reference,
          source_amount:
            row.expected_amount ?? row.reported_amount ?? row.bank_amount,
          settled_or_allocated: row.bank_settled ?? row.allocated,
          remaining:
            row.outstanding_amount ??
            row.unsettled_reported_amount ??
            row.unallocated_bank_amount,
        }))
      : body?.workflow === "statutory-dues" &&
          body.obligation_population_scope ===
            "ARREARS_ONLY_NOT_COMPLETE_MONTHLY_RETURN" &&
          !showRuleProvenance
        ? (body.rows || []).map((row): Record<string, unknown> => ({
            ...row,
            expected_amount: (row.amounts as Record<string, unknown>)?.expected,
            return_amount: (row.amounts as Record<string, unknown>)?.return,
            payment_amount: (row.amounts as Record<string, unknown>)?.payment,
          }))
        : compactVAT && !showRuleProvenance
          ? (body.rows || [])
              .map((row): Record<string, unknown> => ({
                ...row,
                taxable_difference: (
                  row.differences as Record<string, unknown> | undefined
                )?.taxable_amount,
                tax_difference: (
                  row.differences as Record<string, unknown> | undefined
                )?.tax,
                adjustment_difference: (
                  row.differences as Record<string, unknown> | undefined
                )?.adjustment,
              }))
              .sort((left, right) => Number(left.box) - Number(right.box))
          : body?.rows || [];
  const allColumns = [
    ...new Set(rows.flatMap((row) => Object.keys(row))),
  ].filter((k) => !["auditor", "auditor_at"].includes(k));
  const compactArrear =
    body?.native_metadata?.layout ===
    "EPFO_ECR2_ARREAR_8_FIELDS_HASH_TILDE_HASH";
  const compactArrearResult =
    body?.workflow === "statutory-dues" &&
    body.obligation_population_scope ===
      "ARREARS_ONLY_NOT_COMPLETE_MONTHLY_RETURN";
  const compactWPS =
    body?.native_metadata?.profile === "emirates-islamic-edr-evp-scr/1";
  const compactSource =
    detail.data?.kind === "workflow-source" &&
    (["transactions", "audit-open-items", "bank-outstanding"].includes(
      body?.table_type || "",
    ) ||
      compactWPS ||
      compactArrear);
  const compactCredit = body?.workflow === "credit-note-applications";
  const compactBankClearance = body?.workflow === "bank-subsequent-clearance";
  const compactDues = body?.workflow === "obligation-bank-allocations";
  const compactImport = body?.workflow === "uae-import-vat";
  const compactBenefit =
    body?.workflow === "uae-benefit-review" ||
    body?.table_type === "benefit-rules";
  const compactWithholding = [
    "india-withholding-liability",
    "india-withholding-credit",
  ].includes(body?.workflow || "");
  const assessmentAttention =
    compactWithholding &&
    rows.some(
      (row) =>
        Array.isArray(row.assessment_issues) &&
        row.assessment_issues.length > 0,
    );
  const defaultColumns =
    compactVAT && !showRuleProvenance
      ? [
          "box",
          "registration",
          "period_start",
          "period_end",
          "currency",
          "taxable_difference",
          "tax_difference",
          "adjustment_difference",
          "state",
        ].filter((key) => allColumns.includes(key))
      : compactBenefit && !showRuleProvenance
        ? (body?.table_type === "benefit-rules"
            ? [
                "regime",
                "cohort",
                "work_model",
                "source_version",
                "selected_service_end_dates",
                "first_tier_days",
                "later_tier_days",
              ]
            : [
                "id",
                "work_model",
                "currency",
                "service_years",
                "expected_benefit",
                "paid_benefit",
                "difference",
                "state",
              ]
          ).filter((key) => allColumns.includes(key))
        : compactDues && !showRuleProvenance
          ? [
              "kind",
              "subject",
              "period",
              "component",
              "currency",
              "source_amount",
              "settled_or_allocated",
              "remaining",
              "state",
            ].filter((key) => allColumns.includes(key))
          : compactImport && !showRuleProvenance
            ? [
                "declaration",
                "line_reference",
                "entry_kind",
                "adjustment_reference",
                "vat201_box",
                "amounts",
                "differences",
                "exceptions",
                "state",
              ].filter((key) => allColumns.includes(key))
            : compactWithholding && !showRuleProvenance
              ? [
                  "transaction_reference",
                  "counterparty",
                  "legal_role",
                  "tax_kind",
                  "period",
                  "currency",
                  "amounts",
                  ...(assessmentAttention
                    ? ["comparison_state", "assessment_issues"]
                    : []),
                  "differences_from_expected",
                  "differences_from_books",
                  "state",
                ].filter((key) => allColumns.includes(key))
              : compactBankClearance && !showRuleProvenance
                ? [
                    "kind",
                    "reference",
                    "currency",
                    "reporting_date_amount",
                    "subsequently_cleared",
                    "remaining_after_review",
                    "statement_amount",
                    "allocated",
                    "unallocated_amount",
                    "state",
                  ].filter((key) => allColumns.includes(key))
                : compactCredit && !showRuleProvenance
                  ? [
                      "kind",
                      "item_id",
                      "currency",
                      "amount",
                      "original_balance",
                      "applied",
                      "remaining_balance",
                      "control_amount",
                      "difference",
                      "state",
                    ].filter((key) => allColumns.includes(key))
                  : compactSource && !showRuleProvenance
                    ? (body?.table_type === "transactions"
                        ? [
                            "reference",
                            "account",
                            "date",
                            "currency",
                            "amount",
                            "counterparty",
                            "source_debit",
                            "source_credit",
                          ]
                        : [
                            "reference",
                            "counterparty",
                            "account",
                            "side",
                            "currency",
                            "document_type",
                            "document_date",
                            "due_date",
                            "balance_date",
                            "amount",
                            "supporting_reported_open_amount",
                          ]
                      ).filter((key) => allColumns.includes(key))
                    : ["india-payroll-rules", "uae-pension-review"].includes(
                          body?.workflow || "",
                        ) && !showRuleProvenance
                      ? [
                          "subject",
                          "period",
                          "component",
                          "authority",
                          "scheme",
                          "membership_cohort",
                          "currency",
                          "assessed_base",
                          "expected_amount",
                          "reported_amount",
                          "difference",
                          "state",
                        ].filter((key) => allColumns.includes(key))
                      : ["india-gst", "uae-vat"].includes(
                            body?.workflow || "",
                          ) && !showRuleProvenance
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
  const columns =
    body?.workflow === "payroll-ledger-rollforward" && !showRuleProvenance
      ? (payrollView === "accounts"
          ? [
              "registration",
              "account",
              "currency",
              "opening_amount",
              "payroll_movement",
              "posted_movement",
              "expected_closing",
              "actual_closing",
              "payroll_closing_difference",
              "posted_closing_difference",
              "state",
            ]
          : [
              "account",
              "wage_month",
              "component",
              "category",
              "currency",
              "payroll_positive",
              "posted_positive",
              "payroll_negative",
              "posted_negative",
              "positive_difference",
              "negative_difference",
              "state",
            ]
        ).filter((key) => allColumns.includes(key))
      : body?.table_type === "bank-outstanding" && !showRuleProvenance
        ? [
            "reference",
            "date",
            "balance_date",
            "currency",
            "amount",
            "previous_outstanding_amount",
            "cleared_in_previous_window",
          ].filter((key) => allColumns.includes(key))
        : compactArrear && !showRuleProvenance
          ? [
              "subject",
              "period",
              "population",
              "component",
              "currency",
              "amount",
              "source_row",
            ].filter((key) => allColumns.includes(key))
          : compactArrearResult && !showRuleProvenance
            ? [
                "subject",
                "period",
                "component",
                "currency",
                "expected_amount",
                "return_amount",
                "payment_amount",
                "state",
              ].filter((key) => allColumns.includes(key))
            : compactWPS && !showRuleProvenance
              ? [
                  "subject",
                  "period",
                  "currency",
                  "fixed_income",
                  "variable_income",
                  "amount",
                  "unpaid_days",
                ].filter((key) => allColumns.includes(key))
              : defaultColumns;
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
              ...(inventoryControlsEnabled &&
              ["stock", "stock-movements"].includes(tableType)
                ? { inventory_quantity_controls: JSON.parse(inventoryControls) }
                : {}),
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
              ...([
                "fx-rates",
                "payroll-rules",
                "pension-rules",
                "benefit-rules",
                "withholding-records",
              ].includes(tableType) && ruleDocument
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
                    ...(gstrBundle
                      ? {
                          gstr2b_parts: JSON.parse(gstrParts),
                          gstr2b_expected_files: Number(gstrFiles),
                          gstr2b_retrieval_assessment: gstrAssessment,
                        }
                      : {}),
                  }
                : {}),
              ...(sourceFormat !== "canonical-csv" && account
                ? { account_identifier: account }
                : {}),
              ...(["camt053", "swift-mt940"].includes(sourceFormat) &&
              statementIdentifier
                ? { statement_identifier: statementIdentifier }
                : {}),
              ...(sourceFormat === "india-epfo-arrear-ecr-v2"
                ? {
                    ecr_arrear_controls: JSON.parse(ecrArrearControls),
                    arrear_context_evidence_version_id: ecrArrearContext,
                    arrear_disbursement_date: ecrDisbursed,
                    arrear_scope_assessment: ecrArrearAssessment,
                  }
                : {}),
              ...(sourceFormat === "uae-wps-sif-evp"
                ? {
                    wps_variable_pay_count: wpsVariableCount.trim()
                      ? Number(wpsVariableCount)
                      : null,
                    wps_variable_pay_totals: JSON.parse(wpsVariableTotals),
                  }
                : {}),
              ...([
                "uae-wps-sif",
                "uae-wps-sif-evp",
                "india-epfo-ecr",
                "india-epfo-arrear-ecr-v2",
              ].includes(sourceFormat) && employerRegistration
                ? { employer_registration: employerRegistration }
                : {}),
              ...([
                "uae-wps-sif",
                "uae-wps-sif-evp",
                "india-epfo-ecr",
                "india-epfo-arrear-ecr-v2",
              ].includes(sourceFormat) && obligationDue
                ? { obligation_due_date: obligationDue }
                : {}),
              ...(["india-epfo-ecr", "india-epfo-arrear-ecr-v2"].includes(
                sourceFormat,
              )
                ? {
                    obligation_period: obligationPeriod,
                    expected_members: Number(expectedMembers),
                  }
                : {}),
              table_type: tableType,
              ...(tableType === "import-vat-lines"
                ? { import_taxable_base_control: importBaseControl }
                : {}),
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
        if (
          workflow === "obligation-bank-allocations" &&
          (!bankPaymentSign ||
            !obligationMonthStart ||
            !obligationMonthEnd ||
            !settlementStart ||
            !account.trim())
        )
          throw new Error(
            "Declare obligation months, bank account, settlement window and payment sign before allocating.",
          );
        if (workflow === "open-item-allocations" && !invoiceFaceAmounts)
          throw new Error(
            "Confirm that invoices contain face amounts before cash allocation.",
          );
        if (workflow === "credit-note-applications" && !invoiceFaceAmounts)
          throw new Error(
            "Confirm that balances are before the listed credit applications.",
          );
        if (
          ["india-withholding-liability", "india-withholding-credit"].includes(
            workflow,
          ) &&
          !withholdingRole
        )
          throw new Error(
            "Select the organization’s legal withholding role before comparing sources.",
          );
        payload = {
          workflow,
          ...([
            "india-withholding-liability",
            "india-withholding-credit",
          ].includes(workflow)
            ? { withholding_role: withholdingRole }
            : {}),
          ...(workflow === "open-item-allocations"
            ? { allocation_basis: "invoice_face_amounts" }
            : workflow === "credit-note-applications"
              ? { allocation_basis: "pre_application_balances" }
              : {}),
          ...(workflow === "inventory-count-bridge"
            ? {
                stock_bridge_mode: stockControlled
                  ? "bidirectional-controlled"
                  : "forward",
                ...(stockControlled
                  ? {
                      review_through: reviewThrough,
                      stock_cutoff_assessment: stockCutoffAssessment,
                    }
                  : {}),
              }
            : {}),
          ...([
            "statutory-dues",
            "india-payroll-rules",
            "obligation-bank-allocations",
          ].includes(workflow)
            ? { arrear_only: arrearsOnly }
            : {}),
          source_ids: sources,
          as_of: asOf,
          title: label,
          rationale: reason,
          currency: [
            "india-payroll-rules",
            "india-gst",
            "india-withholding",
            "india-withholding-liability",
            "india-withholding-credit",
          ].includes(workflow)
            ? "INR"
            : workflow === "uae-pension-review"
              ? "AED"
              : currency,
          ...([
            "bank-subsequent-clearance",
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
            "payroll-ledger-rollforward",
          ].includes(workflow)
            ? { period_start: periodStart }
            : {}),
          ...(taxYear ? { tax_year_start: taxYear } : {}),
          ...(workflow === "bank-brs" ? { account, ...balances } : {}),
          ...(workflow === "bank-subsequent-clearance" ? { account } : {}),
          ...(workflow === "obligation-bank-allocations"
            ? {
                account,
                obligation_month_start: obligationMonthStart,
                obligation_month_end: obligationMonthEnd,
                settlement_start: settlementStart,
                bank_payment_sign: bankPaymentSign,
              }
            : {}),
          required_checks: requiredChecks
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          required_boxes: requiredBoxes
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          ...(workflow === "uae-vat-return" && restrictBoxes
            ? {
                restrict_to_required_boxes: true,
                box_scope_assessment: boxScopeAssessment,
              }
            : {}),
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
    <div className="intelligence-workspace">
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
      {mode === "workflow-source" && config.data?.country === "AE" && (
        <VATCompositionSource
          eid={eid}
          sources={results.data?.items || []}
          onCreated={setSelected}
        />
      )}
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
                        setRuleDocument("");
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
                  {["payroll-bases", "pension-bases"].includes(tableType) && (
                    <p>
                      Payroll base controls sum assessed bases across component
                      rows. They are not gross payroll totals. Record each
                      authority, scheme, membership continuity, salary basis,
                      exemption decision and its evidence reference explicitly.
                    </p>
                  )}
                  {[
                    "fx-rates",
                    "payroll-rules",
                    "pension-rules",
                    "benefit-rules",
                    "withholding-records",
                  ].includes(tableType) && (
                    <>
                      <label>
                        {tableType === "fx-rates"
                          ? "Retained exchange-rate quote (optional shared document)"
                          : tableType === "withholding-records"
                            ? "Withholding assessment document (optional shared document)"
                            : `${tableType === "benefit-rules" ? "Benefit" : tableType === "pension-rules" ? "Pension" : "Payroll"} rule source document (optional shared document)`}
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
                        {tableType === "fx-rates" ? (
                          <>
                            Select the retained quote to bind its document ID
                            and hash to blank CSV fields. Conflicting references
                            are rejected. Declare the direct currency pair,
                            effective coverage, rate method and applicability
                            assessment in the CSV; independently review the rate
                            source before conversion.
                          </>
                        ) : tableType === "withholding-records" ? (
                          <>
                            Select a retained assessment document to fill blank
                            evidence IDs and hashes. Declare the assessment kind
                            and coverage dates in the CSV; certificate
                            assessments also require a shared amount cap.
                            Expected liability and certificate-credit records
                            need this support before approval. Selection does
                            not establish legal applicability.
                          </>
                        ) : (
                          <>
                            Select a retained document to fill blank
                            source-document references and hashes in the CSV.
                            Conflicting references are rejected. Independently
                            review this source before calculating expected dues.
                            Payroll rules must cover the whole wage month;
                            benefit rules must cover the service-end date and
                            assessed employment regime.
                          </>
                        )}
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
                  {["camt053", "swift-mt940"].includes(sourceFormat) && (
                    <label>
                      {sourceFormat === "swift-mt940"
                        ? "First message reference (optional cross-check)"
                        : "Statement identifier (required when selection is ambiguous)"}
                      <input
                        value={statementIdentifier}
                        onChange={(e) => setStatementIdentifier(e.target.value)}
                      />
                    </label>
                  )}
                  {["uae-wps-sif", "uae-wps-sif-evp"].includes(
                    sourceFormat,
                  ) && (
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
                  {sourceFormat === "uae-wps-sif-evp" && (
                    <fieldset>
                      <legend>WPS variable-pay component controls</legend>
                      <p>
                        EVP details must follow their employee EDR and equal its
                        variable income. Details are already included in salary,
                        so they do not create additional obligations. Confirm
                        this explicit bank layout against your retained source.
                      </p>
                      <label>
                        Independent EVP record count
                        <input
                          type="number"
                          min={0}
                          max={5000}
                          step={1}
                          value={wpsVariableCount}
                          onChange={(e) => setWPSVariableCount(e.target.value)}
                        />
                      </label>
                      <label>
                        Independent EVP component totals (AED, JSON)
                        <textarea
                          style={{ height: 240 }}
                          value={wpsVariableTotals}
                          onChange={(e) => setWPSVariableTotals(e.target.value)}
                          spellCheck={false}
                        />
                      </label>
                      <Button
                        onClick={() =>
                          setWPSVariableTotals(
                            JSON.stringify(
                              {
                                housing_allowance: null,
                                conveyance_allowance: null,
                                medical_allowance: null,
                                annual_passage_allowance: null,
                                overtime_allowance: null,
                                other_allowances: null,
                                leave_encashment: null,
                              },
                              null,
                              2,
                            ),
                          )
                        }
                      >
                        Insert EVP control format
                      </Button>
                      <p>
                        Enter all seven independently checked totals, including
                        explicit zeros. Employee count and salary totals exclude
                        separate EVP detail records. No routing-master
                        verification or bank acceptance is established.
                      </p>
                    </fieldset>
                  )}
                  {sourceFormat === "india-epfo-arrear-ecr-v2" && (
                    <fieldset>
                      <legend>
                        Arrear ECR context and independent controls
                      </legend>
                      <p>
                        Explicit EPFO ECR 2.0 eight-field layout. Employer EPF
                        is field 7 and pension field 8. Declare one assessed
                        wage month for every member; this file does not supply
                        establishment, original wage-month attribution or salary
                        disbursement context. Confirm layout applicability
                        against retained evidence for the selected period.
                      </p>
                      <label>
                        Retained arrear month/disbursement context
                        <select
                          value={ecrArrearContext}
                          onChange={(e) => setECRArrearContext(e.target.value)}
                        >
                          <option value="">
                            Select separate clean context evidence
                          </option>
                          {inputs.data?.evidence
                            .filter(
                              (item) =>
                                item.scan_status === "CLEAN" &&
                                item.id !== evidence,
                            )
                            .map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.label}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label>
                        Salary arrear disbursement date
                        <input
                          type="date"
                          value={ecrDisbursed}
                          onChange={(e) => setECRDisbursed(e.target.value)}
                        />
                      </label>
                      <label>
                        Independent arrear wage and contribution totals (INR,
                        JSON)
                        <textarea
                          style={{ height: 240 }}
                          value={ecrArrearControls}
                          onChange={(e) => setECRArrearControls(e.target.value)}
                          spellCheck={false}
                        />
                      </label>
                      <Button
                        onClick={() =>
                          setECRArrearControls(
                            JSON.stringify(
                              {
                                epf_wages: null,
                                eps_wages: null,
                                edli_wages: null,
                                employee_pf: null,
                                employer_pf: null,
                                employer_eps: null,
                              },
                              null,
                              2,
                            ),
                          )
                        }
                      >
                        Insert arrear control format
                      </Button>
                      <label>
                        Arrear wage-month attribution assessment
                        <textarea
                          style={{ height: 100 }}
                          value={ecrArrearAssessment}
                          onChange={(e) =>
                            setECRArrearAssessment(e.target.value)
                          }
                        />
                      </label>
                      <p>
                        Declare three component rows per member, including
                        zeros. Salary disbursement is not PF payment. Filing,
                        membership and legal rate correctness remain unverified.
                        Independently review this source and compare it only
                        with separately tagged arrear expectations and payments.
                      </p>
                    </fieldset>
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
                        fields; they do not represent eligible credit. For
                        numbered downloads, select the original pagination
                        manifest as the clean retained evidence and declare
                        every original response below. Unknown sections and
                        token pagination remain unsupported.
                      </p>
                    </>
                  )}
                  {sourceFormat === "india-gstr2b-json" && (
                    <fieldset>
                      <legend>Numbered GSTR-2B response files</legend>
                      <label
                        style={{ flexDirection: "row", alignItems: "center" }}
                      >
                        <input
                          type="checkbox"
                          style={{ width: 16, height: 16, flexShrink: 0 }}
                          checked={gstrBundle}
                          onChange={(event) =>
                            setGSTRBundle(event.target.checked)
                          }
                        />
                        Assemble numbered GSTR-2B files
                      </label>
                      {gstrBundle && (
                        <>
                          <p>
                            The main retained file must be the original manifest
                            containing fc. File numbers refer to original
                            retrieval requests. Missing response dates rely on
                            manifest and batch assessment; independent source
                            review is required.
                          </p>
                          <label>
                            Independent GSTR-2B file count
                            <input
                              type="number"
                              min={1}
                              max={100}
                              value={gstrFiles}
                              onChange={(event) =>
                                setGSTRFiles(event.target.value)
                              }
                            />
                          </label>
                          <label>
                            Original response parts and independent controls
                            (JSON)
                            <textarea
                              value={gstrParts}
                              style={{
                                height: Math.min(
                                  640,
                                  Math.max(
                                    320,
                                    (gstrParts.split("\n").length + 1) * 18,
                                  ),
                                ),
                              }}
                              onChange={(event) =>
                                setGSTRParts(event.target.value)
                              }
                              spellCheck={false}
                            />
                          </label>
                          <Button
                            onClick={() =>
                              setGSTRParts(
                                JSON.stringify(
                                  [
                                    {
                                      file_number: null,
                                      evidence_version_id: "",
                                      expected_documents: null,
                                      tax_total: null,
                                      request_reference: "",
                                    },
                                  ],
                                  null,
                                  2,
                                ),
                              )
                            }
                          >
                            Insert numbered-response format
                          </Button>
                          <label>
                            GSTR-2B retrieval batch assessment
                            <textarea
                              style={{ height: 80 }}
                              value={gstrAssessment}
                              onChange={(event) =>
                                setGSTAssessment(event.target.value)
                              }
                            />
                          </label>
                          <p>
                            Supply all files 1..count, distinct clean evidence
                            versions, per-file document counts and signed INR
                            tax controls. Repeated bytes, missing files and
                            conflicting scope fail preparation. File hashes
                            preserve retained bytes; they do not authenticate
                            GSTN or establish ITC entitlement.
                          </p>
                        </>
                      )}
                    </fieldset>
                  )}
                  {["india-epfo-ecr", "india-epfo-arrear-ecr-v2"].includes(
                    sourceFormat,
                  ) && (
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
                  {["stock", "stock-movements"].includes(tableType) && (
                    <fieldset>
                      <legend>Inventory partition quantity controls</legend>
                      <label
                        style={{ flexDirection: "row", alignItems: "center" }}
                      >
                        <input
                          type="checkbox"
                          style={{ width: 16, height: 16 }}
                          checked={inventoryControlsEnabled}
                          onChange={(e) =>
                            setInventoryControlsEnabled(e.target.checked)
                          }
                        />
                        Declare independent inventory quantity controls
                      </label>
                      {inventoryControlsEnabled && (
                        <>
                          <p>
                            Control every site, SKU, lot, UOM and currency
                            separately. Declare row count and positive/negative
                            quantities independently; a zero net movement is not
                            a nil population. An explicitly nil source uses an
                            empty control list and the nil rationale.
                          </p>
                          <label>
                            Independent inventory partitions (JSON)
                            <textarea
                              style={{
                                height: Math.min(
                                  640,
                                  Math.max(
                                    320,
                                    (inventoryControls.split("\n").length + 1) *
                                      18,
                                  ),
                                ),
                              }}
                              value={inventoryControls}
                              onChange={(e) =>
                                setInventoryControls(e.target.value)
                              }
                              spellCheck={false}
                            />
                          </label>
                          <Button
                            onClick={() =>
                              setInventoryControls(
                                JSON.stringify(
                                  [
                                    {
                                      site: "",
                                      sku: "",
                                      lot: "",
                                      uom: "",
                                      currency: "",
                                      expected_rows: null,
                                      positive_quantity: null,
                                      negative_quantity: null,
                                    },
                                  ],
                                  null,
                                  2,
                                ),
                              )
                            }
                          >
                            Insert inventory control format
                          </Button>
                        </>
                      )}
                    </fieldset>
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
                        {tableType === "return-boxes"
                          ? "Sum the tax fields across every retained row, including summary boxes. This file control is not VAT payable or recoverable."
                          : tableType === "import-vat-lines"
                            ? "Tax totals across every retained row, including superseded and cancelled observations. Control the taxable base separately below."
                            : "Signed amount totals; tax-document sources use tax totals. Confirmation sources use requested amounts."}
                      </small>
                    </label>
                  )}
                  {tableType === "import-vat-lines" && (
                    <label>
                      Independent import taxable-base total (AED)
                      <input
                        value={importBaseControl}
                        onChange={(event) =>
                          setImportBaseControl(event.target.value)
                        }
                      />
                      <small>
                        Control the entire retained file, including superseded
                        observations. The currency total above controls tax
                        separately.
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
                  aria-label="Workflow"
                  value={workflow}
                  onChange={(e) => {
                    setWorkflow(e.target.value);
                    setInvoiceFaceAmounts(false);
                    setWithholdingRole("");
                    setArrearsOnly(false);
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
              {workflow === "inventory-count-bridge" && (
                <fieldset>
                  <legend>Controlled inventory count-date bridge</legend>
                  <label style={{ flexDirection: "row", alignItems: "center" }}>
                    <input
                      type="checkbox"
                      style={{ width: 16, height: 16 }}
                      checked={stockControlled}
                      onChange={(e) => {
                        setStockControlled(e.target.checked);
                        setSources({});
                      }}
                    />
                    Use controlled counts before or after reporting
                  </label>
                  {stockControlled && (
                    <>
                      <label>
                        Inventory reporting currency
                        <input
                          value={currency}
                          maxLength={3}
                          onChange={(e) =>
                            setCurrency(e.target.value.toUpperCase())
                          }
                        />
                      </label>
                      <label>
                        Inventory evidence review through
                        <input
                          type="date"
                          min={asOf}
                          value={reviewThrough}
                          onChange={(e) => setReviewThrough(e.target.value)}
                        />
                      </label>
                      <label>
                        Inventory day-end cutoff assessment
                        <textarea
                          style={{ height: 100 }}
                          value={stockCutoffAssessment}
                          onChange={(e) =>
                            setStockCutoffAssessment(e.target.value)
                          }
                        />
                      </label>
                      <p>
                        All three sources need independent review and partition
                        quantity controls. Earlier counts add movements; later
                        counts subtract movements. The earlier day-end is
                        excluded and the later day-end included. No intraday
                        cutoff, reporting-date condition or physical attendance
                        is inferred.
                      </p>
                    </>
                  )}
                </fieldset>
              )}
              {[
                "statutory-dues",
                "india-payroll-rules",
                "obligation-bank-allocations",
              ].includes(workflow) && (
                <label style={{ flexDirection: "row", alignItems: "center" }}>
                  <input
                    type="checkbox"
                    style={{ width: 16, height: 16 }}
                    checked={arrearsOnly}
                    onChange={(e) => {
                      setArrearsOnly(e.target.checked);
                      setSources({});
                    }}
                  />
                  Compare arrears only, separately from regular monthly dues
                </label>
              )}
              {arrearsOnly && workflow === "statutory-dues" && (
                <label>
                  Arrear comparison currency
                  <input
                    value={currency}
                    maxLength={3}
                    onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                  />
                </label>
              )}
              {arrearsOnly &&
                [
                  "statutory-dues",
                  "india-payroll-rules",
                  "obligation-bank-allocations",
                ].includes(workflow) && (
                  <p>
                    Every expected, reported and payment obligation row must
                    declare population=arrears. Regular monthly activity is
                    outside this comparison. For payroll-rule review, use
                    independently assessed incremental arrear bases and
                    applicable rules.
                  </p>
                )}
              <label>
                Reconciliation date
                <input
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </label>
              {[
                "bank-subsequent-clearance",
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
                "payroll-ledger-rollforward",
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
                          (!arrearsOnly ||
                            r.table_type !== "obligations" ||
                            (r.obligation_populations?.length === 1 &&
                              r.obligation_populations[0] === "arrears")) &&
                          (r.native_format !== "india-epfo-arrear-ecr-v2" ||
                            (arrearsOnly && r.review_status === "REVIEWED")) &&
                          (workflow !== "inventory-count-bridge" ||
                            !stockControlled ||
                            (r.review_status === "REVIEWED" &&
                              r.inventory_controls_verified === true)) &&
                          (!r.allowed_source_roles ||
                            r.allowed_source_roles.includes(role)) &&
                          (![
                            "obligation-bank-allocations",
                            "payroll-ledger-rollforward",
                            "uae-pension-review",
                          ].includes(workflow) ||
                            r.review_status === "REVIEWED") &&
                          (![
                            "uae-wps-sif",
                            "uae-wps-sif-evp",
                            "india-epfo-ecr",
                          ].includes(r.native_format || "") ||
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
                <>
                  <label>
                    Required VAT201 boxes, comma separated
                    <input
                      value={requiredBoxes}
                      onChange={(e) => setRequiredBoxes(e.target.value)}
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={restrictBoxes}
                      onChange={(event) =>
                        setRestrictBoxes(event.target.checked)
                      }
                    />
                    Compare only the required VAT201 boxes
                  </label>
                  {restrictBoxes && (
                    <label>
                      Selected VAT201 box scope assessment
                      <textarea
                        aria-label="Selected VAT201 box scope assessment"
                        value={boxScopeAssessment}
                        onChange={(event) =>
                          setBoxScopeAssessment(event.target.value)
                        }
                      />
                      <small>
                        Other retained boxes remain outside this comparison.
                        Their original rows, counts and totals are retained for
                        review and export.
                      </small>
                    </label>
                  )}
                </>
              )}
              {workflow === "obligation-bank-allocations" && (
                <>
                  <label>
                    First obligation month
                    <input
                      type="month"
                      value={obligationMonthStart}
                      onChange={(e) => setObligationMonthStart(e.target.value)}
                    />
                  </label>
                  <label>
                    Last obligation month
                    <input
                      type="month"
                      value={obligationMonthEnd}
                      onChange={(e) => setObligationMonthEnd(e.target.value)}
                    />
                  </label>
                  <label>
                    Bank settlement window starts
                    <input
                      type="date"
                      value={settlementStart}
                      max={asOf}
                      onChange={(e) => setSettlementStart(e.target.value)}
                    />
                  </label>
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
                  <label>
                    Bank payment sign
                    <select
                      value={bankPaymentSign}
                      onChange={(e) => setBankPaymentSign(e.target.value)}
                    >
                      <option value="">
                        Select the source sign convention
                      </option>
                      <option value="debit-negative">
                        Payments are negative (native bank statements)
                      </option>
                      <option value="debit-positive">
                        Payments are positive (explicit mapped source)
                      </option>
                    </select>
                  </label>
                  <p>
                    Select independently reviewed expected obligations, reported
                    instructions/returns, bank movements and allocations. One
                    bank movement may settle several obligations; partial
                    payments and unallocated movements remain visible. Due dates
                    come from the assessed expected source.
                  </p>
                </>
              )}
              {workflow === "bank-subsequent-clearance" && (
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
                  <p>
                    Allocate later statement movements to retained
                    reporting-date outstanding items. Original outstanding
                    amounts stay unchanged; partial clearances and unallocated
                    movements remain visible.
                  </p>
                </>
              )}
              {workflow === "payroll-ledger-rollforward" && (
                <p>
                  Compare independently reviewed payroll allocations with posted
                  GL lines and prior-day opening / reporting-date closing
                  controls. Expense amounts are debit-positive; liability
                  amounts credit-positive. Wage month, component, posting
                  category, employer, account and currency stay separate. A
                  settlement journal does not prove payment execution.
                </p>
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
              {[
                "india-withholding-liability",
                "india-withholding-credit",
              ].includes(workflow) && (
                <label>
                  Organization legal withholding role
                  <select
                    value={withholdingRole}
                    onChange={(event) => setWithholdingRole(event.target.value)}
                  >
                    <option value="">Select the assessed role</option>
                    {(workflow === "india-withholding-liability"
                      ? [
                          ["deductor", "TDS deductor — liability"],
                          ["collector", "TCS collector — liability"],
                        ]
                      : [
                          ["deductee", "TDS deductee — credit evidence"],
                          ["collectee", "TCS collectee — credit evidence"],
                        ]
                    ).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {["open-item-allocations", "credit-note-applications"].includes(
                workflow,
              ) && (
                <label>
                  <input
                    type="checkbox"
                    checked={invoiceFaceAmounts}
                    onChange={(e) => setInvoiceFaceAmounts(e.target.checked)}
                  />
                  {workflow === "credit-note-applications"
                    ? "Balances are before the listed credit applications; these applications have not already been deducted."
                    : "Invoice amounts are face amounts before cash allocations, rather than already-net balances."}
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
      {mode === "workflow-source" &&
        config.data?.country === "AE" &&
        tableType === "benefit-rules" && (
          <PublishedBenefitSource
            key={`${tenant}:${eid}`}
            eid={eid}
            employees={results.data?.items || []}
            onCreated={setSelected}
          />
        )}
      {mode === "workflow-source" &&
        config.data?.country === "AE" &&
        tableType === "pension-rules" && (
          <PublishedPensionSource
            key={`${tenant}:${eid}`}
            eid={eid}
            employees={results.data?.items || []}
            onCreated={setSelected}
          />
        )}
      {mode === "workflow-source" &&
        config.data?.country === "IN" &&
        tableType === "payroll-rules" && (
          <PublishedPayrollSource
            key={`${tenant}:${eid}`}
            eid={eid}
            employees={results.data?.items || []}
            onCreated={setSelected}
          />
        )}
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
        Saved source or result
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
      {results.hasOlder && (
        <Button disabled={results.loadingOlder} onClick={results.loadOlder}>
          Load older sources and results
        </Button>
      )}
      {detail.data && body && (
        <section className="main-panel" style={{ padding: 20, marginTop: 16 }}>
          <h2>{body.title}</h2>
          {body.box_comparison_scope?.mode === "SELECTED_REQUIRED_BOXES" && (
            <section aria-label="Selected VAT201 comparison scope">
              <p>
                <strong>
                  Selected VAT201 boxes only:{" "}
                  {body.box_comparison_scope.required_boxes.join(", ")}.
                </strong>{" "}
                Whole-return completeness is not determined.
              </p>
              <p>{body.box_comparison_scope.assessment}</p>
              <p>
                {Object.entries(body.box_comparison_scope.excluded_rows)
                  .map(([role, count]) => `${role}: ${count} excluded rows`)
                  .join("; ")}
                . Excluded rows remain retained; the XLSX includes their full
                detail.
              </p>
              {!!body.included_box_controls?.length && (
                <details>
                  <summary>Included box control totals</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>
                    {text(body.included_box_controls)}
                  </pre>
                </details>
              )}
              {!!body.excluded_box_controls?.length && (
                <details>
                  <summary>Excluded box control totals</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>
                    {text(body.excluded_box_controls)}
                  </pre>
                </details>
              )}
              <ExcludedVATBoxes
                key={selected}
                prefix={prefix}
                selected={selected}
                initial={body.excluded_box_rows || []}
                total={
                  detail.data.collection_totals?.excluded_box_rows ??
                  body.excluded_box_rows?.length ??
                  0
                }
              />
            </section>
          )}
          {body.workflow === "bank-brs" &&
            body.review_status === "REVIEWED" &&
            !body.blocked &&
            detail.data.freshness === "CURRENT" && (
              <details>
                <summary>
                  Prepare selected outstanding items for subsequent clearance
                </summary>
                <p>
                  Select book-side exceptions from the displayed rows.
                  Selections persist across result pages. Enter independent
                  controls for the full selection. The new source retains
                  original book dates and requires independent review; this does
                  not establish later clearance.
                </p>
                <fieldset>
                  <legend>Outstanding book items</legend>
                  {rows
                    .filter((row) => row.side === "books")
                    .map((row) => (
                      <label key={String(row.id)}>
                        <input
                          type="checkbox"
                          checked={(
                            outstandingSelections[selected] || []
                          ).includes(String(row.id))}
                          onChange={(event) =>
                            setOutstandingSelections({
                              ...outstandingSelections,
                              [selected]: event.target.checked
                                ? [
                                    ...(outstandingSelections[selected] || []),
                                    String(row.id),
                                  ]
                                : (
                                    outstandingSelections[selected] || []
                                  ).filter((id) => id !== String(row.id)),
                            })
                          }
                        />
                        {String(row.id)} · {text(row.reference)} ·{" "}
                        {text(row.currency)} {text(row.amount)}
                      </label>
                    ))}
                </fieldset>
                <p>
                  {(outstandingSelections[selected] || []).length} selected
                  items
                </p>
                <label>
                  Outstanding source title
                  <input
                    value={outstandingLabel}
                    onChange={(event) =>
                      setOutstandingLabel(event.target.value)
                    }
                  />
                </label>
                <label>
                  Independent outstanding row count
                  <input
                    type="number"
                    min="1"
                    max="5000"
                    value={outstandingCount}
                    onChange={(event) =>
                      setOutstandingCount(event.target.value)
                    }
                  />
                </label>
                <label>
                  Independent outstanding signed total
                  <input
                    value={outstandingTotal}
                    onChange={(event) =>
                      setOutstandingTotal(event.target.value)
                    }
                  />
                </label>
                <label>
                  Outstanding population assessment
                  <textarea
                    value={outstandingAssessment}
                    onChange={(event) =>
                      setOutstandingAssessment(event.target.value)
                    }
                  />
                </label>
                <Button
                  disabled={
                    action.isPending ||
                    !(outstandingSelections[selected] || []).length
                  }
                  onClick={async () => {
                    const created = await action
                      .mutateAsync({
                        path: `${prefix}/events/${selected}/bank-outstanding-source`,
                        body: {
                          exception_ids: outstandingSelections[selected],
                          expected_rows: Number(outstandingCount),
                          signed_total: outstandingTotal,
                          label: outstandingLabel,
                          assessment: outstandingAssessment,
                        },
                      })
                      .catch(() => null);
                    if (created) {
                      setSelected(created.id);
                      setOffset(0);
                    }
                  }}
                >
                  Prepare outstanding source
                </Button>
              </details>
            )}
          {compactBankClearance &&
            body.review_status === "REVIEWED" &&
            !body.blocked &&
            detail.data.freshness === "CURRENT" && (
              <BankCarryforwardSource
                key={selected}
                prefix={prefix}
                selected={selected}
                onCreated={(id) => {
                  setSelected(id);
                  setOffset(0);
                }}
              />
            )}
          {compactImport &&
            body.review_status === "REVIEWED" &&
            !body.blocked &&
            detail.data.freshness === "CURRENT" && (
              <details>
                <summary>
                  Prepare selected import boxes for VAT201 comparison
                </summary>
                <p>
                  Choose the assessed source role and populated boxes. Supply
                  independent controls for each selected population. Missing Box
                  7 detail is not a nil declaration. The new source requires
                  independent review and can feed only the books side of the
                  VAT201 comparison.
                </p>
                <label>
                  Import box source title
                  <input
                    value={importBridgeLabel}
                    onChange={(event) =>
                      setImportBridgeLabel(event.target.value)
                    }
                  />
                </label>
                <label>
                  Assessed import source role
                  <select
                    value={importBridgeRole}
                    onChange={(event) =>
                      setImportBridgeRole(event.target.value)
                    }
                  >
                    <option value="">Select assessed role</option>
                    <option value="books">Books</option>
                    <option value="customs">Customs</option>
                    <option value="portal">Portal import detail</option>
                  </select>
                </label>
                {(["6", "7"] as const).map((box) => (
                  <fieldset key={box}>
                    <legend>Import Box {box}</legend>
                    <label>
                      <input
                        type="checkbox"
                        checked={importBridgeBoxes[box]}
                        onChange={(event) =>
                          setImportBridgeBoxes({
                            ...importBridgeBoxes,
                            [box]: event.target.checked,
                          })
                        }
                      />
                      Include import Box {box}
                    </label>
                    {importBridgeBoxes[box] &&
                      (
                        [
                          ["expected_rows", "expected detail rows"],
                          ["taxable_amount", "taxable amount (AED)"],
                          ["tax", "tax (AED)"],
                        ] as const
                      ).map(([field, label]) => (
                        <label key={field}>
                          Box {box} {label}
                          <input
                            value={importBridgeControls[box][field]}
                            onChange={(event) =>
                              setImportBridgeControls({
                                ...importBridgeControls,
                                [box]: {
                                  ...importBridgeControls[box],
                                  [field]: event.target.value,
                                },
                              })
                            }
                          />
                        </label>
                      ))}
                  </fieldset>
                ))}
                <label>
                  Import box scope assessment
                  <textarea
                    value={importBridgeAssessment}
                    onChange={(event) =>
                      setImportBridgeAssessment(event.target.value)
                    }
                  />
                </label>
                <Button
                  disabled={action.isPending}
                  onClick={async () => {
                    const boxes = Object.fromEntries(
                      Object.entries(importBridgeBoxes)
                        .filter(([, enabled]) => enabled)
                        .map(([box]) => [
                          box,
                          {
                            ...importBridgeControls[box],
                            expected_rows: Number(
                              importBridgeControls[box].expected_rows,
                            ),
                          },
                        ]),
                    );
                    const created = await action
                      .mutateAsync({
                        path: `${prefix}/events/${selected}/import-vat-box-source`,
                        body: {
                          source_role: importBridgeRole,
                          boxes,
                          label: importBridgeLabel,
                          assessment: importBridgeAssessment,
                        },
                      })
                      .catch(() => null);
                    if (created) {
                      setSelected(created.id);
                      setOffset(0);
                    }
                  }}
                >
                  Prepare import box source
                </Button>
              </details>
            )}
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
          {["open-item-allocations", "credit-note-applications"].includes(
            body.workflow ?? "",
          ) &&
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
          {compactImport && body.role_totals && (
            <div style={{ overflowX: "auto" }}>
              <p>
                Assessed import detail only. Box 6 and Box 7 populations remain
                separate; an absent population is not a verified nil return box.
              </p>
              <table aria-label="Import VAT selected population totals">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Population / indicative box</th>
                    <th>Selected rows</th>
                    <th>Taxable base AED</th>
                    <th>Tax AED</th>
                    <th>Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(body.role_totals).flatMap(([role, kinds]) =>
                    Object.entries(kinds).map(([kind, total]) => (
                      <tr key={`${role}:${kind}`}>
                        <td>{role}</td>
                        <td>
                          {kind} / {kind === "declaration" ? "6" : "7"}
                        </td>
                        <td>{total.selected_rows}</td>
                        <td>{total.net ?? "Not determined"}</td>
                        <td>{total.tax ?? "Not determined"}</td>
                        <td>
                          {total.complete_for_selected_population &&
                          total.selected_rows
                            ? "Selected current population"
                            : "Incomplete or not assessed"}
                        </td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          )}
          {["india-payroll-rules", "uae-pension-review"].includes(
            body.workflow || "",
          ) && (
            <>
              <p>
                {body.expected_total_complete === false
                  ? "Partial expected total"
                  : "Expected contributions"}
                : {body.currency} {body.expected_total}. Reported contributions:{" "}
                {body.currency} {body.reported_total}. Payment is not verified
                by this comparison.
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
          {["uae-pension-review", "india-payroll-rules"].includes(
            body.workflow || "",
          ) &&
            detail.data.freshness === "CURRENT" &&
            body.review_status === "REVIEWED" &&
            !body.blocked &&
            body.expected_total_complete === true && (
              <ContributionObligationSource
                key={`${tenant}:${eid}:${selected}`}
                eid={eid}
                resultId={selected}
                pension={body.workflow === "uae-pension-review"}
                evidence={inputs.data?.evidence || []}
                onCreated={setSelected}
              />
            )}
          {["india-gst", "uae-vat", "uae-vat-return"].includes(
            body.workflow || "",
          ) && (
            <label style={{ flexDirection: "row", alignItems: "center" }}>
              <input
                type="checkbox"
                style={{ width: 16, height: 16, flexShrink: 0 }}
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
          {body.allocation_controls && (
            <section aria-label="Obligation allocation controls">
              <h3>Obligation and bank allocation controls</h3>
              <dl
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                  gap: 12,
                }}
              >
                {Object.entries(body.allocation_controls).map(
                  ([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{value}</dd>
                    </div>
                  ),
                )}
              </dl>
              <details>
                <summary>Declared payment scope</summary>
                <dl>
                  {Object.entries(body.payment_scope || {}).map(
                    ([key, value]) => (
                      <div key={key}>
                        <dt>{key.replaceAll("_", " ")}</dt>
                        <dd>{value}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </details>
            </section>
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
          {body.workflow === "payroll-ledger-rollforward" && (
            <label>
              Payroll accounting view
              <select
                value={payrollView}
                onChange={(event) => {
                  setPayrollView(event.target.value);
                  setOffset(0);
                }}
              >
                <option value="accounts">
                  Account opening and closing balances
                </option>
                <option value="postings">
                  Payroll and posted direction comparisons
                </option>
              </select>
            </label>
          )}
          {body.payroll_posting_links && (
            <PayrollPostingLinks
              key={selected}
              prefix={prefix}
              selected={selected}
              initial={body.payroll_posting_links}
              total={
                detail.data.collection_totals?.payroll_posting_links ??
                body.payroll_posting_links.length
              }
            />
          )}
          {body.inventory_quantity_controls && (
            <InventoryEvidenceTable
              key={selected + ":inventory-controls"}
              prefix={prefix}
              selected={selected}
              initial={body.inventory_quantity_controls}
              total={
                detail.data.collection_totals?.inventory_quantity_controls ??
                body.inventory_quantity_controls.length
              }
            />
          )}
          {body.count_bridges && (
            <InventoryEvidenceTable
              key={selected + ":count-bridges"}
              prefix={prefix}
              selected={selected}
              initial={body.count_bridges}
              total={
                detail.data.collection_totals?.count_bridges ??
                body.count_bridges.length
              }
              bridge
            />
          )}
          {body.obligation_population_scope ===
            "ARREARS_ONLY_NOT_COMPLETE_MONTHLY_RETURN" && (
            <p role="note">
              Arrears only: regular monthly obligations, returns and payments
              are outside this comparison. Salary disbursement does not
              establish payment of PF contributions.
            </p>
          )}
          {body.native_metadata && (
            <details>
              <summary>Original source controls and calculation basis</summary>
              <dl>
                {Object.entries(body.native_metadata)
                  .filter(
                    ([key]) =>
                      !["message_controls", "page_controls"].includes(key) ||
                      !Array.isArray(body.native_metadata?.[key]),
                  )
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{text(value)}</dd>
                    </div>
                  ))}
              </dl>
              {!!body.native_metadata.variable_pay_component_totals &&
                typeof body.native_metadata.variable_pay_component_totals ===
                  "object" && (
                  <table aria-label="WPS variable-pay component controls">
                    <thead>
                      <tr>
                        <th>Variable-pay component</th>
                        <th>AED control total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {WPS_VARIABLE_FIELDS.map((name) => (
                        <tr key={name}>
                          <td>{name.replaceAll("_", " ")}</td>
                          <td>
                            {text(
                              (
                                body.native_metadata
                                  ?.variable_pay_component_totals as Record<
                                  string,
                                  unknown
                                >
                              )[name],
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              {!!body.native_metadata.arrear_controls &&
                typeof body.native_metadata.arrear_controls === "object" && (
                  <table aria-label="Arrear ECR independent controls">
                    <thead>
                      <tr>
                        <th>Arrear field</th>
                        <th>INR control total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        "epf_wages",
                        "eps_wages",
                        "edli_wages",
                        "employee_pf",
                        "employer_pf",
                        "employer_eps",
                      ].map((name) => (
                        <tr key={name}>
                          <td>{name.replaceAll("_", " ")}</td>
                          <td>
                            {text(
                              (
                                body.native_metadata?.arrear_controls as Record<
                                  string,
                                  unknown
                                >
                              )[name],
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              {Array.isArray(body.native_metadata.page_controls) && (
                <div className="table-wrap">
                  <table aria-label="CAMT statement page controls">
                    <thead>
                      <tr>
                        {[
                          "Page",
                          "Original statement position",
                          "Sequence",
                          "Currency",
                          "Opening",
                          "Closing",
                          "Entries",
                          "Entry total",
                          "Final page",
                        ].map((label) => (
                          <th key={label}>{label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        body.native_metadata.page_controls as Record<
                          string,
                          unknown
                        >[]
                      ).map((page, index) => (
                        <tr key={index}>
                          {[
                            "page_number",
                            "source_statement_position",
                            "electronic_sequence",
                            "currency",
                            "opening",
                            "closing",
                            "entry_count",
                            "entry_total",
                            "last_page",
                          ].map((key) => (
                            <td key={key}>{text(page[key])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <details>
                    <summary>
                      All retained statement page control fields
                    </summary>
                    <pre>
                      {JSON.stringify(
                        body.native_metadata.page_controls,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </div>
              )}
              {Array.isArray(body.native_metadata.message_controls) && (
                <div className="table-wrap">
                  <table aria-label="MT940 message controls">
                    <thead>
                      <tr>
                        {[
                          "Sequence",
                          "Original message",
                          "Reference",
                          "Currency",
                          "Opening tag",
                          "Opening",
                          "Closing tag",
                          "Closing",
                          "Entries",
                        ].map((label) => (
                          <th key={label}>{label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        body.native_metadata.message_controls as Record<
                          string,
                          unknown
                        >[]
                      ).map((message, index) => (
                        <tr key={index}>
                          <td>{text(message.statement_sequence)}</td>
                          <td>{text(message.source_message_index)}</td>
                          <td>{text(message.statement_id)}</td>
                          <td>{text(message.currency)}</td>
                          <td>{text(message.opening_tag)}</td>
                          <td>{text(message.opening)}</td>
                          <td>{text(message.closing_tag)}</td>
                          <td>{text(message.closing)}</td>
                          <td>{text(message.entry_count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <details>
                    <summary>All retained message control fields</summary>
                    <pre>
                      {JSON.stringify(
                        body.native_metadata.message_controls,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </div>
              )}
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
            {(compactSource ||
              compactArrearResult ||
              compactBenefit ||
              body.workflow === "payroll-ledger-rollforward" ||
              compactBankClearance ||
              compactDues ||
              compactCredit ||
              compactWithholding ||
              compactImport) && (
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  style={{ width: 16, height: 16, minHeight: 0, margin: 0 }}
                  checked={showRuleProvenance}
                  onChange={(event) =>
                    setShowRuleProvenance(event.target.checked)
                  }
                />
                Show source provenance and all columns
              </label>
            )}
            <table>
              <caption>
                Source-linked schedule · rows {offset + 1}–
                {offset + rows.length}; XLSX contains the full result
              </caption>
              <thead>
                <tr>
                  {columns.map((k) => (
                    <th key={k} scope="col">
                      {compactDues && k === "settled_or_allocated"
                        ? "allocated"
                        : k.replaceAll("_", " ")}
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
                      <td key={k}>
                        {compactWithholding &&
                        k === "assessment_issues" &&
                        Array.isArray(row[k]) ? (
                          <ul>
                            {(row[k] as unknown[]).map((issue) => (
                              <li key={String(issue)}>
                                {text(issue).replaceAll("_", " ").toLowerCase()}
                              </li>
                            ))}
                          </ul>
                        ) : compactWithholding &&
                          [
                            "amounts",
                            "differences_from_expected",
                            "differences_from_books",
                          ].includes(k) &&
                          row[k] &&
                          typeof row[k] === "object" &&
                          !Array.isArray(row[k]) ? (
                          <div style={{ display: "grid", gap: 4 }}>
                            {Object.entries(
                              row[k] as Record<string, unknown>,
                            ).map(([role, value]) => (
                              <span key={role}>
                                {role}: {text(value)}
                              </span>
                            ))}
                          </div>
                        ) : (
                          text(row[k])
                        )}
                      </td>
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
