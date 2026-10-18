import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class AIScope(Owned):
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)


class Workflow(AIScope, Base):
    __tablename__ = "ai_workflow_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "created_by", "idempotency_key"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    idempotency_key: Mapped[str]
    task: Mapped[str]
    prompt: Mapped[str]
    state: Mapped[str] = mapped_column(default="CREATED", index=True)
    plan: Mapped[list] = mapped_column(JSONB)
    inputs: Mapped[dict] = mapped_column(JSONB)
    outputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class Event(AIScope, Base):
    __tablename__ = "ai_workflow_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("run_id", "key"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["ai_workflow_runs.tenant_id", "ai_workflow_runs.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    run_id: Mapped[uuid.UUID]
    key: Mapped[str]
    kind: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]


class Extraction(AIScope, Base):
    __tablename__ = "ai_document_extractions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "record_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    record_id: Mapped[uuid.UUID]
    evidence_version_id: Mapped[uuid.UUID]
    record_version: Mapped[int]
    parent_id: Mapped[uuid.UUID | None]
    source_hash: Mapped[str]
    classification: Mapped[str]
    confidentiality: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)


class Chunk(AIScope, Base):
    __tablename__ = "ai_document_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "extraction_id"],
            ["ai_document_extractions.tenant_id", "ai_document_extractions.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(index=True)
    page: Mapped[int]
    section: Mapped[str]
    text: Mapped[str]
    metadata_details: Mapped[dict] = mapped_column(JSONB)


class Proposal(AIScope, Base):
    __tablename__ = "ai_approval_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["ai_workflow_runs.tenant_id", "ai_workflow_runs.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    run_id: Mapped[uuid.UUID]
    action: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    payload_hash: Mapped[str]
    state: Mapped[str] = mapped_column(default="AWAITING_APPROVAL")
    decision: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class Schedule(AIScope, Base):
    __tablename__ = "ai_scheduled_workflows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    task: Mapped[str]
    frequency: Mapped[str]
    active: Mapped[bool] = mapped_column(default=False)
    next_due: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    inputs: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class MatchDecision(AIScope, Base):
    __tablename__ = "ai_document_match_decisions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "created_by", "payload_hash"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "extraction_id"],
            ["ai_document_extractions.tenant_id", "ai_document_extractions.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "journal_id"], ["journal_lines.tenant_id", "journal_lines.id"]
        ),
    )
    extraction_id: Mapped[uuid.UUID]
    journal_id: Mapped[uuid.UUID]
    payload_hash: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)
