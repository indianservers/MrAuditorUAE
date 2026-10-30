import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from app.modules.audit_execution.schemas import Body, Strict
from app.modules.grc.deadlines import DeadlineRule
from app.modules.grc.deadlines import calculate as calculate_deadline

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Nonnegative = Annotated[Money, Field(ge=0)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Evidence = Annotated[list[uuid.UUID], Field(max_length=50)]


def calendar_date(value):
    if type(value) is date or isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    raise ValueError("Use an explicit ISO calendar date; timestamps and timezones are not inferred")


SoDDate = Annotated[date, BeforeValidator(calendar_date)]


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

    @model_validator(mode="after")
    def exact_pair(self):
        if self.first == self.second or any(
            not value.strip() or value != value.strip() or any(c in value for c in "\r\n\t\0")
            for value in (self.first, self.second)
        ):
            raise ValueError("SoD pairs require distinct exact permission identifiers")
        return self


class ScopeOverlap(Strict):
    first_scope: str = Field(min_length=1, max_length=200)
    second_scope: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=10, max_length=4000)
    evidence_reference: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def explicit_relation(self):
        if self.first_scope == self.second_scope or any(
            not value.strip() or value != value.strip() or any(c in value for c in "\r\n\t\0")
            for value in (self.first_scope, self.second_scope)
        ):
            raise ValueError("Declare distinct exact scopes; identical scopes already overlap")
        if len(self.rationale.strip()) < 10 or not self.evidence_reference.strip():
            raise ValueError(
                "Scope overlap needs its independently reviewed rationale and definition reference"
            )
        return self


class SoDRule(Body):
    system: Text
    version_number: int = Field(ge=1)
    pairs: list[SoDPair] = Field(min_length=1, max_length=100)
    definition_evidence_id: uuid.UUID
    effective_from: SoDDate | None = None
    effective_to: SoDDate | None = None
    scope_mode: Literal["exact", "reviewed-overlap"] = "exact"
    scope_overlaps: list[ScopeOverlap] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def scope_policy(self):
        if self.effective_to is not None and (
            self.effective_from is None or self.effective_to < self.effective_from
        ):
            raise ValueError(
                "SoD definition effective dates must be ordered and identify their start"
            )
        if self.scope_mode == "reviewed-overlap" and self.effective_from is None:
            raise ValueError("Reviewed overlap policies must identify their effective date")

        pairs = [frozenset((pair.first, pair.second)) for pair in self.pairs]
        overlaps = [
            frozenset((item.first_scope, item.second_scope)) for item in self.scope_overlaps
        ]
        if len(set(pairs)) != len(pairs) or len(set(overlaps)) != len(overlaps):
            raise ValueError(
                "Duplicate or reversed SoD permission/scope pairs are not separate rules"
            )
        if (self.scope_mode == "exact" and self.scope_overlaps) or (
            self.scope_mode == "reviewed-overlap" and not self.scope_overlaps
        ):
            raise ValueError(
                "Reviewed overlap mode needs explicit mappings; exact mode cannot silently ignore them"
            )
        return self


class AccessAssignment(Strict):
    principal: str = Field(min_length=1, max_length=200)
    permission: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1, max_length=200)
    valid_from: SoDDate
    valid_to: SoDDate | None = None

    @model_validator(mode="after")
    def exact_assignment(self):
        if any(
            not value.strip() or value != value.strip() or any(c in value for c in "\r\n\t\0")
            for value in (self.principal, self.permission, self.scope)
        ):
            raise ValueError("Access principals, permissions and scopes require exact identifiers")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("Access validity end precedes start")
        return self


