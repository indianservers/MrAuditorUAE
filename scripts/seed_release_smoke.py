"""Bootstrap only an explicitly guarded disposable test database, never demo/production."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import settings
from app.core.security import hash_password
from app.db.models.platform import Membership, MembershipRole, Role, User
from app.db.session import Session, engine
from app.modules.demo.guard import test_database_guard
from app.modules.identity.schemas import Bootstrap
from app.modules.identity.service import bootstrap
from sqlalchemy import select, text


async def main():
    async with Session() as db, db.begin():
        test_database_guard(
            settings(), await db.scalar(text("SELECT current_database()"))
        )
        await bootstrap(
            db,
            Bootstrap(
                email=os.environ["AUDITOS_SMOKE_EMAIL"],
                password=os.environ["AUDITOS_SMOKE_PASSWORD"],
                tenant_name="Synthetic release smoke",
            ),
            settings().bootstrap_secret,
        )
        reviewer_email = os.environ["AUDITOS_SMOKE_REVIEWER_EMAIL"].lower()
        if reviewer_email == os.environ["AUDITOS_SMOKE_EMAIL"].lower():
            raise ValueError(
                "Distinct synthetic preparer and reviewer identities required"
            )
        owner = await db.scalar(
            select(User).where(User.email == os.environ["AUDITOS_SMOKE_EMAIL"].lower())
        )
        membership = await db.scalar(
            select(Membership).where(Membership.user_id == owner.id)
        )
        role = await db.scalar(select(Role).where(Role.name == "Firm Administrator"))
        reviewer = User(
            email=reviewer_email,
            password_hash=hash_password(os.environ["AUDITOS_SMOKE_PASSWORD"]),
        )
        db.add(reviewer)
        await db.flush()
        reviewer_membership = Membership(
            tenant_id=membership.tenant_id, user_id=reviewer.id
        )
        db.add(reviewer_membership)
        await db.flush()
        db.add(MembershipRole(membership_id=reviewer_membership.id, role_id=role.id))
        identities = {
            "synthetic_only": True,
            "tenant_id": str(membership.tenant_id),
            "reviewer_membership_id": str(reviewer_membership.id),
            "reviewer_role_id": str(role.id),
        }
    target = (
        Path(__file__).resolve().parents[1]
        / ".local-runtime/release-smoke/identities.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(identities), encoding="utf-8")
    await engine.dispose()
    print("Isolated smoke identity created; credentials withheld")


if __name__ == "__main__":
    asyncio.run(main())
