import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.db.models.platform import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
)
from app.modules.audit_execution.models import AuditAccess, RolePolicy


async def visible_engagements(db, ctx):
    roles = await firm_roles(db, ctx.tenant_id, ctx.user_id)
    if any(r.name == "Firm Administrator" for r in roles):
        return None
    return (
        select(AuditAccess.engagement_id)
        .join(Membership, Membership.id == AuditAccess.membership_id)
        .where(
            AuditAccess.tenant_id == ctx.tenant_id,
            Membership.user_id == ctx.user_id,
            Membership.status == "active",
            AuditAccess.active.is_(True),
            or_(AuditAccess.expires_at.is_(None), AuditAccess.expires_at > datetime.now(UTC)),
        )
    )


async def role_permissions(db, tenant_id, role_ids):
    policies = {
        p.role_id: set(p.permissions)
        for p in (
            await db.scalars(
                select(RolePolicy).where(
                    RolePolicy.tenant_id == tenant_id, RolePolicy.role_id.in_(role_ids)
                )
            )
        ).all()
    }
    rows = (
        await db.execute(
            select(RolePermission.role_id, Permission.code)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
        )
    ).all()
    result = set()
    for rid in role_ids:
        result.update(policies.get(rid, {code for role, code in rows if role == rid}))
    return frozenset(result)


async def firm_roles(db, tenant_id, user_id):
    return (
        await db.execute(
            select(Role.id, Role.name)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .join(Membership, Membership.id == MembershipRole.membership_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        )
    ).all()


async def engagement_permissions(db, ctx, engagement_id: uuid.UUID, permission: str):
    from app.core.read_projection import read_once

    if not permission.endswith("read"):
        return await _engagement_permissions(db, ctx, engagement_id, permission)
    return await read_once(db, ctx, "engagement-permission", (str(engagement_id), permission),
                           lambda: _engagement_permissions(db, ctx, engagement_id, permission))


async def _engagement_permissions(db, ctx, engagement_id: uuid.UUID, permission: str):
    # Recheck identities and permissions inside services; callers cannot forge a trusted Context.
    user = await db.get(User, ctx.user_id)
    tenant = await db.get(Tenant, ctx.tenant_id)
    member = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == ctx.tenant_id,
            Membership.user_id == ctx.user_id,
            Membership.status == "active",
        )
    )
    if not user or user.status != "active" or not member or not tenant or tenant.status != "active":
        raise HTTPException(403, "Active membership required")
    if not permission.endswith("read"):
        from app.modules.saas.service import background_allowed

        feature = permission.split(".")[0]
        feature = {
            "workingpaper": "audit",
            "engagement": "audit",
            "monitor": "grc",
            "risk": "grc",
            "control": "grc",
            "remediation": "grc",
            "governance": "grc",
        }.get(feature, feature)
        if feature in {"audit", "ifrs", "tax", "vat", "tp", "dmtt", "grc", "ai", "ml"}:
            await background_allowed(db, ctx.tenant_id, feature)
    roles = await firm_roles(db, ctx.tenant_id, ctx.user_id)
    firm = await role_permissions(db, ctx.tenant_id, [r.id for r in roles])
    # Firm administrators assign teams; professional actions still obey review separation.
    if any(r.name == "Firm Administrator" for r in roles) and permission in firm:
        return firm, {r.name for r in roles}
    grants = (
        await db.execute(
            select(Role.id, Role.name)
            .join(AuditAccess, AuditAccess.role_id == Role.id)
            .where(
                AuditAccess.tenant_id == ctx.tenant_id,
                AuditAccess.engagement_id == engagement_id,
                AuditAccess.membership_id == member.id,
                AuditAccess.active.is_(True),
                or_(AuditAccess.expires_at.is_(None), AuditAccess.expires_at > datetime.now(UTC)),
            )
        )
    ).all()
    codes = await role_permissions(db, ctx.tenant_id, [r.id for r in grants])
    if permission not in codes:
        raise HTTPException(403, "Engagement assignment and permission required")
    return codes, {r.name for r in grants}
