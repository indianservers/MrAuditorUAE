import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import func, select

from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import JournalLine
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.ml.models import MLEvent
from app.modules.ml.service import read_object

ROOT = Path(__file__).resolve().parents[1]


async def main():
    runs = json.loads((ROOT / "docs/phase-9/training-results.json").read_text())
    chosen = next(x for x in runs if x["family"] == "journal-classifier")
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        model = await db.get(MLEvent, __import__("uuid").UUID(chosen["id"]))
        dataset = await db.get(MLEvent, model.parent_id)
        started = time.perf_counter()
        count = await db.scalar(select(func.count()).select_from(JournalLine))
        query = time.perf_counter() - started
    with tempfile.TemporaryDirectory(prefix="phase9-benchmark-") as folder:
        p = Path(folder)
        (p / "dataset.json").write_bytes(read_object(dataset.body["object"]))
        for name, obj in model.body["artifacts"].items():
            (p / name).write_bytes(read_object(obj))
        subprocess.run(
            [
                "node",
                "--max-old-space-size=1536",
                str(ROOT / "ml-engine/dist/src/benchmark.js"),
                str(p / "dataset.json"),
                str(p),
                str(ROOT / "docs/phase-9/performance.json"),
            ],
            check=True,
            timeout=300,
        )
    f = ROOT / "docs/phase-9/performance.json"
    data = json.loads(f.read_text())
    data["database"] = {"journal_lines": count, "count_query_seconds": query}
    f.write_text(json.dumps(data, indent=2) + "\n")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
