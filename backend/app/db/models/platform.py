import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class Tenant(Record, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(default="active")


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="active")
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    mfa_last_counter: Mapped[int] = mapped_column(default=-1, server_default="-1")


class Membership(Record, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"), UniqueConstraint("tenant_id", "id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(default="active")


class Role(Record, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(unique=True)


class Permission(Record, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(unique=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class MembershipRole(Base):
    __tablename__ = "membership_roles"
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant_memberships.id"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)


class RefreshSession(Record, Base):
    __tablename__ = "refresh_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    mfa_verified: Mapped[bool] = mapped_column(default=False, server_default="false")


class Owned(Record):
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Client(Owned, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("kind IN ('individual','company','group')"),
    )
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(default="company")
    status: Mapped[str] = mapped_column(default="active")
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class LegalEntity(Owned, Base):
    __tablename__ = "legal_entities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        CheckConstraint("length(country) = 2"),
        CheckConstraint("length(functional_currency) = 3 AND length(presentation_currency) = 3"),
    )
    client_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2))
    jurisdiction: Mapped[str] = mapped_column(String(100))
    functional_currency: Mapped[str] = mapped_column(String(3))
    presentation_currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(default="active")
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class EntityRelationship(Owned, Base):
    __tablename__ = "entity_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "child_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        CheckConstraint(
            "parent_id <> child_id AND ownership_percent >= 0 AND ownership_percent <= 100"
        ),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from"),
    )
    parent_id: Mapped[uuid.UUID]
    child_id: Mapped[uuid.UUID]
    ownership_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    effective_from: Mapped[date]
    effective_to: Mapped[date | None]


class FinancialPeriod(Owned, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        UniqueConstraint("tenant_id", "entity_id", "start_date", "end_date"),
        CheckConstraint("end_date >= start_date"),
    )
    entity_id: Mapped[uuid.UUID]
    start_date: Mapped[date]
    end_date: Mapped[date]
    lock_state: Mapped[str] = mapped_column(Text, default="OPEN", server_default="OPEN")
    lock_version: Mapped[int] = mapped_column(default=1, server_default="1")


class Engagement(Owned, Base):
    __tablename__ = "engagements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "period_id"], ["financial_periods.tenant_id", "financial_periods.id"]
        ),
    )
    entity_id: Mapped[uuid.UUID]
    period_id: Mapped[uuid.UUID | None]
    name: Mapped[str] = mapped_column(String(200))
    engagement_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft")
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class EngagementTeamMember(Owned, Base):
    __tablename__ = "engagement_team_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
        ),
        UniqueConstraint("engagement_id", "membership_id"),
    )
    engagement_id: Mapped[uuid.UUID]
    membership_id: Mapped[uuid.UUID]


class AIProviderConfig(Record, Base):
    __tablename__ = "ai_providers"
    name: Mapped[str] = mapped_column(unique=True)
    adapter: Mapped[str]
    credential_reference: Mapped[str | None]


class AIModelConfiguration(Record, Base):
    __tablename__ = "ai_model_configurations"
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_providers.id"))
    name: Mapped[str] = mapped_column(unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    max_tokens: Mapped[int] = mapped_column(default=512)


class PromptTemplate(Record, Base):
    __tablename__ = "ai_prompt_templates"
    __table_args__ = (UniqueConstraint("name", "version"),)
    name: Mapped[str]
    version: Mapped[int]
    content: Mapped[str] = mapped_column(Text)


class AIExecution(Owned, Base):
    __tablename__ = "ai_executions"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_model_configurations.id"))
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_prompt_templates.id"))
    status: Mapped[str] = mapped_column(default="running")
    request_id: Mapped[str]
    duration_ms: Mapped[int | None]
    error_category: Mapped[str | None]


class AIUsageRecord(Owned, Base):
    __tablename__ = "ai_usage_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "execution_id"], ["ai_executions.tenant_id", "ai_executions.id"]
        ),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0"),
    )
    execution_id: Mapped[uuid.UUID]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    usage_source: Mapped[str]


class BackgroundJob(Owned, Base):
    __tablename__ = "background_jobs"
    job_type: Mapped[str] = mapped_column(default="diagnostic", server_default="diagnostic")
    progress: Mapped[int] = mapped_column(default=0, server_default="0")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    result: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_category: Mapped[str | None]


class AuditEvent(Owned, Base):
    __tablename__ = "audit_events"
    action: Mapped[str]
    resource_id: Mapped[uuid.UUID | None]
    request_id: Mapped[str]
    details: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)


class SystemSetting(Record, Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(unique=True)
    value: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"))


Index("ix_audit_tenant_created", AuditEvent.tenant_id, AuditEvent.created_at)

Index("uq_users_email_normalized", func.lower(User.email), unique=True)

UniqueConstraint(
    LegalEntity.tenant_id, LegalEntity.client_id, LegalEntity.id, name="uq_entity_client_scope"
)
UniqueConstraint(
    FinancialPeriod.tenant_id,
    FinancialPeriod.entity_id,
    FinancialPeriod.id,
    name="uq_period_entity_scope",
)
