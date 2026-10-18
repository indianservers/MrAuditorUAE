import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Nonnegative = Annotated[Money, Field(ge=0)]
Rate = Annotated[Decimal, Field(ge=0, le=1, max_digits=18, decimal_places=12)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
MethodName = Literal["CUP", "RPM", "COST_PLUS", "TNMM", "PROFIT_SPLIT", "OTHER"]
PLI = Literal[
    "operating_margin", "op_oc", "gross_margin", "gross_cost_plus", "net_cost_plus", "roa", "value"
]


class RuleParameters(Strict):
    own_revenue: Nonnegative = Decimal("200000000")
    group_revenue: Nonnegative = Decimal("3150000000")
    rp_total: Nonnegative = Decimal("40000000")
    rp_category: Nonnegative = Decimal("4000000")
    connected_total: Nonnegative = Decimal("500000")
    apa_materiality: Nonnegative = Decimal("100000000")


class Rule(Body):
    source_id: str
    article: str
    jurisdiction: str = "AE"
    category: Literal[
        "relationships",
        "connected_person",
        "documentation",
        "disclosure",
        "connected_disclosure",
        "methodology",
        "apa",
    ]
    rule_key: str = Field(min_length=1, max_length=100)
    rule_version: int = Field(ge=1)
    effective_from: date
    effective_to: date | None = None
    known_from: date
    document_version: Text
    technical_review: Text
    conditions: Text
    parameters: RuleParameters = Field(default_factory=RuleParameters)


class Profile(Body):
    financial_run_id: uuid.UUID
    tax_start: date
    tax_end: date
    legal_as_of: date
    rules: dict[str, uuid.UUID] = Field(min_length=4, max_length=10)
    mne_member: bool
    uae_headquartered_non_mne_group: bool = False
    group_revenue: Nonnegative
    group_facts: Text
    financial_classification: Text


class Scoped(Body):
    profile_id: uuid.UUID


class Supported(Scoped):
    evidence_record_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    rationale: Text


class Party(Supported):
    name: Text
    entity_id: uuid.UUID | None = None
    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    party_type: Literal["company", "person", "pe", "partnership", "government"]
    identifiers: str = Field(default="", max_length=1000)
    phase6_counterparty_id: uuid.UUID | None = None
    synthetic: bool = False


class Relationship(Supported):
    related_party_applicable: bool | None = None
    connected_person_rule_id: uuid.UUID | None = None
    entity_relationship_id: uuid.UUID | None = None
    from_party_id: uuid.UUID
    to_party_id: uuid.UUID
    relationship_type: Literal[
        "ownership",
        "common_control",
        "director",
        "officer",
        "key_management",
        "family",
        "joint_venture",
        "associate",
        "pe",
        "other",
    ]
    ownership: Rate = Decimal(0)
    effective_from: date
    effective_to: date | None = None
    control_facts: Text
    decision: Literal["RELATED", "CONNECTED", "UNRELATED", "REVIEW_REQUIRED"]
    rule_id: uuid.UUID

    @model_validator(mode="after")
    def interval(self):
        if self.decision == "RELATED" and self.related_party_applicable is False:
            raise ValueError("RELATED classification cannot exclude related-party scope")
        if self.decision not in {"RELATED", "CONNECTED"} and self.related_party_applicable:
            raise ValueError(
                "Related-party scope requires a reviewed related or connected decision"
            )
        if (
            self.from_party_id == self.to_party_id
            or self.effective_to
            and self.effective_to < self.effective_from
        ):
            raise ValueError("Invalid relationship interval or self-link")
        return self


class Transaction(Supported):
    connected_payment_or_benefit: bool | None = None
    relationship_id: uuid.UUID
    counterparty_id: uuid.UUID
    transaction_date: date
    category: Literal[
        "goods",
        "services",
        "intellectual_property",
        "interest",
        "assets",
        "liabilities",
        "other",
        "dividend",
    ]
    nature: Literal[
        "sales",
        "purchases",
        "management_fee",
        "corporate_service",
        "loan",
        "interest_income",
        "interest_expense",
        "guarantee",
        "royalty",
        "license",
        "reimbursement",
        "shared_service",
        "asset_transfer",
        "restructuring",
        "director_remuneration",
        "benefit",
        "advance",
        "treasury",
        "other",
    ]
    side: Literal["revenue", "expense", "receivable", "payable", "interest", "principal"]
    economic_key: str = Field(min_length=1, max_length=200)
    journal_line_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    source_role: Literal["original", "settlement", "elimination"] = "original"
    is_reversal: bool = False
    source_amount: Money
    source_currency: str = Field(pattern=r"^[A-Z]{3}$")
    base_amount: Money
    base_currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")
    exchange_rate: Annotated[Decimal, Field(gt=0)] = Decimal(1)
    contract_reference: Text
    method: MethodName | None = None
    connected_group_key: str = Field(default="", max_length=200)
    disclosure_market_value: Nonnegative | None = None


class Allocation(Strict):
    segment: str = Field(min_length=1, max_length=100)
    weight: Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=8)]


