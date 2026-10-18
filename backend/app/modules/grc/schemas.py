import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Nonnegative = Annotated[Money, Field(ge=0)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Evidence = Annotated[list[uuid.UUID], Field(max_length=50)]


class Framework(Body):
    identifier: str = Field(min_length=1, max_length=100)
    version_number: int = Field(ge=1)
    effective_from: date
    effective_to: date | None = None
    applicability: Text
    technical_review: Text
    requirement_mapping: dict[str, str] = Field(default_factory=dict, max_length=100)
    proprietary_text_authorized: bool = False
    supersedes_id: uuid.UUID | None = None
    custom_source_url: str = Field(default="", max_length=1000)
    authority: Literal[
        "professional_standard",
        "topical_requirement",
        "framework",
        "guidance",
        "internal_policy",
        "uae_regulation",
    ] = "internal_policy"


class Universe(Body):
    owner_id: uuid.UUID
    entity_id: uuid.UUID
    unit_type: Literal[
        "business_unit",
        "department",
        "location",
        "process",
        "system",
        "third_party",
        "project",
        "asset",
        "obligation",
    ]
    objective: Text
    exposure: Nonnegative = Decimal(0)
    inherent_rating: int = Field(ge=1, le=25)
    maturity: int = Field(ge=1, le=5)
    previous_audit: date | None = None
    frequency_months: int = Field(ge=1, le=120)
    assigned_auditor_id: uuid.UUID
    parent_id: uuid.UUID | None = None


class Scoring(Body):
    version_number: int = Field(ge=1)
    matrix_size: Literal[3, 5] = 5
    method: Literal["product", "lookup"] = "product"
    cells: list[list[Nonnegative]] = Field(default_factory=list, max_length=5)
    appetite: Nonnegative
    criteria_weights: dict[str, Annotated[Decimal, Field(ge=0, le=1)]] = Field(
        min_length=1, max_length=30
    )
    criteria_scale: int = Field(default=5, ge=1, le=100)
    labels: dict[str, str] = Field(default_factory=dict, max_length=25)

    @model_validator(mode="after")
    def dimensions(self):
        if sum(self.criteria_weights.values()) != 1:
            raise ValueError("Criterion weights must sum to 1")
        if self.method == "lookup" and (
            len(self.cells) != self.matrix_size
            or any(len(r) != self.matrix_size for r in self.cells)
        ):
            raise ValueError("Complete square matrix required")
        return self


class PlanItem(Strict):
    universe_id: uuid.UUID
    auditor_id: uuid.UUID
    starts: date
    ends: date
    budget_hours: Nonnegative
    actual_hours: Nonnegative = Decimal(0)
    criteria: dict[str, Nonnegative] = Field(min_length=1, max_length=30)
    deferred: bool = False
    deferral_reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def dates(self):
        if self.ends < self.starts:
            raise ValueError("Plan end precedes start")
        if self.deferred and not self.deferral_reason:
            raise ValueError("Deferral requires rationale")
        return self


class Plan(Body):
    year: int = Field(ge=2020, le=2100)
    scoring_id: uuid.UUID
    items: list[PlanItem] = Field(min_length=1, max_length=500)
    capacity_hours: dict[uuid.UUID, Nonnegative] = Field(min_length=1, max_length=500)
    committee_evidence_id: uuid.UUID
    revision_of_id: uuid.UUID | None = None


class IAEngagement(Body):
    owner_id: uuid.UUID
    universe_id: uuid.UUID
    plan_id: uuid.UUID
    objective: Text
    scope: Text
    criteria: Text
    program: list[str] = Field(min_length=1, max_length=100)
    team_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    starts: date
    ends: date


class Risk(Body):
    owner_id: uuid.UUID
    universe_id: uuid.UUID
    category: Literal[
        "strategic",
        "financial",
        "operational",
        "compliance",
        "cybersecurity",
        "technology",
        "fraud",
        "reputational",
        "third_party",
        "environmental",
        "continuity",
        "governance",
    ]
    objective: Text
    description: Text
    cause: Text
    consequence: Text
    treatment: Literal["accept", "avoid", "reduce", "transfer"]
    review_date: date
    evidence_ids: Evidence = Field(default_factory=list)


class Assessment(Body):
    owner_id: uuid.UUID
    risk_id: uuid.UUID
    scoring_id: uuid.UUID
    as_of: date
    inherent_likelihood: int = Field(ge=1, le=5)
    inherent_impact: int = Field(ge=1, le=5)
    residual_likelihood: int = Field(ge=1, le=5)
    residual_impact: int = Field(ge=1, le=5)
    velocity: Literal["slow", "moderate", "rapid"]
    rationale: Text
    evidence_ids: Evidence = Field(min_length=1)


class KRIObservation(Strict):
    observed_on: date
    value: Money
    evidence_id: uuid.UUID


class KRI(Body):
    owner_id: uuid.UUID
    risk_id: uuid.UUID
    unit: str = Field(min_length=1, max_length=100)
    direction: Literal["above", "below"]
    threshold: Money
    observations: list[KRIObservation] = Field(min_length=1, max_length=1000)


class Control(Body):
    owner_id: uuid.UUID
    universe_id: uuid.UUID
    subprocess: Text
    description: Text
    control_type: Literal[
        "sod",
        "authorization",
        "reconciliation",
        "access",
        "change",
        "physical",
        "application",
        "monitoring",
    ]
    frequency: Literal[
        "per_transaction", "daily", "weekly", "monthly", "quarterly", "annual", "event"
    ]
    approach: Literal["preventive", "detective"]
    operation: Literal["manual", "automated", "hybrid"]
    key_control: bool
    procedure: Text
    framework_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    policy_id: uuid.UUID | None = None


class Link(Body):
    risk_id: uuid.UUID
    control_id: uuid.UUID
    rationale: Text


class TestItem(Strict):
    line_id: uuid.UUID
    outcome: Literal["passed", "exception", "not_provided"]
    evidence_ids: Evidence = Field(default_factory=list)
    comments: Text


class ControlTest(Body):
    owner_id: uuid.UUID
    control_id: uuid.UUID
    test_type: Literal["design", "implementation", "operating", "retest"]
    procedure: Text
    period_start: date
    period_end: date
    sample_run_id: uuid.UUID | None = None
    population_snapshot_id: uuid.UUID | None = None
    results: list[TestItem] = Field(default_factory=list, max_length=1000)
    evidence_ids: Evidence = Field(default_factory=list)
    conclusion: Literal["effective", "ineffective", "inconclusive"]
    rationale: Text
    retests_id: uuid.UUID | None = None


class SoDPair(Strict):
    first: str = Field(min_length=1, max_length=200)
    second: str = Field(min_length=1, max_length=200)
    rationale: Text


class SoDRule(Body):
    system: Text
    version_number: int = Field(ge=1)
    pairs: list[SoDPair] = Field(min_length=1, max_length=100)
    definition_evidence_id: uuid.UUID


class AccessAssignment(Strict):
    principal: str = Field(min_length=1, max_length=200)
    permission: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1, max_length=200)
    valid_from: date
    valid_to: date | None = None


