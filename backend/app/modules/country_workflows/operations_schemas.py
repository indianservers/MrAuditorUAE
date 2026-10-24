"""Canonical operational movements, not payment instructions."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

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
    amount: Money = Field(gt=0)
    evidence_reference: ID
    rationale: str = Field(min_length=10, max_length=2000)


OPERATION_ROW_TYPES = {"cash-payments": CashPayment, "item-allocations": ItemAllocation}
OPERATION_WORKFLOWS = {"open-item-allocations": (
    "Invoice / confirmed receipt-payment allocations / unapplied cash / control accounts", [],
    {"items": "audit-open-items", "controls": "balance-controls", "payments": "cash-payments", "allocations": "item-allocations"})}
