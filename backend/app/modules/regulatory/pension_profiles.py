"""Shared explicit UAE pension parameters; no statutory rates are supplied."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")]
Component = Literal["PENSION:EMPLOYEE", "PENSION:EMPLOYER", "PENSION:GOVERNMENT"]


class PensionScope(Strict):
    authority: Identifier
    scheme: Identifier
    membership_cohort: Identifier
    pension_country: str = Field(pattern=r"^[A-Z]{2}$")
    nationality: str = Field(pattern=r"^[A-Z]{2}$")
    employment_sector: Literal["government", "private", "other"]
    jurisdiction: Identifier

    @model_validator(mode="after")
    def countries_exist(self):
        import pycountry

        if any(
            pycountry.countries.get(alpha_2=value) is None
            for value in (self.pension_country, self.nationality)
        ):
            raise ValueError("Pension country and nationality must be recognized ISO countries")
        return self


class PensionParameters(PensionScope):
    component: Component
    minimum_basis: Money = Field(default=Decimal(0), ge=0)
    salary_cap: Money | None = Field(default=None, gt=0)
    formula: Literal["rate", "fixed", "employer-minus-government"]
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=18, decimal_places=12)
    fixed_amount: Money | None = Field(default=None, ge=0)
    rounding: Literal["nearest-fils", "next-fils", "floor-fils"]

    @model_validator(mode="after")
    def consistent_parameters(self):
        if self.salary_cap is not None and self.salary_cap < self.minimum_basis:
            raise ValueError("Salary cap cannot be below the reviewed minimum basis")
        if self.formula == "fixed":
            if self.fixed_amount is None or self.rate is not None or self.salary_cap is not None:
                raise ValueError("Fixed pension amounts require no rate or salary cap")
        elif self.rate is None or self.fixed_amount is not None:
            raise ValueError("A pension rate formula requires an explicit rate only")
        if self.formula == "employer-minus-government" and self.component != "PENSION:EMPLOYER":
            raise ValueError("Only employer contributions may deduct resolved government support")
        return self