class SoDAccess(Body):
    system: Text
    rule_id: uuid.UUID
    as_of: date
    assignments: list[AccessAssignment] = Field(min_length=1, max_length=10000)
    source_evidence_id: uuid.UUID
    source_hash: str = Field(default="", max_length=64)


class MonitorRule(Body):
    owner_id: uuid.UUID
    rule_key: str = Field(min_length=1, max_length=100)
    version_number: int = Field(ge=1)
    input_kind: Literal["ledger", "workpapers"]
    snapshot_id: uuid.UUID | None = None
    rule_code: str = Field(min_length=1, max_length=100)
    criteria: dict = Field(default_factory=dict)
    decision_rationale: Text
    ml_deployment_id: uuid.UUID | None = None
    ml_family: (
        Literal["autoencoder", "journal-classifier", "risk-ranking", "account-classifier"] | None
    ) = None
    ml_limit: int = Field(default=1000, ge=1, le=10000)
    trigger_on_import: bool = False


class AlertDecision(Body):
    owner_id: uuid.UUID
    alert_id: uuid.UUID
    decision: Literal[
        "assigned", "investigate", "false_positive", "confirmed_exception", "insufficient_evidence"
    ]
    rationale: Text
    evidence_ids: Evidence = Field(default_factory=list)


class Deficiency(Body):
    owner_id: uuid.UUID
    control_id: uuid.UUID
    risk_id: uuid.UUID
    test_id: uuid.UUID
    alert_id: uuid.UUID | None = None
    description: Text
    root_cause_method: Literal[
        "five_whys", "fishbone", "process", "human", "system", "policy", "monitoring"
    ]
    root_cause: Text
    consequence: Text
    severity: Literal["low", "moderate", "high", "critical"]
    severity_methodology: Text
    affected_from: date
    affected_to: date
    evidence_ids: Evidence = Field(min_length=1)


