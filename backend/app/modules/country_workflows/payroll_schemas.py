"""Explicit assessed wage bases and reviewed, effective-dated India payroll rules."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.payroll_profiles import Component, PayrollParameters

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]


class PayrollBasis(Strict):
    id: Identifier
    registration: Identifier
    subject: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Component
    currency: Literal["INR"] = "INR"
    amount: Money = Field(
        ge=0, description="Assessed wage or refund base for this component; not gross payroll"
    )
    rule_group: Identifier
    jurisdiction: Identifier
    eligible: bool
    eligibility_reference: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)


class PayrollRule(PayrollParameters):
    id: Identifier
    effective_from: date
    effective_to: date
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_evidence_version_id: uuid.UUID
    source_version: str = Field(min_length=1, max_length=120)
    evidence_reference: str = Field(min_length=3, max_length=200)
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def consistent(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Rule dates must be ordered")
        return self


PAYROLL_ROW_TYPES: dict[str, type[BaseModel]] = {
    "payroll-bases": PayrollBasis,
    "payroll-rules": PayrollRule,
}
PAYROLL_WORKFLOWS = {
    "india-payroll-rules": (
        "India payroll contribution rules review",
        ["IN"],
        {"bases": "payroll-bases", "rules": "payroll-rules", "reported": "obligations"},
    )
}
