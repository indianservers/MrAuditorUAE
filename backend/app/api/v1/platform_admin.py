"""Metadata-only operations, separately provisioned operators with mandatory MFA."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.dependencies import DB, Context, current_user, require
from app.db.models.platform import Tenant, User
from app.db.session import tenant_context
from app.modules.saas.models import Operation, PlatformOperator, Subscription, Usage
from app.modules.saas.service import FEATURES, PLANS

router = APIRouter(tags=["SaaS operations"])


async def operator(db: DB, user: Annotated[User, Depends(current_user)], request: Request):
    grant = await db.scalar(
        select(PlatformOperator).where(
            PlatformOperator.user_id == user.id, PlatformOperator.active.is_(True)
        )
    )
    if not grant or not user.mfa_enabled or not request.state.mfa_verified:
        raise HTTPException(403, "Separately provisioned platform operator and MFA required")
    return user


Operator = Annotated[User, Depends(operator)]


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Literal["Starter", "Professional", "Enterprise"]
    status: Literal["trial", "active", "past_due", "suspended", "cancelled"]
    valid_until: datetime
    grace_until: datetime
    features: list[str] = Field(max_length=10)
    limits: dict[str, int] = Field(max_length=5)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=500)

    @model_validator(mode="after")
    def valid(self):
        if (
            not self.valid_until.tzinfo
            or not self.grace_until.tzinfo
            or self.grace_until < self.valid_until
            or not set(self.features) <= FEATURES
            or set(self.limits) != set(PLANS[self.plan])
            or any(v < 0 or v > 10**15 for v in self.limits.values())
        ):
            raise ValueError(
                "Complete bounded quotas, supported features, and aware validity dates required"
            )
        return self


def view(sub):
    return {
        "plan": sub.plan,
        "status": sub.status,
        "valid_until": sub.valid_until,
        "grace_until": sub.grace_until,
        "limits": sub.limits,
        "features": sub.features,
        "version": sub.version,
    }


@router.get("/subscriptions/current")
async def current(db: DB, ctx: Annotated[Context, Depends(require("clients.read"))]):
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == ctx.tenant_id))
    return {
        "subscription": view(sub) if sub else None,
        "billing_provider": "NOT_CONFIGURED",
        "invoices": [],
        "plans": PLANS,
    }


@router.put("/platform/tenants/{tenant_id}/subscription")
async def change(tenant_id: uuid.UUID, data: Change, db: DB, user: Operator):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant unavailable")
    await tenant_context(db, str(tenant_id))
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 12))"), {"key": str(tenant_id)}
    )
    sub = await db.scalar(
        select(Subscription).where(Subscription.tenant_id == tenant_id).with_for_update()
    )
    if (sub.version if sub else 0) != data.expected_version:
        raise HTTPException(409, "Subscription version changed")
    previous = view(sub) if sub else None
    if not sub:
        sub = Subscription(tenant_id=tenant_id, created_by=user.id)
        db.add(sub)
    for key in ("plan", "status", "valid_until", "grace_until", "features", "limits"):
        setattr(sub, key, getattr(data, key))
    await db.flush()
    from fastapi.encoders import jsonable_encoder

    db.add(
        Operation(
            actor_id=user.id,
            tenant_id=tenant_id,
            action="subscription.changed",
            details=jsonable_encoder(
                {"before": previous, "after": view(sub), "reason": data.reason}
            ),
        )
    )
    return view(sub)


class Lifecycle(BaseModel):
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=10, max_length=500)


@router.patch("/platform/tenants/{tenant_id}")
async def lifecycle(tenant_id: uuid.UUID, data: Lifecycle, db: DB, user: Operator):
    tenant = await db.get(Tenant, tenant_id, with_for_update=True)
    if not tenant:
        raise HTTPException(404, "Tenant unavailable")
    previous = tenant.status
    tenant.status = data.status
    db.add(
        Operation(
            actor_id=user.id,
            tenant_id=tenant_id,
            action="tenant.status",
            details={"before": previous, "after": data.status, "reason": data.reason},
        )
    )
    return {"id": tenant.id, "status": tenant.status}


@router.get("/platform/qa-center")
async def qa_center(db: DB, user: Operator):
    if settings().environment not in {"development", "test"} or not settings().qa_campaign_enabled:
        raise HTTPException(404, "QA campaign is disabled")
    rows = (
        await db.scalars(
            select(Operation)
            .where(Operation.action == "qa.campaign.results")
            .order_by(Operation.created_at.desc(), Operation.id)
            .limit(20)
        )
    ).all()
    return {
        "runs": [
            {"id": row.id, "executed_at": row.created_at, "results": row.details} for row in rows
        ],
        "production_readiness": "Not certified by this QA dashboard",
    }


@router.get("/platform/{area}")
async def workspace(
    area: Literal[
        "overview",
        "tenants",
        "subscriptions",
        "usage",
        "services",
        "incidents",
        "security",
        "releases",
    ],
    db: DB,
    user: Operator,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    if area in {"overview", "tenants", "subscriptions", "usage"}:
        tenants = (
            await db.scalars(
                select(Tenant).order_by(Tenant.created_at, Tenant.id).offset(offset).limit(limit)
            )
        ).all()
        items = []
        for tenant in tenants:
            # RLS remains forced; switch context only to read operational tables.
            await tenant_context(db, str(tenant.id))
            sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
            usage = (
                await db.scalars(
                    select(Usage).where(
                        Usage.tenant_id == tenant.id,
                        Usage.period == datetime.now(UTC).strftime("%Y-%m"),
                    )
                )
            ).all()
            items.append(
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "status": tenant.status,
                    "subscription": view(sub) if sub else None,
                    "usage": [
                        {"metric": row.metric, "quantity": row.quantity, "period": row.period}
                        for row in usage
                    ],
                }
            )
        total = await db.scalar(select(func.count()).select_from(Tenant))
        return {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "billing_provider": "NOT_CONFIGURED",
        }
    if area == "services":
        from app.api.v1.health import ready

        result = await ready()
        return {
            "database_redis": result.status,
            "workers": "NOT_MEASURED",
            "backup_monitor": "NOT_CONNECTED",
            "tracing": "NOT_CONFIGURED",
        }
    if area == "releases":
        return {
            "release": settings().release_id,
            "environment": settings().environment,
            "deployment_authorized": False,
        }
    if area == "incidents":
        return {
            "status": "EXTERNAL_DEPENDENCY",
            "message": "Incident system is not connected; an empty result is not evidence of zero incidents.",
        }
    rows = (
        await db.scalars(
            select(Operation)
            .order_by(Operation.created_at.desc(), Operation.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "actor_id": row.actor_id,
                "tenant_id": row.tenant_id,
                "action": row.action,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "offset": offset,
        "limit": limit,
    }