class Remediation(Body):
    owner_id: uuid.UUID
    deficiency_id: uuid.UUID
    corrective_action: Text
    management_response: Text
    target_date: date
    management_status: Literal["planned", "in_progress", "reported_complete"]
    evidence_ids: Evidence = Field(default_factory=list)


class Closure(Body):
    remediation_id: uuid.UUID
    retest_id: uuid.UUID
    conclusion: Text
    evidence_ids: Evidence = Field(min_length=1)


class Obligation(Body):
    owner_id: uuid.UUID
    entity_id: uuid.UUID
    module: Literal[
        "corporate_tax",
        "vat",
        "dmtt",
        "tp",
        "einvoice",
        "ifrs",
        "license",
        "governance",
        "industry",
        "policy",
        "contract",
        "reconciliation",
    ]
    source_url: str = Field(min_length=1, max_length=2000)
    jurisdiction: Text
    effective_from: date
    deadline: date
    required_evidence: Text
    compliance_assessment: Literal["not_assessed", "pending", "exception", "supported"]
    evidence_ids: Evidence = Field(default_factory=list)
    statutory_record_id: uuid.UUID | None = None


class Policy(Body):
    owner_id: uuid.UUID
    version_number: int = Field(ge=1)
    effective_from: date
    review_date: date
    policy_text: str = Field(min_length=20, max_length=12000)
    supersedes_id: uuid.UUID | None = None
    obligation_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class ThirdParty(Body):
    owner_id: uuid.UUID
    name: Text
    vendor_source_key: str = Field(default="", max_length=200)
    services: Text
    criticality: Literal["low", "moderate", "high", "critical"]
    geography: Text
    dependency: Nonnegative
    security_assessment: Text
    renewal_date: date
    sla_exceptions: Text
    evidence_ids: Evidence = Field(min_length=1)


class Report(Body):
    ia_engagement_id: uuid.UUID
    executive_summary: Text
    objective: Text
    scope: Text
    methodology: Text
    overall_assessment: Text
    deficiency_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    recommendations: Text
    management_response: Text
    appendices: Text
    synthetic: bool = False


class BoardPackage(Body):
    report_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    executive_briefing: Text
    authorized_audience: Literal["audit_committee", "board", "both"]
    valid_until: date
    synthetic: bool = False


class QAIP(Body):
    owner_id: uuid.UUID
    framework_id: uuid.UUID
    assessment_type: Literal[
        "ongoing", "periodic_internal", "engagement_quality", "external_request"
    ]
    scheduled_on: date
    conformance_assessment: Text
    findings: Text
    improvement_actions: Text
    training_needs: Text
    evidence_ids: Evidence = Field(min_length=1)
    external_certification_claimed: Literal[False] = False


BODIES: dict[str, type[Body]] = {
    "framework": Framework,
    "universe": Universe,
    "scoring": Scoring,
    "plan": Plan,
    "engagement": IAEngagement,
    "risk": Risk,
    "assessment": Assessment,
    "kri": KRI,
    "control": Control,
    "link": Link,
    "test": ControlTest,
    "sod-rule": SoDRule,
    "sod-access": SoDAccess,
    "monitor-rule": MonitorRule,
    "alert-decision": AlertDecision,
    "deficiency": Deficiency,
    "remediation": Remediation,
    "closure": Closure,
    "obligation": Obligation,
    "policy": Policy,
    "third-party": ThirdParty,
    "report": Report,
    "board": BoardPackage,
    "qaip": QAIP,
}


class ScheduleInput(Strict):
    rule_id: uuid.UUID
    frequency: Literal["daily", "weekly", "monthly", "quarterly"]
    next_due: datetime


class Transition(Strict):
    expected_stage: Literal[
        "DRAFT",
        "PLANNED",
        "APPROVED",
        "FIELDWORK",
        "REVIEW",
        "REPORTING",
        "ISSUED",
        "FOLLOW_UP",
        "CLOSED",
    ]
    next_stage: Literal[
        "DRAFT",
        "PLANNED",
        "APPROVED",
        "FIELDWORK",
        "REVIEW",
        "REPORTING",
        "ISSUED",
        "FOLLOW_UP",
        "CLOSED",
    ]
    rationale: Text
    report_id: uuid.UUID | None = None
