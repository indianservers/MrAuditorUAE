"""Read the isolated restored database and restored object directory through real APIs."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings
from app.db.session import Session, engine, tenant_context
from app.main import app
from app.modules.demo.guard import test_database_guard


async def main():
    tenant = "8733db06-81bc-59b3-afcc-bf0f4c0cd8a2"
    credentials = json.loads(
        (ROOT / ".local-runtime/phase7/demo-login.local.json").read_text(encoding="utf-8")
    )
    async with Session() as db:
        name = await db.scalar(text("SELECT current_database()"))
        test_database_guard(settings(), name)
        if name != "auditos_phase12_restore_test":
            raise RuntimeError("Explicit restored destination required")
        await tenant_context(db, tenant)
        before = await db.scalar(text("SELECT count(*) FROM journal_lines"))
        evidence = (
            (
                await db.execute(
                    text(
                        "SELECT v.id,v.record_id,v.sha256,r.engagement_id FROM audit_evidence_versions v JOIN audit_records r ON r.id=v.record_id WHERE v.scan_status='CLEAN' ORDER BY v.created_at LIMIT 1"
                    )
                )
            )
            .mappings()
            .one()
        )
    if (
        Path(settings().source_storage_path).resolve()
        != ROOT / ".local-runtime/phase12-recovery/restored-objects"
    ):
        raise RuntimeError("Restored private object directory required")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": "synthetic.user01@auditos.test", "password": credentials["password"]},
        )
        if login.status_code != 200:
            raise RuntimeError("Restored identity did not authenticate")
        tokens = login.json()
        headers = {"Authorization": "Bearer " + tokens["access_token"], "X-Tenant-ID": tenant}
        results = {}
        for path in [
            "/health/ready",
            "/api/v1/clients?limit=25",
            "/api/v1/accounting/ledger?limit=50",
        ]:
            response = await client.get(path, headers=headers)
            if response.status_code != 200:
                raise RuntimeError("Restored application read failed")
            results[path] = {"status": response.status_code, "total": response.json().get("total")}
        response = await client.get(
            f"/api/v1/engagements/{evidence['engagement_id']}/audit/evidence-files/{evidence['record_id']}/{evidence['id']}/download",
            headers=headers,
        )
        if (
            response.status_code != 200
            or hashlib.sha256(response.content).hexdigest() != evidence["sha256"]
        ):
            raise RuntimeError("Restored object did not download with original SHA")
        results["private_download"] = {
            "status": response.status_code,
            "sha256_matches": True,
            "bytes": len(response.content),
            "scanner_scope": "Original synthetic test-double verdict retained; not real scanner qualification",
        }
        await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    async with Session() as db:
        await tenant_context(db, tenant)
        after = await db.scalar(text("SELECT count(*) FROM journal_lines"))
    if before != after:
        raise RuntimeError("Recovery smoke modified accounting data")
    output = {
        "status": "PASS",
        "database": name,
        "ledger_before": before,
        "ledger_after": after,
        "api_results": results,
        "scope": "Local isolated restored DB and restored object directory; only authentication/audit metadata writes",
    }
    (ROOT / "docs/phase-12/recovery-app-smoke.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    await engine.dispose()
    print("Restored database and restored private-object API smoke passed")


if __name__ == "__main__":
    asyncio.run(main())
