import uuid

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class IntelligenceEvent(Owned, Base):
    __tablename__ = "audit_intelligence_events"
    __table_args__ = (
        Index(
            "ix_audit_intelligence_events_engagement", "tenant_id", "engagement_id", "created_at"
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "root_id", "version"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID]
    root_id: Mapped[uuid.UUID]
    version: Mapped[int]
    kind: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    sha256: Mapped[str]


class IntelligenceJob(Owned, Base):
    __tablename__ = "audit_intelligence_jobs"
    __table_args__ = (
        Index("ix_audit_intelligence_jobs_engagement", "tenant_id", "engagement_id", "created_at"),
        UniqueConstraint("tenant_id", "created_by", "idempotency_key"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID]
    idempotency_key: Mapped[str]
    operation: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_sha256: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    progress: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=1)
    result_id: Mapped[uuid.UUID | None]
    error_category: Mapped[str | None]
    error_details: Mapped[dict | None] = mapped_column(JSONB)
    __mapper_args__ = {"version_id_col": version}
