import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.country_workflows.audit_schemas import AUDIT_ROW_TYPES
from app.modules.country_workflows.diligence_schemas import DILIGENCE_ROW_TYPES
from app.modules.country_workflows.operations_schemas import OPERATION_ROW_TYPES
from app.modules.country_workflows.payroll_schemas import PAYROLL_ROW_TYPES
from app.modules.country_workflows.pension_schemas import PENSION_ROW_TYPES
from app.modules.country_workflows.sector_schemas import SECTOR_ROW_TYPES
from app.modules.country_workflows.withholding_schemas import WithholdingRecord, WithholdingRole
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.conversion import ExchangeRate
from app.modules.regulatory.pension_profiles import PensionScope

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]


class Transaction(Strict):
    id: Identifier
    account: Identifier
    reference: str = Field(max_length=120)
    date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money
    counterparty: str = Field(default="", max_length=120)


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
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money
    due_date: date | None = None
    payment_date: date | None = None
    pension_scope: PensionScope | None = Field(default=None, exclude_if=lambda value: value is None)

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
    site: Identifier
    sku: Identifier
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
    "fx-rates": ExchangeRate,
    "withholding-records": WithholdingRecord,
    **OPERATION_ROW_TYPES,
    **PAYROLL_ROW_TYPES,
    **PENSION_ROW_TYPES,
    **AUDIT_ROW_TYPES,
    **DILIGENCE_ROW_TYPES,
    **SECTOR_ROW_TYPES,
    "return-boxes": ReturnBox,
    "transactions": Transaction,
    "tax-documents": TaxDocument,
    "obligations": Obligation,
    "stock": Stock,
    "checks": Control,
}


class SourceInput(Strict):
    evidence_version_id: uuid.UUID
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
        "canonical-csv",
        "camt053",
        "swift-mt940",
        "uae-wps-sif",
        "india-inv01-json",
        "india-epfo-ecr",
        "india-gstr2b-json",
    ] = "canonical-csv"
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


class WorkflowInput(Strict):
    withholding_role: WithholdingRole | None = None
    allocation_basis: Literal["invoice_face_amounts", "pre_application_balances"] | None = None
    workflow: Literal[
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
        "uae-vat",
        "uae-vat-return",
        "india-gst",
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
    period_start: date | None = None
    tax_year_start: date | None = None
    title: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=10, max_length=4000)
    account: str | None = Field(default=None, max_length=120)
    currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")
    book_opening: Money | None = None
    book_closing: Money | None = None
    statement_opening: Money | None = None
    statement_closing: Money | None = None
    tolerance: Money = Field(default=Decimal(0), ge=0)
    date_tolerance: int = Field(default=0, ge=0, le=90)
    stale_days: int = Field(default=90, ge=1, le=3650)
    required_checks: list[Identifier] = Field(default_factory=list, max_length=100)
    required_boxes: list[Identifier] = Field(default_factory=list, max_length=50)
    restrict_to_required_boxes: bool = False
    box_scope_assessment: str = Field(default="", max_length=2000)
    subjects: list[Identifier] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def independent_sources(self):
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
