"""Explicit synthetic PostgreSQL benchmark; requires BENCHMARK_DATABASE=1 on a disposable DB."""

import asyncio
import csv
import json
import os
import sys
import tempfile
import threading
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import Client, FinancialPeriod, LegalEntity, Membership, Tenant, User
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import ImportSnapshot
from app.modules.accounting.schemas import ImportOptions
from app.modules.accounting.service import commit, upload, validate
from app.modules.audit_analytics.schemas import AnalyticsRequest
from app.modules.audit_analytics.service import analytics
from app.modules.reconciliation.service import run_reconciliation


async def main():
    if os.getenv("BENCHMARK_DATABASE") != "1" or settings().environment != "development":
        raise SystemExit("Use a disposable development database and explicit BENCHMARK_DATABASE=1")
    count = int(os.getenv("BENCHMARK_LINES", "10000"))
    peak = [0]
    stop = threading.Event()

    def memory():
        while not stop.wait(0.02):
            peak[0] = max(peak[0], psutil.Process().memory_info().rss)

    monitor = threading.Thread(target=memory, daemon=True)
    monitor.start()
    async with Session() as db, db.begin():
        user = await db.scalar(select(User).where(User.status == "active"))
        if not user:
            raise SystemExit("Run integration setup first; no active test identity exists")
        tenant = Tenant(name="SYNTHETIC BENCHMARK ONLY")
        db.add(tenant)
        await db.flush()
        await tenant_context(db, str(tenant.id))
        db.add(Membership(tenant_id=tenant.id, user_id=user.id))
        client = Client(
            tenant_id=tenant.id,
            created_by=user.id,
            code="SYNTHETIC",
            name="FICTIONAL benchmark company",
        )
        db.add(client)
        await db.flush()
        entity = LegalEntity(
            tenant_id=tenant.id,
            created_by=user.id,
            client_id=client.id,
            name="SYNTHETIC",
            country="AE",
            jurisdiction="Synthetic",
            functional_currency="AED",
            presentation_currency="AED",
        )
        db.add(entity)
        await db.flush()
        period = FinancialPeriod(
            tenant_id=tenant.id,
            created_by=user.id,
            entity_id=entity.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        db.add(period)
        await db.flush()
        options = ImportOptions(
            client_id=client.id,
            entity_id=entity.id,
            period_id=period.id,
            expected_rows=count,
            source_complete=True,
        )
        ctx = Context(user.id, tenant.id, frozenset())
        tenant_id = tenant.id
    with tempfile.TemporaryFile(mode="w+", newline="", encoding="utf-8") as source:
        writer = csv.writer(source)
        writer.writerow(
            ["account_code", "journal_ref", "posting_date", "debit", "credit", "source_id"]
        )
        total = Decimal(0)
        for index in range(count):
            value = Decimal(index // 2 % 1000 + 1) / 100
            writer.writerow(
                [
                    "A" if index % 2 == 0 else "B",
                    str(index // 2),
                    "2026-06-01",
                    value if index % 2 == 0 else 0,
                    value if index % 2 else 0,
                    str(index),
                ]
            )
            if index % 2 == 0:
                total += value
        source.flush()
        source.seek(0)
        options = options.model_copy(update={"expected_debit": total, "expected_credit": total})
        async with Session() as db, db.begin():
            await tenant_context(db, str(tenant_id))
            start = time.perf_counter()
            batch = await upload(
                db, ctx, options, "SYNTHETIC-benchmark.csv", source.buffer, "benchmark"
            )
            identifier = batch.id
            upload_seconds = time.perf_counter() - start
        async with Session() as db, db.begin():
            await tenant_context(db, str(tenant_id))
            start = time.perf_counter()
            batch = await validate(db, ctx, identifier, "benchmark")
            validation_seconds = time.perf_counter() - start
            assert batch.status == "validated"
        async with Session() as db, db.begin():
            await tenant_context(db, str(tenant_id))
            start = time.perf_counter()
            await commit(db, ctx, identifier, "benchmark")
            commit_seconds = time.perf_counter() - start
            snapshot = await db.scalar(
                select(ImportSnapshot).where(
                    ImportSnapshot.batch_id == identifier, ImportSnapshot.tenant_id == tenant_id
                )
            )
            snapshot_id = snapshot.id
        async with Session() as db, db.begin():
            await tenant_context(db, str(tenant_id))
            start = time.perf_counter()
            result = await run_reconciliation(db, ctx, snapshot_id, None, Decimal(0))
            reconciliation_seconds = time.perf_counter() - start
        async with Session() as db, db.begin():
            await tenant_context(db, str(tenant_id))
            start = time.perf_counter()
            await analytics(db, ctx, AnalyticsRequest(snapshot_id=snapshot_id))
            analytics_seconds = time.perf_counter() - start
    stop.set()
    monitor.join()
    await engine.dispose()
    result = {
        "synthetic": True,
        "mode": "real PostgreSQL service pipeline, not HTTP; durations exclude final transaction commit overhead",
        "lines": count,
        "upload_seconds": upload_seconds,
        "validation_seconds": validation_seconds,
        "ledger_commit_seconds": commit_seconds,
        "reconciliation_seconds": reconciliation_seconds,
        "analytics_with_persistence_seconds": analytics_seconds,
        "peak_python_rss_bytes": peak[0],
        "database_server_memory_excluded": True,
    }
    print(json.dumps(result))
    output = Path(__file__).resolve().parents[1] / "docs/evidence/phase-2-postgres-benchmark.json"
    output.parent.mkdir(exist_ok=True, parents=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")


asyncio.run(main())
