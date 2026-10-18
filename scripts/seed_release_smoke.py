"""Bootstrap only an explicitly guarded disposable test database, never demo/production."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import text

from app.core.config import settings
from app.db.session import Session, engine
from app.modules.demo.guard import test_database_guard
from app.modules.identity.schemas import Bootstrap
from app.modules.identity.service import bootstrap


async def main():
    async with Session() as db, db.begin():
        test_database_guard(settings(), await db.scalar(text("SELECT current_database()")))
        await bootstrap(
            db,
            Bootstrap(
                email=os.environ["AUDITOS_SMOKE_EMAIL"],
                password=os.environ["AUDITOS_SMOKE_PASSWORD"],
                tenant_name="Synthetic release smoke",
            ),
            settings().bootstrap_secret,
        )
    await engine.dispose()
    print("Isolated smoke identity created; credentials withheld")


if __name__ == "__main__":
    asyncio.run(main())
