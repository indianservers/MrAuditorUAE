"""Provider-independent entitlements. No card data or simulated payments."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.db.models.platform import Client, Membership
from app.modules.saas.models import Subscription, Usage

PLANS = {
    "Starter": {
        "users": 5,
        "clients": 10,
        "ai_requests": 100,
        "ml_requests": 0,
        "storage_bytes": 1073741824,
    },
    "Professional": {
        "users": 25,
        "clients": 100,
        "ai_requests": 2000,
        "ml_requests": 100,
        "storage_bytes": 21474836480,
    },
    "Enterprise": {
        "users": 200,
        "clients": 1000,
        "ai_requests": 20000,
        "ml_requests": 1000,
        "storage_bytes": 214748364800,
    },
}
FEATURES = {"accounting", "audit", "ifrs", "tax", "vat", "tp", "dmtt", "grc", "ai", "ml"}


def writable(subscription, now=None):
    now = now or datetime.now(UTC)
    return subscription.status in {"active", "trial", "past_due"} and now <= (
        subscription.grace_until if subscription.status == "past_due" else subscription.valid_until
    )


async def enforce(db, tenant, request):
    # Stopping one's own running training is a safety control, not a billable write.
    # Its route still checks active identity, ownership and current ML read access.
    import re

    if request.method == "POST" and re.fullmatch(
        r"/api/v1/ml/jobs/[a-f0-9-]{36}/cancel", request.url.path
    ):
        return
    if str(tenant) in getattr(request.state, "entitlements_checked", set()):
        return
    if request.method != "GET":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 12))"), {"key": str(tenant)}
        )
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant))
    if not sub:
        if settings().environment == "production":
            raise HTTPException(403, "Tenant subscription provisioning required")
        return
    path = request.url.path.removeprefix("/api/v1/")
    feature = path.split("/")[0]
    feature = {
        "analytics": "accounting",
        "reconciliation": "accounting",
        "sampling": "accounting",
        "connectors": "accounting",
        "financial-ai": "ai",
    }.get(feature, feature)
    if "/audit/" in path:
        feature = "audit"
    if feature in FEATURES and feature not in sub.features:
        raise HTTPException(403, "Feature is outside tenant entitlements")
    if request.method == "GET":
        return  # Expiry retains authorized reads, never deletes accounting records.
    if not writable(sub):
        raise HTTPException(403, "Subscription is read-only; contact billing administrator")
    if request.method != "POST":
        return
    from typing import Any

    admissions: list[tuple[str, Any, str]] = [
        ("clients", Client, "clients"),
        ("admin/invitations", Membership, "users"),
    ]
    for resource, model, quota_metric in admissions:
        if path == resource:
            count = await db.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == tenant)
            )
            if count >= sub.limits[quota_metric]:
                raise HTTPException(409, f"Tenant {quota_metric} limit reached")
    metric = (
        "ai_requests"
        if feature == "ai" or path.endswith("/ai") or "/ai/" in path
        else "ml_requests"
        if feature == "ml"
        else None
    )
    if metric:
        period = datetime.now(UTC).strftime("%Y-%m")
        counter = await db.scalar(
            select(Usage).where(
                Usage.tenant_id == tenant, Usage.period == period, Usage.metric == metric
            )
        )
        if counter is None:
            counter = Usage(
                tenant_id=tenant, created_by=None, period=period, metric=metric, quantity=0
            )
            db.add(counter)
        if counter.quantity >= sub.limits[metric]:
            raise HTTPException(429, "Monthly tenant operation allowance exhausted")
        counter.quantity += 1
        await db.flush()
    request.state.entitlements_checked = {str(tenant)}


async def background_allowed(db, tenant, feature):
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant))
    if (not sub and settings().environment == "production") or (
        sub and (feature not in sub.features or not writable(sub))
    ):
        raise HTTPException(403, "Background feature entitlement unavailable")


async def admit_user(db, tenant):
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 12))"), {"key": str(tenant)}
    )
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant))
    if not sub:
        if settings().environment == "production":
            raise HTTPException(403, "Subscription provisioning required")
        return
    count = await db.scalar(
        select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant)
    )
    if not writable(sub) or count >= sub.limits["users"]:
        raise HTTPException(409, "Tenant user limit reached or subscription read-only")
