"""Read-only financial population checks and real API access probes in the guarded demo."""

import asyncio
import json
import sys
import time
import uuid
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from sqlalchemy import text

from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.demo.guard import DEMO_TENANT, guard

ROOT = Path(__file__).resolve().parents[1]


async def main():
    manifest = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    report = {"database_checks": [], "role_probes": [], "api_latency_seconds": []}
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        count = await db.scalar(text("SELECT count(*) FROM journal_lines"))
        assert count >= 250000
        report["journal_lines"] = count
        unbalanced = await db.scalar(
            text(
                "SELECT count(*) FROM (SELECT journal_id FROM journal_lines GROUP BY journal_id HAVING sum(base_debit-base_credit) <> 0) j"
            )
        )
        assert unbalanced == 0
        report["unbalanced_journals"] = unbalanced
        invalid_tb = await db.scalar(
            text("SELECT count(*) FROM trial_balance_lines WHERE closing <> opening+debit-credit")
        )
        assert invalid_tb == 0
        report["invalid_tb_equations"] = invalid_tb
        for e in manifest["engagements"]:
            balances = dict(
                (
                    await db.execute(
                        text(
                            "SELECT a.code, sum(j.base_debit-j.base_credit) FROM journal_lines j JOIN accounts a ON a.id=j.account_id WHERE j.snapshot_id=:sid GROUP BY a.code"
                        ),
                        {"sid": uuid.UUID(e["snapshot_id"])},
                    )
                ).all()
            )
            for code, expected in e["expected_balances"].items():
                assert D(balances.get(code, 0)) == D(expected), (e["id"], code)
            report["database_checks"].append(
                {"engagement_id": e["id"], "gl_expected_balances": "PASS"}
            )
        report["rls_tables"] = [
            dict(row._mapping)
            for row in (
                await db.execute(
                    text(
                        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('vat_computation_runs','synthetic_datasets','journal_lines','audit_records')"
                    )
                )
            ).all()
        ]
    e = next(x for x in manifest["engagements"] if x["year"] == 2026)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58003/api/v1", timeout=90) as client:
        for index, user in enumerate(manifest["users"]):
            headers = {
                "Authorization": "Bearer " + access_token(uuid.UUID(user["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            }
            r = await client.get(f"/vat/engagements/{e['id']}/workspace", headers=headers)
            assert r.status_code in {200, 401, 403}
            if index in {0, 14, 15, 16, 17, 18, 23, 24}:
                assert r.status_code in {401, 403}
            if index in {1, 20, 21, 22}:
                assert r.status_code == 200
            if index == 22:
                denied = await client.post(
                    f"/vat/engagements/{e['id']}/computations/{e['vat_profile_id']}",
                    headers=headers,
                )
                assert denied.status_code == 403
            report["role_probes"].append(
                {
                    "role": user["role"],
                    "email": user["email"],
                    "vat_workspace_status": r.status_code,
                }
            )
        headers = {
            "Authorization": "Bearer " + access_token(uuid.UUID(manifest["users"][1]["id"])),
            "X-Tenant-ID": str(DEMO_TENANT),
        }
        for _ in range(20):
            start = time.perf_counter()
            r = await client.get(
                f"/vat/engagements/{e['id']}/records/invoice?limit=50", headers=headers
            )
            assert r.status_code == 200
            report["api_latency_seconds"].append(time.perf_counter() - start)
        start = time.perf_counter()
        jobs = []
        for i in range(20):
            job = await client.post(
                "/jobs/diagnostic",
                headers={**headers, "Idempotency-Key": f"phase7-worker-diagnostic-{i}"},
            )
            assert job.status_code == 202, job.text
            jobs.append(job.json()["id"])
        pending = set(jobs)
        for _ in range(30):
            for jid in list(pending):
                r = await client.get(f"/jobs/{jid}", headers=headers)
                assert r.status_code == 200
                assert r.json()["status"] != "failed", r.text
                if r.json()["status"] == "completed":
                    pending.remove(jid)
            if not pending:
                break
            await asyncio.sleep(1)
        assert not pending, "Worker completion timeout"
        report["worker_diagnostics"] = {
            "completed": len(jobs),
            "submit_to_all_complete_seconds": time.perf_counter() - start,
            "scope": "20 harmless diagnostic jobs; no inference of financial workload throughput; replay keys return existing jobs",
        }
    times = sorted(report["api_latency_seconds"])
    report["api_latency_p50_seconds"] = times[len(times) // 2]
    report["api_latency_p95_seconds"] = times[int(len(times) * 0.95) - 1]
    (ROOT / "docs/phase-7/demo-verification.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "periods_reconciled": len(report["database_checks"]),
                "journal_lines": count,
                "roles_probed": len(report["role_probes"]),
                "p95_seconds": report["api_latency_p95_seconds"],
            }
        )
    )


async def run():
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
