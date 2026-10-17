from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import Session

router = APIRouter(tags=["Health"])


class Health(BaseModel):
    status: str


class Version(BaseModel):
    version: str = "0.1.0"
    environment: str


@router.get("/health/live", response_model=Health)
async def live():
    return Health(status="live")


@router.get("/health/ready", response_model=Health)
async def ready():
    try:
        async with Session() as db:
            unsafe_role = await db.scalar(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
            )
            if unsafe_role:
                raise RuntimeError("Unsafe database role")
            await db.execute(text("SELECT version_num FROM alembic_version"))
        async with Redis.from_url(
            settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            await redis.ping()
    except Exception:
        raise HTTPException(503, "Critical dependency unavailable") from None
    return Health(status="ready")


@router.get("/api/v1/system/version", response_model=Version)
async def version():
    return Version(environment=settings().environment)
