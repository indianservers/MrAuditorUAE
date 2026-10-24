"""Canonical audit populations. Balances use the declared subledger's normal sign."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.ifrs.schemas import Asset
from app.modules.jurisdictions.profiles import Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class OpenItem(Strict):
    id: Identifier
    account: Identifier
    counterparty: Identifier
    reference: Identifier
    side: Literal["receivable", "payable"]
    currency: Currency
    document_date: date
    due_date: date
    balance_date: date
    amount: Money
    document_type: Literal["invoice", "credit-note", "debit-note"] = "invoice"

    @model_validator(mode="after")
    def dates_and_sign(self):
        if self.document_date > self.balance_date:
            raise ValueError("An open item cannot precede its document")
        if (self.document_type == "credit-note" and self.amount > 0) or (
            self.document_type != "credit-note" and self.amount < 0
        ):
            raise ValueError("Credit notes are non-positive; invoices/debit notes non-negative")
        return self


class Settlement(Strict):
    id: Identifier
    item_id: Identifier
    account: Identifier
    counterparty: Identifier
    currency: Currency
    date: date
    amount: Money
    evidence_reference: Identifier
    allocation_reference: Identifier


class BalanceControl(Strict):
    id: Identifier
    account: Identifier
    side: Literal["receivable", "payable"]
    currency: Currency
    as_of: date
    amount: Money


class Confirmation(Strict):
    id: Identifier
    item_id: Identifier
    counterparty: Identifier
    currency: Currency
    as_of: date
    requested_amount: Money
    response_amount: Money | None = None
    status: Literal["not-sent", "pending", "received", "disputed", "undeliverable"]
    requested_on: date | None = None
    responded_on: date | None = None
    contact_verified: bool = False
    independently_received: bool = False
    evidence_reference: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def chronology(self):
        if self.responded_on and (not self.requested_on or self.responded_on < self.requested_on):
            raise ValueError("Response date must follow request date")
        if self.status in {"received", "disputed"} and (
            self.response_amount is None or not self.responded_on
        ):
            raise ValueError("A response needs an amount and date")
        if self.status not in {"received", "disputed"} and (
            self.response_amount is not None or self.responded_on
        ):
            raise ValueError("An outstanding confirmation cannot contain a response")
        if self.status != "not-sent" and not self.requested_on:
            raise ValueError("A dispatched request needs a request date")
        return self


class CutoffDocument(Strict):
    id: Identifier
    counterparty: Identifier
    reference: Identifier
    currency: Currency
    amount: Money = Field(ge=0)
    invoice_date: date
    recognition_date: date
    posting_date: date | None = None
    evidence_reference: Identifier
    recognition_basis: Literal["goods-received", "service-performed", "reviewed-accrual"]


class LossRate(Strict):
    id: Identifier
    min_overdue_days: int = Field(ge=0, le=36500)
    max_overdue_days: int = Field(ge=0, le=36500)
    weighted_loss_rate: Decimal = Field(ge=0, le=1, decimal_places=10)
    effective_from: date
    effective_to: date
    evidence_reference: Identifier
    methodology: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def ordered(self):
        if self.max_overdue_days < self.min_overdue_days or self.effective_to < self.effective_from:
            raise ValueError("Loss-rate day and effective-date ranges must be ordered")
        return self


class CashForecast(Strict):
    id: Identifier
    scenario: Identifier
    currency: Currency
    date: date
    opening_cash: Money
    inflows: Money = Field(ge=0)
    outflows: Money = Field(ge=0)
    committed_funding: Money = Field(ge=0)
    funding_evidence: str = Field(default="", max_length=120)
    minimum_cash: Money
    assumptions_reference: Identifier


class PurchaseLine(Strict):
    id: Identifier
    order_id: Identifier
    line_reference: Identifier
    vendor: Identifier
    currency: Currency
    date: date
    document_type: Literal["order", "receipt", "invoice", "payment"]
    quantity: Money = Field(ge=0)
    unit_price: Money = Field(ge=0)
    amount: Money = Field(ge=0)
    evidence_reference: Identifier


class PartyMaster(Strict):
    id: Identifier
    bank_account_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    effective_from: date
    effective_to: date | None = None
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Master effective dates must be ordered")
        return self


class ExpenseClaim(Strict):
    id: Identifier
    employee: Identifier
    currency: Currency
    date: date
    amount: Money = Field(ge=0)
    approved_limit: Money = Field(ge=0)
    receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool
    policy_reference: Identifier
    evidence_reference: Identifier


class BenefitEmployee(Strict):
    id: Identifier
    regime: Identifier
    currency: Currency
    service_start: date
    service_end: date
    excluded_service_days: int = Field(ge=0, le=36500)
    monthly_basic_salary: Money = Field(ge=0)
    amount: Money = Field(ge=0)
    scheme: Literal["gratuity", "alternative"]
    contract_evidence: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.service_end < self.service_start:
            raise ValueError("Service dates must be ordered")
        if self.excluded_service_days > (self.service_end - self.service_start).days + 1:
            raise ValueError("Excluded service exceeds employment span")
        return self


class BenefitRule(Strict):
    id: Identifier
    regime: Identifier
    effective_from: date
    effective_to: date
    minimum_service_years: Money = Field(ge=0)
    year_days: Money = Field(gt=0, le=366)
    salary_divisor: Money = Field(gt=0, le=31)
    first_tier_years: Money = Field(ge=0)
    first_tier_days: Money = Field(ge=0)
    later_tier_days: Money = Field(ge=0)
    maximum_salary_months: Money = Field(gt=0)
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Benefit rule effective dates must be ordered")
        return self


class AssetAudit(Asset):
    id: Identifier
    account: Identifier
    currency: Currency
    recorded_depreciation: Money = Field(ge=0)
    recorded_carrying: Money = Field(ge=0)
    physical_evidence: str = Field(default="", max_length=120)
    ownership_evidence: str = Field(default="", max_length=120)


class AccountingControl(Strict):
    id: Identifier
    account: Identifier
    currency: Currency
    as_of: date
    amount: Money


class StockMovement(Strict):
    id: Identifier
    site: Identifier
    sku: Identifier
    uom: Identifier
    currency: Currency
    date: date
    quantity: Money
    evidence_reference: Identifier


AUDIT_ROW_TYPES: dict[str, type[BaseModel]] = {
    "asset-register": AssetAudit,
    "accounting-controls": AccountingControl,
    "stock-movements": StockMovement,
    "ecl-loss-rates": LossRate,
    "cash-forecasts": CashForecast,
    "purchase-lines": PurchaseLine,
    "party-masters": PartyMaster,
    "expense-claims": ExpenseClaim,
    "benefit-employees": BenefitEmployee,
    "benefit-rules": BenefitRule,
    "audit-open-items": OpenItem,
    "settlements": Settlement,
    "balance-controls": BalanceControl,
    "confirmations": Confirmation,
    "cutoff-documents": CutoffDocument,
}

AUDIT_WORKFLOWS: dict[str, tuple[str, list[str], dict[str, str]]] = {
    "asset-register-review": (
        "Asset register / depreciation / GL and verification evidence",
        [],
        {"register": "asset-register", "controls": "accounting-controls"},
    ),
    "inventory-count-bridge": (
        "Inventory count-date movement bridge to reporting-date books",
        [],
        {"books": "stock", "counts": "stock", "movements": "stock-movements"},
    ),
    "receivables-ecl": (
        "Reporting-date open items to reviewed IFRS 9 provision matrix",
        [],
        {"items": "audit-open-items", "controls": "balance-controls", "rates": "ecl-loss-rates"},
    ),
    "going-concern-cash": (
        "Cash forecast funding gaps and covenant thresholds",
        [],
        {"forecast": "cash-forecasts"},
    ),
    "procurement-match": (
        "Order / receipt / invoice / payment matching",
        [],
        {
            "orders": "purchase-lines",
            "receipts": "purchase-lines",
            "invoices": "purchase-lines",
            "payments": "purchase-lines",
        },
    ),
    "vendor-employee-conflicts": (
        "Shared bank-account evidence across vendor and employee masters",
        [],
        {"vendors": "party-masters", "employees": "party-masters"},
    ),
    "employee-expenses": (
        "Expense policy, approval and reused receipt checks",
        [],
        {"claims": "expense-claims"},
    ),
    "uae-benefit-review": (
        "End-of-service comparison against explicitly supplied regime rules",
        ["AE"],
        {"employees": "benefit-employees", "rules": "benefit-rules"},
    ),
    "subledger-control": (
        "Receivable/payable open items to GL control",
        [],
        {"items": "audit-open-items", "controls": "balance-controls"},
    ),
    "subsequent-settlements": (
        "Subsequent receipts/payments against reporting-date open items",
        [],
        {"items": "audit-open-items", "settlements": "settlements", "controls": "balance-controls"},
    ),
    "balance-confirmations": (
        "External balance confirmation evidence and exceptions",
        [],
        {"items": "audit-open-items", "responses": "confirmations", "controls": "balance-controls"},
    ),
    "expense-cutoff": (
        "Expense cutoff and unrecorded liability evidence",
        [],
        {"documents": "cutoff-documents"},
    ),
}
