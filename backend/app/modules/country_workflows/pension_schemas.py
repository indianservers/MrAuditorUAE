"""Reviewed UAE pension inputs; authority and membership are never inferred."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.regulatory.pension_profiles import (
    Component,
    Identifier,
    Money,
    PensionParameters,
    PensionScope,
)


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


class PensionRule(PensionParameters):
    id: Identifier
    effective_from: date
    effective_to: date
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
