import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models.platform import (
    Membership,
    MembershipRole,
    Permission,
    RolePermission,
    Tenant,
    User,
)
from app.db.session import database, tenant_context

DB = Annotated[AsyncSession, Depends(database, scope="function")]
oauth = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def current_user(db: DB, token: Annotated[str, Depends(oauth)]) -> User:
    try:
        user_id = decode_token(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired access token") from None
    user = await db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "Inactive identity")
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
        if permission not in codes:
            raise HTTPException(403, "Permission denied")
        await tenant_context(db, str(x_tenant_id))
        return Context(user.id, x_tenant_id, codes)

    return authorize
