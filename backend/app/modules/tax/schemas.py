import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict
from app.modules.ifrs.schemas import Money, Nonnegative, Positive, Rate

Assessment = Literal["PASS", "FAIL", "REVIEW_REQUIRED", "NOT_APPLICABLE", "INSUFFICIENT_DATA"]


class RuleParameters(Strict):
    standard_threshold: Nonnegative = Decimal("375000")
    standard_rate: Rate = Decimal("0.09")
    entertainment_disallowance: Rate = Decimal("0.5")
    revenue_threshold: Nonnegative = Decimal("3000000")
    sbr_last_period_end: date = date(2026, 12, 31)
    de_minimis_rate: Rate = Decimal("0.05")
    de_minimis_cap: Nonnegative = Decimal("5000000")
    disqualification_periods: int = Field(default=5, ge=1, le=10)
    interest_threshold: Nonnegative = Decimal("12000000")
    interest_percentage: Rate = Decimal("0.3")
    interest_carry_periods: int = Field(default=10, ge=1, le=20)
    loss_percentage: Rate = Decimal("0.75")
    group_ownership: Rate = Decimal("0.95")
    filing_months: int = Field(default=9, ge=0, le=24)


class Rule(Body):
    rule_key: str = Field(min_length=1, max_length=100)
    rule_version: int = Field(ge=1)
    category: Literal[
        "standard",
        "adjustments",
        "sbr",
        "qfzp",
        "interest",
        "losses",
        "group",
        "relief",
        "transitional",
        "exemption",
        "deadline",
        "foundation",
        "classification",
    ]
    source_id: str
    article: str = Field(default="", max_length=100)
    decision_number: str = Field(min_length=1, max_length=200)
    effective_from: date
    effective_to: date | None = None
    known_from: date
    source_document_version: str = Field(min_length=1, max_length=300)
    source_sha256: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")
    conditions: str = Field(min_length=1, max_length=6000)
    exceptions: str = Field(min_length=1, max_length=6000)
    technical_review: str = Field(min_length=1, max_length=6000)
    lifecycle: Literal["ACTIVE", "SUPERSEDED", "RETIRED"] = "ACTIVE"
    parameters: RuleParameters = Field(default_factory=RuleParameters)

    @model_validator(mode="after")
    def dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Invalid legal applicability dates")
        return self


class TaxProfile(Body):
    financial_run_id: uuid.UUID
    classification: Literal[
        "resident_juridical",
        "nonresident_juridical",
        "permanent_establishment",
        "natural_person",
        "free_zone",
        "qfzp",
        "exempt_person",
        "tax_group",
        "unincorporated_partnership",
        "family_foundation",
    ]
    legal_form: str = Field(min_length=1, max_length=300)
    registration_details: str = Field(min_length=1, max_length=2000)
    trn: str = Field(default="", pattern=r"^(\d{15})?$")
    residence_assessment: str = Field(min_length=1, max_length=4000)
    resident: bool
    free_zone: bool = False
    licensed_activities: str = Field(min_length=1, max_length=4000)
    ownership_assessment: str = Field(min_length=1, max_length=4000)
    accounting_framework: Literal["IFRS", "IFRS_SME"] = "IFRS"
    tax_start: date
    tax_end: date
    legal_as_of: date
    rules: dict[str, uuid.UUID] = Field(min_length=1, max_length=20)
    revenue: Nonnegative
    revenue_reconciliation_adjustment: Money = Decimal(0)
    revenue_adjustment_evidence_id: uuid.UUID | None = None
    revenue_source: str = Field(min_length=1, max_length=2000)
    scope_assessment: str = Field(min_length=1, max_length=4000)
    pillar_two_in_scope: bool
    audited_financials_required: bool
    audited_financials_evidence_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.tax_end < self.tax_start:
            raise ValueError("Invalid tax period/as-of date")
        return self


class Adjustment(Body):
    profile_id: uuid.UUID
    source_engagement_id: uuid.UUID | None = None
    category: Literal[
        "nondeductible",
        "entertainment",
        "fine",
        "compensatory_payment",
        "donation",
        "nonbusiness",
        "capital",
        "depreciation",
        "provision",
        "impairment",
        "unrealised",
        "related_party",
        "connected_person",
        "specific_interest",
        "transitional",
        "other",
    ]
    rule_id: uuid.UUID
    account_codes: list[str] = Field(min_length=1, max_length=100)
    accounting_amount: Money
    entertainment_scope: (
        Literal["customers_suppliers_partners", "employees_only", "other_review"] | None
    ) = None
    proposed_adjustment: Money
    treatment: Literal[
        "statutory_disallowance", "partial_deduction", "no_adjustment", "professional_adjustment"
    ]
    rationale: str = Field(min_length=1, max_length=4000)
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    ai_suggestion_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def scope(self):
        if self.category == "entertainment" and self.entertainment_scope is None:
            raise ValueError("Entertainment recipient scope must be explicitly assessed")
        return self


class Condition(Strict):
    requirement: str = Field(min_length=1, max_length=200)
    assessment: Assessment
    rationale: str = Field(min_length=1, max_length=4000)
    evidence_record_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)


