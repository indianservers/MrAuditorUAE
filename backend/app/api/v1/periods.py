from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import DB, Context, require
from app.db.models.platform import FinancialPeriod
from app.modules.clients.schemas import PeriodCreate, PeriodOut
from app.modules.clients.service import ResourceService

router = APIRouter(tags=["Financial periods"])


@router.post("/financial-periods", response_model=PeriodOut, status_code=201)
async def create(
    data: PeriodCreate,
    db: DB,
    ctx: Annotated[Context, Depends(require("entities.write"))],
    request: Request,
):
    return await ResourceService(FinancialPeriod).create(db, ctx, data, request.state.request_id)
