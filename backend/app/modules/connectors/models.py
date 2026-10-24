"""Tenant-isolated connector operations, independent of long-running import transactions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class ConnectorState(Owned, Base):
    __tablename__ = "connector_states"
    __table_args__ = (UniqueConstraint("tenant_id", "namespace", "key", name="uq_connector_state"),)
    # Deliberately no FK to the row-locked connection: checkpoints must commit
    # independently while an import transaction holds that connection lock.
    connection_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    namespace: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
