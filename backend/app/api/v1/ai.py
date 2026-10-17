import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import DB, Context, require
from app.db.models.platform import AIExecution, AIModelConfiguration
from app.modules.ai_engine.schemas import ExecuteRequest, Summary
from app.modules.ai_engine.service import execute
from app.modules.clients.service import ResourceService

router = APIRouter(prefix="/ai", tags=["AI gateway"])
Read = Annotated[Context, Depends(require("ai.read"))]
Write = Annotated[Context, Depends(require("ai.execute"))]


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    max_tokens: int


class AIHealth(BaseModel):
    mock_available: bool
    real_provider_configured: bool
    real_provider_connectivity: Literal["not_probed"] = "not_probed"


class ExecuteOut(BaseModel):
    execution_id: uuid.UUID
    status: str
    output: Summary | None
    error_category: str | None


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    model_id: uuid.UUID
    template_id: uuid.UUID
    status: str
    duration_ms: int | None
    error_category: str | None
    request_id: str
    created_at: datetime


@router.get("/health", response_model=AIHealth)
async def health(ctx: Read):
    return AIHealth(
        mock_available=True,
        real_provider_configured=bool(settings().ai_api_key and settings().ai_model),
    )


@router.get("/models", response_model=list[ModelOut])
async def models(db: DB, ctx: Read):
    return (
        await db.scalars(select(AIModelConfiguration).where(AIModelConfiguration.enabled.is_(True)))
    ).all()


@router.post("/execute", response_model=ExecuteOut)
async def run(data: ExecuteRequest, db: DB, ctx: Write, request: Request):
    return await execute(db, ctx, data, request.state.request_id)


@router.get("/executions/{identifier}", response_model=ExecutionOut)
async def execution(identifier: uuid.UUID, db: DB, ctx: Read):
    return await ResourceService(AIExecution).get(db, ctx, identifier)
