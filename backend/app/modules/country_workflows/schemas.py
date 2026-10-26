import uuid
from datetime import date
from datetime import date as CalendarDate
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.country_workflows.audit_schemas import AUDIT_ROW_TYPES
from app.modules.country_workflows.bank_accounts import BankAccountEvidence
from app.modules.country_workflows.diligence_schemas import DILIGENCE_ROW_TYPES
from app.modules.country_workflows.document_series import DocumentSeries, SeriesCounts
from app.modules.country_workflows.ecr_arrear_schemas import ECRArrearControls
from app.modules.country_workflows.esic_population import ESICMember
from app.modules.country_workflows.gst_summary import METRICS, GSTSummaryMetric
from app.modules.country_workflows.gstr1_schemas import GSTR1SectionControl
from app.modules.country_workflows.gstr2b_part_schemas import GSTR2BPart
from app.modules.country_workflows.import_nil_schemas import ImportNilScope
from app.modules.country_workflows.inventory_controls import InventoryQuantityControl
from app.modules.country_workflows.inventory_valuation import (
    InventoryValuation,
    InventoryValueControl,
)
from app.modules.country_workflows.operations_schemas import OPERATION_ROW_TYPES
from app.modules.country_workflows.payroll_ledger_schemas import PAYROLL_LEDGER_ROW_TYPES
from app.modules.country_workflows.payroll_schemas import PAYROLL_ROW_TYPES
from app.modules.country_workflows.pension_schemas import PENSION_ROW_TYPES
from app.modules.country_workflows.sector_schemas import SECTOR_ROW_TYPES
from app.modules.country_workflows.vat201_layouts import LAYOUTS, VAT201Layout
from app.modules.country_workflows.withholding_schemas import WithholdingRecord, WithholdingRole
from app.modules.country_workflows.withholding_scope import WithholdingSettlementScope
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.conversion import ExchangeRate
from app.modules.regulatory.pension_profiles import PensionScope

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]
WPSVariableComponent = Literal[
    "housing_allowance", "conveyance_allowance", "medical_allowance",
    "annual_passage_allowance", "overtime_allowance", "other_allowances", "leave_encashment",
]
WPS_VARIABLE_FIELDS = (
    "housing_allowance", "conveyance_allowance", "medical_allowance",
    "annual_passage_allowance", "overtime_allowance", "other_allowances", "leave_encashment",
)


class Transaction(Strict):
    id: Identifier
    account: Identifier
    reference: str = Field(max_length=120)
    date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money
    counterparty: str = Field(default="", max_length=120)
    is_reversal: bool = False
    bank_booking_date: CalendarDate | None = Field(default=None, exclude_if=lambda value: value is None)
    bank_value_date: CalendarDate | None = Field(default=None, exclude_if=lambda value: value is None)
    bank_date_basis: Literal["BOOKING_DATE", "ENTRY_DATE_INFERRED_YEAR", "VALUE_DATE_FALLBACK"] | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def bank_dates(self):
        if self.bank_booking_date is not None and self.bank_booking_date != self.date:
            raise ValueError("Transaction date must equal the separately retained booking date")
        if self.bank_date_basis in {"BOOKING_DATE", "ENTRY_DATE_INFERRED_YEAR"} and self.bank_booking_date is None:
            raise ValueError("Booking-date basis requires an explicit booking date")
        if self.bank_date_basis == "VALUE_DATE_FALLBACK" and (self.bank_value_date != self.date or self.bank_booking_date is not None):
            raise ValueError("Value-date fallback requires the value date and cannot assert a booking date")
        return self


class TaxDocument(Strict):
    id: Identifier
    registration: Identifier
    counterparty: Identifier
    reference: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    document_type: Literal["invoice", "credit-note", "debit-note"]
    net: Money
    tax: Money
    component: Identifier
    status: Literal["active", "rejected", "pending"] = "active"

    @model_validator(mode="after")
    def sign(self):
        if self.document_type == "credit-note" and (self.net > 0 or self.tax > 0):
            raise ValueError("Credit notes require signed non-positive amounts")
        if self.document_type != "credit-note" and (self.net < 0 or self.tax < 0):
            raise ValueError("Invoices/debit notes require non-negative amounts")
        return self


