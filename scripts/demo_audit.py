"""Auditor investigation and CA preparation/independent review on actual stored demo sources."""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from sqlalchemy import select

from app.core.security import access_token
from app.db.models.platform import MembershipRole, Permission, Role, RolePermission
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.vat.models import DemoDataset

ROOT = Path(__file__).resolve().parents[1]


async def main():
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    e = next(x for x in m["engagements"] if x["year"] == 2026)
    eid = e["id"]
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        role = await db.scalar(select(Role).where(Role.name == "Audit Analytics [SYNTHETIC DEMO]"))
        if not role:
            role = Role(name="Audit Analytics [SYNTHETIC DEMO]")
            db.add(role)
            await db.flush()
            for code in ["accounting.read", "analytics.run", "analytics.read"]:
                permission = await db.scalar(select(Permission).where(Permission.code == code))
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        membership = uuid.UUID(m["users"][6]["membership_id"])
        if not await db.scalar(
            select(MembershipRole).where(
                MembershipRole.membership_id == membership, MembershipRole.role_id == role.id
            )
        ):
            db.add(MembershipRole(membership_id=membership, role_id=role.id))
        partner = await db.scalar(select(Role).where(Role.name == "Audit Partner"))
        partner_id = str(partner.id)
    report = m.setdefault("audit_scenarios", {})
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58003/api/v1", timeout=120) as c:

        async def call(path, body=None, who=1, expected=200):
            h = {
                "Authorization": "Bearer " + access_token(uuid.UUID(m["users"][who]["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            }
            r = await c.request(
                "POST" if body is not None else "GET",
                path,
                headers=h,
                **({"json": body} if body is not None else {}),
            )
            assert r.status_code == expected, (path, r.status_code, r.text)
            return r.json()

        await call(
            f"/engagements/{eid}/audit/team",
            {"membership_id": m["users"][3]["membership_id"], "role_id": partner_id},
        )
        if not report.get("analytics_run_id"):
            run = await call(
                "/analytics/runs", {"snapshot_id": e["snapshot_id"]}, who=6, expected=201
            )
            report["analytics_run_id"] = run["id"]
        findings = await call(
            f"/analytics/findings?run_id={report['analytics_run_id']}&limit=50", who=6
        )
        assert findings["total"] > 0
        finding = next(x for x in findings["items"] if x.get("line_id"))
        lineage = await call(f"/accounting/lineage/{finding['line_id']}", who=6)
        assert lineage["journal_line"]["id"] == finding["line_id"]
        report["investigated_finding_id"] = finding["id"]
        report["source_line_id"] = finding["line_id"]

        async def paper(ref, who):
            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                old = await db.scalar(
                    select(AuditRecord).where(
                        AuditRecord.engagement_id == uuid.UUID(eid), AuditRecord.reference == ref
                    )
                )
                obj = (
                    {
                        "id": str(old.id),
                        "version": old.version,
                        "status": old.status,
                        "body": old.body,
                    }
                    if old
                    else None
                )
            if not obj:
                obj = await call(
                    f"/engagements/{eid}/audit/working-papers",
                    {
                        "reference": ref,
                        "title": "SYNTHETIC investigation working paper",
                        "body": {
                            "folder": "Synthetic review",
                            "sections": [
                                {
                                    "heading": "Actual lineage",
                                    "text": "Reviewed synthetic anomaly and original journal source",
                                }
                            ],
                            "conclusion": "Synthetic indicator requires professional judgment; no automatic misstatement",
                            "sources": [{"kind": "journal", "id": finding["line_id"]}],
                        },
                    },
                    who=who,
                    expected=201,
                )
            path = f"/engagements/{eid}/audit/records/{obj['id']}/actions"
            if obj["status"] == "IN_PROGRESS":
                obj = await call(
                    path,
                    {
                        "version": obj["version"],
                        "action": "submit",
                        "comments": "Synthetic real source reviewed",
                    },
                    who=who,
                )
            if obj["status"] == "REVIEW_REQUIRED" and obj["body"].get("review_stage", 0) == 0:
                obj = await call(
                    path,
                    {
                        "version": obj["version"],
                        "action": "approve",
                        "comments": "Independent manager source review",
                    },
                    who=4,
                )
            return obj, path

        prepared, _ = await paper("P7-CA-PREPARED", 3)
        reviewed, path = await paper("P7-CA-INDEPENDENT-REVIEW", 1)
        if reviewed["status"] != "APPROVED":
            reviewed = await call(
                path,
                {
                    "version": reviewed["version"],
                    "action": "approve",
                    "comments": "Independent CA final source review",
                },
                who=3,
            )
        assert reviewed["status"] == "APPROVED"
        report.update(
            ca_prepared_id=prepared["id"],
            ca_reviewed_id=reviewed["id"],
            note="CA-prepared paper awaits a different final partner; CA independently approved the admin-prepared paper after manager review",
        )
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        dataset = await db.scalar(select(DemoDataset).where(DemoDataset.tenant_id == DEMO_TENANT))
        dataset.manifest = m
    (ROOT / "docs/phase-7/demo-manifest.json").write_text(json.dumps(m, indent=2))
    print(
        "PASS Auditor actual anomaly run/source investigation; CA actual preparation and independent final review"
    )


async def run():
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
