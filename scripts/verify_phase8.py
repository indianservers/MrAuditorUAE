"""Real API/worker probes in the explicitly guarded synthetic tenant."""

import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from sqlalchemy import select, text


async def main():
    root = Path(__file__).resolve().parents[1]
    tp = json.loads((root / "docs/phase-8/demo-manifest.json").read_text())
    base = json.loads((root / "docs/phase-7/demo-manifest.json").read_text())
    report = {"synthetic": True, "role_probes": [], "base_sources": {}}
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        report["base_sources"]["journal_lines"] = await db.scalar(
            text("SELECT count(*) FROM journal_lines")
        )
        report["base_sources"]["unbalanced_journals"] = await db.scalar(
            text(
                "SELECT count(*) FROM (SELECT journal_id FROM journal_lines GROUP BY journal_id HAVING sum(base_debit-base_credit)<>0) j"
            )
        )
        for entry in base["engagements"]:
            balances=dict((await db.execute(text("SELECT a.code,sum(j.base_debit-j.base_credit) FROM journal_lines j JOIN accounts a ON a.id=j.account_id WHERE j.snapshot_id=:snapshot GROUP BY a.code"),{"snapshot":uuid.UUID(entry["snapshot_id"])})).all())
            assert all(balances.get(code,Decimal(0))==Decimal(value) for code,value in entry["expected_balances"].items()),entry["id"]
        report["base_sources"]["source_snapshots_reconciled"]=len(base["engagements"])
        loan = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == DEMO_TENANT,
                AuditRecord.reference == "P8-LOAN-1",
            )
        )
        far = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == DEMO_TENANT, AuditRecord.reference == "P8-FAR"
            )
        )
    from app.main import app

    path = f"/api/v1/tp/engagements/{tp['engagement_id']}"

    def headers(user):
        return {
            "Authorization": "Bearer " + access_token(uuid.UUID(user["id"])),
            "X-Tenant-ID": str(DEMO_TENANT),
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=120,
    ) as c:
        for entry in [x for x in base["engagements"] if x["year"]==2026]:
            source=await c.get(f"/api/v1/ifrs/engagements/{entry['id']}/runs/{entry['ifrs_run_id']}",headers=headers(base["users"][1]))
            assert source.status_code==200 and source.json()["dependencies_current"],source.text
        report["base_sources"]["approved_ifrs_runs_current"]=10
        for user in tp["users"]:
            r = await c.get(path + "/workspace", headers=headers(user))
            assert r.status_code == 200, (user["role"], r.text)
            report["role_probes"].append(
                {"role": user["role"], "workspace": r.status_code}
            )
        readonly = tp["users"][-1]
        r = await c.post(
            path + f"/matrix/{tp['profile_id']}", headers=headers(readonly)
        )
        assert r.status_code == 403, r.text
        report["readonly_calculate"] = r.status_code
        for index in [6, 18, 24]:
            r = await c.get(path + "/workspace", headers=headers(base["users"][index]))
            assert r.status_code == (401 if index == 24 else 403), r.text
            report["role_probes"].append(
                {
                    "role": base["users"][index]["role"],
                    "disabled": index == 24,
                    "workspace": r.status_code,
                }
            )
        h = headers(tp["users"][0])
        candidate = await c.get(path + f"/candidates/{tp['profile_id']}", headers=h)
        assert candidate.status_code == 200, candidate.text
        report["candidate_count"] = candidate.json()["total"]
        queued = await c.post(path + f"/calculate/{loan.id}?background=true", headers=h)
        assert queued.status_code == 201, queued.text
        job_id = queued.json()["id"]
        for _ in range(150):
            job = await c.get("/api/v1/jobs/" + job_id, headers=h)
            assert job.status_code == 200, job.text
            if job.json()["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)
        assert job.json()["status"] == "completed", job.text
        report["worker_job"] = {
            "id": job_id,
            "status": job.json()["status"],
            "progress": job.json()["progress"],
            "resource_id": job.json()["result"]["resource_id"],
        }
        foreign = await c.get(
            "/api/v1/jobs/" + job_id, headers=headers(tp["users"][-1])
        )
        assert foreign.status_code == 403, foreign.text
        report["readonly_job_read"] = foreign.status_code
        report["browser_ai_source_id"] = str(far.id)
    assert report["base_sources"]["journal_lines"] == 250024
    assert report["base_sources"]["unbalanced_journals"] == 0
    (root / "docs/phase-8/verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
