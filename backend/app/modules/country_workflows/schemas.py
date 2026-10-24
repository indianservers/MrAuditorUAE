import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.country_workflows.audit_schemas import AUDIT_ROW_TYPES
from app.modules.country_workflows.diligence_schemas import DILIGENCE_ROW_TYPES
from app.modules.country_workflows.sector_schemas import SECTOR_ROW_TYPES
from app.modules.jurisdictions.profiles import Strict

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
    file_format: Literal[
        "canonical-csv",
        "camt053",
        "swift-mt940",
        "uae-wps-sif",
        "india-inv01-json",
        "india-epfo-ecr",
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
    table_type: Literal[
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

    @model_validator(mode="after")
    def declared_nil(self):
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
    workflow: Literal[
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
    subjects: list[Identifier] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def independent_sources(self):
        if self.workflow == "ownership-lookthrough" and not self.subjects:
            raise ValueError(
                "Ownership look-through requires an explicit company subject population"
            )
        if self.workflow in {
            "subsequent-settlements",
            "balance-confirmations",
            "expense-cutoff",
            "going-concern-cash",
        }:
            if self.review_through is None or self.review_through < self.as_of:
                raise ValueError("Declare a review window ending on or after the reporting date")
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
