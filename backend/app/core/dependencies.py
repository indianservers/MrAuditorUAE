import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_claims
from app.db.models.platform import (
    Membership,
    MembershipRole,
    Permission,
    RefreshSession,
    RolePermission,
    Tenant,
    User,
)
from app.db.session import database, tenant_context

DB = Annotated[AsyncSession, Depends(database, scope="function")]
oauth = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def current_user(db: DB, token: Annotated[str, Depends(oauth)], request: Request) -> User:
    try:
        claims = decode_claims(token)
        user_id = uuid.UUID(claims["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired access token") from None
    user = await db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "Inactive identity")
    from datetime import UTC, datetime

    from app.core.config import settings

    sid = claims.get("sid")
    session = None
    if sid:
        session = await db.get(RefreshSession, uuid.UUID(sid))
        if (
            not session
            or session.user_id != user.id
            or session.revoked
            or session.expires_at <= datetime.now(UTC)
        ):
            raise HTTPException(401, "Session revoked or expired")
    elif settings().environment == "production":
        raise HTTPException(401, "Session-bound token required")
    request.state.mfa_verified = bool(session and claims.get("mfa") and session.mfa_verified)
    if settings().environment == "production" and not request.state.mfa_verified:
        if request.url.path not in {
            "/api/v1/auth/me",
            "/api/v1/auth/mfa",
            "/api/v1/auth/mfa/enroll",
            "/api/v1/auth/mfa/confirm",
        }:
            raise HTTPException(403, "MFA enrollment and verified sign-in required")
    return user


@dataclass(frozen=True)
class Context:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    permissions: frozenset[str]


def require(permission: str):
    async def authorize(
        db: DB,
        user: Annotated[User, Depends(current_user)],
        x_tenant_id: Annotated[uuid.UUID, Header()],
        request: Request,
    ) -> Context:
        membership = await db.scalar(
            select(Membership)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(
                Membership.tenant_id == x_tenant_id,
                Membership.user_id == user.id,
                Membership.status == "active",
                Tenant.status == "active",
            )
        )
        if not membership:
            raise HTTPException(403, "Tenant membership required")
        codes = frozenset(
            (
                await db.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
                    .where(MembershipRole.membership_id == membership.id)
                )
            ).all()
        )
        await tenant_context(db, str(x_tenant_id))
        from app.modules.audit_execution.access import firm_roles, role_permissions

        roles = await firm_roles(db, x_tenant_id, user.id)
        codes = await role_permissions(db, x_tenant_id, [r.id for r in roles])
        if permission and permission not in codes:
            raise HTTPException(403, "Permission denied")
        from app.modules.saas.service import enforce

        await enforce(db, x_tenant_id, request)
        return Context(user.id, x_tenant_id, codes)

    return authorize
