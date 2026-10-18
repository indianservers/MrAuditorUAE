import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import EmailStr, Field
from sqlalchemy import func, select

from app.core.dependencies import DB, Context, require
from app.core.security import digest, hash_password, refresh_token
from app.db.models.platform import (
    AuditEvent,
    Membership,
    MembershipRole,
    Permission,
    RefreshSession,
    Role,
    User,
)
from app.modules.audit_execution.models import AuditInvitation, ClientAccess, RolePolicy
from app.modules.audit_execution.schemas import Strict
from app.modules.audit_execution.service import serialize
from app.modules.audit_log.service import record

router = APIRouter(prefix="/admin", tags=["Firm administration"])
Admin = Annotated[Context, Depends(require("users.assign_roles"))]


class Invite(Strict):
    email: EmailStr
    role_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class Redeem(Strict):
    token: str = Field(min_length=40, max_length=200)
    password: str = Field(min_length=14, max_length=128)


class MemberUpdate(Strict):
    status: Literal["active", "disabled"]
    role_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class Permissions(Strict):
    permissions: list[str] = Field(max_length=100)


class ClientGrant(Strict):
    membership_id: uuid.UUID
    client_id: uuid.UUID
    expires_at: datetime | None = None


@router.get("/users")
async def users(
    db: DB,
    ctx: Admin,
    search: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    conditions = [
        Membership.tenant_id == ctx.tenant_id,
        User.email.icontains(search, autoescape=True),
    ]
    rows = (
        await db.execute(
            select(Membership, User.email, User.status)
            .join(User, User.id == Membership.user_id)
            .where(*conditions)
            .order_by(User.email)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    result = []
    for member, email, user_status in rows:
        roles = (
            await db.scalars(
                select(MembershipRole.role_id).where(MembershipRole.membership_id == member.id)
            )
        ).all()
        sessions = await db.scalar(
            select(func.count())
            .select_from(RefreshSession)
            .where(
                RefreshSession.user_id == member.user_id,
                RefreshSession.revoked.is_(False),
                RefreshSession.expires_at > datetime.now(UTC),
            )
        )
        result.append(
            {
                **serialize(member),
                "email": email,
                "identity_status": user_status,
                "role_ids": [str(r) for r in roles],
                "active_sessions": sessions,
            }
        )
    total = await db.scalar(
        select(func.count())
        .select_from(Membership)
        .join(User, User.id == Membership.user_id)
        .where(*conditions)
    )
    return {"items": result, "total": total, "offset": offset, "limit": limit}


@router.get("/roles")
async def roles(db: DB, ctx: Admin):
    from app.modules.audit_execution.access import role_permissions

    result = []
    for role in (await db.scalars(select(Role).order_by(Role.name))).all():
        result.append(
            {
                "id": str(role.id),
                "name": role.name,
                "permissions": sorted(await role_permissions(db, ctx.tenant_id, [role.id])),
            }
        )
    return {"items": result}


@router.get("/permissions")
async def permissions(db: DB, ctx: Admin):
    return {"items": (await db.scalars(select(Permission.code).order_by(Permission.code))).all()}


@router.post("/roles/{rid}/permissions")
async def policy(rid: uuid.UUID, data: Permissions, db: DB, ctx: Admin, request: Request):
    role = await db.get(Role, rid)
    if not role or role.name.startswith("Platform"):
        raise HTTPException(403, "Platform roles cannot be administered by firms")
    known = set((await db.scalars(select(Permission.code))).all())
    if not set(data.permissions) <= known or any(
        p.startswith("platform.") for p in data.permissions
    ):
        raise HTTPException(422, "Unknown or platform permission")
    if role.name.startswith("Client") and not set(data.permissions) <= {
        "portal.read",
        "portal.respond",
    }:
        raise HTTPException(422, "Client roles are restricted to the client portal")
    obj = await db.scalar(
        select(RolePolicy).where(RolePolicy.tenant_id == ctx.tenant_id, RolePolicy.role_id == rid)
    )
    if obj:
        obj.permissions = data.permissions
    else:
        obj = RolePolicy(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            role_id=rid,
            permissions=data.permissions,
        )
        db.add(obj)
    record(
        db,
        ctx,
        "admin.permissions.changed",
        rid,
        request.state.request_id,
        {"permissions": data.permissions},
    )
    return {"status": "updated"}


async def valid_roles(db, ids):
    roles = (await db.scalars(select(Role).where(Role.id.in_(ids)))).all()
    if len(roles) != len(set(ids)) or any(r.name.startswith("Platform") for r in roles):
        raise HTTPException(422, "Valid firm or client roles required")
    if any(r.name.startswith("Client") for r in roles) and not all(
        r.name.startswith("Client") for r in roles
    ):
        raise HTTPException(422, "Client and firm identities must remain separate")
    return roles


@router.post("/invitations", status_code=201)
async def invite(
    data: Invite,
    db: DB,
    ctx: Annotated[Context, Depends(require("users.invite"))],
    request: Request,
):
    if "users.assign_roles" not in ctx.permissions:
        raise HTTPException(403, "Role assignment permission required to invite with roles")
    await valid_roles(db, data.role_ids)
    # The invitation is delivered by an authorized administrator; no mail provider is presumed.
    raw = str(ctx.tenant_id) + "." + refresh_token()
    obj = AuditInvitation(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        email=str(data.email).lower(),
        token_hash=digest(raw),
        role_ids=[str(r) for r in data.role_ids],
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    db.add(obj)
    await db.flush()
    record(db, ctx, "admin.invitation.created", obj.id, request.state.request_id)
    return {
        "id": str(obj.id),
        "token": raw,
        "expires_at": obj.expires_at,
        "delivery": "administrator_delivery_required",
    }


@router.post("/invitations/redeem", status_code=201)
async def redeem(data: Redeem, db: DB):
    try:
        tid = uuid.UUID(data.token.split(".", 1)[0])
    except ValueError:
        raise HTTPException(422, "Invitation is invalid or expired")
    from app.db.session import tenant_context

    await tenant_context(db, str(tid))
    obj = await db.scalar(
        select(AuditInvitation)
        .where(AuditInvitation.token_hash == digest(data.token))
        .with_for_update()
    )
    if not obj or obj.used or obj.expires_at <= datetime.now(UTC):
        raise HTTPException(422, "Invitation is invalid or expired")
    from app.modules.saas.service import admit_user

    await admit_user(db, tid)
    user = await db.scalar(select(User).where(User.email == obj.email))
    if user:
        raise HTTPException(409, "Existing identities require authenticated membership acceptance")
    user = User(email=obj.email, password_hash=hash_password(data.password))
    db.add(user)
    await db.flush()
    member = Membership(tenant_id=obj.tenant_id, user_id=user.id)
    db.add(member)
    await db.flush()
    await valid_roles(db, [uuid.UUID(r) for r in obj.role_ids])
    for rid in obj.role_ids:
        db.add(MembershipRole(membership_id=member.id, role_id=uuid.UUID(rid)))
    obj.used = True
    record(
        db,
        Context(user.id, obj.tenant_id, frozenset()),
        "admin.invitation.accepted",
        obj.id,
        "invitation",
    )
    return {"status": "active", "email": user.email}


@router.patch("/users/{mid}")
async def update_member(mid: uuid.UUID, data: MemberUpdate, db: DB, ctx: Admin, request: Request):
    from sqlalchemy import delete

    obj = await db.scalar(
        select(Membership)
        .where(Membership.id == mid, Membership.tenant_id == ctx.tenant_id)
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Member not found")
    if obj.user_id == ctx.user_id:
        raise HTTPException(409, "Use another administrator to change your own access")
    await valid_roles(db, data.role_ids)
    obj.status = data.status
    await db.execute(delete(MembershipRole).where(MembershipRole.membership_id == mid))
    for rid in set(data.role_ids):
        db.add(MembershipRole(membership_id=mid, role_id=rid))
    # Deactivates this firm's access immediately without disabling unrelated firm memberships.
    record(
        db,
        ctx,
        "admin.member.updated",
        obj.id,
        request.state.request_id,
        data.model_dump(mode="json"),
    )
    return {"status": obj.status}


@router.post("/client-access")
async def client_access(data: ClientGrant, db: DB, ctx: Admin, request: Request):
    from app.db.models.platform import Client

    member = await db.scalar(
        select(Membership).where(
            Membership.id == data.membership_id, Membership.tenant_id == ctx.tenant_id
        )
    )
    client = await db.scalar(
        select(Client).where(Client.id == data.client_id, Client.tenant_id == ctx.tenant_id)
    )
    if not member or not client:
        raise HTTPException(404, "Member or client not found")
    obj = await db.scalar(
        select(ClientAccess).where(
            ClientAccess.tenant_id == ctx.tenant_id,
            ClientAccess.client_id == data.client_id,
            ClientAccess.membership_id == data.membership_id,
        )
    )
    if obj:
        obj.expires_at = data.expires_at
    else:
        obj = ClientAccess(tenant_id=ctx.tenant_id, created_by=ctx.user_id, **data.model_dump())
        db.add(obj)
    await db.flush()
    record(db, ctx, "admin.client_access.updated", obj.id, request.state.request_id)
    return serialize(obj)


@router.get("/activity")
async def activity(
    db: DB, ctx: Admin, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    conditions = [AuditEvent.tenant_id == ctx.tenant_id]
    rows = (
        await db.scalars(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [serialize(r) for r in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }
