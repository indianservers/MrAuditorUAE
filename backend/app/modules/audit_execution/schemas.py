import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.audit_execution.catalogue import ASSERTIONS


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    kind: Literal["record", "finding", "journal", "snapshot", "sample", "intelligence", "ml"]
    id: uuid.UUID


class Body(Strict):
    narrative: str = Field(default="", max_length=12000)
    sources: list[Source] = Field(default_factory=list, max_length=100)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    area: str = Field(default="", max_length=200)
    assertions: list[str] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def known_assertions(self):
        if not set(self.assertions) <= set(ASSERTIONS):
            raise ValueError("Unsupported assertion")
        return self


class Acceptance(Body):
    background: str = Field(min_length=1, max_length=4000)
    ownership: str = Field(min_length=1, max_length=4000)
    operations: str = Field(min_length=1, max_length=4000)
    ethics: str = Field(min_length=1, max_length=4000)
    conflicts: str = Field(min_length=1, max_length=4000)
    management_integrity: str = Field(min_length=1, max_length=4000)
    capability: str = Field(min_length=1, max_length=4000)
    staffing: str = Field(min_length=1, max_length=4000)
    previous_auditor: str = Field(min_length=1, max_length=4000)
    scope_and_terms: str = Field(min_length=1, max_length=4000)


class Independence(Body):
    financial_interests: bool
    relationships: bool
    other_services: bool
    threats: str = Field(min_length=1, max_length=4000)
    safeguards: str = Field(min_length=1, max_length=4000)
    expires_on: date


class Planning(Body):
    strategy: str = Field(min_length=1, max_length=6000)
    scope: str = Field(min_length=1, max_length=4000)
    timetable: str = Field(min_length=1, max_length=4000)
    methodology_version: str = Field(min_length=1, max_length=100)
    standards_edition: str = Field(min_length=1, max_length=200)


class Materiality(Body):
    benchmark: Literal["profit_before_tax", "revenue", "assets", "equity", "expenses", "other"]
    benchmark_amount: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    selected_percentage: Decimal = Field(gt=0, le=100, decimal_places=6)
    performance_percentage: Decimal = Field(gt=0, le=100, decimal_places=6)
    trivial_percentage: Decimal = Field(gt=0, le=100, decimal_places=6)
    benchmark_source: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    effective_date: date
    specific_materiality: Decimal | None = Field(
        default=None, gt=0, max_digits=28, decimal_places=8
    )

    @model_validator(mode="after")
    def thresholds(self):
        if self.trivial_percentage >= self.performance_percentage:
            raise ValueError("Trivial threshold must be below performance materiality")
        return self


class Risk(Body):
    level: Literal[
        "financial_statement", "assertion", "account_balance", "transaction_class", "disclosure"
    ]
    inherent_risk: Literal["low", "moderate", "high"]
    control_risk: Literal["low", "moderate", "high", "not_assessed"]
    significant: bool = False
    fraud: bool = False
    response: str = Field(min_length=1, max_length=4000)


class Program(Body):
    methodology_version: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=4000)


class Procedure(Program):
    required_evidence: str = Field(min_length=1, max_length=4000)
    instructions: str = Field(min_length=1, max_length=4000)
    procedure_type: Literal[
        "details",
        "controls",
        "analytical",
        "cutoff",
        "confirmation",
        "subsequent_settlement",
        "unrecorded_liabilities",
        "inventory_observation",
        "subsequent_events",
    ] = "details"
    risk_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    account_codes: list[str] = Field(default_factory=list, max_length=1000)
    reliance_on_controls: str = Field(default="", max_length=4000)
    scope_exclusions: str = Field(default="", max_length=4000)


class TestItem(Strict):
    line_id: uuid.UUID
    outcome: Literal["passed", "exception", "not_tested"]
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    observations: str = Field(min_length=1, max_length=4000)


class Testing(Body):
    sample_id: uuid.UUID
    population_completeness: str = Field(min_length=1, max_length=4000)
    reconciliation: str = Field(min_length=1, max_length=4000)
    methodology_rationale: str = Field(min_length=1, max_length=4000)
    results: list[TestItem] = Field(default_factory=list, max_length=1000)
    exceptions: str = Field(default="", max_length=4000)
    conclusion: str = Field(min_length=1, max_length=4000)
    procedure_id: uuid.UUID | None = None
    steps_performed: str = Field(default="", max_length=8000)
    evaluation_basis: Literal["nonstatistical", "targeted", "full_population", "statistical"] = (
        "nonstatistical"
    )
    projected_misstatement: Decimal | None = Field(default=None, max_digits=28, decimal_places=8)


