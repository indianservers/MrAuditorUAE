"""Measured local synthetic GRC APIs and existing analytics over the retained population."""

# ruff: noqa: E402
import asyncio
import csv
import json
import logging
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from sqlalchemy import select

from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import Account, Journal, JournalLine
from app.modules.audit_analytics.engine import COLUMNS, AnalyticsEngine
from app.modules.audit_analytics.schemas import AnalyticsRequest
from app.modules.demo.guard import DEMO_TENANT, guard


async def main():
    demo = json.loads((ROOT / "docs/phase-10/demo-verification.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text(encoding="utf-8"))
    result = {
        "environment": "Local in-process ASGI / PostgreSQL / DuckDB, synthetic data; no network SLA",
        "api": {},
    }
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
    from app.main import app

    logging.getLogger("auditos").setLevel(logging.WARNING)
    headers = {
        "Authorization": "Bearer " + access_token(uuid.UUID(manifest["users"][1]["id"])),
        "X-Tenant-ID": str(DEMO_TENANT),
    }
    base = f"/api/v1/grc/engagements/{demo['engagement_id']}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=120
    ) as c:
        for name, path in {
            "dashboard": base + "/dashboard",
            "rcm_300": base + "/rcm?limit=500",
            "risk_100": base + "/records/risk?limit=100",
            "controls_200_page": base + "/records/control?limit=100",
            "alert_page_50": base + "/alerts?limit=50",
            "board_package": base + "/board/packages/" + demo["board_publication"],
        }.items():
            timings = []
            for _ in range(5):
                started = time.perf_counter()
                r = await c.get(path, headers=headers)
                assert r.status_code == 200, r.text
                timings.append((time.perf_counter() - started) * 1000)
            result["api"][name] = {
                "p50_ms": round(statistics.median(timings), 2),
                "max_ms": round(max(timings), 2),
                "samples": len(timings),
                "bytes": len(r.content),
                "total": r.json().get("total"),
            }
        started = time.perf_counter()
        for offset in range(0, 500, 50):
            r = await c.get(base + f"/alerts?limit=50&offset={offset}", headers=headers)
            assert r.status_code == 200 and len(r.json()["items"]) == 50
        result["api"]["500_alerts_paged_seconds"] = round(time.perf_counter() - started, 3)
    with tempfile.TemporaryDirectory(prefix="grc-benchmark-") as directory:
        path = Path(directory) / "retained-population.csv"
        count = 0
        started = time.perf_counter()
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            cursor = await db.stream(
                select(JournalLine, Account.code, Account.classification, Journal.reference)
                .join(Account, Account.id == JournalLine.account_id)
                .join(Journal, Journal.id == JournalLine.journal_id)
                .where(JournalLine.tenant_id == DEMO_TENANT)
                .order_by(JournalLine.id)
            )
            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=COLUMNS)
                writer.writeheader()
                async for partition in cursor.partitions(1000):
                    for row, code, category, reference in partition:
                        writer.writerow(
                            {
                                "id": str(row.id),
                                "account_code": code,
                                "category": category,
                                "journal_ref": str(row.journal_id) + ":" + reference,
                                "posting_date": str(row.posting_date),
                                "document_date": str(row.document_date)
                                if row.document_date
                                else "",
                                "debit": str(row.base_debit),
                                "credit": str(row.base_credit),
                                "amount": str(row.base_debit + row.base_credit),
                                "description": row.description,
                                "counterparty": row.counterparty,
                            }
                        )
                        count += 1
        extracted = time.perf_counter() - started
        with path.open(encoding="utf-8", newline="") as file:
            analytics = AnalyticsEngine(csv.DictReader(file))
        loaded = time.perf_counter() - started - extracted
        tick = time.perf_counter()
        try:
            summaries = analytics.evaluate(
                AnalyticsRequest(snapshot_id=uuid.UUID(demo["snapshot_id"]))
            )
        finally:
            analytics.close()
        result["retained_population"] = {
            "rows": count,
            "extract_seconds": round(extracted, 3),
            "duckdb_load_seconds": round(loaded, 3),
            "rules_seconds": round(time.perf_counter() - tick, 3),
            "rules": len(summaries),
            "status_counts": {
                status: sum(x["status"] == status for x in summaries)
                for status in sorted({x["status"] for x in summaries})
            },
            "scope": "Cross-period synthetic benchmark only; not an engagement conclusion",
            "memory_limit": "DuckDB 1GB, two threads; peak process RSS not measured",
        }
    result["engagement_monitors"] = [
        {
            "rule": x["rule"],
            "seconds": x["seconds"],
            "population": x["results"].get("population"),
            "status": x["results"]["status"],
        }
        for x in demo["monitoring"]
    ]
    (ROOT / "docs/phase-10/performance.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
