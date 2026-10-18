"""Exercise defective invoice and real client upload without bypassing quarantine."""

import asyncio
import io
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.core.security import access_token
from app.db.models.platform import Engagement, LegalEntity, MembershipRole, Role
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard

ROOT = Path(__file__).resolve().parents[1]


async def main():
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    e = next(x for x in m["engagements"] if x["year"] == 2026)
    eid = e["id"]
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        eng = await db.get(Engagement, uuid.UUID(eid))
        entity = await db.get(LegalEntity, eng.entity_id)
        client_id = str(entity.client_id)
        validator_role = await db.scalar(select(Role).where(Role.name == "Invoice Validator"))
        validator_membership = uuid.UUID(m["users"][20]["membership_id"])
        if not await db.scalar(
            select(MembershipRole).where(
                MembershipRole.membership_id == validator_membership,
                MembershipRole.role_id == validator_role.id,
            )
        ):
            db.add(MembershipRole(membership_id=validator_membership, role_id=validator_role.id))
        validator_role_id = str(validator_role.id)
        source = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind == "vat-invoice",
                AuditRecord.status == "APPROVED",
            )
        )
        invoice = {
            k: v
            for k, v in source.body.items()
            if k not in {"review_stage", "review_cycle", "review_approvers", "calculation"}
        }
        existing = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.engagement_id == eng.id, AuditRecord.reference == "P7-DEFECTIVE-INVOICE"
            )
        )
        defective = str(existing.id) if existing else None
        existing = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.engagement_id == eng.id, AuditRecord.reference == "P7-CLIENT-UPLOAD"
            )
        )
        request = (
            {
                "id": str(existing.id),
                "version": existing.version,
                "status": existing.status,
                "body": existing.body,
            }
            if existing
            else None
        )
    report = {}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58003/api/v1", timeout=90) as c:

        async def call(path, body=None, who=1, files=None, expected=200):
            h = {
                "Authorization": "Bearer " + access_token(uuid.UUID(m["users"][who]["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            }
            r = await c.request(
                "POST" if body is not None or files else "GET",
                path,
                headers=h,
                **({"json": body} if body is not None else {}),
                **({"files": files} if files else {}),
            )
            assert r.status_code == expected, (path, r.status_code, r.text)
            return r.json()

        await call(
            f"/engagements/{eid}/audit/team",
            {"membership_id": str(validator_membership), "role_id": validator_role_id},
        )
        computation = await call(
            f"/vat/engagements/{eid}/computations/{e['vat_profile_id']}", {}, who=20, expected=201
        )
        assert computation["results"]["validation"]["ready"]
        from decimal import Decimal

        assert Decimal(computation["results"]["net_vat"]) == Decimal(e["expected_net_vat"])
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            old_return = await db.scalar(
                select(AuditRecord).where(
                    AuditRecord.engagement_id == uuid.UUID(eid),
                    AuditRecord.reference == "P7-VAT-ANALYST-RETURN",
                )
            )
            return_id = str(old_return.id) if old_return else None
        if not return_id:
            draft = await call(
                f"/vat/engagements/{eid}/records/return",
                {
                    "reference": "P7-VAT-ANALYST-RETURN",
                    "title": "SYNTHETIC analyst draft VAT return",
                    "body": {
                        "run_id": computation["id"],
                        "filing_state": "DRAFT",
                        "checklist_complete": True,
                        "rationale": "Synthetic source and VAT control reconciliation checked; independent review required",
                    },
                },
                who=20,
                expected=201,
            )
            return_id = draft["id"]
        report["vat_analyst"] = {
            "reconciliation_run_id": computation["id"],
            "return_id": return_id,
            "net_vat": computation["results"]["net_vat"],
        }
        if not defective:
            invoice.update(
                invoice_number="SYN-DEFECTIVE-P7",
                sequence=999999,
                supplier_address="",
                declared_tax="999.00",
            )
            obj = await call(
                f"/vat/engagements/{eid}/records/invoice",
                {
                    "reference": "P7-DEFECTIVE-INVOICE",
                    "title": "SYNTHETIC deliberately defective invoice",
                    "body": invoice,
                },
                who=20,
                expected=201,
            )
            defective = obj["id"]
        result = await call(f"/vat/engagements/{eid}/invoices/{defective}/validate", {}, who=20)
        assert not result.get("valid", result.get("results", {}).get("valid", True)), result
        report["invoice_validation"] = {"record_id": defective, "result": result}
        if not request:
            request = await call(
                f"/engagements/{eid}/audit/requests",
                {
                    "reference": "P7-CLIENT-UPLOAD",
                    "title": "SYNTHETIC requested support",
                    "body": {
                        "client_id": client_id,
                        "question": "Upload synthetic invoice evidence for auditor review",
                    },
                },
                expected=201,
            )
        if request["status"] == "DRAFT":
            request = await call(
                f"/engagements/{eid}/audit/records/{request['id']}/actions",
                {
                    "version": request["version"],
                    "action": "SENT",
                    "comments": "Synthetic client request",
                },
            )
        viewed = await call(f"/client-portal/requests/{request['id']}/view", {}, who=17)
        evidence_ids = viewed.get("evidence_ids", [])
        if not evidence_ids:
            pdf = io.BytesIO()
            doc = canvas.Canvas(pdf)
            doc.drawString(70, 750, "SYNTHETIC DEMO SUPPORT - NOT A REAL TAX INVOICE")
            doc.save()
            upload = await call(
                f"/client-portal/requests/{request['id']}/upload",
                who=17,
                files={"file": ("synthetic-support.pdf", pdf.getvalue(), "application/pdf")},
                expected=201,
            )
            evidence_ids = [upload["evidence_id"]]
            assert upload["scan_status"] == "QUARANTINED"
        records = await call(f"/engagements/{eid}/audit/evidence?limit=100", who=4)
        evidence = next(x for x in records["items"] if x["id"] == evidence_ids[0])
        blocked = await call(
            f"/engagements/{eid}/audit/records/{evidence['id']}/actions",
            {
                "version": evidence["version"],
                "action": "submit",
                "comments": "Auditor review attempted; quarantine must block approval",
            },
            who=4,
            expected=409,
        )
        report["portal_upload_review"] = {
            "request_id": request["id"],
            "evidence_id": evidence["id"],
            "reviewer": m["users"][4]["email"],
            "state": "QUARANTINED",
            "submission_blocked": blocked,
            "live_scanner": "unavailable",
        }
    (ROOT / "docs/phase-7/portal-invoice-scenarios.json").write_text(json.dumps(report, indent=2))
    print(
        "Defective invoice detected; real client PDF uploaded and auditor review correctly blocked by quarantine"
    )


async def run():
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
