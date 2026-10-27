"""Assessed payroll accounting allocations, independent of wage or tax calculation."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.jurisdictions.profiles import Strict

Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]


class PayrollAccount(Strict):
    id: Identifier
    registration: Identifier
    account: Identifier
    account_class: Literal["expense", "liability"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Money
    evidence_reference: Identifier

    @field_validator("id", "registration", "account", "evidence_reference")
    @classmethod
    def exact(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Payroll accounting identifiers must be exact nonblank values")
        return value


class PayrollAccountBalance(PayrollAccount):
    as_of: date


class PayrollLedgerLine(PayrollAccount):
    posting_date: date
    wage_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Identifier
    category: Literal["accrual", "settlement", "adjustment"]
    subject: Identifier
    reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed_posting(self):
        if date.fromisoformat(self.wage_month + "-01") > self.posting_date:
            raise ValueError("Wage month cannot begin after the assessed posting date")
        if not self.amount:
            raise ValueError("Use an explicit nil population instead of zero payroll journal rows")
        if (
            any(
                not value.strip() or value != value.strip()
                for value in (self.component, self.subject, self.reference)
            )
            or len(self.assessment.strip()) < 10
        ):
            raise ValueError(
                "Assess payroll allocation, subject, component and journal reference explicitly"
            )
        return self


PAYROLL_LEDGER_ROW_TYPES: dict[str, type[BaseModel]] = {
    "payroll-account-balances": PayrollAccountBalance,
    "payroll-ledger-lines": PayrollLedgerLine,
}
PAYROLL_LEDGER_WORKFLOWS = {
    "payroll-ledger-rollforward": (
        "Payroll account movements and GL balance bridge",
        ["AE", "IN"],
        {
            "opening": "payroll-account-balances",
            "payroll": "payroll-ledger-lines",
            "posted": "payroll-ledger-lines",
            "closing": "payroll-account-balances",
        },
    ),
}
