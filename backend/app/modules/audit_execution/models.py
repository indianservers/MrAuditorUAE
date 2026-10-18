import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class AuditAccess(Owned, Base):
    __tablename__ = "audit_access_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
        ),
        UniqueConstraint("engagement_id", "membership_id", "role_id"),
    )
    engagement_id: Mapped[uuid.UUID]
    membership_id: Mapped[uuid.UUID]
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True)


class RolePolicy(Owned, Base):
    __tablename__ = "audit_role_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "role_id"),)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    permissions: Mapped[list] = mapped_column(JSONB, default=list)


class EngagementPolicy(Owned, Base):
    __tablename__ = "audit_engagement_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        UniqueConstraint("tenant_id", "engagement_id"),
    )
    engagement_id: Mapped[uuid.UUID]
    quality_review_required: Mapped[bool] = mapped_column(default=False)
    review_chain: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["Audit Manager", "Audit Partner"]
    )
    methodology: Mapped[dict] = mapped_column(JSONB, default=dict)


class AuditRecord(Owned, Base):
    """Typed service schemas define record bodies; each update creates an immutable revision."""

    __tablename__ = "audit_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("engagement_id", "kind", "reference"),
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(index=True)
    reference: Mapped[str]
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="IN_PROGRESS", index=True)
    body: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    prepared_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    __mapper_args__ = {"version_id_col": version}


class AuditRevision(Owned, Base):
    __tablename__ = "audit_record_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "record_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
        UniqueConstraint("record_id", "version"),
    )
    record_id: Mapped[uuid.UUID]
    version: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSONB)


class ReviewDecision(Owned, Base):
    __tablename__ = "audit_review_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "record_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
        UniqueConstraint("record_id", "version", "stage", "decision"),
    )
    record_id: Mapped[uuid.UUID]
    version: Mapped[int]
    stage: Mapped[int]
    decision: Mapped[str]
    comments: Mapped[str]
    prior_status: Mapped[str]


class EvidenceVersion(Owned, Base):
    __tablename__ = "audit_evidence_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "record_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
        UniqueConstraint("record_id", "number"),
    )
    record_id: Mapped[uuid.UUID]
    number: Mapped[int]
    filename: Mapped[str]
    media_type: Mapped[str]
    object_key: Mapped[str]
    object_version: Mapped[str]
    sha256: Mapped[str]
    size: Mapped[int]
    scan_status: Mapped[str] = mapped_column(default="QUARANTINED")


class ClientAccess(Owned, Base):
    __tablename__ = "audit_client_access"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
        ),
        UniqueConstraint("tenant_id", "client_id", "membership_id"),
    )
    client_id: Mapped[uuid.UUID]
    membership_id: Mapped[uuid.UUID]
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditInvitation(Owned, Base):
    __tablename__ = "audit_invitations"
    email: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True)
    role_ids: Mapped[list] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(default=False)


class MethodologyVersion(Owned, Base):
    __tablename__ = "audit_methodology_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "name", "version"),)
    name: Mapped[str]
    version: Mapped[int]
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    profile: Mapped[dict] = mapped_column(JSONB)
