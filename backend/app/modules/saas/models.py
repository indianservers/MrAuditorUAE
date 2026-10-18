"""Operational metadata only. Platform operators receive no tenant membership."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record
from app.db.models.platform import Owned


class PlatformOperator(Record, Base):
    __tablename__ = "platform_operators"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    active: Mapped[bool] = mapped_column(default=True)


class Subscription(Owned, Base):
    __tablename__ = "tenant_subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id"),)
    plan: Mapped[str]
    status: Mapped[str]
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grace_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    limits: Mapped[dict] = mapped_column(JSONB)
    features: Mapped[list] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class Usage(Owned, Base):
    __tablename__ = "tenant_usage_counters"
    __table_args__ = (UniqueConstraint("tenant_id", "period", "metric"),)
    period: Mapped[str]
    metric: Mapped[str]
    quantity: Mapped[int] = mapped_column(default=0)


class Operation(Record, Base):
    __tablename__ = "platform_operations"
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    action: Mapped[str]
    details: Mapped[dict] = mapped_column(JSONB)
