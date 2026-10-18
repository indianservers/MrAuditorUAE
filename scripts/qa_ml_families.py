"""Fit every remaining implemented family on the real synthetic registry dataset."""

import asyncio
import json
import sys
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.dependencies import Context
from app.core.permissions import ROLE_PERMISSIONS
from app.db.session import Session, engine, tenant_context
from app.modules.ml import service
from app.modules.ml.models import MLEvent
from qa_campaign import guard
from sqlalchemy import select


async def main():
    out = ROOT / "docs/qa-campaign"
    data = json.loads((out / "dataset.json").read_text(encoding="utf8"))
    user = next(u for u in data["users"] if u["role"] == "Firm Administrator")
    ctx = Context(
        uuid.UUID(user["id"]),
        uuid.UUID(data["tenant_id"]),
        frozenset(ROLE_PERMISSIONS["Firm Administrator"]),
    )
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, data["tenant_id"])
        source = await db.scalar(
            select(MLEvent)
            .where(MLEvent.kind == "dataset")
            .order_by(MLEvent.created_at)
            .limit(1)
        )
        assert source and source.body["synthetic"]
        source_id = str(source.id)
    results = []
    for family in ["autoencoder", "risk-ranking", "account-classifier"]:
        start = time.perf_counter()
        record = {
            "family": family,
            "source_id": source_id,
            "production_promoted": False,
        }
        try:
            async with Session() as db, db.begin():
                await guard(db)
                await tenant_context(db, data["tenant_id"])
                result = await service.execute_job(
                    db,
                    ctx,
                    {
                        "operation": "train",
                        "source_id": source_id,
                        "config": {
                            "family": family,
                            "epochs": 3,
                            "batch_size": 32,
                            "learning_rate": 0.003,
                            "seed": 7,
                            "patience": 2,
                        },
                    },
                )
                model = await db.get(MLEvent, uuid.UUID(result["id"]))
                assert model.body["production_validated"] is False
                record.update(
                    status="PASS_ARTIFACT_WORKFLOW",
                    model_id=result["id"],
                    metrics=model.body["metrics"],
                )
        except Exception as exc:  # noqa: BLE001 - record each failure and continue other independent families
            record.update(
                status="FAIL", error=str(exc), traceback=traceback.format_exc()
            )
        record["seconds"] = time.perf_counter() - start
        results.append(record)
        (out / "ml-family-results.json").write_text(
            json.dumps(results, indent=2), encoding="utf8"
        )
        print(
            json.dumps(
                {k: v for k, v in record.items() if k not in {"metrics", "traceback"}}
            ),
            flush=True,
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