class Obligation(Strict):
    id: Identifier
    registration: Identifier
    subject: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Identifier
    population: Literal["unspecified", "regular", "arrears"] = "unspecified"
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money
    due_date: date | None = None
    payment_date: date | None = None
    withholding_scope: WithholdingSettlementScope | None = Field(default=None, exclude_if=lambda value: value is None)
    pension_scope: PensionScope | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("withholding_scope", mode="before")
    @classmethod
    def csv_withholding_scope(cls, value):
        if isinstance(value, str):
            import json

            try:
                return json.loads(value)
            except ValueError:
                raise ValueError("Withholding scope CSV values require a JSON object") from None
        return value

    @field_validator("pension_scope", mode="before")
    @classmethod
    def csv_scope(cls, value):
        if isinstance(value, str):
            import json

            try:
                return json.loads(value)
            except ValueError:
                raise ValueError("Pension scope CSV values require a JSON object") from None
        return value

    @model_validator(mode="after")
    def scope_component(self):
        if self.withholding_scope is not None:
            scope = self.withholding_scope
            if self.pension_scope is not None or self.currency != "INR" or self.component != scope.tax_kind or self.population == "arrears":
                raise ValueError("Withholding obligations require INR, the exact TDS/TCS component and a separate liability scope")
            if not scope.tax_year_start.strftime("%Y-%m") <= self.period <= scope.tax_year_end.strftime("%Y-%m"):
                raise ValueError("Withholding obligation period is outside its assessed tax year")
        if self.pension_scope is not None and not self.component.startswith("PENSION:"):
            raise ValueError("Pension scope applies only to pension components")
        return self


class ReturnBox(Strict):
    id: Identifier
    registration: Identifier
    period_start: date
    period_end: date
    box: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    taxable_amount: Money
    tax: Money
    adjustment: Money = Decimal(0)

    @model_validator(mode="after")
    def period(self):
        if self.period_end < self.period_start:
            raise ValueError("Return period ends before it starts")
        return self


class Stock(Strict):
    id: Identifier
    account: Identifier | None = None
    site: Identifier
    sku: Identifier
    lot: str = Field(default="", max_length=120)
    uom: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    quantity: Money
    unit_cost: Money = Field(ge=0)
    unit_nrv: Money | None = Field(default=None, ge=0)
    ownership: Literal["owned", "third-party", "unconfirmed"] = "unconfirmed"
    condition: Literal["good", "obsolete", "expired", "unconfirmed"] = "unconfirmed"
    count_date: date


class Control(Strict):
    id: Identifier
    subject: Identifier
    requirement: Identifier
    state: Literal["supported", "exception", "missing", "not-applicable"]
    evidence_reference: str = Field(default="", max_length=120)
    expires_on: date | None = None
    rationale: str = Field(default="", max_length=2000)


ROW_TYPES: dict[str, type[BaseModel]] = {
    "inventory-valuations": InventoryValuation,
    "esic-members": ESICMember,
    "gst-document-series": DocumentSeries,
    "gst-summary-metrics": GSTSummaryMetric,
    "fx-rates": ExchangeRate,
    "withholding-records": WithholdingRecord,
    **OPERATION_ROW_TYPES,
    **PAYROLL_ROW_TYPES,
    **PAYROLL_LEDGER_ROW_TYPES,
    **PENSION_ROW_TYPES,
    **AUDIT_ROW_TYPES,
    **DILIGENCE_ROW_TYPES,
    **SECTOR_ROW_TYPES,
    "return-boxes": ReturnBox,
    "transactions": Transaction,
    "bank-account-evidence": BankAccountEvidence,
    "tax-documents": TaxDocument,
    "obligations": Obligation,
    "stock": Stock,
    "checks": Control,
}


