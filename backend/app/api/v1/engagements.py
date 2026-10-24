import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import DB, Context, require
from app.db.models.platform import Engagement
from app.modules.clients.schemas import EngagementCreate, EngagementOut, EngagementPatch, Page
from app.modules.clients.service import ResourceService

router = APIRouter(prefix="/engagements", tags=["Engagements"])
service = ResourceService(Engagement)
Read = Annotated[Context, Depends(require("engagements.read"))]
Write = Annotated[Context, Depends(require("engagements.write"))]


@router.get("", response_model=Page[EngagementOut])
async def listing(
    db: DB,
    ctx: Read,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, max_length=30),
    search: str | None = Query(None, max_length=200),
    sort: str = "-created_at",
    country: str | None = Query(None, pattern=r"^[A-Z]{2}$"),
):
    return await service.listing(db, ctx, offset, limit, status, search, sort, country)


@router.post("", response_model=EngagementOut, status_code=201)
async def create(data: EngagementCreate, db: DB, ctx: Write, request: Request):
    return await service.create(db, ctx, data, request.state.request_id)


@router.get("/{identifier}", response_model=EngagementOut)
async def get(identifier: uuid.UUID, db: DB, ctx: Read):
    return await service.get(db, ctx, identifier)


@router.patch("/{identifier}", response_model=EngagementOut)
async def patch(identifier: uuid.UUID, data: EngagementPatch, db: DB, ctx: Write, request: Request):
    return await service.patch(db, ctx, identifier, data, request.state.request_id)
