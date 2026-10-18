import uuid
from datetime import date

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record
from app.db.models.platform import Owned


class StandardVersion(Record, Base):
    __tablename__ = "ifrs_standards_registry"
    __table_args__ = (UniqueConstraint("code", "rule_version"),)
    code: Mapped[str]
    title: Mapped[str]
    rule_version: Mapped[int]
    issued_date: Mapped[date | None]
    effective_date: Mapped[date | None]
    support_status: Mapped[str]
    metadata_details: Mapped[dict] = mapped_column(JSONB)


class CalculationRun(Owned, Base):
    __tablename__ = "ifrs_calculation_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "record_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)
    record_id: Mapped[uuid.UUID | None]
    kind: Mapped[str] = mapped_column(index=True)
    methodology_version: Mapped[str] = mapped_column(default="auditos-ifrs/1.0")
    inputs: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    results: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]
