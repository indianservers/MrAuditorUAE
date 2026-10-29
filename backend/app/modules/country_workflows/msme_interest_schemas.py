"""Explicit assessed MSE interest conventions and independently retained observations."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.country_workflows.interest_accrual import Day, RateWindow
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.payroll_profiles import Identifier, Money

CONTRACT = "india-msme-assessed-interest/1"


class InterestPartyRow(Strict):
    id: Identifier
    buyer_id: Identifier
    supplier_id: Identifier
    invoice_id: Identifier
    currency: Literal["INR"] = "INR"


class InterestEvidence(Strict):
    source_url: HttpUrl
    source_evidence_version_id: UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_version: Identifier
    evidence_reference: Identifier
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed_evidence(self):
        if len(self.applicability_review.strip()) < 10:
            raise ValueError("Assess the applicable version and source interpretation")
        return self


class MSMEInterestPolicy(InterestPartyRow, InterestEvidence):
    eligible: bool
    amount: Money = Field(
        ge=0, description="Explicit assessed interest principal, not inferred gross invoice value"
    )
    effective_from: Day
    effective_to: Day
    history_from: Day
    history_assessment: str = Field(min_length=10, max_length=2000)
    interest_start: Day | None = None
    start_basis: Literal["TIMING_DUE_PLUS_ONE", "SEPARATELY_ASSESSED_START"] | None = None
    start_assessment: str | None = Field(default=None, min_length=10, max_length=2000)
    rate_group: Identifier | None = None
    bank_rate_multiplier: Literal["3"] | None = None
    rest_basis: Literal["CALENDAR_MONTH_END", "MONTHLY_ANNIVERSARY"] | None = None
    day_basis: Literal["ACT_365_FIXED", "ACT_ACT_YEAR"] | None = None
    event_timing: Literal["BEGINNING_OF_DAY", "END_OF_DAY"] | None = None
    rest_rounding: Literal["ROUND_EACH_REST", "CARRY_PRECISION"] | None = None
    rounding: Literal["HALF_UP", "CEILING", "FLOOR"] | None = None

    @model_validator(mode="after")
    def explicit_conventions(self):
        if self.effective_to < self.effective_from or len(self.history_assessment.strip()) < 10:
            raise ValueError("Assess ordered policy validity and complete payment history")
        options = (
            self.interest_start,
            self.start_basis,
            self.start_assessment,
            self.rate_group,
            self.bank_rate_multiplier,
            self.rest_basis,
            self.day_basis,
            self.event_timing,
            self.rest_rounding,
            self.rounding,
        )
        if self.eligible:
            if (
                any(value is None for value in options)
                or len((self.start_assessment or "").strip()) < 10
            ):
                raise ValueError(
                    "Eligible MSE interest requires every explicit accrual convention and start assessment"
                )
        elif self.amount != 0 or any(value is not None for value in options):
            raise ValueError(
                "Assessed outside-scope interest requires explicit zero principal without competing accrual conventions"
            )
        return self


class MSMEBankRate(RateWindow, InterestEvidence):
    rate_kind: Literal["RBI_BANK_RATE"]
    rate_group: Identifier


class MSMEPrincipalChange(InterestPartyRow):
    mode: Literal["BANK_PRINCIPAL_PORTION", "DOCUMENTED_PRINCIPAL_REDUCTION"]
    amount: Money = Field(ge=0)
    principal_allocation_id: Identifier | None = None
    day: Day | None = None
    evidence_reference: Identifier
    rationale: str = Field(min_length=10, max_length=2000)
    source_url: HttpUrl | None = None
    source_evidence_version_id: UUID | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_version: Identifier | None = None
    applicability_review: str | None = Field(default=None, min_length=10, max_length=2000)

    @model_validator(mode="after")
    def single_evidence_basis(self):
        documents = (
            self.source_url,
            self.source_evidence_version_id,
            self.source_sha256,
            self.source_version,
            self.applicability_review,
        )
        if len(self.rationale.strip()) < 10:
            raise ValueError("Assess the principal portion or documented non-cash reduction")
        if self.mode == "BANK_PRINCIPAL_PORTION":
            if (
                self.principal_allocation_id is None
                or self.day is not None
                or any(value is not None for value in documents)
            ):
                raise ValueError(
                    "A principal bank portion derives its date from the original allocation; no replacement date or document basis"
                )
        elif (
            self.principal_allocation_id is not None
            or self.day is None
            or self.amount <= 0
            or any(value is None for value in documents)
            or len((self.applicability_review or "").strip()) < 10
        ):
            raise ValueError(
                "A non-cash principal reduction needs a positive amount, explicit date and retained assessment document"
            )
        return self


class MSMEInterestAllocation(InterestPartyRow):
    payment_id: Identifier
    amount: Money = Field(gt=0)
    bucket: Literal["UNCAPITALIZED_INTEREST", "CAPITALIZED_INTEREST"]
    evidence_reference: Identifier
    rationale: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed(self):
        if len(self.rationale.strip()) < 10:
            raise ValueError(
                "Assess the bank interest payment and its explicit unpaid-interest bucket"
            )
        return self


class MSMEReportedInterest(InterestPartyRow):
    as_of: Day
    amount: Money = Field(ge=0)
    evidence_reference: Identifier


ROW_TYPES: dict[str, type[BaseModel]] = {
    "msme-interest-policies": MSMEInterestPolicy,
    "msme-bank-rates": MSMEBankRate,
    "msme-principal-changes": MSMEPrincipalChange,
    "msme-interest-allocations": MSMEInterestAllocation,
    "msme-reported-interest": MSMEReportedInterest,
}
ROLES = {
    "assessments": "msme-supplier-assessments",
    "invoices": "msme-invoices",
    "bank": "transactions",
    "allocations": "item-allocations",
    "interest_policies": "msme-interest-policies",
    "bank_rates": "msme-bank-rates",
    "principal_changes": "msme-principal-changes",
    "interest_allocations": "msme-interest-allocations",
    "reported": "msme-reported-interest",
}
