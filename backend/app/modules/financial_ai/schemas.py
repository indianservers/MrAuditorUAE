import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.accounting.schemas import SnapshotRequest


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1, max_length=4000)
    citations: list[uuid.UUID] = Field(min_length=1, max_length=20)
    requires_review: Literal[True]


class Classification(Suggestion):
    proposed_classification: Literal[
        "Assets", "Liabilities", "Equity", "Income", "Expenses", "Unclassified"
    ]
    statement_group: str = Field(max_length=100)
    confidence: Literal["low", "moderate", "high"]


class AnomalyExplanation(Suggestion):
    potential_issues: list[str] = Field(max_length=10)
    verification_steps: list[str] = Field(max_length=10)
    evidence_requirements: list[str] = Field(max_length=10)


class AuditProcedures(Suggestion):
    suggested_tests: list[str] = Field(max_length=10)
    evidence_requests: list[str] = Field(max_length=10)
    assertions: list[str] = Field(max_length=10)
    reviewer_notes: str = Field(max_length=1000)


class Commentary(Suggestion):
    causation_established: Literal[False]
    investigation_areas: list[str] = Field(max_length=10)
    management_questions: list[str] = Field(max_length=10)


class FinancialRequest(SnapshotRequest):
    model: str = "mock-diagnostic"
    account_id: uuid.UUID | None = None
    line_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    analytics_run_id: uuid.UUID | None = None
    prior_snapshot_id: uuid.UUID | None = None
    assertions: list[str] = Field(default_factory=list, max_length=10)


class GatewayInput(BaseModel):
    text: str = Field(max_length=12000)


class FinancialGatewayRequest(BaseModel):
    task_type: Literal[
        "account_classification", "anomaly_explanation", "audit_procedures", "financial_commentary"
    ]
    input: GatewayInput
    model: str


OUTPUTS: dict[str, type[Suggestion]] = {
    "account_classification": Classification,
    "anomaly_explanation": AnomalyExplanation,
    "audit_procedures": AuditProcedures,
    "financial_commentary": Commentary,
}
