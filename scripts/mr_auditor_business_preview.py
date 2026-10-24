"""Synthetic browser seed; refuses every database except the owned disposable audit-gap DB."""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings
    if settings().environment != "test" or not settings().database_url.endswith("/auditos_audit_gap_test") or os.getenv("INTEGRATION_TESTS") != "1":
        raise SystemExit("Only the owned auditos_audit_gap_test database is allowed")
    from tests.integration.test_platform import environment
    from tests.phase5.test_reporting import prepared
    fixture = environment.__wrapped__()
    client = await anext(fixture)
    try:
        h, eid, base, reviewer, partner, profile, _, _, ready = await prepared(client)
        lease = await ready("lease", {"profile_id": profile["id"], "commencement": "2026-01-01", "end_date": "2026-12-31",
            "annual_discount_rate": "0.05", "payments": [{"date": "2026-12-31", "amount": "12000"}],
            "recognition_assessment": "SYNTHETIC office lease evidence", "options_assessment": "No renewal options in this synthetic fixture"})
        from tests.phase4.test_workflows import create, approve, action
        from tests.unit.test_uae_advanced import fixture as schedule_fixture
        from app.db.session import Session, tenant_context
        from app.db.models.platform import RolePermission, Permission
        from sqlalchemy import select
        import uuid
        async with Session() as db, db.begin():
            await tenant_context(db,h["X-Tenant-ID"])
            for actor in [reviewer,partner]:
                for code in ["vat.read","accounting.read"]:
                    pid=await db.scalar(select(Permission.id).where(Permission.code==code))
                    existing=await db.scalar(select(RolePermission.role_id).where(RolePermission.role_id==uuid.UUID(actor[2]),RolePermission.permission_id==pid))
                    if not existing: db.add(RolePermission(role_id=uuid.UUID(actor[2]),permission_id=pid))
        proof=await create(client,h,base,"working-papers",{"folder":"SYNTHETIC", "sections":[{"heading":"Source","text":"SYNTHETIC independently approved allocation method/population"}],"conclusion":"Synthetic test evidence only"})
        proof=await approve(client,h,reviewer[0],base,proof)
        proof=await action(client,partner[0],base,proof,"approve")
        advanced_ids={}
        for case_id in [52,91]:
            schedule=schedule_fixture(case_id);schedule["policy"]["source_id"]=proof["id"]
            for row in schedule["rows"]:row["evidence_id"]=proof["id"]
            if case_id==52: schedule["rows"][0].update(direct_recoverable="100",direct_blocked="50",residual="200",numerator="3",denominator="4",previously_claimed="240")
            paper=await create(client,h,base,"working-papers",{"folder":"SYNTHETIC", "sections":[{"heading":"Input","text":"SYNTHETIC approved schedule"}],"conclusion":"Synthetic input, not assurance", "sources":[{"kind":"record","id":proof["id"]}],"advanced_input":schedule})
            paper=await approve(client,h,reviewer[0],base,paper)
            paper=await action(client,partner[0],base,paper,"approve")
            advanced_ids[str(case_id)]=paper["id"]
        target = ROOT / ".local-runtime/mr-auditor-business/fixture.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"tenant_id": h["X-Tenant-ID"], "engagement_id": eid,
            "lease_id": lease["id"], "advanced_ids":advanced_ids, "policy_source_id":proof["id"], "synthetic": True}, indent=2))
        print(json.dumps({"seeded": True, "synthetic": True, "engagement_id": eid}))
    finally:
        await fixture.aclose()


asyncio.run(main())