class SegmentLine(Strict):
    financial_line_code: str
    metric: Literal["revenue", "cost_sales", "opex", "assets", "non_operating", "other"]
    classification: Literal["related", "unrelated", "shared", "other"]
    driver: Literal[
        "direct", "revenue", "headcount", "floor_area", "volume", "time", "direct_cost", "custom"
    ]
    allocation: list[Allocation] = Field(min_length=1, max_length=1000)
    methodology: Text


class Segmentation(Supported):
    lines: list[SegmentLine] = Field(min_length=1, max_length=1000)


class FAR(Supported):
    party_id: uuid.UUID
    functions: list[Text] = Field(min_length=1, max_length=30)
    assets: list[Text] = Field(min_length=1, max_length=30)
    risks: list[Text] = Field(min_length=1, max_length=30)
    actual_conduct: Text
    risk_control: Text
    tested_party_considerations: Text
    missing_interviews: list[Text] = Field(default_factory=list, max_length=30)


class Method(Supported):
    transaction_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    far_id: uuid.UUID
    method: MethodName
    tested_party_id: uuid.UUID
    pli: PLI
    economic_characteristics: Text
    available_comparables: Text
    rejected_alternatives: dict[str, str] = Field(min_length=1, max_length=6)


class Dataset(Supported):
    source_name: Text
    source_url: str = Field(default="", max_length=2000)
    license_type: Literal["synthetic", "licensed", "public", "internal"]
    license_reference: Text
    valid_until: date
    authorized_use: bool
    allow_raw_export: bool = False
    allow_derived_export: bool = False
    allow_ai: bool = False
    observation_date: date
    data_version: str = Field(min_length=1, max_length=100)


class Study(Supported):
    missing_policy: Literal["reject", "exclude_explicit"] = "reject"
    dataset_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    method_id: uuid.UUID
    pli: PLI
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    fiscal_years: list[int] = Field(min_length=1, max_length=20)
    aggregation: Literal["year_specific", "company_unweighted", "company_weighted"]
    quantile: Literal["inclusive", "exclusive"]
    purpose: Literal["profitability", "interest", "remuneration", "royalty"]
    screening_criteria: Text
    comparability_review: Text
    selected_target: Money | None = None
    target_rationale: str = Field(default="", max_length=4000)


class ScreeningDecision(Strict):
    observation_id: uuid.UUID
    decision: Literal["ACCEPT", "REJECT"]
    reason: Text
    independence_review: Text
    loss_review: Text
    functional_review: Text
    financial_adjustment: Money = Decimal(0)
    adjustment_basis: str = Field(default="", max_length=2000)


class Screening(Supported):
    study_id: uuid.UUID
    decisions: list[ScreeningDecision] = Field(min_length=1, max_length=200)


class CashFlow(Strict):
    date: date
    kind: Literal["drawdown", "repayment", "interest_payment"]
    amount: Annotated[Money, Field(gt=0)]
    reference: Text


class Reset(Strict):
    date: date
    annual_rate: Annotated[Decimal, Field(ge=0, le=2)]
    reference_source: Text


class Loan(Supported):
    accrual_start: date | None = None
    relationship_id: uuid.UUID
    lender_id: uuid.UUID
    borrower_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    functional_currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")
    exchange_rate: Annotated[Decimal, Field(gt=0)] = Decimal(1)
    exchange_rate_source: Text
    principal: Nonnegative
    drawdown_date: date
    maturity: date
    calculation_end: date
    annual_rate: Annotated[Decimal, Field(ge=0, le=2)]
    interest_type: Literal["fixed", "floating"]
    day_count: Literal["ACT/365", "ACT/360", "30E/360"]
    compounding: Literal["none", "monthly", "annual"] = "none"
    payment_frequency: Text
    cashflows: list[CashFlow] = Field(default_factory=list, max_length=1000)
    resets: list[Reset] = Field(default_factory=list, max_length=1000)
    security: Text
    guarantees: Text
    covenants: Text
    seniority: Text
    credit_characteristics: Text
    prepayment_options: Text
    subordination: Text
    purpose: Text
    expected_outstanding: Nonnegative | None = None
    benchmark_study_id: uuid.UUID | None = None
    credit_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def dates(self):
        if not self.drawdown_date < self.calculation_end <= self.maturity:
            raise ValueError("Calculation interval must lie within loan term")
        if (
            self.accrual_start
            and not self.drawdown_date <= self.accrual_start < self.calculation_end
        ):
            raise ValueError("Accrual start outside loan interval")
        if self.currency == self.functional_currency and self.exchange_rate != 1:
            raise ValueError("Same-currency FX must equal one")
        if self.interest_type == "floating" and not self.resets:
            raise ValueError("Floating loans need sourced reset observations")
        return self