class SourceInput(Strict):
    inventory_cost_document_version_id: uuid.UUID | None = None
    inventory_nrv_document_version_id: uuid.UUID | None = None
    inventory_valuation_controls: list[InventoryValueControl] | None = Field(default=None, max_length=20)
    esic_context_evidence_version_id: uuid.UUID | None = None
    esic_return_kind: Literal["monthly", "supplementary"] | None = None
    esic_scope_assessment: str = Field(default="", max_length=2000)
    esic_paid_days_control: int | None = Field(default=None, ge=0, le=155000, strict=True)
    esic_zero_wage_members_control: int | None = Field(default=None, ge=0, le=5000, strict=True)
    evidence_version_id: uuid.UUID
    ecr_arrear_controls: ECRArrearControls | None = None
    arrear_context_evidence_version_id: uuid.UUID | None = None
    arrear_disbursement_date: date | None = None
    arrear_scope_assessment: str = Field(default="", max_length=2000)
    inventory_quantity_controls: list[InventoryQuantityControl] | None = Field(default=None, max_length=5000)
    wps_variable_pay_count: int | None = Field(default=None, ge=0, le=5000, strict=True)
    wps_variable_pay_totals: dict[WPSVariableComponent, Money] = Field(default_factory=dict, max_length=7)
    gstr2b_parts: list[GSTR2BPart] = Field(default_factory=list, max_length=100)
    gstr2b_expected_files: int | None = Field(default=None, ge=1, le=100, strict=True)
    gstr2b_retrieval_assessment: str = Field(default="", max_length=2000)
    supporting_table_id: uuid.UUID | None = None
    supporting_scope_assessment: str = Field(default="", max_length=2000)
    supporting_side: Literal["receivable", "payable"] | None = None
    supporting_balance_date: date | None = None
    supporting_amount_sign: Literal["as-reported", "reverse-sign"] = "as-reported"
    column_mapping: dict[Identifier, Identifier] = Field(default_factory=dict, max_length=60)
    ignored_columns: list[Identifier] = Field(default_factory=list, max_length=60)
    mapping_rationale: str = Field(default="", max_length=2000)
    delimiter: Literal[",", ";", "\t"] = ","
    amount_derivation: Literal["none", "debit-positive", "credit-positive"] = "none"
    debit_column: Identifier | None = None
    credit_column: Identifier | None = None
    file_format: Literal[
        "india-esic-members-xls",
        "canonical-csv",
        "camt053",
        "swift-mt940",
        "uae-wps-sif",
        "uae-wps-sif-evp",
        "india-inv01-json",
        "india-epfo-ecr",
        "india-epfo-arrear-ecr-v2",
        "india-gstr2b-json",
        "india-gstr1-summary-json",
        "india-gstr1-document-series-json",
        "india-gstr1-documents-json",
    ] = "canonical-csv"
    gstr1_section_controls: list[GSTR1SectionControl] = Field(default_factory=list, max_length=10)
    gstr1_context_evidence_version_id: uuid.UUID | None = None
    gstr1_retrieval_assessment: str = Field(default="", max_length=2000)
    document_series_controls: SeriesCounts | None = None
    gst_summary_metric_controls: dict[str, Money] = Field(default_factory=dict, max_length=19)
    gst_registration: str | None = Field(
        default=None, pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]$"
    )
    gst_direction: Literal["purchase", "sale"] | None = None
    gst_period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    account_identifier: Identifier | None = None
    statement_identifier: Identifier | None = None
    employer_registration: Identifier | None = None
    obligation_due_date: date | None = None
    obligation_period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    expected_members: int | None = Field(default=None, ge=1, le=1666)
    expected_documents: int | None = Field(default=None, ge=0, le=1250)
    rule_document_version_id: uuid.UUID | None = None
    table_type: Literal[
        "inventory-valuations",
        "esic-members",
        "gst-document-series",
        "gst-summary-metrics",
        "payroll-account-balances",
        "payroll-ledger-lines",
        "obligation-allocations",
        "fx-rates",
        "bank-outstanding",
        "bank-clearances",
        "withholding-records",
        "credit-applications",
        "cash-payments",
        "item-allocations",
        "pension-bases",
        "pension-rules",
        "pension-reported",
        "payroll-bases",
        "payroll-rules",
        "transactions",
        "bank-account-evidence",
        "tax-documents",
        "obligations",
        "stock",
        "checks",
        "return-boxes",
        "audit-open-items",
        "settlements",
        "balance-controls",
        "confirmations",
        "cutoff-documents",
        "ecl-loss-rates",
        "cash-forecasts",
        "purchase-lines",
        "party-masters",
        "expense-claims",
        "benefit-employees",
        "benefit-rules",
        "trade-lines",
        "import-vat-lines",
        "price-bands",
        "excise-movements",
        "excise-rules",
        "excise-returns",
        "metal-lines",
        "escrow-entries",
        "escrow-authorisations",
        "billing-lines",
        "construction-projects",
        "asset-register",
        "accounting-controls",
        "stock-movements",
        "diligence-subjects",
        "ownership-edges",
        "ownership-policies",
        "screening-subjects",
        "sanctions-entries",
        "screening-policies",
    ]
    label: str = Field(min_length=1, max_length=200)
    expected_rows: int = Field(ge=0, le=5000)
    nil_reason: str | None = Field(default=None, min_length=10, max_length=2000)
    control_totals: dict[str, Money] = Field(default_factory=dict, max_length=20)
    import_taxable_base_control: Money | None = None

    @model_validator(mode="after")
    def declared_nil(self):
        if (self.inventory_cost_document_version_id is not None or self.inventory_nrv_document_version_id is not None) and (self.table_type != "inventory-valuations" or self.file_format != "canonical-csv"):
            raise ValueError("Shared inventory documents apply only to canonical valuation evidence sources")
        if self.table_type == "inventory-valuations":
            if self.inventory_valuation_controls is None or self.control_totals:
                raise ValueError("Inventory valuations require independent currency cost/NRV controls without mixed monetary totals")
        elif self.inventory_valuation_controls is not None:
            raise ValueError("Inventory valuation controls apply only to valuation evidence sources")
        if self.table_type == "esic-members":
            if self.file_format not in {"canonical-csv", "india-esic-members-xls"} or self.esic_paid_days_control is None or self.esic_zero_wage_members_control is None or set(self.control_totals) != {"INR"}:
                raise ValueError("ESIC populations require controlled CSV/XLS with independent paid-day and zero-wage member totals")
        elif self.esic_paid_days_control is not None or self.esic_zero_wage_members_control is not None:
            raise ValueError("ESIC population controls apply only to ESIC member sources")
        if self.file_format == "india-esic-members-xls":
            registration = self.employer_registration or ""
            if self.table_type != "esic-members" or not self.esic_context_evidence_version_id or self.esic_context_evidence_version_id == self.evidence_version_id or self.esic_return_kind is None or len(self.esic_scope_assessment.strip()) < 10 or not self.obligation_period or not registration.isascii() or not registration.isdigit() or len(registration) != 17:
                raise ValueError("ESIC XLS requires one employer/month, declared return kind, distinct retained context and meaningful scope assessment")
            date.fromisoformat(f"{self.obligation_period}-01")
        elif self.esic_context_evidence_version_id is not None or self.esic_return_kind is not None or self.esic_scope_assessment:
            raise ValueError("ESIC workbook context applies only to the explicit native XLS profile")
        if self.table_type == "gst-document-series":
            if self.document_series_controls is None or self.control_totals or self.expected_rows < 1:
                raise ValueError("Document series require explicit range rows and independent issued/cancelled/net count controls without money totals")
        elif self.document_series_controls is not None:
            raise ValueError("Document-series count controls apply only to document-series sources")
        if self.file_format == "india-gstr1-document-series-json":
            if self.table_type != "gst-document-series" or not self.gst_registration or not self.gst_period or not self.gstr1_context_evidence_version_id or self.gstr1_context_evidence_version_id == self.evidence_version_id or len(self.gstr1_retrieval_assessment.strip()) < 10 or self.gstr1_section_controls:
                raise ValueError("Native document series require distinct retained request context, assessed GSTIN/period and count controls")
        if self.file_format == "india-gstr1-documents-json":
            controls = self.gstr1_section_controls
            sections = [c.section for c in controls]
            with localcontext() as arithmetic:
                arithmetic.prec = 80
                tax = sum((c.igst + c.cgst + c.sgst + c.cess for c in controls), Decimal(0))
            if not controls or len(set(sections)) != len(sections) or not self.gstr1_context_evidence_version_id or self.gstr1_context_evidence_version_id == self.evidence_version_id or len(self.gstr1_retrieval_assessment.strip()) < 10 or not self.gst_registration or not self.gst_period or self.table_type != "tax-documents" or self.expected_documents != sum(c.document_count for c in controls) or self.expected_rows != 4 * sum(c.document_count for c in controls) or self.control_totals != {"INR": tax}:
                raise ValueError("GSTR-1 documents require distinct retained request context, assessed retrieval scope, unique section counts/base/component controls and agreeing whole-source controls")
        elif self.file_format != "india-gstr1-document-series-json" and (self.gstr1_section_controls or self.gstr1_context_evidence_version_id is not None or self.gstr1_retrieval_assessment):
            raise ValueError("GSTR-1 document controls/context apply only to the explicit invoice/note profile")
        if self.table_type == "gst-summary-metrics":
            if not self.gst_summary_metric_controls or set(self.gst_summary_metric_controls) - METRICS or self.control_totals or self.expected_rows < 1:
                raise ValueError("GST summary sources require explicit rows and every independent metric control; do not use mixed currency totals")
        elif self.gst_summary_metric_controls:
            raise ValueError("GST summary metric controls apply only to summary metric sources")
        if self.file_format == "india-epfo-arrear-ecr-v2":
            if self.ecr_arrear_controls is None or self.arrear_context_evidence_version_id is None or self.arrear_disbursement_date is None or len(self.arrear_scope_assessment.strip()) < 10:
                raise ValueError("Arrear ECR requires independent wage/contribution controls, distinct retained context, disbursement date and month attribution assessment")
            if self.arrear_context_evidence_version_id == self.evidence_version_id:
                raise ValueError("Retain arrear filing context separately from the member text")
            if not self.obligation_period or not self.employer_registration or self.expected_members is None or self.expected_rows != 3 * self.expected_members:
                raise ValueError("Arrear ECR requires one establishment, declared wage month, independent member count and three component rows per member")
            if self.arrear_disbursement_date < date.fromisoformat(self.obligation_period + "-01"):
                raise ValueError("Arrear disbursement cannot precede the declared wage month")
        elif self.ecr_arrear_controls is not None or self.arrear_context_evidence_version_id is not None or self.arrear_disbursement_date is not None or self.arrear_scope_assessment:
            raise ValueError("Arrear controls and context apply only to the explicit eight-field arrear ECR profile")
        if self.inventory_quantity_controls is not None and self.table_type not in {"stock", "stock-movements"}:
            raise ValueError("Inventory quantity controls apply only to stock and stock-movement sources")
        if self.file_format == "uae-wps-sif-evp":
            if self.wps_variable_pay_count is None or set(self.wps_variable_pay_totals) != set(WPS_VARIABLE_FIELDS):
                raise ValueError("Declare the EVP record count and every independent variable-pay component total")
            if any(value < 0 for value in self.wps_variable_pay_totals.values()):
                raise ValueError("WPS variable-pay controls must be non-negative")
        elif self.wps_variable_pay_count is not None or self.wps_variable_pay_totals:
            raise ValueError("Variable-pay controls apply only to the explicit EDR/EVP/SCR WPS profile")
        if self.gstr2b_parts:
            numbers = [part.file_number for part in self.gstr2b_parts]
            identifiers = [part.evidence_version_id for part in self.gstr2b_parts]
            with localcontext() as arithmetic:
                arithmetic.prec = 80
                part_total = sum((part.tax_total for part in self.gstr2b_parts), Decimal(0))
            if (self.file_format != "india-gstr2b-json" or self.table_type != "tax-documents"
                or self.supporting_table_id or self.gstr2b_expected_files != len(numbers)
                or sorted(numbers) != list(range(1, len(numbers) + 1))
                or len(set(identifiers)) != len(identifiers) or self.evidence_version_id in identifiers
                or len(self.gstr2b_retrieval_assessment.strip()) < 10
                or self.expected_documents != sum(part.expected_documents for part in self.gstr2b_parts)
                or self.expected_rows != 4 * sum(part.expected_documents for part in self.gstr2b_parts)
                or self.control_totals != {"INR": part_total}):
                raise ValueError("GSTR-2B assembly requires distinct original files numbered 1..count, independent per-part and whole-source controls, and a retrieval assessment")
        elif self.gstr2b_expected_files is not None or self.gstr2b_retrieval_assessment:
            raise ValueError("GSTR-2B assembly controls require numbered original response parts")
        if self.table_type == "import-vat-lines":
            if self.import_taxable_base_control is None:
                raise ValueError(
                    "Import VAT sources require an independent AED taxable-base control"
                )
        elif self.import_taxable_base_control is not None:
            raise ValueError("Import taxable-base controls apply only to import VAT detail")
        if self.supporting_table_id:
            if (
                self.file_format != "canonical-csv"
                or self.table_type not in {"transactions", "audit-open-items"}
                or not self.account_identifier
                or len(self.supporting_scope_assessment.strip()) < 10
                or self.column_mapping
                or self.ignored_columns
                or self.mapping_rationale
                or self.delimiter != ","
                or self.amount_derivation != "none"
            ):
                raise ValueError(
                    "Supporting tables require an explicit account/scope and cannot use additional CSV transformations"
                )
            if self.table_type == "audit-open-items" and (
                not self.supporting_side or not self.supporting_balance_date
            ):
                raise ValueError(
                    "Supporting open items require an explicit receivable/payable side and balance date"
                )
            if self.table_type == "transactions" and (
                self.supporting_side
                or self.supporting_balance_date
                or self.supporting_amount_sign != "as-reported"
            ):
                raise ValueError(
                    "Open-item balance options cannot be applied to supporting bank tables"
                )
        elif (
            self.supporting_scope_assessment
            or self.supporting_side
            or self.supporting_balance_date
            or self.supporting_amount_sign != "as-reported"
        ):
            raise ValueError(
                "Supporting scope and sign options require a supporting table selection"
            )
        if self.amount_derivation != "none":
            if self.file_format != "canonical-csv" or self.table_type != "transactions":
                raise ValueError("Debit/credit derivation applies only to transaction CSV sources")
            if (
                not self.debit_column
                or not self.credit_column
                or self.debit_column == self.credit_column
            ):
                raise ValueError("Select distinct debit and credit columns")
            if len(self.mapping_rationale.strip()) < 10:
                raise ValueError(
                    "Debit/credit derivation requires an explicit sign-basis assessment"
                )
        elif self.debit_column or self.credit_column:
            raise ValueError("Debit/credit columns require an explicit amount derivation")
        if (self.expected_rows == 0) != bool(self.nil_reason):
            raise ValueError(
                "Zero-row sources require an explicit nil-population rationale; populated sources cannot be declared nil"
            )
        return self


