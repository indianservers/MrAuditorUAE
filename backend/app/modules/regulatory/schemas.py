import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, model_validator

from app.modules.jurisdictions.profiles import Strict

Fact = Annotated[str, Field(max_length=4000)] | bool | int | None


class Citation(Strict):
    authority: str = Field(min_length=2, max_length=200)
    legislation: str = Field(min_length=2, max_length=300)
    url: HttpUrl
    paragraph: str = Field(min_length=1, max_length=200)
    document_sha256: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    retrieved_on: date | None = None
    retrieval_status: Literal["AWAITING_VALIDATION", "RETRIEVED"] = "AWAITING_VALIDATION"


class Predicate(Strict):
    field: str = Field(pattern="^[a-z][a-z0-9_]{0,79}$")
    operator: Literal["equals", "in", "gte", "gt", "lte", "lt"]
    values: list[Annotated[str, Field(max_length=300)]] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def valid_operand(self):
        if self.operator != "in" and len(self.values) != 1:
            raise ValueError("This predicate requires exactly one comparison value")
        if self.operator in {"gte", "gt", "lte", "lt"}:
            from decimal import InvalidOperation

            try:
                if not Decimal(self.values[0]).is_finite():
                    raise ValueError("Non-finite predicate threshold")
            except InvalidOperation:
                raise ValueError("Invalid predicate threshold") from None
        return self


class Rule(Strict):
    rule_key: str = Field(pattern="^[A-Z]{2}-[A-Z0-9-]{2,100}$")
    country: str = Field(pattern="^[A-Z]{2}$")
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=10, max_length=6000)
    framework: str = Field(min_length=2, max_length=100)
    source_category: Literal["legislation", "official_guidance", "accounting_requirement", "firm_policy", "reviewer_judgment"] | None = None
    publication_date: date | None = None
    topic: str | None = Field(default=None, max_length=200)
    implementation_reference: str | None = Field(default=None, max_length=300)
    period_basis: Literal["period_start", "period_end", "transaction_date"]
    effective_from: date
    effective_to: date | None = None
    citations: list[Citation] = Field(min_length=1, max_length=20)
    applicability: list[Predicate] = Field(default_factory=list, max_length=50)
    input_requirements: list[str] = Field(min_length=1, max_length=50)
    output_requirements: list[str] = Field(min_length=1, max_length=50)
    exceptions_and_elections: list[str] = Field(default_factory=list, max_length=50)
    method: Literal["checklist", "flat_rate"] = "checklist"
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=18, decimal_places=12)
    validation_status: Literal["AWAITING_VALIDATION", "VALIDATED"] = "AWAITING_VALIDATION"
    professional_review_status: Literal["PENDING", "REVIEWED"] = "PENDING"
    last_reviewed: date | None = None
    amendment_reason: str = Field(min_length=10, max_length=4000)
    expected_sequence: int = Field(ge=0)
    reverts_version_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def coherent(self):
        if not self.rule_key.startswith(self.country + "-"):
            raise ValueError("Rule key and country differ")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Effective dates reversed")
        if (self.method == "flat_rate") != (self.rate is not None):
            raise ValueError("A flat-rate method requires an explicit reviewed rate only")
        if self.method == "flat_rate" and "tax_base" not in self.input_requirements:
            raise ValueError("A flat-rate calculation requires tax_base")
        return self


class Decision(Strict):
    action: Literal["approve", "reject", "publish"]
    expected_sequence: int = Field(ge=1)
    comments: str = Field(min_length=10, max_length=4000)


class FactSource(Strict):
    kind: Literal["record", "intelligence"]
    id: uuid.UUID
    path: list[Annotated[str, Field(max_length=100)] | int] = Field(min_length=1, max_length=8)


class Assessment(Strict):
    rule_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    facts: dict[str, Fact] = Field(max_length=100)
    transaction_date: date | None = None
    source_event_id: uuid.UUID | None = None
    fact_sources: dict[str, FactSource] = Field(default_factory=dict, max_length=100)
    rationale: str = Field(min_length=10, max_length=4000)


class ChecklistItem(Strict):
    clause: str = Field(min_length=1, max_length=100)
    rule_id: uuid.UUID
    state: Literal[
        "APPLICABLE",
        "NOT_APPLICABLE",
        "PENDING",
        "EVIDENCE_REQUIRED",
        "EXCEPTION_IDENTIFIED",
        "PREPARED",
    ]
    facts: dict[str, Fact] = Field(max_length=100)
    fact_sources: dict[str, FactSource] = Field(default_factory=dict, max_length=20)
    procedure: str = Field(default="", max_length=6000)
    conclusion: str = Field(default="", max_length=6000)
    management_response: str = Field(default="", max_length=6000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)


class Checklist(Strict):
    area: Literal[
        "companies-act",
        "caro",
        "india-tax-audit",
        "india-disclosures",
        "uae-disclosures",
        "qfzp-assessment",
        "dmtt-applicability",
        "group-audit",
    ]
    title: str = Field(min_length=3, max_length=300)
    items: list[ChecklistItem] = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=10, max_length=4000)
    prior_id: uuid.UUID | None = None
    expected_version: int = Field(default=0, ge=0)


class IndiaStatements(Strict):
    snapshot_id: uuid.UUID
    mapping_profile_id: uuid.UUID
    applicability_id: uuid.UUID
    division: Literal["I", "II", "III"]
    comparative_snapshot_id: uuid.UUID | None = None
    rationale: str = Field(min_length=10, max_length=4000)


class ReportBlock(Strict):
    key: str = Field(pattern="^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=200)
    kind: Literal[
        "financial_table",
        "comparative_table",
        "regulatory_checklist",
        "disclosure",
        "reconciliation",
        "analysis",
        "graph",
        "findings_summary",
        "narrative",
        "working_paper_reference",
        "audit_conclusion",
    ]
    source_kind: Literal["record", "intelligence"] | None = None
    source_id: uuid.UUID | None = None
    text: str = Field(default="", max_length=6000)
    calculation_module: Literal["ifrs", "tax", "vat", "tp"] | None = None
    calculation_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def source_contract(self):
        if bool(self.source_kind) != bool(self.source_id) or bool(self.calculation_module) != bool(
            self.calculation_id
        ):
            raise ValueError("Source and calculation identifiers must be paired")
        if self.kind != "narrative" and not self.source_id:
            raise ValueError("A source reference is required for non-narrative content")
        if self.calculation_id and self.source_kind != "record":
            raise ValueError("Calculations require their approved audit release record")
        return self


class ReportTemplate(Strict):
    title: str = Field(min_length=3, max_length=300)
    category: Literal[
        "india-statutory",
        "caro",
        "schedule-iii",
        "india-tax-audit",
        "uae-ifrs",
        "uae-ct",
        "vat",
        "tp-local",
        "tp-master",
        "dmtt",
        "group-audit",
        "consolidation",
        "internal-audit",
        "management-letter",
        "audit-committee",
    ]
    blocks: list[ReportBlock] = Field(min_length=1, max_length=50)
    rationale: str = Field(min_length=10, max_length=4000)
    prior_id: uuid.UUID | None = None
    expected_version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({b.key for b in self.blocks}) != len(self.blocks):
            raise ValueError("Report block identifiers must be unique")
        return self


class ReportGenerate(Strict):
    template_id: uuid.UUID
    rationale: str = Field(min_length=10, max_length=4000)
