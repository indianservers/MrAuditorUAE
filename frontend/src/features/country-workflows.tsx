"use client";

import Link from "next/link";
import { useState } from "react";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
import { BankCarryforwardSource } from "./bank-carryforward-source";
import { BankCashReview } from "./bank-cash-review";
import { ScreeningCandidates } from "./screening-candidates";
import { OwnershipPathEvidence } from "./ownership-path-evidence";
import { PartyConfirmationEvidence } from "./party-confirmation-evidence";
import { WithholdingObligationSource } from "./withholding-obligation-source";
import { ContributionObligationSource } from "./contribution-obligation-source";
import {
  BankAccountLinkReview,
  type BankAccountLink,
} from "./bank-account-link";
import { BankAccountEvidenceReview } from "./bank-account-evidence";
import { ImportNilScopeForm, type ImportNilDraft } from "./import-nil-scope";
import { BankTransactionDates } from "./bank-transaction-dates";
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
  workflow?: string | null;
  blocked?: boolean;
  as_of?: string | null;
  bank_account_scope?: { account: string; currency: string } | null;
  table_type?: string;
  native_format?: string;
  allowed_source_roles?: string[] | null;
  allowed_workflows?: string[] | null;
  invoice_direction?: string | null;
  inventory_controls_verified?: boolean;
  purchase_controls_verified?: boolean;
  obligation_populations?: string[] | null;
  table_kind?: string;
  evidence_version_id?: string;
};
type Workflow = {
  id: string;
  title: string;
  available: boolean;
  roles: Record<string, string>;
  optional_roles?: Record<string, string>;
};
type Result = {
  dependencies?: {
    type: string;
    id: string;
    record_id?: string;
    sha256?: string;
  }[];
  id: string;
  version: number;
  kind: string;
  freshness: string;
  collection_totals?: Record<string, number>;
  body: {
    workflow?: string;
    vat201_layout?: string;
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
    outward_gst_scope?: Record<string, unknown>;
    invoice_evidence_scope?: { direction: string; filing_status: string };
    execution_mode?: string;
    language_model_dependency?: boolean;
    blocked?: boolean;
    booking_date_review_count?: number;
    bank_account_evidence?: BankAccountLink;
    document_series_scope?: { registration: string; period: string };
    inventory_valuation_scope?: {
      as_of: string;
      review_through: string;
      gl_basis: string;
      assessment: string;
    };
    confirmation_scope?: {
      as_of: string;
      review_through: string;
      open_items: number;
      party_positions: number;
      confirmation_rows: number;
      coverage_rows?: number;
    };
    confirmation_coverage_links?: Record<string, unknown>[];
    ownership_path_contract?: string;
    ownership_paths?: Record<string, unknown>[];
    ownership_path_steps?: Record<string, unknown>[];
    ownership_scope?: Record<string, unknown>;
    cutoff_document_controls?: Record<string, unknown>[];
    cutoff_posting_links?: Record<string, unknown>[];
    cutoff_schedule_contract?: string;
    esic_population_scope?: { registration: string; period: string };
    esic_population_binding?: {
      status: string;
      members?: number;
      basis_rows?: number;
      documented_population_exceptions?: number;
      components?: string[];
      assessment?: string;
      review_receipt?: { id: string };
      scope?: { registration: string; period: string };
    };
    esic_population_totals?: Record<
      string,
      {
        members: number;
        wages: string;
        paid_days: number;
        zero_wage_members: number;
      }
    >;
    import_nil_scope?: ImportNilDraft & { binding_status: string };
    exception_count?: number;
    table_type?: string;
    rows: Record<string, unknown>[];
    count_bridges?: Record<string, unknown>[];
    payroll_posting_links?: Record<string, unknown>[];
    transaction_dates?: Record<string, unknown>[];
    inventory_quantity_controls?: Record<string, unknown>[];
    purchase_quantity_controls?: Record<string, unknown>[];
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
    metric_controls?: Record<string, string>;
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
  "esic-members",
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
  "cutoff-recognition-lines",
  "cutoff-posting-lines",
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
  initialEvent = "",
}: {
  eid: string;
  mode: "workflow-source" | "country-workflow";
  initialEvent?: string;
}) {
  const prefix = `intelligence/engagements/${eid}`;
  const tenant = useScope((s) => s.tenant);
  const canUseVAT = useCan("vat.read");
  const config = useAPI<{
    country: string;
    items: Workflow[];
    vat201_layouts?: Record<string, { label: string; boxes: string[] }>;
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
    evidence: {
      id: string;
      label: string;
      scan_status: string;
      sha256?: string;
    }[];
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
  const [selected, setSelected] = useState(initialEvent);
  const [showAllJobs, setShowAllJobs] = useState(false);
  const [offset, setOffset] = useState(0);
  const [payrollView, setPayrollView] = useState("accounts");
  const [inventoryView, setInventoryView] = useState("valuations");
  const [confirmationView, setConfirmationView] = useState("parties");
  const detail = useAPI<Result>(
    `${prefix}/events/${selected}?offset=${offset}&limit=100&payroll_view=${payrollView}&inventory_view=${inventoryView}&confirmation_view=${confirmationView}`,
    !!selected,
  );
  const [workflow, setWorkflow] = useState("bank-brs");
  const [invoiceDirection, setInvoiceDirection] = useState("");
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
  const [inventoryValueControls, setInventoryValueControls] = useState("[]");
  const [purchaseControls, setPurchaseControls] = useState("[]");
  const [confirmationDocuments, setConfirmationDocuments] = useState<
    Record<string, string>
  >({});
  const [confirmationResponseTotals, setConfirmationResponseTotals] =
    useState("{}");
  const [confirmationRequestTotals, setConfirmationRequestTotals] =
    useState("{}");
  const [inventoryCostEvidence, setInventoryCostEvidence] = useState("");
  const [inventoryNRVEvidence, setInventoryNRVEvidence] = useState("");
  const [inventoryGLBasis, setInventoryGLBasis] = useState("");
  const [inventoryScopeAssessment, setInventoryScopeAssessment] = useState("");
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
  const [seriesControls, setSeriesControls] = useState({
    issued: "",
    cancelled: "",
    net_issued: "",
  });
  const [gstr1Controls, setGSTR1Controls] = useState("[]");
  const [gstr1Context, setGSTR1Context] = useState("");
  const [gstr1Assessment, setGSTR1Assessment] = useState("");
  const [gstSummaryControls, setGSTSummaryControls] = useState("{}");
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
  const [esicDaysControl, setEsicDaysControl] = useState("");
  const [esicZeroControl, setEsicZeroControl] = useState("");
  const [esicContextEvidence, setEsicContextEvidence] = useState("");
  const [esicReturnKind, setEsicReturnKind] = useState("monthly");
  const [esicScopeAssessment, setEsicScopeAssessment] = useState("");
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
  const [vatLayout, setVATLayout] = useState("custom");
  const [restrictBoxes, setRestrictBoxes] = useState(false);
  const [boxScopeAssessment, setBoxScopeAssessment] = useState("");
  const [subjects, setSubjects] = useState("");
  const [account, setAccount] = useState("");
  const [importNil, setImportNil] = useState<ImportNilDraft | null>(null);
  const [bankAccountReview, setBankAccountReview] = useState("");
  const [esicPopulationReview, setEsicPopulationReview] = useState("");
  const [esicBasisAssessment, setEsicBasisAssessment] = useState("");
  const [esicComponents, setEsicComponents] = useState("both");
  const [bankAccountAssessment, setBankAccountAssessment] = useState("");
  const [bankOwnerName, setBankOwnerName] = useState("");
  const [bankOwnerScheme, setBankOwnerScheme] = useState("");
  const [bankOwnerIdentifier, setBankOwnerIdentifier] = useState("");
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
    body?.workflow === "india-document-series" && !showRuleProvenance
      ? (body.rows || []).map((row) => ({
          id: row.id,
          doc_num: row.doc_num,
          serial_from: row.serial_from,
          serial_to: row.serial_to,
          ...Object.fromEntries(
            ["issued", "cancelled", "net_issued"].flatMap((field) => [
              [
                `books_${field}`,
                (row.books_counts as Record<string, number> | null)?.[field] ??
                  "Not determined",
              ],
              [
                `reported_${field}`,
                (row.reported_counts as Record<string, number> | null)?.[
                  field
                ] ?? "Not determined",
              ],
              [
                `${field}_difference`,
                (row.differences as Record<string, number | null>)[field] ??
                  "Not determined",
              ],
            ]),
          ),
          state: row.state,
        }))
      : body?.workflow === "obligation-bank-allocations" && !showRuleProvenance
        ? (body.rows || []).map((row) => ({
            ...row,
            subject: row.subject ?? row.reference,
            ...(row.withholding_scope
              ? {
                  tax_section: (row.withholding_scope as Record<string, string>)
                    .rule_reference,
                  tax_year: `${(row.withholding_scope as Record<string, string>).tax_year_start} to ${(row.withholding_scope as Record<string, string>).tax_year_end}`,
                  withholding_transaction: (
                    row.withholding_scope as Record<string, string>
                  ).transaction_reference,
                  withholding_date: (
                    row.withholding_scope as Record<string, string>
                  ).transaction_date,
                }
              : {}),
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
              expected_amount: (row.amounts as Record<string, unknown>)
                ?.expected,
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
          "emirate",
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
              "tax_section",
              "tax_year",
              "withholding_transaction",
              "withholding_date",
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
                          "esic_payroll_wages",
                          "esic_reported_wages",
                          "esic_base_minus_payroll_wages",
                          "esic_base_minus_reported_wages",
                          "expected_amount",
                          "reported_amount",
                          "difference",
                          "state",
                        ].filter((key) => allColumns.includes(key))
                      : [
                            "india-gst",
                            "india-gstr1-documents",
                            "uae-vat",
                            "india-invoice-register",
                          ].includes(body?.workflow || "") &&
                          !showRuleProvenance
                        ? [
                            "counterparty",
                            "reference",
                            "document_type",
                            "component",
                            "currency",
                            "books_tax",
                            "return_tax",
                            "invoices_tax",
                            "tax_difference",
                            "net_difference",
                            "state",
                            "source_review_reasons",
                          ].filter((key) => allColumns.includes(key))
                        : allColumns;
  const baseColumns =
    (body?.workflow === "india-gstr1-summary" ||
      body?.table_type === "gst-summary-metrics") &&
    !showRuleProvenance
      ? [
          "section",
          "sub_section",
          "nature",
          "counterparty",
          "state_code",
          "metric",
          "unit",
          "value",
          "books_value",
          "return_value",
          "difference",
          "state",
        ].filter((key) => allColumns.includes(key))
      : body?.workflow === "payroll-ledger-rollforward" && !showRuleProvenance
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
                "subject",
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
  const columns =
    body?.workflow === "ownership-lookthrough" && !showRuleProvenance
      ? [
          "company",
          "person_id",
          "economic_fraction",
          "fraction_scope",
          "threshold_candidate",
          "path_count",
          "state",
        ].filter((key) => allColumns.includes(key))
      : body?.cutoff_schedule_contract && !showRuleProvenance
        ? [
            "allocation_source_id",
            "document_source_id",
            "counterparty",
            "currency",
            "recognition_date",
            "expected_period_amount",
            "posted_period_amount",
            "difference",
            "state",
          ].filter((key) => allColumns.includes(key))
        : body?.workflow === "party-balance-confirmations" &&
            !showRuleProvenance
          ? (confirmationView === "gl-controls"
              ? [
                  "account",
                  "side",
                  "currency",
                  "subledger_amount",
                  "control_amount",
                  "difference",
                  "state",
                ]
              : [
                  "account",
                  "counterparty",
                  "side",
                  "currency",
                  "open_item_count",
                  "book_balance",
                  "request_basis",
                  "confirmation_status",
                  "response_amount",
                  "difference",
                  "state",
                ]
            ).filter((key) => allColumns.includes(key))
          : body?.workflow === "procurement-match" && !showRuleProvenance
            ? [
                "order_id",
                "line_reference",
                "vendor",
                "currency",
                "uom",
                "quantity_comparison_status",
                "quantities",
                "amounts",
                "exceptions",
                "state",
              ].filter((key) => allColumns.includes(key))
            : body?.workflow === "sanctions-name-review" && !showRuleProvenance
              ? [
                  "id",
                  "subject_name",
                  "list_version",
                  "candidate_count",
                  "candidate_preview_truncated",
                  "state",
                  "reviewer_disposition",
                ].filter((key) => allColumns.includes(key))
              : body?.workflow === "inventory-valuation-control" &&
                  !showRuleProvenance
                ? (inventoryView === "gl-controls"
                    ? [
                        "account",
                        "currency",
                        "recorded_book_value",
                        "gl_amount",
                        "difference",
                        "state",
                      ]
                    : [
                        "site",
                        "sku",
                        "lot",
                        "uom",
                        "currency",
                        "book_quantity",
                        "book_unit_cost",
                        "assessed_unit_cost",
                        "book_unit_nrv",
                        "assessed_unit_nrv",
                        "recorded_gl_basis_value",
                        "assessed_lower_cost_nrv_value",
                        "recorded_minus_assessed_value",
                        "exceptions",
                        "state",
                      ]
                  ).filter((key) => allColumns.includes(key))
                : body?.table_type === "esic-members" && !showRuleProvenance
                  ? [
                      "subject",
                      "member_name",
                      "period",
                      "currency",
                      "amount",
                      "paid_days",
                      "zero_wage_reason",
                      "zero_day_reason",
                      "last_working_day",
                      "source_row",
                    ].filter((key) => allColumns.includes(key))
                  : body?.workflow === "india-esic-population" &&
                      !showRuleProvenance
                    ? [
                        "subject",
                        "payroll_member_name",
                        "reported_member_name",
                        "payroll_amount",
                        "reported_amount",
                        "wage_difference",
                        "payroll_paid_days",
                        "reported_paid_days",
                        "paid_day_difference",
                        "exceptions",
                        "state",
                      ].filter((key) => allColumns.includes(key))
                    : baseColumns;
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
              ...(tableType === "party-confirmations"
                ? {
                    confirmation_request_totals: JSON.parse(
                      confirmationRequestTotals,
                    ),
                    confirmation_response_totals: JSON.parse(
                      confirmationResponseTotals,
                    ),
                    ...Object.fromEntries(
                      Object.entries(confirmationDocuments)
                        .filter(([, value]) => value)
                        .map(([prefix, value]) => [
                          `confirmation_${prefix}_document_version_id`,
                          value,
                        ]),
                    ),
                  }
                : {}),
              ...(tableType === "purchase-lines"
                ? { purchase_quantity_controls: JSON.parse(purchaseControls) }
                : {}),
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
              ...(tableType === "gst-document-series"
                ? { document_series_controls: seriesControls }
                : {}),
              ...(sourceFormat === "india-gstr1-document-series-json"
                ? {
                    gst_registration: gstRegistration,
                    gst_period: gstPeriod,
                    gstr1_context_evidence_version_id: gstr1Context,
                    gstr1_retrieval_assessment: gstr1Assessment,
                  }
                : {}),
              ...(tableType === "gst-summary-metrics"
                ? {
                    gst_summary_metric_controls: JSON.parse(gstSummaryControls),
                  }
                : {}),
              ...(sourceFormat === "india-gstr1-documents-json"
                ? {
                    gst_registration: gstRegistration,
                    gst_period: gstPeriod,
                    expected_documents: Number(expectedDocuments),
                    gstr1_section_controls: JSON.parse(gstr1Controls),
                    gstr1_context_evidence_version_id: gstr1Context,
                    gstr1_retrieval_assessment: gstr1Assessment,
                  }
                : {}),
              ...(sourceFormat === "india-gstr1-summary-json"
                ? { gst_registration: gstRegistration, gst_period: gstPeriod }
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
              ...(tableType === "inventory-valuations"
                ? {
                    inventory_valuation_controls: JSON.parse(
                      inventoryValueControls,
                    ),
                    ...(inventoryCostEvidence
                      ? {
                          inventory_cost_document_version_id:
                            inventoryCostEvidence,
                        }
                      : {}),
                    ...(inventoryNRVEvidence
                      ? {
                          inventory_nrv_document_version_id:
                            inventoryNRVEvidence,
                        }
                      : {}),
                  }
                : {}),
              ...(sourceFormat === "india-esic-members-xls"
                ? {
                    employer_registration: employerRegistration,
                    obligation_period: obligationPeriod,
                    esic_context_evidence_version_id: esicContextEvidence,
                    esic_return_kind: esicReturnKind,
                    esic_scope_assessment: esicScopeAssessment,
                  }
                : {}),
              ...(tableType === "esic-members"
                ? {
                    esic_paid_days_control: esicDaysControl.trim()
                      ? Number(esicDaysControl)
                      : null,
                    esic_zero_wage_members_control: esicZeroControl.trim()
                      ? Number(esicZeroControl)
                      : null,
                  }
                : {}),
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
        if (
          [
            "bank-brs",
            "bank-subsequent-clearance",
            "obligation-bank-allocations",
          ].includes(workflow) &&
          bankAccountReview &&
          bankAccountAssessment.trim().length < 10
        )
          throw new Error(
            "Assess the linked bank account, original bank identifier and complete review window before calculation.",
          );
        if (
          workflow === "bank-account-evidence" &&
          (!account.trim() ||
            !bankOwnerName.trim() ||
            !bankOwnerScheme.trim() ||
            !bankOwnerIdentifier.trim())
        )
          throw new Error(
            "Declare the account, engagement entity name and owner identifier before comparison.",
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
          ...(workflow === "inventory-valuation-control"
            ? {
                inventory_gl_basis: inventoryGLBasis,
                inventory_scope_assessment: inventoryScopeAssessment,
                review_through: reviewThrough,
              }
            : {}),
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
          ...(workflow === "india-invoice-register"
            ? { invoice_direction: invoiceDirection }
            : {}),
          ...(workflow === "india-payroll-rules" && esicPopulationReview
            ? {
                esic_population_review_id: esicPopulationReview,
                esic_basis_scope_assessment: esicBasisAssessment,
                esic_components:
                  esicComponents === "both"
                    ? ["ESI:EMPLOYEE", "ESI:EMPLOYER"]
                    : [esicComponents],
              }
            : {}),
          ...(workflow === "uae-import-vat" && importNil
            ? { import_nil_scope: importNil }
            : {}),
          source_ids: sources,
          as_of: asOf,
          title: label,
          rationale: reason,
          currency: [
            "india-esic-population",
            "india-document-series",
            "india-gstr1-documents",
            "india-gstr1-summary",
            "india-payroll-rules",
            "india-gst",
            "india-invoice-register",
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
            "party-balance-confirmations",
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
          ...(workflow === "bank-account-evidence"
            ? {
                account,
                bank_owner_name: bankOwnerName,
                bank_owner_identifier_scheme: bankOwnerScheme,
                bank_owner_identifier: bankOwnerIdentifier,
              }
            : {}),
          ...([
            "bank-brs",
            "bank-subsequent-clearance",
            "obligation-bank-allocations",
          ].includes(workflow) && bankAccountReview
            ? {
                bank_account_review_id: bankAccountReview,
                bank_account_scope_assessment: bankAccountAssessment,
              }
            : {}),
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
          ...(workflow === "uae-vat-return"
            ? { vat201_layout: vatLayout }
            : {}),
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
          layouts={config.data?.vat201_layouts}
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
                        if (chosenFormat?.table_type === "gst-document-series")
                          setTotals("");
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
                        if (e.target.value === "gst-document-series")
                          setTotals("");
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
                  {sourceFormat === "india-gstr1-documents-json" && (
                    <fieldset style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                      <legend>
                        Outward invoice/note request scope and independent
                        controls
                      </legend>
                      <label>
                        Supplier GSTIN
                        <input
                          value={gstRegistration}
                          onChange={(event) =>
                            setGSTRegistration(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        GSTR-1 document reporting month
                        <input
                          type="month"
                          value={gstPeriod}
                          onChange={(event) => setGSTPeriod(event.target.value)}
                        />
                      </label>
                      <label>
                        Independent GSTR-1 document count
                        <input
                          type="number"
                          min={0}
                          max={1250}
                          value={expectedDocuments}
                          onChange={(event) =>
                            setExpectedDocuments(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        Retained GSTR-1 request context
                        <select
                          aria-label="Retained GSTR-1 request context"
                          value={gstr1Context}
                          onChange={(event) =>
                            setGSTR1Context(event.target.value)
                          }
                        >
                          <option value="">
                            Select distinct clean request-context evidence
                          </option>
                          {inputs.data?.evidence
                            .filter((item) => item.id !== evidence)
                            .map((item) => (
                              <option
                                key={item.id}
                                value={item.id}
                                disabled={item.scan_status !== "CLEAN"}
                              >
                                {item.label} · {item.scan_status}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label style={{ display: "block" }}>
                        Independent GSTR-1 section controls (JSON)
                        <textarea
                          aria-label="Independent GSTR-1 section controls (JSON)"
                          style={{
                            height: 220,
                            width: "100%",
                            display: "block",
                          }}
                          value={gstr1Controls}
                          onChange={(event) =>
                            setGSTR1Controls(event.target.value)
                          }
                        />
                      </label>
                      <label style={{ display: "block" }}>
                        GSTR-1 retrieval scope assessment
                        <textarea
                          style={{
                            height: 100,
                            width: "100%",
                            display: "block",
                          }}
                          value={gstr1Assessment}
                          onChange={(event) =>
                            setGSTR1Assessment(event.target.value)
                          }
                        />
                      </label>
                      <p>
                        Declare every retained section, document count, signed
                        taxable_base and igst/cgst/sgst/cess totals. Four
                        component rows are prepared per document. Retain the
                        request GSTIN, month, sections and assessed
                        filters/pagination separately. These sources do not
                        establish filing or a complete outward return.
                        Amendments and source status/de-link flags remain
                        unresolved.
                      </p>
                    </fieldset>
                  )}
                  {tableType === "gst-document-series" && (
                    <fieldset style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                      <legend>
                        Independent document-series count controls
                      </legend>
                      <p>
                        Enter separately checked counts across all retained
                        serial rows. Cancelled documents stay explicit. Counts
                        are exact and have no currency; leave monetary control
                        totals empty.
                      </p>
                      {(
                        [
                          ["issued", "Issued documents control"],
                          ["cancelled", "Cancelled documents control"],
                          ["net_issued", "Net issued documents control"],
                        ] as const
                      ).map(([field, label]) => (
                        <label key={field}>
                          {label}
                          <input
                            inputMode="numeric"
                            value={seriesControls[field]}
                            onChange={(event) =>
                              setSeriesControls({
                                ...seriesControls,
                                [field]: event.target.value,
                              })
                            }
                          />
                        </label>
                      ))}
                      {sourceFormat === "india-gstr1-document-series-json" && (
                        <>
                          <label>
                            Document-series GSTIN
                            <input
                              value={gstRegistration}
                              onChange={(event) =>
                                setGSTRegistration(event.target.value)
                              }
                            />
                          </label>
                          <label>
                            Document-series reporting month
                            <input
                              type="month"
                              value={gstPeriod}
                              onChange={(event) =>
                                setGSTPeriod(event.target.value)
                              }
                            />
                          </label>
                          <label>
                            Document-series request context
                            <select
                              value={gstr1Context}
                              onChange={(event) =>
                                setGSTR1Context(event.target.value)
                              }
                            >
                              <option value="">
                                Select separate clean evidence
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
                            Document-series retrieval assessment
                            <textarea
                              value={gstr1Assessment}
                              onChange={(event) =>
                                setGSTR1Assessment(event.target.value)
                              }
                            />
                          </label>
                          <p>
                            Imports the declared doc_issue section only.
                            Category codes and serial endpoints remain literal;
                            range continuity, provider origin and filing are not
                            established by this file.
                          </p>
                        </>
                      )}
                    </fieldset>
                  )}
                  {tableType === "gst-summary-metrics" && (
                    <fieldset style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                      <legend>
                        Independent GST summary metric controls (JSON)
                      </legend>
                      <textarea
                        aria-label="Independent GST summary metric controls (JSON)"
                        style={{ height: 200, width: "100%", display: "block" }}
                        value={gstSummaryControls}
                        onChange={(event) =>
                          setGSTSummaryControls(event.target.value)
                        }
                      />
                      <p>
                        Supply every retained metric name and its independently
                        assessed sum across all supplied hierarchy levels. These
                        arithmetic controls are not return liability. Counts
                        remain separate from INR values; omitted fields are not
                        zero.
                      </p>
                    </fieldset>
                  )}
                  {sourceFormat === "india-gstr1-summary-json" && (
                    <>
                      <label>
                        Entity GSTIN
                        <input
                          value={gstRegistration}
                          onChange={(event) =>
                            setGSTRegistration(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        GSTR-1 summary month
                        <input
                          type="month"
                          value={gstPeriod}
                          onChange={(event) => setGSTPeriod(event.target.value)}
                        />
                      </label>
                      <p>
                        Import retained section, subsection and counterparty
                        metrics without netting overlapping levels. A generated
                        summary does not establish filing or invoice
                        completeness.
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
                  {sourceFormat === "india-esic-members-xls" && (
                    <fieldset>
                      <legend>ESIC six-column XLS scope</legend>
                      <label>
                        ESIC employer registration
                        <input
                          value={employerRegistration}
                          onChange={(e) =>
                            setEmployerRegistration(e.target.value)
                          }
                        />
                      </label>
                      <label>
                        ESIC wage month
                        <input
                          type="month"
                          value={obligationPeriod}
                          onChange={(e) => setObligationPeriod(e.target.value)}
                        />
                      </label>
                      <label>
                        ESIC return kind
                        <select
                          value={esicReturnKind}
                          onChange={(e) => setEsicReturnKind(e.target.value)}
                        >
                          <option value="monthly">Monthly</option>
                          <option value="supplementary">
                            Supplementary (kept separate)
                          </option>
                        </select>
                      </label>
                      <label>
                        Retained ESIC employer/month context
                        <select
                          value={esicContextEvidence}
                          onChange={(e) =>
                            setEsicContextEvidence(e.target.value)
                          }
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
                        ESIC workbook scope assessment
                        <textarea
                          value={esicScopeAssessment}
                          onChange={(e) =>
                            setEsicScopeAssessment(e.target.value)
                          }
                        />
                      </label>
                      <p>
                        Retain one visible six-column text-only .xls worksheet
                        with its original headers. Employer/month context is
                        independently assessed. This file supplies reported
                        members and wages, not filing or payment proof;
                        supplementary files are not merged.
                      </p>
                    </fieldset>
                  )}
                  {[
                    "cutoff-documents",
                    "cutoff-recognition-lines",
                    "cutoff-posting-lines",
                  ].includes(tableType) && (
                    <p>
                      For split cut-off use explicit-schedule documents with no
                      document-level recognition or posting date, exact
                      recognition allocations covering each document amount, and
                      separate posting lines linked by allocation ID. Keep
                      original dates and signed reversals. Invoice amounts are
                      nonnegative and credit-note amounts nonpositive; no
                      service-period proration is inferred.
                    </p>
                  )}
                  {tableType === "party-confirmations" && (
                    <fieldset>
                      <legend>Positive party confirmation documents</legend>
                      <label>
                        Independent written-request totals (JSON)
                        <textarea
                          value={confirmationRequestTotals}
                          onChange={(event) =>
                            setConfirmationRequestTotals(event.target.value)
                          }
                          rows={3}
                          placeholder={'{"AED":"150"}'}
                        />
                      </label>
                      <label>
                        Independent written-response totals (JSON)
                        <textarea
                          value={confirmationResponseTotals}
                          onChange={(event) =>
                            setConfirmationResponseTotals(event.target.value)
                          }
                          rows={3}
                          placeholder={'{"AED":"150"}'}
                        />
                      </label>
                      <p>
                        Ordinary money controls cover assessed scope balances.
                        Written-request and written-response totals are
                        separate. Use {"{}"} for blank requests with no stated
                        amount, or for absent response amounts. Blank requests
                        require an explicit scope_balance in the CSV. Select
                        shared documents only when they apply to every row;
                        otherwise supply each row's retained version and hash in
                        the CSV. Sender authenticity and direct receipt require
                        independent assessment.
                      </p>
                      {(["request", "response", "followup"] as const).map(
                        (prefix) => (
                          <label key={prefix}>
                            Shared{" "}
                            {prefix === "followup" ? "follow-up" : prefix}{" "}
                            document (optional)
                            <select
                              value={confirmationDocuments[prefix] || ""}
                              onChange={(event) =>
                                setConfirmationDocuments({
                                  ...confirmationDocuments,
                                  [prefix]: event.target.value,
                                })
                              }
                            >
                              <option value="">
                                Use per-row retained document bindings
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
                        ),
                      )}
                    </fieldset>
                  )}
                  {tableType === "purchase-lines" && (
                    <fieldset>
                      <legend>Independent purchase quantity controls</legend>
                      <label>
                        Purchase row and quantity controls (JSON)
                        <textarea
                          value={purchaseControls}
                          onChange={(event) =>
                            setPurchaseControls(event.target.value)
                          }
                          rows={6}
                          placeholder={
                            '[{"order_id":"PO-1","line_reference":"LINE-1","vendor":"V1","currency":"AED","uom":"PCS","document_type":"order","expected_rows":1,"quantity":"2"}]'
                          }
                        />
                      </label>
                      <p>
                        Declare each non-payment
                        order/line/vendor/currency/unit/document partition
                        independently. Use [] for a payments-only source. Money
                        controls remain separate. No unit conversion is
                        inferred.
                      </p>
                    </fieldset>
                  )}
                  {tableType === "inventory-valuations" && (
                    <fieldset>
                      <legend>Inventory valuation evidence controls</legend>
                      <label>
                        Independent extended cost/NRV controls (JSON)
                        <textarea
                          value={inventoryValueControls}
                          onChange={(e) =>
                            setInventoryValueControls(e.target.value)
                          }
                          rows={6}
                          placeholder={
                            '[{"currency":"AED","expected_rows":1,"cost_value":"1000","nrv_value":"1100"}]'
                          }
                        />
                      </label>
                      <p>
                        Declare per-currency row counts and extended cost/NRV
                        totals independently. Unit prices and incompatible
                        quantities are not summed together.
                      </p>
                      {[
                        {
                          key: "cost",
                          caption:
                            "Retained cost evidence (optional shared document)",
                          value: inventoryCostEvidence,
                          setValue: setInventoryCostEvidence,
                        },
                        {
                          key: "nrv",
                          caption:
                            "Retained selling/NRV evidence (optional shared document)",
                          value: inventoryNRVEvidence,
                          setValue: setInventoryNRVEvidence,
                        },
                      ].map(({ key, caption, value, setValue }) => (
                        <label key={key}>
                          {caption}
                          <select
                            value={value}
                            onChange={(e) => setValue(e.target.value)}
                          >
                            <option value="">
                              Use explicit document references in the CSV
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
                      ))}
                      <p>
                        Selected documents supply retained evidence references;
                        conflicting CSV references are rejected. Assess original
                        reference locations and cost/NRV applicability in every
                        row.
                      </p>
                    </fieldset>
                  )}
                  {tableType === "esic-members" && (
                    <fieldset>
                      <legend>Independent ESIC population controls</legend>
                      <label>
                        Total paid days
                        <input
                          type="number"
                          min={0}
                          max={155000}
                          step={1}
                          value={esicDaysControl}
                          onChange={(e) => setEsicDaysControl(e.target.value)}
                        />
                      </label>
                      <label>
                        Zero-wage members
                        <input
                          type="number"
                          min={0}
                          max={5000}
                          step={1}
                          value={esicZeroControl}
                          onChange={(e) => setEsicZeroControl(e.target.value)}
                        />
                      </label>
                      <p>
                        Declare totals independently of the uploaded file.
                        Currency totals control wages in INR, not contribution
                        dues. Retain original evidence and the assessed
                        zero-wage reasons.
                      </p>
                    </fieldset>
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
                    setInvoiceDirection("");
                    setWithholdingRole("");
                    setArrearsOnly(false);
                    setVATLayout("custom");
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
              {workflow === "inventory-valuation-control" && (
                <fieldset>
                  <legend>Inventory valuation and recorded GL scope</legend>
                  <label>
                    Recorded inventory GL basis
                    <select
                      value={inventoryGLBasis}
                      onChange={(e) => setInventoryGLBasis(e.target.value)}
                    >
                      <option value="">Select the recorded basis</option>
                      <option value="gross-cost">Gross recorded cost</option>
                      <option value="recorded-lower-of-cost-nrv">
                        Recorded lower of cost and NRV
                      </option>
                    </select>
                  </label>
                  <label>
                    Valuation evidence review through
                    <input
                      type="date"
                      min={asOf}
                      value={reviewThrough}
                      onChange={(e) => setReviewThrough(e.target.value)}
                    />
                  </label>
                  <label>
                    Inventory framework and scope assessment
                    <textarea
                      value={inventoryScopeAssessment}
                      onChange={(e) =>
                        setInventoryScopeAssessment(e.target.value)
                      }
                    />
                  </label>
                  <p>
                    Independently review all sources. Book quantity controls,
                    exact SKU/site/lot/UOM/currency identity, retained cost/NRV
                    documents and mapped GL accounts are required. Price tests
                    do not prove physical existence, ownership or framework
                    applicability.
                  </p>
                </fieldset>
              )}
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
                "party-balance-confirmations",
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
                          (workflow !== "inventory-valuation-control" ||
                            role !== "books" ||
                            r.inventory_controls_verified === true) &&
                          (r.native_format !== "india-gstr1-documents-json" ||
                            workflow === "india-gstr1-documents") &&
                          (r.native_format !== "india-gstr2b-json" ||
                            workflow === "india-gst") &&
                          (r.native_format !== "india-inv01-json" ||
                            (workflow === "india-invoice-register"
                              ? role === "invoices"
                              : role === "books" &&
                                (workflow === "india-gst" ||
                                  (workflow === "india-gstr1-documents" &&
                                    r.invoice_direction === "sale")))) &&
                          (workflow !== "uae-vat-return" ||
                            vatLayout !== "emirate-20" ||
                            r.review_status === "REVIEWED") &&
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
                          (workflow !== "procurement-match" ||
                            (r.review_status === "REVIEWED" &&
                              (role === "payments" ||
                                r.purchase_controls_verified === true))) &&
                          (workflow !== "party-balance-confirmations" ||
                            r.review_status === "REVIEWED") &&
                          (![
                            "india-invoice-register",
                            "india-gstr1-summary",
                          ].includes(workflow) ||
                            r.native_format !== "india-inv01-json" ||
                            r.invoice_direction === invoiceDirection) &&
                          (!r.allowed_workflows ||
                            r.allowed_workflows.includes(workflow)) &&
                          (!r.allowed_source_roles ||
                            r.allowed_source_roles.includes(role)) &&
                          (workflow !== "india-payroll-rules" ||
                            !esicPopulationReview ||
                            r.review_status === "REVIEWED") &&
                          (![
                            "ownership-lookthrough",
                            "bank-account-evidence",
                            "inventory-valuation-control",
                            "obligation-bank-allocations",
                            "payroll-ledger-rollforward",
                            "india-esic-population",
                            "india-document-series",
                            "india-gstr1-documents",
                            "india-gstr1-summary",
                            "india-invoice-register",
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
              {Object.entries(chosen?.optional_roles || {}).map(
                ([role, type]) => (
                  <label key={role}>
                    {role} source (optional)
                    <select
                      aria-label={`${role} source (optional)`}
                      value={sources[role] || ""}
                      onChange={(event) =>
                        setSources((previous) => {
                          const next = { ...previous };
                          if (event.target.value)
                            next[role] = event.target.value;
                          else delete next[role];
                          return next;
                        })
                      }
                    >
                      <option value="">No {type} source selected</option>
                      {results.data?.items
                        .filter(
                          (row) =>
                            row.kind === "workflow-source" &&
                            row.table_type === type &&
                            row.freshness === "CURRENT" &&
                            row.review_status === "REVIEWED" &&
                            (!row.allowed_workflows ||
                              row.allowed_workflows.includes(workflow)) &&
                            (!row.allowed_source_roles ||
                              row.allowed_source_roles.includes(role)),
                        )
                        .map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.label} · v{row.version} · {row.review_status}
                          </option>
                        ))}
                    </select>
                    <small>
                      {workflow === "expense-cutoff"
                        ? "Explicit schedules require both reviewed recognition and posting sources. Use a controlled nil posting source when no postings were observed. No proration or posting links are inferred."
                        : "Partial replies require explicit reviewed item links. No subset is inferred from matching amounts."}
                    </small>
                  </label>
                ),
              )}
              {workflow === "uae-import-vat" && (
                <ImportNilScopeForm
                  value={importNil}
                  onChange={setImportNil}
                  evidence={inputs.data?.evidence || []}
                />
              )}
              {workflow === "india-invoice-register" && (
                <>
                  <label>
                    Invoice comparison direction
                    <select
                      value={invoiceDirection}
                      onChange={(event) => {
                        setInvoiceDirection(event.target.value);
                        setSources({});
                      }}
                    >
                      <option value="">Select purchase or sale</option>
                      <option value="purchase">Purchase invoices</option>
                      <option value="sale">Sales invoices</option>
                    </select>
                  </label>
                  <p>
                    Compare independently reviewed register and invoice
                    evidence. INV-01 files supply the invoices role; they do not
                    establish filed GST returns or IRP authenticity.
                  </p>
                </>
              )}
              {workflow === "uae-vat-return" && (
                <>
                  <label>
                    VAT201 comparison layout
                    <select
                      value={vatLayout}
                      onChange={(event) => {
                        const next = event.target.value;
                        setVATLayout(next);
                        setRestrictBoxes(false);
                        setBoxScopeAssessment("");
                        setSources({});
                        if (next !== "custom")
                          setRequiredBoxes(
                            config.data?.vat201_layouts?.[next]?.boxes.join(
                              ",",
                            ) || "",
                          );
                      }}
                    >
                      <option value="custom">Custom assessed box scope</option>
                      {Object.entries(config.data?.vat201_layouts || {}).map(
                        ([value, item]) => (
                          <option key={value} value={value}>
                            {item.label}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  {vatLayout === "emirate-20" && (
                    <p>
                      Compare all twenty explicit rows for one TRN and period in
                      AED, including zero-valued emirates. Independently review
                      both source populations. Missing emirate evidence blocks
                      approval; aggregate Box 1 cannot substitute for assessed
                      geographic allocations.
                    </p>
                  )}
                  <label>
                    Required VAT201 boxes, comma separated
                    <input
                      value={requiredBoxes}
                      disabled={vatLayout !== "custom"}
                      onChange={(e) => setRequiredBoxes(e.target.value)}
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={restrictBoxes}
                      disabled={vatLayout !== "custom"}
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
              {workflow === "india-payroll-rules" && (
                <fieldset>
                  <legend>ESIC member population link (optional)</legend>
                  <label>
                    Reviewed ESIC population
                    <select
                      value={esicPopulationReview}
                      onChange={(e) => {
                        setEsicPopulationReview(e.target.value);
                        setSources({});
                        if (!e.target.value) setEsicBasisAssessment("");
                      }}
                    >
                      <option value="">No ESIC population linked</option>
                      {results.data?.items
                        .filter(
                          (row) =>
                            row.kind === "country-workflow" &&
                            row.workflow === "india-esic-population" &&
                            row.review_status === "REVIEWED" &&
                            row.freshness === "CURRENT" &&
                            !row.blocked,
                        )
                        .map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.label} · v{row.version}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    ESI components covered
                    <select
                      value={esicComponents}
                      disabled={!esicPopulationReview}
                      onChange={(e) => setEsicComponents(e.target.value)}
                    >
                      <option value="both">Employee and employer</option>
                      <option value="ESI:EMPLOYEE">Employee only</option>
                      <option value="ESI:EMPLOYER">Employer only</option>
                    </select>
                  </label>
                  <label>
                    ESIC wage-to-basis assessment
                    <textarea
                      value={esicBasisAssessment}
                      disabled={!esicPopulationReview}
                      onChange={(e) => setEsicBasisAssessment(e.target.value)}
                    />
                  </label>
                  <p>
                    Every retained member needs an assessed basis for each
                    selected component, including zero-wage and ineligible
                    members. Wages, eligibility and assessed contribution bases
                    remain separate; differences are retained for review.
                  </p>
                </fieldset>
              )}
              {workflow === "india-esic-population" && (
                <p>
                  Compare independently reviewed payroll and reported ESIC
                  member populations for one employer and wage month. Member
                  IDs, paid days, names, zero-wage reasons and leaving dates
                  stay separate from wage amounts. Contributions, eligibility,
                  supplementary-return composition and portal filing require
                  separate procedures. Native XLS preparation supports the
                  explicit text-only profile with independently retained
                  employer/month context.
                </p>
              )}
              {workflow === "payroll-ledger-rollforward" && (
                <p>
                  Compare independently reviewed payroll allocations with posted
                  GL lines and prior-day opening / reporting-date closing
                  controls. Expense amounts are debit-positive; liability
                  amounts credit-positive. Wage month, component, posting
                  category, subject, employer, account and currency stay
                  separate. Aggregate GL journals need independently evidenced
                  subject allocations. A settlement journal does not prove
                  payment execution.
                </p>
              )}
              {[
                "bank-brs",
                "bank-subsequent-clearance",
                "obligation-bank-allocations",
              ].includes(workflow) && (
                <fieldset>
                  <legend>Account evidence scope</legend>
                  <label>
                    Reviewed bank account evidence (optional)
                    <select
                      value={bankAccountReview}
                      onChange={(event) => {
                        setBankAccountReview(event.target.value);
                        if (!event.target.value) setBankAccountAssessment("");
                      }}
                    >
                      <option value="">
                        Arithmetic and declared account labels only
                      </option>
                      {results.data?.items
                        .filter(
                          (row) =>
                            row.kind === "country-workflow" &&
                            row.workflow === "bank-account-evidence" &&
                            row.freshness === "CURRENT" &&
                            row.review_status === "REVIEWED" &&
                            !row.blocked,
                        )
                        .map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.label} · {row.bank_account_scope?.account} ·{" "}
                            {row.bank_account_scope?.currency} · {row.as_of}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Linked account scope assessment
                    <textarea
                      disabled={!bankAccountReview}
                      value={bankAccountAssessment}
                      onChange={(event) =>
                        setBankAccountAssessment(event.target.value)
                      }
                    />
                  </label>
                  <p>
                    A linked review must cover the selected ledger account,
                    currency and entire financial window. Its comparison date
                    must equal this window's end. Matching account numbers can
                    map bank identifiers to ledger labels; no bank
                    authentication or payment authority is inferred.
                  </p>
                </fieldset>
              )}
              {workflow === "bank-account-evidence" && (
                <fieldset>
                  <legend>Bank account and owner evidence scope</legend>
                  <p>
                    Compare independently reviewed register, ledger setup and
                    bank evidence. UAE IBAN and India IFSC checks verify format
                    only. No bank ownership confirmation or payment is
                    requested.
                  </p>
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
                    Engagement legal entity name
                    <input
                      value={bankOwnerName}
                      onChange={(e) => setBankOwnerName(e.target.value)}
                    />
                  </label>
                  <label>
                    Owner identifier scheme
                    <input
                      value={bankOwnerScheme}
                      onChange={(e) => setBankOwnerScheme(e.target.value)}
                    />
                  </label>
                  <label>
                    Owner identifier
                    <input
                      value={bankOwnerIdentifier}
                      onChange={(e) => setBankOwnerIdentifier(e.target.value)}
                    />
                  </label>
                </fieldset>
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
          {results.hasOlder && (
            <Button disabled={results.loadingOlder} onClick={results.loadOlder}>
              Load older source choices
            </Button>
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
          {selected &&
            detail.data &&
            !results.data?.items.some((r) => r.id === selected) && (
              <option value={selected}>
                Linked source or result · {selected}
              </option>
            )}
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
          {body.outward_gst_scope && (
            <details>
              <summary>Assessed outward source scope</summary>
              <pre>{JSON.stringify(body.outward_gst_scope, null, 2)}</pre>
            </details>
          )}
          {body.workflow === "india-gstr1-documents" && (
            <p role="note">
              Outward invoice/note comparison for the declared retained
              sections. Request context is assessed evidence; matching does not
              establish filing, complete GSTR-1 coverage or customer identity
              for unregistered/export category keys.
            </p>
          )}
          {body.workflow === "india-gstr1-summary" && (
            <p role="note">
              GSTR-1 summary metrics compared at their original hierarchy level.
              Counts are separate from INR values; matching does not establish
              filing or invoice completeness.
            </p>
          )}
          {body.metric_controls && (
            <details>
              <summary>Independent GST summary metric controls</summary>
              <p>
                Arithmetic controls across retained hierarchy levels; these are
                not a tax-liability total.
              </p>
              <pre>{JSON.stringify(body.metric_controls, null, 2)}</pre>
            </details>
          )}

          {body.invoice_evidence_scope && (
            <p role="note">
              {body.invoice_evidence_scope.direction === "purchase"
                ? "Purchase"
                : "Sales"}{" "}
              register compared with invoice evidence. This comparison does not
              establish GST return filing or IRP authenticity.
            </p>
          )}
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
                    const enabledBoxes = Object.entries(
                      importBridgeBoxes,
                    ).filter(([, enabled]) => enabled);
                    if (
                      !enabledBoxes.length ||
                      enabledBoxes.some(
                        ([box]) =>
                          !/^(0|[1-9][0-9]*)$/.test(
                            importBridgeControls[box].expected_rows.trim(),
                          ) ||
                          !importBridgeControls[box].taxable_amount.trim() ||
                          !importBridgeControls[box].tax.trim(),
                      )
                    ) {
                      setLocalError(
                        new Error(
                          "Enter independent detail-count, taxable-base and tax controls for every selected import box, including explicit zeros.",
                        ),
                      );
                      return;
                    }
                    setLocalError(null);
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
              {body.booking_date_review_count
                ? `Approval blocked: ${body.booking_date_review_count} bank ${body.booking_date_review_count === 1 ? "row uses" : "rows use"} a value-date fallback. Retain explicit booking-date evidence and regenerate.`
                : "Approval blocked: correct source controls or missing/expired evidence and regenerate."}
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
                            : body.import_nil_scope?.kinds.includes(kind) &&
                                body.import_nil_scope.binding_status ===
                                  "VERIFIED_RETAINED_CONTEXT"
                              ? "Explicit evidenced nil"
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
          {body.table_type === "withholding-records" &&
            config.data?.country === "IN" &&
            body.review_status === "REVIEWED" &&
            detail.data.freshness === "CURRENT" && (
              <WithholdingObligationSource
                key={`${tenant}:${eid}:${selected}`}
                eid={eid}
                sourceId={selected}
                onCreated={(id) => {
                  setSelected(id);
                  setOffset(0);
                }}
              />
            )}
          {body.workflow === "obligation-bank-allocations" && (
            <BankCashReview
              key={`${tenant}:${eid}:${selected}`}
              eid={eid}
              eventId={selected}
              version={detail.data.version}
              onSelected={(id) => {
                setSelected(id);
                setOffset(0);
              }}
            />
          )}
          {body.workflow === "india-document-series" && (
            <section aria-label="Document-series comparison scope">
              <p>
                GSTIN {body.document_series_scope?.registration}; reporting
                month {body.document_series_scope?.period}.
              </p>
              <p>
                Document counts are compared exactly for each retained category
                and literal serial range. Differences are reported minus books;
                monetary tolerances do not apply. Missing ranges remain unknown.
                This comparison does not establish invoice-level completeness or
                filing.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={showRuleProvenance}
                  onChange={(event) =>
                    setShowRuleProvenance(event.target.checked)
                  }
                />
                Show document-series source references and full scope
              </label>
            </section>
          )}
          {body.import_nil_scope && (
            <section aria-label="Evidenced nil import scope">
              <h3>Evidenced nil import scope</h3>
              <p>
                TRN {body.import_nil_scope.registration}:{" "}
                {body.import_nil_scope.period_start} to{" "}
                {body.import_nil_scope.period_end}. Declared nil:{" "}
                {body.import_nil_scope.kinds.join(", ")}.{" "}
                {body.import_nil_scope.binding_status}
              </p>
              <p>{body.import_nil_scope.assessment}</p>
              <p>
                Supporting evidence version:{" "}
                {body.import_nil_scope.context_evidence_version_id}. Other boxes
                and recoverability require separate assessment.
              </p>
            </section>
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
          {[
            "india-gst",
            "uae-vat",
            "uae-vat-return",
            "india-invoice-register",
          ].includes(body.workflow || "") && (
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
          {body.bank_account_evidence && (
            <BankAccountLinkReview
              link={body.bank_account_evidence}
              open={(identifier) => setSelected(identifier)}
            />
          )}
          {body.workflow === "bank-account-evidence" && (
            <BankAccountEvidenceReview rows={rows} />
          )}
          {body.transaction_dates && (
            <BankTransactionDates
              key={selected + ":bank-dates"}
              prefix={prefix}
              selected={selected}
              initial={body.transaction_dates}
              total={
                detail.data.collection_totals?.transaction_dates ??
                body.transaction_dates.length
              }
            />
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
          {body.workflow === "ownership-lookthrough" && (
            <>
              {!body.ownership_path_contract && (
                <p>
                  Historical result has no retained path contract. Regenerate
                  before independent approval.
                </p>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={showRuleProvenance}
                  onChange={(event) =>
                    setShowRuleProvenance(event.target.checked)
                  }
                />{" "}
                Show ownership source provenance and all columns
              </label>
            </>
          )}
          {body.ownership_path_contract && (
            <OwnershipPathEvidence
              prefix={prefix}
              selected={selected}
              scope={body.ownership_scope || {}}
              paths={body.ownership_paths || []}
              steps={body.ownership_path_steps || []}
              pathTotal={
                detail.data.collection_totals?.ownership_paths ??
                body.ownership_paths?.length ??
                0
              }
              stepTotal={
                detail.data.collection_totals?.ownership_path_steps ??
                body.ownership_path_steps?.length ??
                0
              }
            />
          )}
          {body.cutoff_schedule_contract && (
            <>
              <p>
                Explicit cut-off allocations compare only the declared reporting
                period. Future recognition dates are assessed schedules.
                Document allocations must exactly cover invoice or credit-note
                amounts; postings retain their actual dates.
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={showRuleProvenance}
                  onChange={(event) =>
                    setShowRuleProvenance(event.target.checked)
                  }
                />{" "}
                Show cutoff source provenance and all columns
              </label>
            </>
          )}
          {(["controls", "postings"] as const).map((mode) => {
            const key =
              mode === "controls"
                ? "cutoff_document_controls"
                : "cutoff_posting_links";
            const initial = body[key];
            return initial ? (
              <InventoryEvidenceTable
                key={`${selected}:cutoff:${mode}`}
                prefix={prefix}
                selected={selected}
                initial={initial}
                total={detail.data.collection_totals?.[key] ?? initial.length}
                cutoff={mode}
              />
            ) : null;
          })}
          {body.confirmation_coverage_links && (
            <InventoryEvidenceTable
              key={selected + ":confirmation-links"}
              prefix={prefix}
              selected={selected}
              initial={body.confirmation_coverage_links}
              total={
                detail.data.collection_totals?.confirmation_coverage_links ??
                body.confirmation_coverage_links.length
              }
              confirmation
            />
          )}
          {body.purchase_quantity_controls && (
            <InventoryEvidenceTable
              key={selected + ":purchase-controls"}
              prefix={prefix}
              selected={selected}
              initial={body.purchase_quantity_controls}
              total={
                detail.data.collection_totals?.purchase_quantity_controls ??
                body.purchase_quantity_controls.length
              }
              purchase
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
          {body.confirmation_scope && (
            <section aria-label="Positive party confirmation scope">
              <h3>Positive party-balance evidence</h3>
              <p>
                Reporting date {body.confirmation_scope.as_of} · review through{" "}
                {body.confirmation_scope.review_through} ·{" "}
                {body.confirmation_scope.open_items} open items ·{" "}
                {body.confirmation_scope.party_positions} party positions ·{" "}
                {body.confirmation_scope.confirmation_rows} assessment rows.
                Counts do not establish sent requests or confirmed balances.
              </p>
              <label>
                Confirmation view
                <select
                  value={confirmationView}
                  onChange={(event) => {
                    setConfirmationView(event.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="parties">Party balance evidence</option>
                  <option value="gl-controls">GL control tie-outs</option>
                </select>
              </label>
              {confirmationView === "parties" && (
                <PartyConfirmationEvidence
                  key={`${selected}:${offset}`}
                  eid={eid}
                  tenant={tenant}
                  rows={rows}
                  dependencies={detail.data.dependencies || []}
                />
              )}
            </section>
          )}
          {body.inventory_valuation_scope && (
            <section aria-label="Inventory valuation scope">
              <h3>Inventory valuation and GL controls</h3>
              <p>
                Reporting date {body.inventory_valuation_scope.as_of} · evidence
                review through {body.inventory_valuation_scope.review_through} ·
                GL basis {body.inventory_valuation_scope.gl_basis}
              </p>
              <p>{body.inventory_valuation_scope.assessment}</p>
              <label>
                Inventory valuation view
                <select
                  value={inventoryView}
                  onChange={(e) => {
                    setInventoryView(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="valuations">Cost and NRV tests</option>
                  <option value="gl-controls">Recorded GL controls</option>
                </select>
              </label>
            </section>
          )}
          {body.esic_population_binding && (
            <section aria-label="ESIC contribution population binding">
              <h3>ESIC contribution population link</h3>
              <p>
                {body.esic_population_binding.status === "BOUND"
                  ? `${body.esic_population_binding.members} members · ${body.esic_population_binding.basis_rows} assessed bases · ${body.esic_population_binding.components?.join(", ")} · ${body.esic_population_binding.documented_population_exceptions ?? 0} documented population exceptions`
                  : "No reviewed ESIC population linked"}
              </p>
              {body.esic_population_binding.review_receipt && (
                <Link
                  href={`/intelligence/${eid}/country-workflow?event=${body.esic_population_binding.review_receipt.id}`}
                >
                  Open linked ESIC population review
                </Link>
              )}
              <p>{body.esic_population_binding.assessment}</p>
              <p>
                Eligibility and contribution bases remain separately assessed.
                This link does not verify filing or payment.
              </p>
            </section>
          )}
          {body.esic_population_scope && (
            <section aria-label="ESIC comparison scope and totals">
              <h3>ESIC wage and member population</h3>
              <p>
                Employer {body.esic_population_scope.registration} · wage month{" "}
                {body.esic_population_scope.period}. Wages are compared
                separately from contribution dues.
              </p>
              {Object.entries(body.esic_population_totals || {}).map(
                ([role, totals]) => (
                  <p key={role}>
                    {role}: {totals.members} members · INR {totals.wages} wages
                    · {totals.paid_days} paid days · {totals.zero_wage_members}{" "}
                    zero-wage members
                  </p>
                ),
              )}
            </section>
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
          {body.workflow === "sanctions-name-review" && (
            <ScreeningCandidates key={`${selected}:${offset}`} rows={rows} />
          )}
          <div style={{ overflowX: "auto" }}>
            {(compactSource ||
              compactArrearResult ||
              compactBenefit ||
              body.workflow === "bank-account-evidence" ||
              body.workflow === "payroll-ledger-rollforward" ||
              body.workflow === "inventory-valuation-control" ||
              body.workflow === "sanctions-name-review" ||
              body.workflow === "procurement-match" ||
              body.workflow === "party-balance-confirmations" ||
              body.workflow === "india-esic-population" ||
              body.workflow === "india-gstr1-documents" ||
              body.workflow === "india-invoice-register" ||
              body.workflow === "india-gstr1-summary" ||
              body.table_type === "gst-summary-metrics" ||
              body.table_type === "esic-members" ||
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
            {(body.workflow !== "bank-account-evidence" ||
              showRuleProvenance) && (
              <table>
                <caption>
                  {rows.length
                    ? `Source-linked schedule · rows ${offset + 1}–${offset + rows.length}; XLSX contains the full result`
                    : "No schedule rows on this page; XLSX contains the full result"}
                </caption>
                <thead>
                  <tr>
                    {columns.map((k) => (
                      <th key={k} scope="col">
                        {body.workflow === "party-balance-confirmations" &&
                        k === "difference"
                          ? "response comparison"
                          : compactDues && k === "settled_or_allocated"
                            ? "allocated"
                            : k.replaceAll("_", " ")}
                      </th>
                    ))}
                    {detail.data.kind === "country-workflow" &&
                      rows.length > 0 && <th scope="col">Disposition</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={String(row.id || i)}>
                      {columns.map((k) => (
                        <td
                          key={k}
                          style={
                            [
                              "procurement-match",
                              "party-balance-confirmations",
                              "ownership-lookthrough",
                            ].includes(body.workflow || "")
                              ? { maxWidth: 200, overflowWrap: "anywhere" }
                              : undefined
                          }
                        >
                          {body.workflow === "party-balance-confirmations" &&
                          k === "difference" &&
                          row.confirmation_status === "partially-received" ? (
                            <span>
                              Covered reply difference:{" "}
                              {String(
                                row.covered_response_difference ?? "Unknown",
                              )}
                              . Covered book:{" "}
                              {String(row.covered_book_balance ?? "Unknown")}.
                              Uncovered book:{" "}
                              {String(row.uncovered_book_balance ?? "Unknown")}.
                              Full balance not compared.
                            </span>
                          ) : ((compactWithholding &&
                              k === "assessment_issues") ||
                              (body.workflow === "procurement-match" &&
                                k === "exceptions")) &&
                            Array.isArray(row[k]) ? (
                            <ul>
                              {(row[k] as unknown[]).map((issue) => (
                                <li key={String(issue)}>
                                  {text(issue)
                                    .replaceAll("_", " ")
                                    .toLowerCase()}
                                </li>
                              ))}
                            </ul>
                          ) : ((body.workflow === "procurement-match" &&
                              ["quantities", "amounts"].includes(k)) ||
                              (compactWithholding &&
                                [
                                  "amounts",
                                  "differences_from_expected",
                                  "differences_from_books",
                                ].includes(k))) &&
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
            )}
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
