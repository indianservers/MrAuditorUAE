import uuid

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


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
