import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned


class SharedLink(Owned, Base):
    __tablename__ = "client_collaboration_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "engagement_id"], ["engagements.tenant_id", "engagements.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "request_id"], ["audit_records.tenant_id", "audit_records.id"]
        ),
    )
    engagement_id: Mapped[uuid.UUID]
    request_id: Mapped[uuid.UUID]
    request_version: Mapped[int]
    token_hash: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retain_until: Mapped[date]
    revoked: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=1)
    responses: Mapped[int] = mapped_column(default=0)
    uploads: Mapped[int] = mapped_column(default=0)
    limits: Mapped[dict] = mapped_column(JSONB)
    __mapper_args__ = {"version_id_col": version}


class SharedSubmission(Owned, Base):
    __tablename__ = "client_collaboration_submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "link_id"],
            ["client_collaboration_links.tenant_id", "client_collaboration_links.id"],
        ),
    )
    link_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    body: Mapped[dict] = mapped_column(JSONB)