class LedgerSourceInput(Strict):
    source_kind: Literal["transactions", "balance-controls"] = "transactions"
    balance_side: Literal["receivable", "payable"] | None = None
    snapshot_id: uuid.UUID
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=1)
    bank_account: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    label: str = Field(min_length=3, max_length=200)
    as_of: date
    from_date: date | None = None
    nil_reason: str | None = Field(default=None, min_length=10, max_length=2000)

    @model_validator(mode="after")
    def balance_scope(self):
        if self.source_kind == "balance-controls" and (not self.balance_side or self.from_date):
            raise ValueError(
                "A GL balance control needs a side and cannot use a movement start date"
            )
        return self


class VATSourceInput(Strict):
    run_id: uuid.UUID
    label: str = Field(min_length=3, max_length=200)


ESIComponent = Literal["ESI:EMPLOYEE", "ESI:EMPLOYER"]


def esi_components() -> list[ESIComponent]:
    return ["ESI:EMPLOYEE", "ESI:EMPLOYER"]


class WorkflowInput(Strict):
    inventory_gl_basis: Literal["gross-cost", "recorded-lower-of-cost-nrv"] | None = None
    inventory_scope_assessment: str = Field(default="", max_length=2000)
    esic_population_review_id: uuid.UUID | None = None
    esic_basis_scope_assessment: str = Field(default="", max_length=2000)
    esic_components: list[ESIComponent] = Field(default_factory=esi_components, min_length=1, max_length=2)
    withholding_role: WithholdingRole | None = None
    allocation_basis: Literal["invoice_face_amounts", "pre_application_balances"] | None = None
    workflow: Literal[
        "inventory-valuation-control",
        "india-esic-population",
        "india-document-series",
        "payroll-ledger-rollforward",
        "obligation-bank-allocations",
        "bank-subsequent-clearance",
        "india-withholding-liability",
        "india-withholding-credit",
        "credit-note-applications",
        "open-item-allocations",
        "india-payroll-rules",
        "uae-pension-review",
        "subledger-control",
        "subsequent-settlements",
        "balance-confirmations",
        "expense-cutoff",
        "receivables-ecl",
        "going-concern-cash",
        "procurement-match",
        "vendor-employee-conflicts",
        "employee-expenses",
        "uae-benefit-review",
        "customs-reconciliation",
        "uae-import-vat",
        "trade-document-review",
        "excise-reconciliation",
        "gold-reconciliation",
        "escrow-disbursements",
        "hospitality-revenue",
        "healthcare-billing",
        "construction-contracts",
        "asset-register-review",
        "inventory-count-bridge",
        "kyc-edd-review",
        "ownership-lookthrough",
        "sanctions-name-review",
        "bank-brs",
        "bank-account-evidence",
        "uae-vat",
        "uae-vat-return",
        "india-gst",
        "india-invoice-register",
        "india-gstr1-summary",
        "india-gstr1-documents",
        "payroll-settlement",
        "statutory-dues",
        "india-withholding",
        "stock-audit",
        "controls",
        "vendor-diligence",
        "nonprofit-diligence",
        "tax-close",
    ]
    source_ids: dict[str, uuid.UUID] = Field(min_length=1, max_length=4)
    as_of: date
    obligation_month_start: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    obligation_month_end: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    settlement_start: date | None = None
    bank_payment_sign: Literal["debit-negative", "debit-positive"] | None = None
    review_through: date | None = None
    stock_bridge_mode: Literal["forward", "bidirectional-controlled"] = "forward"
    arrear_only: bool = False
    stock_cutoff_assessment: str = Field(default="", max_length=2000)
    period_start: date | None = None
    tax_year_start: date | None = None
    title: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=10, max_length=4000)
    account: str | None = Field(default=None, max_length=120)
    currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")
    import_nil_scope: ImportNilScope | None = None
    bank_account_review_id: uuid.UUID | None = None
    bank_account_scope_assessment: str = Field(default="",max_length=2000)
    bank_owner_name: str = Field(default="", max_length=200)
    bank_owner_identifier_scheme: str = Field(default="", max_length=80)
    bank_owner_identifier: str = Field(default="", max_length=120)
    book_opening: Money | None = None
    book_closing: Money | None = None
    statement_opening: Money | None = None
    statement_closing: Money | None = None
    tolerance: Money = Field(default=Decimal(0), ge=0)
    date_tolerance: int = Field(default=0, ge=0, le=90)
    stale_days: int = Field(default=90, ge=1, le=3650)
    required_checks: list[Identifier] = Field(default_factory=list, max_length=100)
    invoice_direction: Literal["purchase", "sale"] | None = None
    vat201_layout: VAT201Layout | Literal["custom"] = "custom"
    required_boxes: list[Identifier] = Field(default_factory=list, max_length=50)
    restrict_to_required_boxes: bool = False
    box_scope_assessment: str = Field(default="", max_length=2000)
    subjects: list[Identifier] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def independent_sources(self):
        if self.workflow == "inventory-valuation-control":
            if self.inventory_gl_basis is None or self.review_through is None or self.review_through < self.as_of or len(self.inventory_scope_assessment.strip()) < 10:
                raise ValueError("Inventory valuation requires an explicit recorded GL basis, review-through date and source/framework scope assessment")
        elif self.inventory_gl_basis is not None or self.inventory_scope_assessment:
            raise ValueError("Inventory valuation basis and scope apply only to the valuation-control workflow")
        if self.esic_population_review_id is not None:
            if self.workflow != "india-payroll-rules" or len(self.esic_basis_scope_assessment.strip()) < 10 or len(set(self.esic_components)) != len(self.esic_components):
                raise ValueError("An ESIC population link requires India contribution review, explicit unique ESI components and a meaningful basis assessment")
        elif self.esic_basis_scope_assessment or self.esic_components != ["ESI:EMPLOYEE", "ESI:EMPLOYER"]:
            raise ValueError("ESIC basis assessment/component selection requires an explicit reviewed population link")
        if self.import_nil_scope is not None:
            if self.workflow != "uae-import-vat" or self.import_nil_scope.period_end > self.as_of:
                raise ValueError("Nil import scope requires the UAE import workflow and a closed assessed period")
        if self.bank_account_review_id is not None:
            if self.workflow not in {"bank-brs","bank-subsequent-clearance","obligation-bank-allocations"} or len(self.bank_account_scope_assessment.strip())<10:
                raise ValueError("A bank account evidence link requires a supported financial workflow and meaningful scope assessment")
        elif self.bank_account_scope_assessment:
            raise ValueError("Account scope assessment requires an explicit reviewed bank account link")
        if self.workflow == "bank-account-evidence":
            if not self.account or any(not value.strip() for value in (self.bank_owner_name,self.bank_owner_identifier_scheme,self.bank_owner_identifier)):
                raise ValueError("Account evidence comparison requires account and explicit owner name/identifier scope")
        elif any((self.bank_owner_name,self.bank_owner_identifier_scheme,self.bank_owner_identifier)):
            raise ValueError("Bank owner scope applies only to bank account evidence comparison")
        if self.workflow == "india-invoice-register":
            if self.invoice_direction is None:
                raise ValueError("Select purchase or sale for the invoice evidence comparison")
        elif self.invoice_direction is not None:
            raise ValueError("Invoice direction applies only to invoice evidence/register comparison")
        if self.vat201_layout != "custom":
            if self.workflow != "uae-vat-return" or self.restrict_to_required_boxes or set(self.required_boxes) != set(LAYOUTS[self.vat201_layout]["boxes"]):
                raise ValueError("A selected VAT201 layout requires all its explicit boxes without selected-box exclusion")
        if self.workflow == "payroll-ledger-rollforward" and (self.period_start is None or self.period_start <= date.min or self.period_start > self.as_of):
            raise ValueError("Payroll ledger bridge requires an ordered accounting period and prior-day opening balance")
        if self.arrear_only and self.workflow not in {"statutory-dues", "india-payroll-rules", "obligation-bank-allocations"}:
            raise ValueError("Arrear-only scope applies to statutory dues, India payroll rules or obligation bank allocations")
        if self.stock_bridge_mode == "bidirectional-controlled":
            if self.workflow != "inventory-count-bridge" or self.review_through is None or self.review_through < self.as_of or len(self.stock_cutoff_assessment.strip()) < 10:
                raise ValueError("Controlled inventory bridging requires the inventory workflow, an ordered review-through date and explicit day-end cutoff assessment")
        elif self.stock_cutoff_assessment:
            raise ValueError("An inventory cutoff assessment requires explicit controlled bridge mode")
        if self.workflow == "obligation-bank-allocations":
            if (
                not self.account
                or not self.account.strip()
                or self.account != self.account.strip()
                or not self.obligation_month_start
                or not self.obligation_month_end
                or self.settlement_start is None
                or self.settlement_start > self.as_of
                or self.bank_payment_sign is None
            ):
                raise ValueError(
                    "Obligation bank allocations require account, month range, payment sign and settlement window"
                )
            if (
                not self.obligation_month_start
                <= self.obligation_month_end
                <= self.as_of.strftime("%Y-%m")
            ):
                raise ValueError(
                    "Obligation months must be ordered and no later than the reporting date"
                )
            first, last = self.obligation_month_start, self.obligation_month_end
            date.fromisoformat(first + "-01")
            date.fromisoformat(last + "-01")
            if (int(last[:4]) - int(first[:4])) * 12 + int(last[5:]) - int(first[5:]) >= 120:
                raise ValueError("Obligation allocation scope is limited to 120 months")
        if self.restrict_to_required_boxes:
            if self.workflow != "uae-vat-return" or len(self.box_scope_assessment.strip()) < 10:
                raise ValueError(
                    "Selected VAT201 box comparison requires an explicit scope assessment"
                )
            if any(not box.strip() or box != box.strip() for box in self.required_boxes):
                raise ValueError("Selected VAT201 box identifiers must be exact nonblank values")
        elif self.box_scope_assessment:
            raise ValueError("A box scope assessment requires explicit selected-box comparison")
        if self.workflow in {"india-withholding-liability", "india-withholding-credit"}:
            allowed = (
                {"deductor", "collector"}
                if self.workflow.endswith("liability")
                else {"deductee", "collectee"}
            )
            if self.withholding_role not in allowed:
                raise ValueError("Explicit liability or beneficiary-credit legal role required")
        if (
            self.workflow == "credit-note-applications"
            and self.allocation_basis != "pre_application_balances"
        ):
            raise ValueError(
                "Explicit pre-application balance basis required; do not apply credits to already-net balances"
            )
        if (
            self.workflow == "open-item-allocations"
            and self.allocation_basis != "invoice_face_amounts"
        ):
            raise ValueError(
                "Explicit invoice-face population basis required; do not deduct cash from already-net open balances"
            )
        if self.workflow == "ownership-lookthrough" and not self.subjects:
            raise ValueError(
                "Ownership look-through requires an explicit company subject population"
            )
        if self.workflow in {
            "bank-subsequent-clearance",
            "subsequent-settlements",
            "balance-confirmations",
            "expense-cutoff",
            "going-concern-cash",
        }:
            if self.review_through is None or self.review_through < self.as_of:
                raise ValueError("Declare a review window ending on or after the reporting date")
        if self.workflow == "bank-subsequent-clearance" and not self.account:
            raise ValueError("Subsequent bank clearance requires an explicit account")
        if self.workflow in {
            "expense-cutoff",
            "excise-reconciliation",
            "gold-reconciliation",
            "asset-register-review",
        } and (self.period_start is None or self.period_start > self.as_of):
            raise ValueError("This workflow requires an ordered reporting-period start")
        if len(set(self.source_ids.values())) != len(self.source_ids):
            raise ValueError("Each source role requires an independent source version")
        if len(set(self.required_checks)) != len(self.required_checks):
            raise ValueError("Duplicate required checks")
        if len(set(self.subjects)) != len(self.subjects):
            raise ValueError("Duplicate subject population")
        if len(set(self.required_boxes)) != len(self.required_boxes):
            raise ValueError("Duplicate required VAT return boxes")
        if self.workflow == "uae-vat-return" and not self.required_boxes:
            raise ValueError("An explicit scope of required return boxes is required")
        if self.workflow == "bank-brs" and (
            not self.account
            or any(
                x is None
                for x in [
                    self.book_opening,
                    self.book_closing,
                    self.statement_opening,
                    self.statement_closing,
                ]
            )
        ):
            raise ValueError("Bank BRS requires an account and all four balance controls")
        if self.workflow in {
            "controls",
            "vendor-diligence",
            "nonprofit-diligence",
            "tax-close",
        } and (not self.required_checks or not self.subjects):
            raise ValueError("Explicit scoped requirement and subject populations are required")
        return self
