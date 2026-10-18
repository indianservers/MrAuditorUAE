import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.db.models.platform import AuditEvent


def record(
    db: AsyncSession,
    ctx: Context,
    action: str,
    resource_id: uuid.UUID | None,
    request_id: str,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            action=action,
            resource_id=resource_id,
            request_id=request_id,
            details=details or {},
        )
    )
