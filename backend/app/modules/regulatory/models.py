import uuid
from datetime import date

from sqlalchemy import Date, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class RuleSourceDocument(Owned, Base):
    """Firm reference material, separate from client/engagement evidence."""

    __tablename__ = "regulatory_source_documents"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)
    title: Mapped[str]
    country: Mapped[str]
    source_url: Mapped[str]
    retrieved_on: Mapped[date] = mapped_column(Date)
    filename: Mapped[str]
    media_type: Mapped[str]
    object_key: Mapped[str]
    object_version: Mapped[str]
    sha256: Mapped[str]
    size: Mapped[int]
    scan_status: Mapped[str]


class RuleVersion(Owned, Base):
    __tablename__ = "regulatory_rule_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "rule_key", "version"),
    )
    rule_key: Mapped[str]
    country: Mapped[str]
    version: Mapped[int]
    body: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]


class RuleAction(Owned, Base):
    __tablename__ = "regulatory_rule_actions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_key", "sequence"),
        ForeignKeyConstraint(
            ["tenant_id", "version_id"],
            ["regulatory_rule_versions.tenant_id", "regulatory_rule_versions.id"],
        ),
    )
    rule_key: Mapped[str]
    version_id: Mapped[uuid.UUID]
    sequence: Mapped[int]
    state: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)