class SoDAccess(Body):
    system: Text
    rule_id: uuid.UUID
    as_of: SoDDate
    assignments: list[AccessAssignment] = Field(min_length=1, max_length=10000)
    source_evidence_id: uuid.UUID
    source_hash: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    period_start: SoDDate | None = None
    population_basis: Literal["point-in-time-export", "validity-history"] = "point-in-time-export"
    coverage_start: SoDDate | None = None
    coverage_end: SoDDate | None = None
    history_scope_assessment: str = Field(default="", max_length=4000)
    expected_assignment_count: int | None = Field(default=None, ge=1, le=10000, strict=True)
    expected_principal_count: int | None = Field(default=None, ge=1, le=10000, strict=True)
    population_control_evidence_id: uuid.UUID | None = None
    population_control_reference: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def analysis_scope(self):
        identities = [
            (item.principal, item.permission, item.scope, item.valid_from, item.valid_to)
            for item in self.assignments
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate access assignments must not multiply conflict evidence")
        if self.period_start is not None and (
            self.period_start > self.as_of or self.population_basis != "validity-history"
        ):
            raise ValueError(
                "Period analysis requires validity history and a start on or before assessment date"
            )
        controls = (
            self.expected_assignment_count,
            self.expected_principal_count,
            self.population_control_evidence_id,
            bool(self.population_control_reference),
        )
        if any(value is not None and value is not False for value in controls):
            if not all(controls) or len(self.population_control_reference.strip()) < 10:
                raise ValueError(
                    "Declare both independent access counts and their separate approved control evidence/reference"
                )
            if self.population_control_evidence_id == self.source_evidence_id:
                raise ValueError(
                    "Independent access controls must be separate from the assignment CSV"
                )
            if self.expected_assignment_count != len(
                self.assignments
            ) or self.expected_principal_count != len(
                {item.principal for item in self.assignments}
            ):
                raise ValueError("Independent access assignment/principal counts do not agree")
        if self.population_basis == "validity-history":
            if (
                self.coverage_start is None
                or self.coverage_end is None
                or not self.coverage_start
                <= (self.period_start or self.as_of)
                <= self.as_of
                <= self.coverage_end
                or len(self.history_scope_assessment.strip()) < 10
                or not all(controls)
                or not self.source_hash
            ):
                raise ValueError(
                    "Validity history requires hashed CSV, declared full coverage, scope assessment and independent population controls"
                )
        elif (
            self.coverage_start is not None
            or self.coverage_end is not None
            or self.history_scope_assessment
        ):
            raise ValueError(
                "History coverage applies only to a declared validity-history population"
            )
        return self


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


class ObligationJurisdictionScope(Strict):
    """Explicitly assessed country relationship; never inferred legal applicability."""

    entity_country: str = Field(pattern=r"^[A-Z]{2}$")
    obligation_country: str = Field(pattern=r"^[A-Z]{2}$")
    relationship: Literal["domestic", "foreign"]
    applicability: Literal["potential", "assessed_applicable", "assessed_not_applicable"]
    registration_reference: str = Field(default="", max_length=200)
    assessment: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def exact_scope(self):
        expected = "domestic" if self.entity_country == self.obligation_country else "foreign"
        if self.relationship != expected:
            raise ValueError("Obligation relationship must agree with the two declared countries")
        if len(self.assessment.strip()) < 10 or self.assessment != self.assessment.strip():
            raise ValueError("Retain an explicit exact country applicability assessment")
        if self.registration_reference != self.registration_reference.strip():
            raise ValueError(
                "Retain the exact registration reference without surrounding whitespace"
            )
        return self


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
    jurisdiction_scope: ObligationJurisdictionScope | None = None
    obligation_period_start: Annotated[date, BeforeValidator(calendar_date)] | None = None
    obligation_period_end: Annotated[date, BeforeValidator(calendar_date)] | None = None
    effective_from: date
    deadline: date | None = None
    deadline_kind: Literal[
        "legal", "authority_extension", "client_agreed", "firm_internal", "unresolved"
    ] = "unresolved"
    deadline_rule: DeadlineRule | None = None
    rule_evidence_id: uuid.UUID | None = None
    calendar_evidence_id: uuid.UUID | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    extension_deadline: date | None = None
    extension_evidence_id: uuid.UUID | None = None
    entity_facts: dict[str, str] = Field(default_factory=dict, max_length=30)
    fact_evidence_ids: Evidence = Field(default_factory=list)
    reviewer_id: uuid.UUID | None = None
    filing_stage: Literal[
        "not_started",
        "preparing",
        "under_review",
        "approved_for_submission",
        "submitted",
        "acknowledged",
    ] = "not_started"
    readiness_evidence_ids: Evidence = Field(default_factory=list)
    submission_evidence_id: uuid.UUID | None = None
    acknowledgment_evidence_id: uuid.UUID | None = None
    blockers: list[Text] = Field(default_factory=list, max_length=100)
    reminder_days: list[int] = Field(default_factory=list, max_length=20)
    notifications_enabled: bool = False
    escalation_after_days: int | None = Field(default=None, ge=1, le=365)
    required_evidence: Text
    compliance_assessment: Literal["not_assessed", "pending", "exception", "supported"]
    evidence_ids: Evidence = Field(default_factory=list)
    statutory_record_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def filing_contract(self):
        if (self.obligation_period_start is None) != (self.obligation_period_end is None):
            raise ValueError("Retain both obligation period dates, or neither")
        if self.obligation_period_start is not None:
            if self.jurisdiction_scope is None:
                raise ValueError("An explicit obligation period requires assessed country scope")
            assert self.obligation_period_end is not None
            if self.obligation_period_end < self.obligation_period_start:
                raise ValueError("Obligation period end cannot precede its start")
        if self.jurisdiction_scope:
            if (
                self.deadline_rule
                and self.deadline_rule.date_basis == "period_end"
                and self.obligation_period_end is None
            ):
                raise ValueError(
                    "Country-scoped period-end rules require an explicit obligation period"
                )
            scope = self.jurisdiction_scope
            if self.jurisdiction != scope.obligation_country:
                raise ValueError(
                    "Structured obligation jurisdiction must equal its obligation country"
                )
            if not self.rule_evidence_id or not self.fact_evidence_ids or not self.entity_facts:
                raise ValueError(
                    "Structured country scope requires separate rule and entity-fact evidence"
                )
            if self.rule_evidence_id in self.fact_evidence_ids:
                raise ValueError("Rule and entity-fact evidence must be separate records")
            if scope.applicability != "assessed_applicable" and (
                self.filing_stage in {"approved_for_submission", "submitted", "acknowledged"}
                or self.compliance_assessment == "supported"
            ):
                raise ValueError(
                    "Unassessed or inapplicable country scope cannot support a filing approval"
                )
        if any(day < 0 or day > 365 for day in self.reminder_days) or len(
            set(self.reminder_days)
        ) != len(self.reminder_days):
            raise ValueError("Reminder offsets must be unique days from 0 through 365")
        if self.deadline_rule:
            if not self.rule_evidence_id:
                raise ValueError("Verified rule evidence required for calculated deadline")
            computed = calculate_deadline(self.deadline_rule)
            if self.deadline is not None and self.deadline != computed:
                raise ValueError("Declared deadline differs from versioned calculation")
            self.deadline = computed
        business_days = self.deadline_rule and self.deadline_rule.day_count_basis == "business"
        if business_days and (
            not self.calendar_evidence_id or self.calendar_evidence_id == self.rule_evidence_id
        ):
            raise ValueError("Business-day deadlines require separate retained calendar evidence")
        if self.calendar_evidence_id and not business_days:
            raise ValueError("Calendar evidence belongs to an explicit business-day deadline")
        if self.extension_deadline and (
            not self.extension_evidence_id
            or not self.deadline
            or self.extension_deadline < self.deadline
        ):
            raise ValueError("Extension requires base deadline and separate authority evidence")
        if self.deadline_kind == "authority_extension" and not self.extension_deadline:
            raise ValueError("Authority extension evidence and date required")
        if self.deadline_kind == "legal" and not self.rule_evidence_id:
            raise ValueError("Legal deadline requires verified supporting rule evidence")
        if self.filing_stage in {"approved_for_submission", "submitted", "acknowledged"}:
            if (
                self.blockers
                or not self.deadline
                or not self.reviewer_id
                or not self.readiness_evidence_ids
            ):
                raise ValueError(
                    "Resolved deadline, independent reviewer and readiness evidence without blockers required"
                )
        if self.filing_stage in {"submitted", "acknowledged"} and not self.submission_evidence_id:
            raise ValueError(
                "Actual submission evidence required; generated exports are not submissions"
            )
        if self.filing_stage == "acknowledged" and not self.acknowledgment_evidence_id:
            raise ValueError("Separate acknowledgment evidence required")
        if (
            self.submission_evidence_id
            and self.submission_evidence_id == self.acknowledgment_evidence_id
        ):
            raise ValueError("Submission and acknowledgment must be separate evidence")
        return self


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
