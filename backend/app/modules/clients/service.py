import uuid
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
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
        if not status and self.model in {Client, LegalEntity}:
            conditions.append(self.model.status != "archived")
        if self.model is Engagement:
            from datetime import UTC, datetime

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
            name_match = self.model.name.icontains(search, autoescape=True)
            conditions.append(
                or_(name_match, Client.code.icontains(search, autoescape=True))
                if self.model is Client
                else name_match
            )
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
        parents: list[tuple[str, Any]] = [
            ("client_id", Client),
            ("entity_id", LegalEntity),
            ("period_id", FinancialPeriod),
        ]
        for field, model in parents:
            if values.get(field):
                parent = await ResourceService(model).get(db, ctx, values[field])
                if model in {Client, LegalEntity}:
                    # Serialize admissions with archival; preserve existing dependent history.
                    parent = await db.scalar(
                        select(model)
                        .where(model.id == parent.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    if not parent or parent.status != "active":
                        raise HTTPException(409, "Active parent required for new records")
                    if model is LegalEntity:
                        client = await db.scalar(
                            select(Client)
                            .where(Client.id == parent.client_id)
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                        if not client or client.status != "active":
                            raise HTTPException(409, "Active client required for new records")
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
        obj = await db.scalar(
            select(self.model)
            .where(self.model.id == obj.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if obj is None:
            raise HTTPException(404, "Resource not found")
        values = data.model_dump(exclude_unset=True)
        reason = values.pop("lifecycle_reason", None)
        if self.model is Engagement and "status" in values:
            raise HTTPException(422, "Use the controlled engagement transition endpoint")
        if obj.version != values.pop("version"):
            raise HTTPException(409, "Resource version conflict")
        changed_status = values.get("status", obj.status) != obj.status
        if (
            self.model in {Client, LegalEntity}
            and changed_status
            and (values.get("status") == "archived" or obj.status == "archived")
        ):
            if values.get("status") == "archived":
                query = select(Engagement.id).where(
                    Engagement.tenant_id == ctx.tenant_id,
                    ~func.upper(Engagement.status).in_(["COMPLETED", "ARCHIVED", "CANCELLED"]),
                )
                query = (
                    query.where(
                        Engagement.entity_id.in_(
                            select(LegalEntity.id).where(LegalEntity.client_id == obj.id)
                        )
                    )
                    if self.model is Client
                    else query.where(Engagement.entity_id == obj.id)
                )
                if await db.scalar(query.limit(1)):
                    raise HTTPException(
                        409, "Finish or archive dependent engagements before parent archival"
                    )
            elif self.model is LegalEntity:
                parent = await db.get(Client, obj.client_id)
                if not parent or parent.status != "active":
                    raise HTTPException(409, "Restore the parent client first")
            if not reason or len(reason.strip()) < 10:
                raise HTTPException(422, "A lifecycle reason is required for archive or restore")
            record(
                db,
                ctx,
                self.model.__tablename__
                + (".archived" if values.get("status") == "archived" else ".restored"),
                obj.id,
                request_id,
                {
                    "reason": reason,
                    "prior_status": obj.status,
                    "next_status": values["status"],
                    "prior_version": obj.version,
                },
            )
        elif self.model in {Client, LegalEntity} and obj.status == "archived":
            raise HTTPException(409, "Restore archived record before editing")
        for field, value in values.items():
            if value is None:
                raise HTTPException(422, "Null updates are not supported")
            setattr(obj, field, value)
        await db.flush()
        await db.refresh(obj)
        record(db, ctx, self.model.__tablename__ + ".updated", obj.id, request_id)
        return obj
