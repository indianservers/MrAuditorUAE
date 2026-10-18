"""Independent read-only PostgreSQL checks on the synthetic campaign database."""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import Session, engine, tenant_context


async def main():
    tenant = json.loads((ROOT / "docs/qa-campaign/dataset.json").read_text())[
        "tenant_id"
    ]
    async with Session() as db, db.begin():
        name = await db.scalar(text("select current_database()"))
        assert name == "auditos_qa_campaign_demo", "Synthetic campaign database only"
        await tenant_context(db, tenant)
        checks = {}
        for key, query in {
            "clients": "select count(*) from clients",
            "journal_lines": "select count(*) from journal_lines",
            "orphan_journal_lines": "select count(*) from journal_lines l left join journal_entries e on e.id=l.journal_id where e.id is null",
            "orphan_revisions": "select count(*) from audit_record_versions v left join audit_records r on r.id=v.record_id where r.id is null",
            "duplicate_client_codes": "select count(*) from (select code from clients group by tenant_id,code having count(*)>1) q",
            "unbalanced_journals": "select count(*) from (select journal_id from journal_lines group by journal_id having sum(debit)<>sum(credit)) q",
            "non_superuser": "select not rolsuper and not rolbypassrls from pg_roles where rolname=current_user",
        }.items():
            checks[key] = await db.scalar(text(query))
        checks["lifecycle_events"] = [
            dict(r)
            for r in (
                await db.execute(
                    text(
                        "select action,count(*) as count from audit_events where action in ('clients.archived','clients.restored','audit.lifecycle') group by action"
                    )
                )
            ).mappings()
        ]
        checks["synthetic_browser_clients"] = [
            dict(r)
            for r in (
                await db.execute(
                    text(
                        "select id::text, code, name, status, version from clients where code like 'CRUD-%' order by code"
                    )
                )
            ).mappings()
        ]
        worker_receipt = ROOT / "docs/qa-crud/worker-results.json"
        if worker_receipt.exists():
            worker = json.loads(worker_receipt.read_text())
            eid = json.loads((ROOT / "docs/qa-campaign/dataset.json").read_text())[
                "companies"
            ][0]["engagements"][0]["id"]
            checks["worker_dataset_rows_sql"] = int(
                await db.scalar(
                    text(
                        "select body->>'total_rows' from ml_registry_events where id=cast(:id as uuid) and kind='dataset'"
                    ),
                    {"id": worker["dataset_id"]},
                )
            )
            checks["worker_active_journal_rows_sql"] = await db.scalar(
                text(
                    "select count(*) from journal_lines l join import_batches b on b.id=l.batch_id join engagements e on e.entity_id=l.entity_id and e.period_id=l.period_id where e.id=cast(:eid as uuid) and b.status='active'"
                ),
                {"eid": eid},
            )
            assert (
                checks["worker_dataset_rows_sql"]
                == checks["worker_active_journal_rows_sql"]
                == worker["rows"]
            )
    assert all(
        checks[key] == 0
        for key in [
            "orphan_journal_lines",
            "orphan_revisions",
            "duplicate_client_codes",
            "unbalanced_journals",
        ]
    )
    assert checks["non_superuser"] is True
    original_engine = create_async_engine(
        "postgresql+asyncpg://auditos_phase4_app@127.0.0.1:55432/auditos_phase7_demo"
    )
    async with original_engine.begin() as connection:
        await connection.execute(
            text("select set_config('app.tenant_id', :tenant, true)"),
            {"tenant": "8733db06-81bc-59b3-afcc-bf0f4c0cd8a2"},
        )
        checks["original_demo_clients"] = await connection.scalar(
            text("select count(*) from clients")
        )
        checks["original_demo_journal_lines"] = await connection.scalar(
            text("select count(*) from journal_lines")
        )
    await original_engine.dispose()
    await engine.dispose()
    (ROOT / "docs/qa-crud/database-integrity.json").write_text(
        json.dumps({"database": name, "tenant": tenant, "checks": checks}, indent=2),
        encoding="utf8",
    )
    print(json.dumps(checks, default=str))


if __name__ == "__main__":
    asyncio.run(main())
