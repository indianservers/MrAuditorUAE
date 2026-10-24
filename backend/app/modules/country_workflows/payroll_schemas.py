"""Explicit assessed wage bases and reviewed, effective-dated India payroll rules."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.jurisdictions.profiles import Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Component = Literal[
    "PF:EMPLOYEE",
    "PF:EPS",
    "PF:EMPLOYER",
    "PF:ADVANCE_REFUND",
    "ESI:EMPLOYEE",
    "ESI:EMPLOYER",
    "PT",
]


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


class PayrollRule(Strict):
    id: Identifier
    rule_group: Identifier
    component: Component
    jurisdiction: Identifier
    effective_from: date
    effective_to: date
    threshold_from: Money = Field(default=Decimal(0), ge=0)
    threshold_to: Money | None = Field(default=None, gt=0)
    salary_cap: Money | None = Field(default=None, gt=0)
    formula: Literal["rate", "fixed", "employer-minus-eps"]
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=18, decimal_places=12)
    fixed_amount: Money | None = Field(default=None, ge=0)
    rounding: Literal["nearest-rupee", "next-rupee", "floor-rupee", "paise"]
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_evidence_version_id: uuid.UUID
    source_version: str = Field(min_length=1, max_length=120)
    evidence_reference: str = Field(min_length=3, max_length=200)
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def consistent(self):
        if self.effective_to < self.effective_from or (
            self.threshold_to is not None and self.threshold_to <= self.threshold_from
        ):
            raise ValueError("Rule dates and half-open threshold bands must be ordered")
        if self.formula == "fixed":
            if self.fixed_amount is None or self.rate is not None or self.salary_cap is not None:
                raise ValueError(
                    "A fixed slab requires a fixed amount without a rate or salary cap"
                )
        elif self.rate is None or self.fixed_amount is not None:
            raise ValueError("A rate formula requires a rate without a fixed amount")
        if self.formula == "employer-minus-eps" and self.component != "PF:EMPLOYER":
            raise ValueError("Employer-minus-EPS applies only to the employer PF component")
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
