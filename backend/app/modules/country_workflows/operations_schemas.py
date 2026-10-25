"""Canonical operational movements, not payment instructions."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]
Money = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False)]


class CashPayment(Strict):
    id: ID
    account: ID
    counterparty: ID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    date: date
    reference: ID
    direction: Literal["receipt", "payment"]
    amount: Money
    confirmation_status: Literal["confirmed", "pending", "reversed"]
    evidence_reference: ID


class ItemAllocation(Strict):
    id: ID
    payment_id: ID
    item_id: ID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money = Field(gt=0)
    evidence_reference: ID
    rationale: str = Field(min_length=10, max_length=2000)


class CreditApplication(Strict):
    id: ID
    credit_item_id: ID
    invoice_item_id: ID
    date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money = Field(gt=0)
    evidence_reference: ID
    allocation_reference: ID
    rationale: str = Field(min_length=10, max_length=2000)


class BankOutstanding(Strict):
    id: ID
    account: ID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    balance_date: date
    date: date
    reference: ID
    amount: Decimal = Field(max_digits=28, decimal_places=8, allow_inf_nan=False)
    evidence_reference: ID

    @field_validator("id", "account", "reference", "evidence_reference")
    @classmethod
    def exact_reference(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Bank outstanding identifiers require exact nonblank values")
        return value

    @model_validator(mode="after")
    def outstanding_scope(self):
        if not self.amount or self.date > self.balance_date:
            raise ValueError(
                "Outstanding bank items need nonzero signed amounts dated by reporting date"
            )
        return self


class BankClearance(Strict):
    id: ID
    outstanding_id: ID
    transaction_id: ID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money = Field(gt=0)
    evidence_reference: ID
    rationale: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def explicit_assessment(self):
        if (
            any(
                not value.strip() or value != value.strip()
                for value in (
                    self.id,
                    self.outstanding_id,
                    self.transaction_id,
                    self.evidence_reference,
                )
            )
            or len(self.rationale.strip()) < 10
        ):
            raise ValueError(
                "Bank clearance requires exact identifiers and a meaningful evidence assessment"
            )
        return self


OPERATION_ROW_TYPES: dict[str, type[BaseModel]] = {
    "bank-outstanding": BankOutstanding,
    "bank-clearances": BankClearance,
    "credit-applications": CreditApplication,
    "cash-payments": CashPayment,
    "item-allocations": ItemAllocation,
}
OPERATION_WORKFLOWS: dict[str, tuple[str, list[str], dict[str, str]]] = {
    "bank-subsequent-clearance": (
        "Outstanding bank items / subsequent statement clearance",
        [],
        {
            "outstanding": "bank-outstanding",
            "statement": "transactions",
            "allocations": "bank-clearances",
        },
    ),
    "credit-note-applications": (
        "Credit-note applications and residual subledger controls",
        [],
        {
            "items": "audit-open-items",
            "controls": "balance-controls",
            "applications": "credit-applications",
        },
    ),
    "open-item-allocations": (
        "Invoice / confirmed receipt-payment allocations / unapplied cash / control accounts",
        [],
        {
            "items": "audit-open-items",
            "controls": "balance-controls",
            "payments": "cash-payments",
            "allocations": "item-allocations",
        },
    ),
}
