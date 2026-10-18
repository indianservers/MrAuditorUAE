"""Verify fresh ledger features through the real QA broker and restarted worker."""

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main():
    assert os.environ.get("DATABASE_URL", "").endswith("/auditos_qa_campaign_demo")
    data = json.loads((ROOT / "docs/qa-campaign/dataset.json").read_text())
    eid = data["companies"][0]["engagements"][0]["id"]
    started = time.perf_counter()
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:58009/api/v1", timeout=60
    ) as client:
        login = await client.post(
            "/auth/login",
            data={
                "username": "qa.admin@auditos.example",
                "password": os.environ["QA_PASSWORD"],
            },
        )
        assert login.status_code == 200, login.status_code
        headers = {
            "Authorization": "Bearer " + login.json()["access_token"],
            "X-Tenant-ID": data["tenant_id"],
        }
        created = await client.post(f"/ml/engagements/{eid}/datasets", headers=headers)
        assert created.status_code == 202, created.text
        identifier = created.json()["id"]
        result = None
        while time.perf_counter() - started < 90:
            response = await client.get("/ml/jobs/" + identifier, headers=headers)
            assert response.status_code == 200, response.text
            result = response.json()
            if result["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.5)
        assert result and result["status"] == "completed", result
        detail = await client.get(
            "/ml/events/" + result["result"]["resource_id"], headers=headers
        )
        assert detail.status_code == 200, detail.text
        event = detail.json()
        assert event["freshness"]["status"] == "CURRENT", event["freshness"]
        assert (
            event["body"]["source_snapshots"]
            and event["body"]["account_mapping_receipt"]
        )
        output = {
            "transport": "HTTP -> Redis 4 -> separately restarted Celery worker -> PostgreSQL -> HTTP read-time freshness",
            "job_id": identifier,
            "status": result["status"],
            "dataset_id": event["id"],
            "rows": event["body"]["total_rows"],
            "source_snapshot_receipts": len(event["body"]["source_snapshots"]),
            "mapping_receipts": len(event["body"]["account_mapping_receipt"]),
            "freshness": event["freshness"],
            "elapsed_seconds": time.perf_counter() - started,
        }
        (ROOT / "docs/qa-crud/worker-results.json").write_text(
            json.dumps(output, indent=2), encoding="utf8"
        )
        print(json.dumps(output))


if __name__ == "__main__":
    asyncio.run(main())
