"""Guarded worker/scheduler, extraction oracle, and retrieval measurements."""

import asyncio
import json
import logging
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
import psutil
from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import JournalLine
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.enterprise_ai.models import Chunk, Extraction
from app.workers.enterprise_ai import dispatch_due
from sqlalchemy import func, select


async def main():
    demo = json.loads(
        (ROOT / "docs/phase-11/demo-verification.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "docs/phase-7/demo-manifest.json").read_text(encoding="utf-8")
    )
    admin = manifest["users"][1]
    eid = demo["engagement_id"]
    base = f"/api/v1/ai/engagements/{eid}"
    headers = {
        "Authorization": "Bearer " + access_token(uuid.UUID(admin["id"])),
        "X-Tenant-ID": str(DEMO_TENANT),
    }
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        count = await db.scalar(select(func.count()).select_from(JournalLine))
        docs = await db.scalar(
            select(func.count())
            .select_from(Extraction)
            .where(Extraction.tenant_id == DEMO_TENANT)
        )
        chunks = await db.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.tenant_id == DEMO_TENANT)
        )
        oracle = []
        for fixture in demo["extractions"]:
            ext = await db.get(Extraction, uuid.UUID(fixture["id"]))
            oracle.append(
                ext.body["fields"]["amount"]["value"] == fixture["expected_amount"]
                and ext.body["fields"]["amount"]["page"] == fixture["expected_page"]
            )
    output = {
        "synthetic": True,
        "financial_lines": count,
        "indexed_documents": docs,
        "chunks": chunks,
        "amount_and_page_oracle": {"correct": sum(oracle), "total": len(oracle)},
        "semantic_benchmark": "NOT_CONFIGURED",
        "external_model_tokens": "NOT_MEASURED; no external model used",
        "external_model_cost": "NOT_MEASURED",
        "rss_before_bytes": psutil.Process().memory_info().rss,
    }
    logging.getLogger("auditos").setLevel(logging.WARNING)
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=120,
    ) as c:

        async def call(path, body=None, method="POST"):
            r = await c.request(
                method,
                path,
                headers=headers,
                **({"json": body} if body is not None else {}),
            )
            assert r.status_code < 400, (path, r.status_code, r.text)
            return r.json()

        worker_run = await call(
            "/api/v1/ai/command",
            {
                "engagement_id": eid,
                "task": "evidence-request",
                "prompt": "Synthetic real worker recovery verification",
                "idempotency_key": "phase11-worker-proof-v1",
                "inputs": {"query": "SYNTHETIC-P11-0000", "limit": 2},
            },
        )
        await call(base + f"/investigations/{worker_run['id']}/dispatch")

        async def wait_run(identifier):
            for _ in range(120):
                result = await call(
                    base + f"/investigations/{identifier}", method="GET"
                )
                if result["state"] in {"COMPLETED", "PARTIALLY_COMPLETED", "FAILED"}:
                    assert result["state"] != "FAILED"
                    return result
                await asyncio.sleep(0.25)
            raise RuntimeError("Real worker did not complete within 30 seconds")

        completed = await wait_run(worker_run["id"])
        before = len([e for e in completed["events"] if e["kind"] == "step"])
        await call(base + f"/investigations/{worker_run['id']}/dispatch")
        replay = await wait_run(worker_run["id"])
        assert before == len([e for e in replay["events"] if e["kind"] == "step"])
        output["real_worker"] = {
            "run_id": worker_run["id"],
            "state": completed["state"],
            "steps": before,
            "replay_duplicates": 0,
        }
        schedule = await call(
            base + "/schedules",
            {
                "task": "evidence-request",
                "frequency": "monthly",
                "next_due": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "active": True,
                "inputs": {"query": "SYNTHETIC-P11-0000", "limit": 1},
            },
        )
        output["scheduler_tick"] = await dispatch_due()
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            from app.modules.enterprise_ai.models import Event

            event = await db.scalar(
                select(Event).where(
                    Event.tenant_id == DEMO_TENANT,
                    Event.kind == "queued",
                    Event.body["schedule_id"].astext == schedule["id"],
                )
            )
            scheduled_id = str(event.run_id)
        scheduled = await wait_run(scheduled_id)
        await call(base + f"/schedules/{schedule['id']}/pause")
        output["scheduled_run"] = {
            "id": scheduled_id,
            "state": scheduled["state"],
            "paused_after_proof": True,
        }
        measurements = {}
        for name, path in {
            "keyword_1000_documents": base + "/knowledge/search?query=SYNTHETIC-P11",
            "document_directory": base + "/documents",
            "workflow_directory": base + "/investigations",
        }.items():
            timings = []
            for _ in range(5):
                start = time.perf_counter()
                await call(path, method="GET")
                timings.append(time.perf_counter() - start)
            measurements[name] = {
                "samples": 5,
                "p50_seconds": statistics.median(timings),
                "max_seconds": max(timings),
            }
        start = time.perf_counter()
        await asyncio.gather(
            *(
                call(base + "/knowledge/search?query=SYNTHETIC-P11", method="GET")
                for _ in range(5)
            )
        )
        output["concurrent_requests"] = {
            "requests": 5,
            "identities": 1,
            "seconds": time.perf_counter() - start,
            "scope": "Same authorized synthetic investigator; not a multi-user load qualification",
        }
        output["latency"] = measurements
        output["rss_after_bytes"] = psutil.Process().memory_info().rss
        output["memory_basis"] = (
            "Verification process RSS before/after; not sampled peak API or worker RSS"
        )
        # Export the actual application report, never a hand-authored substitute.
        folder = ROOT / "docs/phase-11/exports"
        folder.mkdir(exist_ok=True)
        for kind in ["pdf", "docx"]:
            r = await c.get(
                base + f"/investigations/{worker_run['id']}/export/{kind}",
                headers=headers,
            )
            assert r.status_code == 200, r.text
            (folder / f"synthetic-investigation-draft.{kind}").write_bytes(r.content)
        output["export_run_id"] = worker_run["id"]
    (ROOT / "docs/phase-11/verification.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(json.dumps(output, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
