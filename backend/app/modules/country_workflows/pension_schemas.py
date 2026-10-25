"""Reviewed UAE pension inputs; authority and membership are never inferred."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

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


class PensionObservation(PensionScope):
    id: Identifier
    registration: Identifier
    subject: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Component
    currency: Literal["AED"] = "AED"
    amount: Money = Field(ge=0)
    evidence_reference: str = Field(min_length=3, max_length=200)


class PensionBasis(PensionObservation):
    eligible: bool
    membership_reference: str = Field(min_length=3, max_length=200)
    salary_basis_reference: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed(self):
        if any(
            len(value.strip()) < minimum
            for value, minimum in (
                (self.membership_reference, 3),
                (self.salary_basis_reference, 3),
                (self.assessment, 10),
            )
        ):
            raise ValueError(
                "Retain explicit membership, salary-basis and applicability assessments"
            )
        return self


class PensionRule(PensionScope):
    id: Identifier
    component: Component
    effective_from: date
    effective_to: date
    minimum_basis: Money = Field(default=Decimal(0), ge=0)
    salary_cap: Money | None = Field(default=None, gt=0)
    formula: Literal["rate", "fixed", "employer-minus-government"]
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=18, decimal_places=12)
    fixed_amount: Money | None = Field(default=None, ge=0)
    rounding: Literal["nearest-fils", "next-fils", "floor-fils"]
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_evidence_version_id: uuid.UUID
    source_version: Identifier
    evidence_reference: str = Field(min_length=3, max_length=200)
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def consistent(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Pension rule dates must be ordered")
        if self.salary_cap is not None and self.salary_cap < self.minimum_basis:
            raise ValueError("Salary cap cannot be below the reviewed minimum basis")
        if self.formula == "fixed":
            if self.fixed_amount is None or self.rate is not None or self.salary_cap is not None:
                raise ValueError("Fixed pension amounts require no rate or salary cap")
        elif self.rate is None or self.fixed_amount is not None:
            raise ValueError("A pension rate formula requires an explicit rate only")
        if self.formula == "employer-minus-government" and self.component != "PENSION:EMPLOYER":
            raise ValueError("Only employer contributions may deduct resolved government support")
        if len(self.applicability_review.strip()) < 10:
            raise ValueError("Document the legal source and cohort applicability")
        return self


PENSION_ROW_TYPES: dict[str, type[BaseModel]] = {
    "pension-bases": PensionBasis,
    "pension-rules": PensionRule,
    "pension-reported": PensionObservation,
}
PENSION_WORKFLOWS = {
    "uae-pension-review": (
        "UAE pension contribution and government-support review",
        ["AE"],
        {"bases": "pension-bases", "rules": "pension-rules", "reported": "pension-reported"},
    )
}
