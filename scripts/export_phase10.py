"""Export the actual guarded, published synthetic board package for visual QA."""

# ruff: noqa: E402
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import Session, engine, tenant_context
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.grc.models import GRCRun
from app.modules.grc.reporting import render


async def main():
    demo = json.loads((ROOT / "docs/phase-10/demo-verification.json").read_text(encoding="utf-8"))
    output = ROOT / "docs/phase-10/exports"
    output.mkdir(exist_ok=True)
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        package = await db.get(GRCRun, uuid.UUID(demo["board_publication"]))
        for format in ["pdf", "docx"]:
            content, _ = render(package, format)
            (output / ("synthetic-board-package." + format)).write_bytes(content)
            print(format, len(content))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
