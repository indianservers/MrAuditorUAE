import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class GRCRun(Owned, Base):
    __tablename__ = "grc_execution_snapshots"
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
    record_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(index=True)
    inputs: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list] = mapped_column(JSONB)
    results: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]


class MonitorAlert(Owned, Base):
    __tablename__ = "grc_monitor_alerts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "engagement_id", "dedup_key"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["grc_execution_snapshots.tenant_id", "grc_execution_snapshots.id"],
        ),
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(index=True)
    dedup_key: Mapped[str]
    rule_key: Mapped[str] = mapped_column(index=True)
    source_id: Mapped[uuid.UUID | None]
    snapshot_id: Mapped[uuid.UUID | None]
    signals: Mapped[dict] = mapped_column(JSONB)


class MonitorSchedule(Owned, Base):
    __tablename__ = "grc_monitor_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "rule_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(index=True)
    frequency: Mapped[str]
    next_due: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    active: Mapped[bool] = mapped_column(default=True)
    rule_version: Mapped[int]
    last_job_id: Mapped[uuid.UUID | None]
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}
