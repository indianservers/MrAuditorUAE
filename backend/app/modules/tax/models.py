import uuid
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class TaxRun(Owned, Base):
    __tablename__ = "ct_computation_runs"
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
    methodology_version: Mapped[str] = mapped_column(default="auditos-ct/1.0")
    inputs: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    results: Mapped[dict] = mapped_column(JSONB)
    accounting_profit: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=0)
    taxable_income: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=0)
    current_tax: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=0)
    sha256: Mapped[str]


class LossPosting(Owned, Base):
    __tablename__ = "ct_loss_postings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "period_id"], ["financial_periods.tenant_id", "financial_periods.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bucket_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tax_run_id"], ["ct_computation_runs.tenant_id", "ct_computation_runs.id"]
        ),
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    period_id: Mapped[uuid.UUID] = mapped_column(index=True)
    bucket_id: Mapped[uuid.UUID] = mapped_column(index=True)
    tax_run_id: Mapped[uuid.UUID]
    amount_used: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    reason: Mapped[str]


class TaxRelease(Owned, Base):
    __tablename__ = "ct_current_releases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_id", "period_id"),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "period_id"], ["financial_periods.tenant_id", "financial_periods.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tax_run_id"], ["ct_computation_runs.tenant_id", "ct_computation_runs.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "approval_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
    )
    entity_id: Mapped[uuid.UUID]
    period_id: Mapped[uuid.UUID]
    tax_run_id: Mapped[uuid.UUID]
    approval_id: Mapped[uuid.UUID]
