"""Versioned contracts shared by deterministic engines; completeness is explicit."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EngineIssue(Contract):
    code: Literal[
        "invalid_input",
        "missing_evidence",
        "unverified_rule",
        "permission_denied",
        "unsupported_jurisdiction",
        "stale_source_data",
        "dependency_unavailable",
        "incompatible_schema",
    ]
    reason: str
    severity: Literal["info", "warning", "error"] = "error"
    blocking: bool = True
    affected_records: list[str] = Field(default_factory=list)
    remediation: str
    owner: str | None = None
    disposition: Literal["open", "resolved", "accepted"] = "open"
    url: str | None = None


class EngineResult(Contract):
    schema_version: Literal["foundation/1"] = "foundation/1"
    execution_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    entity_id: uuid.UUID
    engagement_id: uuid.UUID
    period_id: uuid.UUID
    jurisdiction: str
    framework: str
    calculation_version: str
    execution_mode: Literal[
        "deterministic",
        "trained_model",
        "statistical_baseline",
        "rules_baseline",
        "diagnostic_mock",
        "unavailable",
    ] = "deterministic"
    execution_status: Literal["succeeded", "failed"] = "succeeded"
    completeness: Literal["complete", "partial", "unknown"] = "unknown"
    review_status: Literal["UNVERIFIED", "PREPARED", "REVIEWED", "REJECTED"] = "UNVERIFIED"
    issues: list[EngineIssue] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence_references: list[dict] = Field(default_factory=list)
    results: dict = Field(default_factory=dict)
