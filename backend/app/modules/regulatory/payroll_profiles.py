"""Explicit assessed India payroll parameters; no statutory rates are supplied."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

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


class PayrollParameters(Strict):
    rule_group: Identifier
    component: Component
    jurisdiction: Identifier
    threshold_from: Money = Field(default=Decimal(0), ge=0)
    threshold_to: Money | None = Field(default=None, gt=0)
    salary_cap: Money | None = Field(default=None, gt=0)
    formula: Literal["rate", "fixed", "employer-minus-eps"]
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=18, decimal_places=12)
    fixed_amount: Money | None = Field(default=None, ge=0)
    rounding: Literal["nearest-rupee", "next-rupee", "floor-rupee", "paise"]

    @model_validator(mode="after")
    def consistent_parameters(self):
        if self.threshold_to is not None and self.threshold_to <= self.threshold_from:
            raise ValueError("Half-open threshold bands must be ordered")
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
