from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.core.dependencies import DB, current_user
from app.core.security import verify_password
from app.db.models.platform import RefreshSession, User
from app.modules.identity import service
from app.modules.identity.schemas import Bootstrap, Refresh, Tokens, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/bootstrap", response_model=Tokens, status_code=201)
async def bootstrap(data: Bootstrap, db: DB, x_bootstrap_secret: Annotated[str, Header()] = ""):
    return await service.bootstrap(db, data, x_bootstrap_secret)


@router.post("/login", response_model=Tokens)
async def login(
    db: DB,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    otp: Annotated[str, Form(max_length=6)] = "",
):
    return await service.login(db, form.username, form.password, otp)


@router.post("/refresh", response_model=Tokens)
async def refresh(data: Refresh, db: DB):
    return await service.rotate(db, data.refresh_token)


@router.post("/logout", status_code=204)
async def logout(data: Refresh, db: DB):
    await service.logout(db, data.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(current_user)]):
    return user


class Enrollment(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class Confirmation(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


@router.get("/mfa")
async def mfa_status(user: Annotated[User, Depends(current_user)], request: Request):
    return {"enabled": user.mfa_enabled, "session_verified": request.state.mfa_verified}


@router.post("/mfa/enroll")
async def mfa_enroll(data: Enrollment, db: DB, user: Annotated[User, Depends(current_user)]):
    from app.modules.identity.mfa import enroll

    user = (
        await db.scalars(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return enroll(user)


@router.post("/mfa/confirm")
async def mfa_confirm(data: Confirmation, db: DB, user: Annotated[User, Depends(current_user)]):
    from app.modules.identity.mfa import verify

    user = (
        await db.scalars(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()
    if user.mfa_enabled:
        raise HTTPException(409, "MFA is already enabled")
    verify(user, data.code)
    user.mfa_enabled = True
    # Enrollment invalidates every old session, including the password-only one.
    await db.execute(
        update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True)
    )
    return {"enabled": True, "sign_in_required": True}
