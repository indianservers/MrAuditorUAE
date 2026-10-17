from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.core.dependencies import DB, current_user
from app.db.models.platform import User
from app.modules.identity import service
from app.modules.identity.schemas import Bootstrap, Refresh, Tokens, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/bootstrap", response_model=Tokens, status_code=201)
async def bootstrap(data: Bootstrap, db: DB, x_bootstrap_secret: Annotated[str, Header()] = ""):
    return await service.bootstrap(db, data, x_bootstrap_secret)


@router.post("/login", response_model=Tokens)
async def login(db: DB, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    return await service.login(db, form.username, form.password)


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