class Credit(Supported):
    borrower_id: uuid.UUID
    debt: Nonnegative
    cash: Nonnegative
    ebit: Money
    interest: Nonnegative
    current_assets: Nonnegative
    current_liabilities: Nonnegative
    operating_cashflow: Money
    standalone_assessment: Text
    group_support: Text
    country_risk: Text
    proxy_label: Text
    proxy_methodology: Text
    benchmark_matching_review: Text


class Remuneration(Supported):
    party_id: uuid.UUID
    transaction_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    base_salary: Nonnegative
    bonus: Nonnegative
    allowances: Nonnegative
    benefits: Nonnegative
    management_fees: Nonnegative
    responsibilities: Text
    time_commitment: Text
    experience: Text
    size_performance: Text
    study_id: uuid.UUID | None = None
    comparability_adjustment: Money = Decimal(0)
    adjustment_basis: Text


class Service(Supported):
    transaction_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    cost_line_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    cost_pool: Nonnegative
    allocations: list[Allocation] = Field(min_length=1, max_length=1000)
    allocation_driver: Text
    methodology: Text
    markup: Annotated[Decimal, Field(ge=0, le=2)]
    benefit_test: Text
    provider_id: uuid.UUID
    recipients: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    simplified_approach: bool = False
    legal_conditions: Text


class Royalty(Supported):
    party_id: uuid.UUID
    transaction_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    dempe: dict[str, str] = Field(min_length=5, max_length=10)
    legal_ownership: Text
    economic_ownership: Text
    revenue_base: Nonnegative
    rate: Rate
    study_id: uuid.UUID | None = None


class Guarantee(Supported):
    relationship_id: uuid.UUID
    characterization: Literal["guarantee", "cash_pool", "deposit", "treasury"]
    principal: Nonnegative
    selected_rate: Rate
    days: int = Field(ge=1, le=3660)
    denominator: Literal[360, 365]
    benefit_assessment: Text
    credit_evidence: Text
    pricing_methodology: Text
    study_id: uuid.UUID | None = None


class Comparability(Supported):
    study_id: uuid.UUID
    tested_receivables: Nonnegative
    tested_inventory: Nonnegative
    tested_payables: Nonnegative
    tested_revenue: Annotated[Money, Field(gt=0)]
    comparable_receivables: Nonnegative
    comparable_inventory: Nonnegative
    comparable_payables: Nonnegative
    comparable_revenue: Annotated[Money, Field(gt=0)]
    financing_rate: Rate
    rate_source: Text
    selected: bool


class Disclosure(Supported):
    population_complete: bool
    exclusions_review: Text
    group_aggregation_review: Text


class Section(Strict):
    key: str
    narrative: Text
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    run_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    human_verified: bool


class Document(Supported):
    sections: list[Section] = Field(min_length=1, max_length=30)
    checklist_complete: bool
    consolidated_run_id: uuid.UUID | None = None
    financial_reconciliation_run_id: uuid.UUID
    license_review: Text
    annual_version: int = Field(ge=1)


class APA(Supported):
    covered_entities: list[uuid.UUID] = Field(min_length=1, max_length=100)
    covered_periods: list[str] = Field(min_length=1, max_length=10)
    method_id: uuid.UUID
    benchmark_run_id: uuid.UUID
    proposed_value: Nonnegative
    critical_assumptions: Text
    checklist: dict[str, bool] = Field(min_length=1, max_length=40)
    correspondence: list[str] = Field(default_factory=list, max_length=50)
    status: Literal["ASSESSING", "PREPARING", "UNDER_REVIEW", "EXTERNAL_CORRESPONDENCE"]
    cross_border_commencement_verified: bool = False


class Judgment(Supported):
    software_test_only: bool = False
    run_id: uuid.UUID
    conclusion: Literal["SUPPORTED", "NOT_SUPPORTED", "MORE_INFORMATION"]
    proposed_tax_adjustment: Money = Decimal(0)
    no_automatic_percentile_conclusion: bool
    fta_downward_approval_id: uuid.UUID | None = None


class Release(Supported):
    document_run_id: uuid.UUID
    client_visible: bool
    confidential_notes_excluded: bool
    disclosure_authorization: Text


BODIES: dict[str, type[Body]] = {
    "rule": Rule,
    "profile": Profile,
    "party": Party,
    "relationship": Relationship,
    "transaction": Transaction,
    "segmentation": Segmentation,
    "far": FAR,
    "method": Method,
    "dataset": Dataset,
    "study": Study,
    "screening": Screening,
    "loan": Loan,
    "credit": Credit,
    "remuneration": Remuneration,
    "service": Service,
    "royalty": Royalty,
    "guarantee": Guarantee,
    "comparability": Comparability,
    "disclosure": Disclosure,
    "localfile": Document,
    "masterfile": Document,
    "apa": APA,
    "judgment": Judgment,
    "release": Release,
}
