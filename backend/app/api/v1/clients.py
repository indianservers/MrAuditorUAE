import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import DB, Context, require
from app.db.models.platform import Client
from app.modules.clients.schemas import ClientCreate, ClientOut, ClientPatch, Page
from app.modules.clients.service import ResourceService

router = APIRouter(prefix="/clients", tags=["Clients"])
service = ResourceService(Client)
Read = Annotated[Context, Depends(require("clients.read"))]
Write = Annotated[Context, Depends(require("clients.write"))]


@router.get("", response_model=Page[ClientOut])
async def listing(
    db: DB,
    ctx: Read,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, max_length=30),
    search: str | None = Query(None, max_length=200),
    sort: str = "-created_at",
):
    return await service.listing(db, ctx, offset, limit, status, search, sort)


@router.post("", response_model=ClientOut, status_code=201)
async def create(data: ClientCreate, db: DB, ctx: Write, request: Request):
    return await service.create(db, ctx, data, request.state.request_id)


@router.get("/{identifier}", response_model=ClientOut)
async def get(identifier: uuid.UUID, db: DB, ctx: Read):
    return await service.get(db, ctx, identifier)


@router.patch("/{identifier}", response_model=ClientOut)
async def patch(identifier: uuid.UUID, data: ClientPatch, db: DB, ctx: Write, request: Request):
    return await service.patch(db, ctx, identifier, data, request.state.request_id)
