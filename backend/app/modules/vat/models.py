import uuid
from datetime import date

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class VATRun(Owned, Base):
    __tablename__ = "vat_computation_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "engagement_id", "kind", "idempotency_key"),
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
    idempotency_key: Mapped[str | None]
    period_start: Mapped[date]
    period_end: Mapped[date]
    methodology_version: Mapped[str] = mapped_column(default="auditos-vat/1.0")
    inputs: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    results: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]


class DemoDataset(Owned, Base):
    __tablename__ = "synthetic_datasets"
    __table_args__ = (UniqueConstraint("tenant_id", "seed_version"),)
    seed_version: Mapped[str]
    status: Mapped[str]
    manifest: Mapped[dict] = mapped_column(JSONB)
