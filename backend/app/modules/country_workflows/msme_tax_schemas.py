"""Assessed MSE tax bases and settlement evidence; no inferred tax eligibility."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.country_workflows.interest_accrual import Day
from app.modules.country_workflows.msme_interest_schemas import InterestEvidence, InterestPartyRow
from app.modules.regulatory.payroll_profiles import Identifier, Money

CONTRACT = "india-msme-annual-tax/1"
METRICS = (
    "INTEREST_PNL_DISALLOWANCE",
    "CURRENT_PRINCIPAL_DISALLOWANCE",
    "PRIOR_PRINCIPAL_RELEASE",
)


class MSMETaxBasis(InterestPartyRow, InterestEvidence):
    amount: Money = Field(
        ge=0,
        description="Assessed otherwise-deductible principal basis, not inferred gross invoice value",
    )
    liability_tax_year_start: Day
    otherwise_allowable: bool | None = None
    history_from: Day
    history_assessment: str = Field(min_length=10, max_length=2000)
    opening_paid_basis: Money = Field(ge=0)
    opening_disallowed_basis: Money = Field(ge=0)
    opening_previously_allowed_unpaid: Money = Field(ge=0)
    tax_reference: Literal["1961:43B(h)", "2025:37(2)(g)"]
    prior_disallowance_reference: Literal["1961:43B(h)", "2025:37(2)(g)"] | None = None
    effective_from: Day
    effective_to: Day
    basis_assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed_scope(self):
        if self.liability_tax_year_start.month != 4 or self.liability_tax_year_start.day != 1:
            raise ValueError("Declare the liability's Indian tax year starting on April 1")
        if (
            self.effective_to < self.effective_from
            or min(len(self.basis_assessment.strip()), len(self.history_assessment.strip())) < 10
        ):
            raise ValueError("Assess the basis, prior tax treatment and ordered policy validity")
        if self.otherwise_allowable is False and self.amount != 0:
            raise ValueError(
                "An otherwise-inadmissible expense has zero basis under this procedure; other tax adjustments remain separate"
            )
        return self


class MSMETaxSettlement(InterestPartyRow):
    mode: Literal[
        "BANK_ALLOCATION_PORTION", "ASSESSED_BANK_ADVANCE_APPLICATION", "ASSESSED_OTHER_SETTLEMENT"
    ]
    amount: Money = Field(ge=0)
    bucket: Literal[
        "CURRENT_EXPENSE", "HISTORICAL_PAID", "PRIOR_DISALLOWED", "PRIOR_ALREADY_ALLOWED"
    ]
    principal_allocation_id: Identifier | None = None
    day: Day | None = None
    qualifies_as_payment: bool | None = None
    settlement_kind: Literal["WITHHOLDING", "NETTING", "ADVANCE_APPROPRIATION", "OTHER"] | None = (
        None
    )
    source_url: HttpUrl | None = None
    source_evidence_version_id: UUID | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_version: Identifier | None = None
    applicability_review: str | None = Field(default=None, min_length=10, max_length=2000)
    evidence_reference: Identifier
    rationale: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def explicit_payment_evidence(self):
        evidence = {key: getattr(self, key) for key in InterestEvidence.model_fields}
        if len(self.rationale.strip()) < 10:
            raise ValueError("Assess the tax-basis portion and its explicit allocation bucket")
        if self.mode == "BANK_ALLOCATION_PORTION":
            if (
                not self.principal_allocation_id
                or self.day is not None
                or self.settlement_kind is not None
                or self.qualifies_as_payment is not True
            ):
                raise ValueError(
                    "Bank portions use the original allocation date and require explicit payment qualification"
                )
            if any(
                value is not None for key, value in evidence.items() if key != "evidence_reference"
            ):
                raise ValueError(
                    "Bank portions retain original bank evidence, not replacement document/date fields"
                )
        elif self.mode == "ASSESSED_BANK_ADVANCE_APPLICATION":
            if (
                not self.principal_allocation_id
                or self.day is None
                or self.settlement_kind != "ADVANCE_APPROPRIATION"
                or self.amount <= 0
            ):
                raise ValueError(
                    "An advance application retains its original bank allocation plus an assessed application date and supporting document"
                )
            InterestEvidence.model_validate(evidence)
        else:
            if (
                self.principal_allocation_id is not None
                or self.day is None
                or self.settlement_kind is None
                or self.amount <= 0
            ):
                raise ValueError(
                    "An assessed other settlement needs a positive amount, date, kind and its own supporting document"
                )
            InterestEvidence.model_validate(evidence)
        return self


class MSMEInterestPNL(InterestPartyRow, InterestEvidence):
    amount: Money = Field(
        description="Assessed current net P&L interest basis; net credits are retained for separate tax treatment, not a negative disallowance"
    )
    tax_year_start: Day
    section23_applies: bool | None = None
    pnl_assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed_pnl(self):
        if len(self.pnl_assessment.strip()) < 10:
            raise ValueError(
                "Assess the current P&L interest charge and any reversal treatment explicitly"
            )
        return self


class MSMETaxReported(InterestPartyRow):
    metric: Literal[
        "INTEREST_PNL_DISALLOWANCE", "CURRENT_PRINCIPAL_DISALLOWANCE", "PRIOR_PRINCIPAL_RELEASE"
    ]
    tax_year_start: Day
    as_of: Day
    amount: Money
    evidence_reference: Identifier

    @model_validator(mode="after")
    def reported_sign(self):
        if self.metric != "INTEREST_PNL_DISALLOWANCE" and self.amount < 0:
            raise ValueError(
                "Principal disallowance and prior release are separately reported non-negative amounts"
            )
        return self


ROW_TYPES: dict[str, type[BaseModel]] = {
    "msme-tax-bases": MSMETaxBasis,
    "msme-tax-settlements": MSMETaxSettlement,
    "msme-interest-pnl": MSMEInterestPNL,
    "msme-tax-reported": MSMETaxReported,
}
ROLES = {
    "assessments": "msme-supplier-assessments",
    "invoices": "msme-invoices",
    "bank": "transactions",
    "allocations": "item-allocations",
    "tax_bases": "msme-tax-bases",
    "tax_settlements": "msme-tax-settlements",
    "interest_pnl": "msme-interest-pnl",
    "reported": "msme-tax-reported",
}
