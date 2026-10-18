"""Measured synthetic workload; no market-comparability claims."""

import asyncio
import json
import sys
import time
import uuid
from decimal import Decimal as D
from pathlib import Path
from threading import Event, Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
import psutil
from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.tp.calculations import allocate, benchmark, loan_schedule
from app.modules.tp.models import Observation
from app.modules.tp.schemas import Allocation, Loan, Study
from app.modules.tp.service import clean
from sqlalchemy import event as sql_event
from sqlalchemy import select, text


async def main():
    sql_queries = 0

    def counted(*args):
        nonlocal sql_queries
        sql_queries += 1

    sql_event.listen(engine.sync_engine, "before_cursor_execute", counted)
    process = psutil.Process()
    memory = {
        "rss_before_bytes": process.memory_info().rss,
        "sampled_peak_rss_bytes": process.memory_info().rss,
    }
    stopped = Event()

    def sample():
        while not stopped.wait(0.01):
            memory["sampled_peak_rss_bytes"] = max(
                memory["sampled_peak_rss_bytes"], process.memory_info().rss
            )

    sampler = Thread(target=sample, daemon=True)
    sampler.start()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/phase-7/demo-manifest.json").read_text())
    tp = json.loads((root / "docs/phase-8/demo-manifest.json").read_text())
    result = {
        "synthetic": True,
        "timings_seconds": {},
        "scope": "Local sequential workload; no production capacity claim",
    }
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        start = time.perf_counter()
        row = (
            await db.execute(
                text("""WITH sample AS MATERIALIZED (
          SELECT description,counterparty FROM journal_lines
          WHERE tenant_id=:tenant ORDER BY id LIMIT 100000)
          SELECT count(*) AS scanned, count(*) FILTER (WHERE
          lower(trim(counterparty)) = ANY(ARRAY['synthetic overseas common parent'])
          OR description ~* '\\m(intercompany|affiliate|related.party|director|royalty|treasury|management.fee|loan)\\M') AS candidates
          FROM sample"""),
                {
                    "tenant": DEMO_TENANT,
                    "period": uuid.UUID(manifest["engagements"][0]["period_id"]),
                },
            )
        ).one()
        result["candidate_scan"] = {
            "source_rows": row.scanned,
            "candidates": row.candidates,
            "scope": "Same exact-name/keyword predicate over first 100,000 existing synthetic source rows; candidate only",
        }
        result["timings_seconds"]["candidate_scan_100k"] = time.perf_counter() - start
        loans = (
            await db.scalars(
                select(AuditRecord)
                .where(
                    AuditRecord.tenant_id == DEMO_TENANT,
                    AuditRecord.engagement_id == uuid.UUID(tp["engagement_id"]),
                    AuditRecord.kind == "tp-loan",
                )
                .order_by(AuditRecord.id)
            )
        ).all()
        study = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == DEMO_TENANT,
                AuditRecord.engagement_id == uuid.UUID(tp["engagement_id"]),
                AuditRecord.reference == "P8-STUDY-1",
            )
        )
        bodies = [Loan.model_validate(clean(x.body)) for x in loans]
        observations = (
            await db.scalars(
                select(Observation).where(
                    Observation.tenant_id == DEMO_TENANT,
                    Observation.dataset_id == uuid.UUID(study.body["dataset_ids"][0]),
                )
            )
        ).all()
        multi_year = [
            {
                **{
                    key: getattr(row, key)
                    for key in [
                        "company_key",
                        "currency",
                        "revenue",
                        "cost_sales",
                        "opex",
                        "assets",
                        "value",
                    ]
                },
                "id": str(row.id) + "-" + str(year),
                "fiscal_year": year,
            }
            for year in [2024, 2025, 2026]
            for row in observations
        ]
        model = Study.model_validate(clean(study.body)).model_copy(
            update={
                "fiscal_years": [2024, 2025, 2026],
                "aggregation": "company_weighted",
            }
        )
    start = time.perf_counter()
    multi_result = benchmark(multi_year, model)
    result["timings_seconds"]["weighted_15000_observations_3_years"] = (
        time.perf_counter() - start
    )
    result["multi_year"] = {
        "companies": multi_result["n"],
        "observations": multi_result["observations_used"],
        "scope": "In-memory three-year replicas of synthetic observations; calculation benchmark, not a stored multi-year economic study",
    }
    start = time.perf_counter()
    for _ in range(50):
        for body in bodies:
            loan_schedule(body)
    result["timings_seconds"]["loan_schedules_1000"] = time.perf_counter() - start
    result["loan_schedules"] = len(bodies) * 50
    start = time.perf_counter()
    allocation = allocate(
        D("999999999.99"), [Allocation(segment=str(i), weight=1) for i in range(1000)]
    )
    result["timings_seconds"]["allocation_1000"] = time.perf_counter() - start
    result["allocation_difference"] = str(
        D("999999999.99") - sum((x["amount"] for x in allocation), D(0))
    )
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=300,
    ) as c:
        headers = {
            "Authorization": "Bearer "
            + access_token(uuid.UUID(manifest["users"][1]["id"])),
            "X-Tenant-ID": str(DEMO_TENANT),
        }
        start=time.perf_counter();query_start=sql_queries
        matrix=await c.post(f"/api/v1/tp/engagements/{tp['engagement_id']}/matrix/{tp['profile_id']}",headers=headers)
        assert matrix.status_code==201,matrix.text
        result["controlled_matrix_100"]={"seconds":time.perf_counter()-start,"sql_queries":sql_queries-query_start,"rows":matrix.json()["results"]["rows_total"],"response_bytes":len(matrix.content)}
        start = time.perf_counter()
        query_start = sql_queries
        response = await c.post(
            f"/api/v1/tp/engagements/{tp['engagement_id']}/calculate/{study.id}",
            headers={
                "Authorization": "Bearer "
                + access_token(uuid.UUID(manifest["users"][1]["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            },
        )
        assert response.status_code == 201, response.text
        result["timings_seconds"]["screened_observation_calculation_5000"] = (
            time.perf_counter() - start
        )
        result["benchmark_population"] = response.json()["results"]["n"]
        result["benchmark_api"] = {
            "sql_queries": sql_queries - query_start,
            "response_bytes": len(response.content),
            "transport": "in-process ASGI including auth/permissions/RLS; excludes network",
        }
        tp["studies"][0] = response.json()["id"]
        (root / "docs/phase-8/demo-manifest.json").write_text(
            json.dumps(tp, indent=2) + "\n"
        )
        start = time.perf_counter()
        page = await c.get(
            f"/api/v1/tp/engagements/{tp['engagement_id']}/runs/{response.json()['id']}?limit=50",
            headers=headers,
        )
        assert page.status_code == 200, page.text
        result["paginated_run_api"] = {
            "seconds": time.perf_counter() - start,
            "response_bytes": len(page.content),
            "population_rows": len(page.json()["results"]["population"]),
        }
        issued = root / "docs/phase-8/issued-demo.json"
        if issued.exists():
            document = json.loads(issued.read_text())
            result["localfile_exports"] = {}
            for format in ["pdf", "docx", "xlsx", "json"]:
                start = time.perf_counter()
                query_start = sql_queries
                exported = await c.get(
                    f"/api/v1/tp/engagements/{tp['engagement_id']}/runs/{document['run_id']}/export/{format}",
                    headers=headers,
                )
                assert exported.status_code == 200, exported.text
                result["localfile_exports"][format] = {
                    "seconds": time.perf_counter() - start,
                    "bytes": len(exported.content),
                    "sql_queries": sql_queries - query_start,
                }
    stopped.set()
    sampler.join(0.2)
    memory["rss_after_bytes"] = process.memory_info().rss
    result["process_memory"] = {
        **memory,
        "scope": "Sampled whole-process RSS including libraries and all sequential workloads; not per-operation memory",
    }
    result["sql_queries_total"] = sql_queries
    (root / "docs/phase-8/performance.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
