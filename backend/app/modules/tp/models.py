import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class TPRun(Owned, Base):
    __tablename__ = "tp_calculation_runs"
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
    methodology_version: Mapped[str] = mapped_column(default="auditos-tp/1.0")
    period_start: Mapped[date]
    period_end: Mapped[date]
    inputs: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    results: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]


class Observation(Owned, Base):
    __tablename__ = "tp_comparable_observations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("dataset_id", "company_key", "fiscal_year"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(index=True)
    company_key: Mapped[str]
    name: Mapped[str]
    country: Mapped[str]
    industry: Mapped[str]
    fiscal_year: Mapped[int]
    currency: Mapped[str]
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    cost_sales: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    opex: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    assets: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    facts: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]
