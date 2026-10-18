import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import Context
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import access_token, digest, hash_password, refresh_token, verify_password
from app.db.models.platform import (
    Membership,
    MembershipRole,
    Permission,
    RefreshSession,
    Role,
    RolePermission,
    Tenant,
    User,
)
from app.db.session import tenant_context
from app.modules.audit_log.service import record
from app.modules.identity.schemas import Bootstrap, Tokens

logger = logging.getLogger("auditos")


async def issue(
    db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None, mfa: bool = False
) -> Tokens:
    raw = refresh_token()
    session = RefreshSession(
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        token_hash=digest(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings().refresh_days),
        mfa_verified=mfa,
    )
    db.add(session)
    await db.flush()
    return Tokens(
        access_token=access_token(user_id, session.id, mfa),
        refresh_token=raw,
        expires_in=settings().access_minutes * 60,
    )


async def bootstrap(db: AsyncSession, data: Bootstrap, secret: str) -> Tokens:
    config = settings()
    if not config.bootstrap_secret or not hmac.compare_digest(config.bootstrap_secret, secret):
        raise HTTPException(403, "First-run setup is disabled or secret is invalid")
    await db.execute(text("SELECT pg_advisory_xact_lock(914201)"))
    if await db.scalar(select(User.id).limit(1)):
        raise HTTPException(409, "Initial setup has already completed")
    tenant = Tenant(name=data.tenant_name)
    user = User(email=str(data.email).lower(), password_hash=hash_password(data.password))
    db.add_all([tenant, user])
    await db.flush()
    membership = Membership(tenant_id=tenant.id, user_id=user.id)
    db.add(membership)
    permissions = {p.code: p for p in (await db.scalars(select(Permission))).all()}
    for code in {code for codes in ROLE_PERMISSIONS.values() for code in codes}:
        if code not in permissions:
            permissions[code] = Permission(code=code)
            db.add(permissions[code])
    roles = {r.name: r for r in (await db.scalars(select(Role))).all()}
    for name in ROLE_PERMISSIONS:
        if name not in roles:
            roles[name] = Role(name=name)
            db.add(roles[name])
    await db.flush()
    existing = set(
        (await db.execute(select(RolePermission.role_id, RolePermission.permission_id))).all()
    )
    for name, codes in ROLE_PERMISSIONS.items():
        db.add_all(
            [
                RolePermission(role_id=roles[name].id, permission_id=permissions[code].id)
                for code in codes
                if (roles[name].id, permissions[code].id) not in existing
            ]
        )
    # Explicit firm administrator membership; platform role carries no client privileges.
    db.add(MembershipRole(membership_id=membership.id, role_id=roles["Firm Administrator"].id))
    await tenant_context(db, str(tenant.id))
    record(db, Context(user.id, tenant.id, frozenset()), "identity.bootstrap", user.id, "bootstrap")
    return await issue(db, user.id)


async def login(db: AsyncSession, email: str, password: str, otp: str = "") -> Tokens:
    user = await db.scalar(select(User).where(User.email == email.lower()).with_for_update())
    # Always perform a password check, including unknown identities.
    encoded = user.password_hash if user else DUMMY_HASH
    valid = verify_password(password, encoded)
    if not user or not valid or user.status != "active":
        logger.info("security", extra={"event": "auth.login_denied", "status": 401})
        raise HTTPException(401, "Invalid credentials")
    if user.mfa_enabled:
        from app.modules.identity.mfa import verify

        verify(user, otp)
    return await issue(db, user.id, mfa=user.mfa_enabled)


DUMMY_HASH = hash_password("timing-defense-only-not-a-user-password")


async def rotate(db: AsyncSession, token: str) -> Tokens:
    row = await db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == digest(token)).with_for_update()
    )
    if not row:
        raise HTTPException(401, "Invalid refresh session")
    if row.revoked:
        await db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == row.family_id)
            .values(revoked=True)
        )
        logger.info("security", extra={"event": "auth.refresh_reuse", "status": 401})
        # Persist family revocation even though the request is rejected.
        await db.commit()
        raise HTTPException(401, "Refresh token reuse detected; family revoked")
    user = await db.get(User, row.user_id)
    if row.expires_at <= datetime.now(UTC) or not user or user.status != "active":
        raise HTTPException(401, "Expired or inactive refresh session")
    row.revoked = True
    return await issue(db, row.user_id, row.family_id, row.mfa_verified)


async def logout(db: AsyncSession, token: str) -> None:
    row = await db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == digest(token)).with_for_update()
    )
    if row:
        await db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == row.family_id)
            .values(revoked=True)
        )
