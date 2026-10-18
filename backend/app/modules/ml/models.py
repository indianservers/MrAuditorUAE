import uuid

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class MLEvent(Owned, Base):
    """Append-only dataset, run, evaluation, approval, deployment and prediction ledger."""

    __tablename__ = "ml_registry_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"], ["ml_registry_events.tenant_id", "ml_registry_events.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(index=True)
    body: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]
