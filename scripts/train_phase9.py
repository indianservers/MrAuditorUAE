"""Real secured API -> Redis/Celery -> dedicated TensorFlow.js child worker."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx

from app.core.security import access_token

ROOT = Path(__file__).resolve().parents[1]


async def main():
    demo = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    dataset = json.loads((ROOT / "docs/phase-9/demo-dataset.json").read_text())
    h = {
        "Authorization": "Bearer " + access_token(demo["users"][1]["id"]),
        "X-Tenant-ID": demo["tenant_id"],
    }
    runs = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58004", timeout=30) as c:
        for family in [
            "autoencoder",
            "journal-classifier",
            "risk-ranking",
            "account-classifier",
        ]:
            r = await c.post(
                "/api/v1/ml/training-jobs",
                headers=h,
                json={
                    "source_id": dataset["dataset_id"],
                    "family": family,
                    "epochs": 12,
                    "batch_size": 128,
                    "learning_rate": 0.003,
                    "seed": 2027,
                    "patience": 3,
                },
            )
            r.raise_for_status()
            job = r.json()
            print(json.dumps({"family": family, "job": job}), flush=True)
            for _ in range(500):
                r = await c.get("/api/v1/jobs/" + job["id"], headers=h)
                r.raise_for_status()
                state = r.json()
                if state["status"] in ["completed", "failed", "cancelled"]:
                    break
                await asyncio.sleep(2)
            if state["status"] != "completed":
                raise RuntimeError(state)
            r = await c.get(
                "/api/v1/ml/events/" + state["result"]["resource_id"], headers=h
            )
            r.raise_for_status()
            model = r.json()
            runs.append(
                {
                    "id": model["id"],
                    "job_id": job["id"],
                    "family": family,
                    "metrics": model["body"]["metrics"],
                }
            )
            (ROOT / "docs/phase-9/training-results.json").write_text(
                json.dumps(runs, indent=2) + "\n"
            )
            print(
                json.dumps(
                    {
                        "family": family,
                        "model_id": model["id"],
                        "counts": model["body"]["metrics"]["counts"],
                        "seconds": model["body"]["metrics"]["resources"]["seconds"],
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
