from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.dependencies import DB, current_user
from app.db.models.platform import Membership, Tenant, User
from app.modules.identity.schemas import TenantOut

router = APIRouter(tags=["Organizations"])


@router.get("/tenants", response_model=list[TenantOut])
async def tenants(db: DB, user: Annotated[User, Depends(current_user)]):
    return (
        await db.scalars(
            select(Tenant)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == user.id, Membership.status == "active")
        )
    ).all()