class Section(Strict):
    heading: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=12000)


class WorkingPaper(Body):
    factual_findings_only: bool = False
    inherit_source_permissions: bool = False
    advanced_input: dict | None = None

    @model_validator(mode="after")
    def advanced_contract(self):
        if self.advanced_input is not None:
            from app.modules.jurisdictions.ae.advanced import Schedule
            schedule = Schedule.model_validate(self.advanced_input)
            linked = {str(s.id) for s in self.sources if s.kind == "record"}
            required = {str(schedule.policy.source_id), *(r["evidence_id"] for r in schedule.rows)}
            required.update(str(value) for row in schedule.rows for key,value in row.items() if key.endswith("_source_id"))
            if not required <= linked:
                raise ValueError("Every schedule row and adopted policy must link to a source record")
            required.update(str(v) for row in schedule.rows for key in ("supporting_sources","contrary_sources") for v in row.get(key,[]))
            if not required <= linked:
                raise ValueError("Every assertion support/contrary source must be a protected source link")
            if schedule.use_case_id==198:self.factual_findings_only=True
            self.advanced_input = schedule.model_dump(mode="json")
            self.inherit_source_permissions = True
        if self.factual_findings_only:
            self.conclusion="Agreed-upon procedures factual findings only; no audit opinion or assurance conclusion."
        return self
    folder: str = Field(min_length=1, max_length=200)
    sections: list[Section] = Field(min_length=1, max_length=30)
    financial_tables: list[dict] = Field(default_factory=list, max_length=10)
    conclusion: str = Field(min_length=1, max_length=6000)


class Evidence(Body):
    category: str = Field(min_length=1, max_length=100)
    retain_until: date


class Finding(Body):
    condition: str = Field(default="", max_length=4000)
    criteria: str = Field(default="", max_length=4000)
    cause: str = Field(default="", max_length=4000)
    effect: str = Field(default="", max_length=4000)
    recommendation: str = Field(default="", max_length=4000)
    finding_type: Literal[
        "misstatement",
        "control_deficiency",
        "missing_evidence",
        "estimate",
        "reconciliation",
        "unusual_journal",
        "disclosure",
        "related_party",
        "compliance",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    financial_impact: Decimal | None = Field(default=None, max_digits=28, decimal_places=8)
    management_response: str = Field(default="", max_length=4000)
    correction_status: Literal["not_applicable", "uncorrected", "corrected"] = "not_applicable"
    qualitative_considerations: str = Field(default="", max_length=4000)
    follow_up: str = Field(default="", max_length=4000)
    correction_evidence_id: uuid.UUID | None = None


class ReviewNote(Body):
    target_id: uuid.UUID
    assigned_reviewer: uuid.UUID


class Completion(Body):
    subsequent_events: str = Field(min_length=1, max_length=4000)
    going_concern: str = Field(min_length=1, max_length=4000)
    unadjusted_misstatements: str = Field(min_length=1, max_length=4000)
    human_evidence_assessment: str = Field(min_length=1, max_length=6000)


class DocumentRequest(Body):
    client_id: uuid.UUID
    question: str = Field(min_length=1, max_length=4000)
    response: str = Field(default="", max_length=6000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)


class AISuggestion(Body):
    task: str
    output: dict
    execution_id: uuid.UUID


BODIES: dict[str, type[Body]] = {
    "acceptance": Acceptance,
    "independence": Independence,
    "planning": Planning,
    "materiality": Materiality,
    "risks": Risk,
    "programs": Program,
    "procedures": Procedure,
    "testing": Testing,
    "working-papers": WorkingPaper,
    "evidence": Evidence,
    "findings": Finding,
    "review-notes": ReviewNote,
    "completion": Completion,
    "requests": DocumentRequest,
    "ai": AISuggestion,
}


class RecordInput(Strict):
    reference: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    body: dict


class RecordPatch(RecordInput):
    version: int = Field(ge=1)


class Action(Strict):
    version: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=50)
    comments: str = Field(min_length=1, max_length=4000)


class Grant(Strict):
    membership_id: uuid.UUID
    role_id: uuid.UUID
    expires_at: datetime | None = None
    active: bool = True


class PolicyInput(Strict):
    quality_review_required: bool = False
    review_chain: list[str] = Field(min_length=1, max_length=5)
    methodology: dict = Field(default_factory=dict)
