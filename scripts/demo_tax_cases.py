"""Add ten source-linked QFZP assessments through normal API review in guarded demo only."""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from sqlalchemy import select

from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.tax.calculations import QFZP_REQUIRED

ROOT = Path(__file__).resolve().parents[1]


async def main():
    async with Session() as db, db.begin():
        await guard(db)
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58003/api/v1", timeout=90) as c:

        async def call(path, body=None, who=10):
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
            if r.status_code >= 400:
                raise RuntimeError(path + " " + r.text)
            return r.json()

        for e in [x for x in m["engagements"] if x["year"] == 2026]:
            eid = e["id"]
            from app.db.models.platform import MembershipRole, Role

            async with Session() as db, db.begin():
                await guard(db)
                await tenant_context(db, str(DEMO_TENANT))
                role = await db.scalar(select(Role).where(Role.name == "Senior Tax Consultant"))
                membership = uuid.UUID(m["users"][10]["membership_id"])
                if not await db.scalar(
                    select(MembershipRole).where(
                        MembershipRole.membership_id == membership,
                        MembershipRole.role_id == role.id,
                    )
                ):
                    db.add(MembershipRole(membership_id=membership, role_id=role.id))
                role_id = str(role.id)
            await call(
                f"/engagements/{eid}/audit/team",
                {"membership_id": str(membership), "role_id": role_id},
                who=1,
            )

            async def ready(kind, body, ref):
                async with Session() as db, db.begin():
                    await tenant_context(db, str(DEMO_TENANT))
                    existing = await db.scalar(
                        select(AuditRecord).where(
                            AuditRecord.engagement_id == uuid.UUID(eid),
                            AuditRecord.reference == ref,
                            AuditRecord.tenant_id == DEMO_TENANT,
                        )
                    )
                    obj = (
                        {
                            "id": str(existing.id),
                            "version": existing.version,
                            "status": existing.status,
                        }
                        if existing
                        else None
                    )
                if not obj:
                    obj = await call(
                        f"/tax/engagements/{eid}/records/{kind}",
                        {"reference": ref, "title": "SYNTHETIC " + ref, "body": body},
                    )
                path = f"/engagements/{eid}/audit/records/{obj['id']}/actions"
                if obj["status"] == "DRAFT":
                    obj = await call(
                        path,
                        {
                            "version": obj["version"],
                            "action": "start",
                            "comments": "Synthetic demo",
                        },
                    )
                if obj["status"] == "IN_PROGRESS":
                    obj = await call(
                        path,
                        {
                            "version": obj["version"],
                            "action": "submit",
                            "comments": "Synthetic demo",
                        },
                    )
                if obj["status"] != "APPROVED":
                    obj = await call(
                        path,
                        {
                            "version": obj["version"],
                            "action": "approve",
                            "comments": "Independent synthetic assessment",
                        },
                        who=9,
                    )
                return obj

            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                original_record = await db.get(AuditRecord, uuid.UUID(e["tax_profile_id"]))
                original = {"body": dict(original_record.body)}
            body = {
                k: v
                for k, v in original["body"].items()
                if k not in {"review_stage", "review_cycle", "review_approvers", "calculation"}
            }
            body.update(
                classification="qfzp",
                free_zone=True,
                legal_form="Synthetic free-zone LLC",
                scope_assessment="Synthetic qualifying service contracts; conditions separately evidenced; no real certification",
            )
            profile = await ready("profile", body, "P7-QFZP-PROFILE")
            note = e["source_note_id"]
            assessment = await ready(
                "qfzp",
                {
                    "profile_id": profile["id"],
                    "conditions": [
                        {
                            "requirement": key,
                            "assessment": "PASS",
                            "rationale": "Synthetic independently reviewed case facts",
                            "evidence_record_ids": [note],
                        }
                        for key in sorted(QFZP_REQUIRED)
                    ],
                    "segments": [
                        {
                            "reference": "SYN-QUALIFYING-SERVICE",
                            "source_line_code": "400",
                            "revenue": body["revenue"],
                            "taxable_profit": e["expected_profit"],
                            "classification": "qualifying",
                            "counterparty": "Synthetic FZ beneficial recipient",
                            "counterparty_type": "free_zone_beneficial_recipient",
                            "activity": "Synthetic qualifying services",
                            "jurisdiction": "AE",
                            "contract_evidence_id": note,
                            "rationale": "Synthetic contract supports reviewed classification",
                        }
                    ],
                    "procedures_applicability_basis": "No distribution activity in this synthetic case",
                },
                "P7-QFZP-ASSESSMENT",
            )
            if not e.get("qfzp_run_id"):
                run = await call(f"/tax/engagements/{eid}/calculate/{assessment['id']}", {})
                assert run["results"]["assessment"] == "PASS"
                assert run["results"]["qfzp_tax_if_qualified"] == "0.00000000"
                e.update(
                    qfzp_profile_id=profile["id"], qfzp_id=assessment["id"], qfzp_run_id=run["id"]
                )
            (ROOT / "docs/phase-7/demo-manifest.json").write_text(json.dumps(m, indent=2))
            print("PASS synthetic QFZP", eid, flush=True)
    from app.modules.vat.models import DemoDataset

    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        dataset = await db.scalar(select(DemoDataset).where(DemoDataset.tenant_id == DEMO_TENANT))
        dataset.manifest = m


async def run():
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