class Exemption(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    exemption_type: Literal[
        "domestic_dividend",
        "participation",
        "foreign_pe",
        "investment",
        "group_relief",
        "restructuring",
        "other",
    ]
    amount: Nonnegative
    source_line_codes: list[str] = Field(min_length=1, max_length=100)
    conditions: list[Condition] = Field(min_length=1, max_length=50)
    rationale: str = Field(min_length=1, max_length=4000)


class SBR(Body):
    profile_id: uuid.UUID
    election_made: bool
    prior_revenues: list[Nonnegative] = Field(max_length=50)
    prior_periods_complete: bool
    is_qfzp: bool
    excluded_multinational: bool
    artificial_separation: bool
    aggregation_review: str = Field(min_length=1, max_length=4000)
    election_evidence_id: uuid.UUID


class ForeignTaxCredit(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    jurisdiction: str = Field(min_length=1, max_length=100)
    foreign_taxable_income: Nonnegative
    foreign_tax_paid: Nonnegative
    uae_tax_attributable: Nonnegative
    source_line_codes: list[str] = Field(min_length=1, max_length=100)
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    allocation_methodology: str = Field(min_length=1, max_length=4000)


class IncomeSegment(Strict):
    reference: str = Field(min_length=1, max_length=100)
    source_line_code: str
    revenue: Nonnegative
    taxable_profit: Money
    classification: Literal[
        "qualifying",
        "nonqualifying",
        "excluded",
        "domestic_pe",
        "foreign_pe",
        "immovable_property",
        "qualifying_ip",
        "other_ip",
        "unresolved",
    ]
    counterparty: str = Field(min_length=1, max_length=300)
    counterparty_type: Literal[
        "free_zone_beneficial_recipient",
        "non_free_zone",
        "natural_person",
        "related_party",
        "public_benefit",
        "unknown",
    ]
    activity: str = Field(min_length=1, max_length=300)
    jurisdiction: str = Field(min_length=1, max_length=100)
    denominator_excluded: bool = False
    exclusion_legal_basis: str = Field(default="", max_length=2000)
    contract_evidence_id: uuid.UUID
    rationale: str = Field(min_length=1, max_length=4000)


class QFZP(Body):
    profile_id: uuid.UUID
    conditions: list[Condition] = Field(min_length=1, max_length=50)
    segments: list[IncomeSegment] = Field(min_length=1, max_length=20000)
    earlier_disqualification_remaining: int = Field(default=0, ge=0, le=4)
    earlier_disqualification_source: str = Field(default="", max_length=2000)
    distribution_activity: bool = False
    procedures_2026_applicable: bool = False
    procedures_rule_id: uuid.UUID | None = None
    procedures_applicability_basis: str = Field(min_length=1, max_length=3000)


class CarryInterest(Strict):
    origin_period_index: int = Field(ge=0)
    balance: Nonnegative
    origin_source: str = Field(min_length=1, max_length=2000)


class Interest(Body):
    profile_id: uuid.UUID
    source_account_codes: list[str] = Field(default_factory=list, max_length=100)
    evidence_record_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    interest_expense: Nonnegative
    interest_income: Nonnegative
    permanent_disallowances: Nonnegative = Decimal(0)
    excluded_expense: Nonnegative = Decimal(0)
    excluded_income: Nonnegative = Decimal(0)
    capitalised_incurred: Nonnegative = Decimal(0)
    capitalised_amortisation: Nonnegative = Decimal(0)
    depreciation_tax_deductible: Nonnegative
    taxable_before_gidlr_losses: Money
    historical_net_interest_adjustment: Money = Decimal(0)
    infrastructure_net_interest_adjustment: Money = Decimal(0)
    period_months: Positive
    period_index: int = Field(ge=0)
    carryforwards: list[CarryInterest] = Field(default_factory=list, max_length=100)
    excluded_taxpayer: bool = False
    exclusion_basis: str = Field(default="", max_length=4000)
    statutory_bridge: str = Field(min_length=1, max_length=6000)
    loan_and_tp_review: str = Field(min_length=1, max_length=6000)


class Loss(Body):
    profile_id: uuid.UUID
    origin_start: date
    origin_end: date
    origin_tax_run_id: uuid.UUID | None = None
    transfer_source_id: uuid.UUID | None = None
    amount: Positive
    eligibility: Assessment
    ownership_continuity: bool
    same_or_similar_business: bool
    listed_or_natural_exception: bool = False
    excluded_pre_ct_or_exempt: bool
    source_reference: str = Field(min_length=1, max_length=2000)


class LossTransfer(Body):
    profile_id: uuid.UUID
    recipient_engagement_id: uuid.UUID
    recipient_profile_id: uuid.UUID
    loss_id: uuid.UUID
    amount: Positive
    common_ownership: Rate
    conditions: list[Condition] = Field(min_length=1, max_length=30)
    own_loss_utilisation_review: str = Field(min_length=1, max_length=4000)


class GroupMember(Strict):
    engagement_id: uuid.UUID
    profile_id: uuid.UUID
    share_capital: Rate
    voting_rights: Rate
    profit_net_asset_rights: Rate
    resident_juridical: bool
    exempt_or_qfzp: bool
    entry_date: date
    exit_date: date | None = None


class Group(Body):
    profile_id: uuid.UUID
    members: list[GroupMember] = Field(min_length=2, max_length=100)
    fta_application_evidence_id: uuid.UUID
    fta_approval_evidence_id: uuid.UUID
    special_purpose_audit_evidence_id: uuid.UUID
    group_adjustments: list[Adjustment] = Field(default_factory=list, max_length=500)
    pre_group_losses_interest_assessment: str = Field(min_length=1, max_length=4000)
    no_restricted_pre_group_attributes: bool
    conditions: list[Condition] = Field(min_length=1, max_length=30)


class Relief(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    relief_type: Literal["qualifying_group", "business_restructuring"]
    transferor_entity_id: uuid.UUID
    transferee_entity_id: uuid.UUID
    transaction_date: date
    common_ownership: Rate
    asset_or_business: str = Field(min_length=1, max_length=2000)
    consideration: Money
    tax_value: Money
    accounting_value: Money
    election_made: bool
    conditions: list[Condition] = Field(min_length=1, max_length=30)
    clawback_event_date: date | None = None
    clawback_review: str = Field(min_length=1, max_length=4000)


class Transitional(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    asset_category: Literal["immovable_property", "intangible", "financial_asset_liability"]
    acquisition_date: date
    first_tax_period_start: date
    election_evidence_id: uuid.UUID
    realisation_date: date | None = None
    accounting_value: Money
    tax_value: Money
    assessed_adjustment: Money
    valuation_evidence_id: uuid.UUID
    methodology_and_conditions: str = Field(min_length=1, max_length=6000)


class RelatedParty(Body):
    profile_id: uuid.UUID
    counterparty: str = Field(min_length=1, max_length=300)
    relationship: Literal["related_party", "connected_person", "third_party"]
    effective_from: date
    effective_to: date | None = None
    transaction_type: str = Field(min_length=1, max_length=300)
    amount: Money
    account_codes: list[str] = Field(min_length=1, max_length=100)
    contract_evidence_id: uuid.UUID
    risk_assessment: str = Field(min_length=1, max_length=4000)
    approved_adjustment_id: uuid.UUID | None = None
    benchmarking_completed: Literal[False] = False


class Foundation(Body):
    profile_id: uuid.UUID
    founders_beneficiaries: str = Field(min_length=1, max_length=4000)
    governance_evidence_id: uuid.UUID
    holding_structure: str = Field(min_length=1, max_length=4000)
    application_evidence_id: uuid.UUID | None = None
    approval_evidence_id: uuid.UUID | None = None
    conditions: list[Condition] = Field(min_length=1, max_length=40)
    treatment: Literal[
        "UNASSESSED", "APPLICATION_PENDING", "APPROVED_TRANSPARENT", "NOT_TRANSPARENT"
    ]
    ongoing_compliance: str = Field(min_length=1, max_length=4000)


class Election(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    election_type: str = Field(min_length=1, max_length=200)
    elected_on: date
    coverage_from: date
    coverage_to: date | None = None
    evidence_record_id: uuid.UUID
    technical_basis: str = Field(min_length=1, max_length=4000)


class ComputationApproval(Body):
    tax_run_id: uuid.UUID
    rationale: str = Field(min_length=1, max_length=4000)


class Return(ComputationApproval):
    checklist: list[Condition] = Field(min_length=1, max_length=40)
    filing_state: Literal[
        "NOT_STARTED",
        "IN_PREPARATION",
        "REVIEW_REQUIRED",
        "RETURN_APPROVED",
        "READY_FOR_FILING",
        "FILED_EXTERNALLY",
        "ACKNOWLEDGED",
    ] = "IN_PREPARATION"
    filing_evidence_id: uuid.UUID | None = None
    acknowledgement_evidence_id: uuid.UUID | None = None
    external_reference: str = Field(default="", max_length=300)


class Deadline(Body):
    profile_id: uuid.UUID
    rule_id: uuid.UUID
    deadline_type: Literal[
        "registration",
        "filing",
        "payment",
        "election",
        "documentation",
        "group_application",
        "other",
    ]
    assessed_due_date: date
    event_basis: str = Field(min_length=1, max_length=4000)
    evidence_record_id: uuid.UUID | None = None


BODIES: dict[str, type[Body]] = {
    "profile": TaxProfile,
    "rule": Rule,
    "adjustment": Adjustment,
    "exemption": Exemption,
    "credit": ForeignTaxCredit,
    "sbr": SBR,
    "qfzp": QFZP,
    "interest": Interest,
    "loss": Loss,
    "loss-transfer": LossTransfer,
    "group": Group,
    "restructuring": Relief,
    "transitional": Transitional,
    "related-party": RelatedParty,
    "foundation": Foundation,
    "election": Election,
    "deadline": Deadline,
    "computation": ComputationApproval,
    "return": Return,
}
