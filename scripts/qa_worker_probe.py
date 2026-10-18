"""Dispatch actual broker jobs and verify persisted worker completion through HTTP."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx


async def main():
    out = ROOT / "docs/qa-campaign"
    data = json.loads((out / "dataset.json").read_text(encoding="utf8"))
    started = time.perf_counter()
    jobs = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58009", timeout=60) as c:
        login = await c.post(
            "/api/v1/auth/login",
            data={
                "username": "qa.admin@auditos.example",
                "password": os.environ["QA_PASSWORD"],
            },
        )
        assert login.status_code == 200, login.text
        h = {
            "Authorization": "Bearer " + login.json()["access_token"],
            "X-Tenant-ID": data["tenant_id"],
        }
        for batch in data["batches"][:3]:
            r = await c.post(
                "/api/v1/analytics/runs?background=true",
                headers=h,
                json={"snapshot_id": batch["snapshot_id"]},
            )
            assert r.status_code == 201, r.text
            jobs.append(r.json())
        for i, job in enumerate(jobs):
            while time.perf_counter() - started < 120:
                r = await c.get("/api/v1/jobs/" + job["id"], headers=h)
                assert r.status_code == 200, r.text
                result = r.json()
                if result["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.5)
            jobs[i] = result
    elapsed = time.perf_counter() - started
    output = {
        "transport": "Real HTTP API -> Redis broker -> separately running Celery solo worker -> persisted PostgreSQL job -> HTTP poll",
        "jobs": jobs,
        "elapsed_seconds": elapsed,
        "completed": sum(j["status"] == "completed" for j in jobs),
        "failed": sum(j["status"] == "failed" for j in jobs),
        "jobs_per_second": sum(j["status"] == "completed" for j in jobs) / elapsed,
    }
    (out / "worker-results.json").write_text(
        json.dumps(output, indent=2), encoding="utf8"
    )
    print(json.dumps({k: v for k, v in output.items() if k != "jobs"}))
    assert output["completed"] == 3, output


if __name__ == "__main__":
    asyncio.run(main())
