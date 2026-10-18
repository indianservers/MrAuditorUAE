import uuid
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.db.models.platform import Client, Engagement, FinancialPeriod, LegalEntity
from app.modules.audit_log.service import record


class ResourceService:
    def __init__(self, model: Any):
        self.model = model

    async def get(self, db: AsyncSession, ctx: Context, identifier: uuid.UUID):
        obj = await db.scalar(
            select(self.model).where(
                self.model.id == identifier, self.model.tenant_id == ctx.tenant_id
            )
        )
        if obj is None:
            raise HTTPException(404, "Resource not found")
        if self.model is Engagement:
            from app.modules.audit_execution.access import engagement_permissions

            await engagement_permissions(db, ctx, obj.id, "audit.read")
        return obj

    async def listing(
        self,
        db: AsyncSession,
        ctx: Context,
        offset: int,
        limit: int,
        status: str | None,
        search: str | None,
        sort: str,
    ):
        conditions = [self.model.tenant_id == ctx.tenant_id]
        if self.model is Engagement:
            from datetime import UTC, datetime

            from sqlalchemy import or_

            from app.db.models.platform import Membership
            from app.modules.audit_execution.access import firm_roles
            from app.modules.audit_execution.models import AuditAccess

            roles = await firm_roles(db, ctx.tenant_id, ctx.user_id)
            if not any(r.name == "Firm Administrator" for r in roles):
                conditions.append(
                    Engagement.id.in_(
                        select(AuditAccess.engagement_id)
                        .join(Membership, Membership.id == AuditAccess.membership_id)
                        .where(
                            AuditAccess.tenant_id == ctx.tenant_id,
                            Membership.user_id == ctx.user_id,
                            AuditAccess.active.is_(True),
                            or_(
                                AuditAccess.expires_at.is_(None),
                                AuditAccess.expires_at > datetime.now(UTC),
                            ),
                        )
                    )
                )
        if status:
            conditions.append(self.model.status == status)
        if search:
            conditions.append(self.model.name.icontains(search, autoescape=True))
        descending = sort.startswith("-")
        field = sort.lstrip("-")
        if field not in {"name", "created_at", "updated_at"}:
            raise HTTPException(422, "Unsupported sort field")
        column = getattr(self.model, field)
        query = (
            select(self.model)
            .where(*conditions)
            .order_by(column.desc() if descending else column.asc(), self.model.id)
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": (await db.scalars(query)).all(),
            "total": await db.scalar(
                select(func.count()).select_from(self.model).where(*conditions)
            ),
            "offset": offset,
            "limit": limit,
        }

    async def create(self, db: AsyncSession, ctx: Context, data: BaseModel, request_id: str):
        values = data.model_dump()
        if self.model is Engagement and values.get("status", "draft").upper() != "DRAFT":
            raise HTTPException(422, "New engagements must begin in DRAFT")
        for field, model in [
            ("client_id", Client),
            ("entity_id", LegalEntity),
            ("period_id", FinancialPeriod),
        ]:
            if values.get(field):
                parent = await ResourceService(model).get(db, ctx, values[field])
                if field == "period_id" and parent.entity_id != values["entity_id"]:
                    raise HTTPException(422, "Financial period belongs to another entity")
        obj = self.model(**values, tenant_id=ctx.tenant_id, created_by=ctx.user_id)
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        record(db, ctx, self.model.__tablename__ + ".created", obj.id, request_id)
        return obj

    async def patch(
        self,
        db: AsyncSession,
        ctx: Context,
        identifier: uuid.UUID,
        data: BaseModel,
        request_id: str,
    ):
        obj = await self.get(db, ctx, identifier)
        values = data.model_dump(exclude_unset=True)
        if self.model is Engagement and "status" in values:
            raise HTTPException(422, "Use the controlled engagement transition endpoint")
        if obj.version != values.pop("version"):
            raise HTTPException(409, "Resource version conflict")
        for field, value in values.items():
            if value is None:
                raise HTTPException(422, "Null updates are not supported")
            setattr(obj, field, value)
        await db.flush()
        await db.refresh(obj)
        record(db, ctx, self.model.__tablename__ + ".updated", obj.id, request_id)
        return obj
