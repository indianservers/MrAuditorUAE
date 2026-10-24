"""Diligence evidence and review signals; never automatic identity or sanctions clearance."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.modules.country_workflows.audit_schemas import Identifier
from app.modules.jurisdictions.profiles import Strict


class DiligenceSubject(Strict):
    id: Identifier
    risk: Literal["low", "medium", "high"]
    pep: bool
    identity_verified: bool
    reviewed_on: date
    review_due: date
    identity_expires: date
    identity_evidence: Identifier
    source_of_funds_evidence: str = Field(default="", max_length=120)
    source_of_wealth_evidence: str = Field(default="", max_length=120)
    senior_approval_evidence: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def ordered(self):
        if self.review_due < self.reviewed_on:
            raise ValueError("Diligence review due date precedes the review")
        return self


class OwnershipEdge(Strict):
    id: Identifier
    company: Identifier
    owner: Identifier
    owner_kind: Literal["company", "person"]
    fraction: Decimal = Field(ge=0, le=1, decimal_places=10)
    effective_from: date
    effective_to: date | None = None
    evidence_reference: Identifier

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Ownership effective dates must be ordered")
        if self.company == self.owner:
            raise ValueError("Direct self-ownership needs a separately assessed treasury-share model")
        return self


class OwnershipPolicy(Strict):
    id: Identifier
    country: str = Field(pattern=r"^[A-Z]{2}$")
    threshold: Decimal = Field(gt=0, le=1, decimal_places=10)
    comparison: Literal["greater-than", "at-least"]
    effective_from: date
    effective_to: date
    evidence_reference: Identifier


class ScreeningSubject(Strict):
    id: Identifier
    name: str = Field(min_length=1, max_length=200)
    evidence_reference: Identifier


class SanctionsEntry(Strict):
    id: Identifier
    list_subject_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    list_version: Identifier
    published_on: date
    evidence_reference: Identifier


class ScreeningPolicy(Strict):
    id: Identifier
    minimum_similarity: Decimal = Field(ge=Decimal("0.5"), le=1, decimal_places=10)
    maximum_list_age_days: int = Field(ge=0, le=365)
    list_version: Identifier
    evidence_reference: Identifier


DILIGENCE_ROW_TYPES: dict[str, type[Strict]] = {
    "diligence-subjects": DiligenceSubject, "ownership-edges": OwnershipEdge,
    "ownership-policies": OwnershipPolicy, "screening-subjects": ScreeningSubject,
    "sanctions-entries": SanctionsEntry, "screening-policies": ScreeningPolicy,
}
DILIGENCE_WORKFLOWS: dict[str, tuple[str, list[str], dict[str, str]]] = {
    "kyc-edd-review": ("KYC periodic review and enhanced-diligence evidence", [],
                       {"subjects": "diligence-subjects"}),
    "ownership-lookthrough": ("Economic ownership look-through with reviewed threshold", [],
                              {"ownership": "ownership-edges", "policy": "ownership-policies"}),
    "sanctions-name-review": ("Uploaded sanctions-list name baseline; independent adjudication required", [],
                              {"subjects": "screening-subjects", "list": "sanctions-entries",
                               "policy": "screening-policies"}),
}
