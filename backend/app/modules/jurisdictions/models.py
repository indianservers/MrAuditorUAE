import uuid

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class CountryPreference(Owned, Base):
    __tablename__ = "country_preferences"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    country: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class EngagementJurisdiction(Owned, Base):
    __tablename__ = "engagement_jurisdictions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "engagement_id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID]
    country: Mapped[str]
    package_version: Mapped[str]
    package_sha256: Mapped[str]
    manifest: Mapped[dict] = mapped_column(JSONB)


class OrganizationJurisdiction(Owned, Base):
    __tablename__ = "organization_jurisdictions"
    __table_args__ = (UniqueConstraint("tenant_id"),)
    country: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class ReportingContextEvent(Owned, Base):
    __tablename__ = "reporting_context_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)


class GraphLayout(Owned, Base):
    __tablename__ = "audit_graph_layouts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "engagement_id", "user_id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)
    body: Mapped[dict] = mapped_column(JSONB)
    __mapper_args__ = {"version_id_col": version}


class GroupRelationship(Owned, Base):
    __tablename__ = "global_group_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "child_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
    )
    parent_id: Mapped[uuid.UUID]
    child_id: Mapped[uuid.UUID]
    body: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}
