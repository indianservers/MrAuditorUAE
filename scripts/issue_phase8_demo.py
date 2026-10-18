"""Issue one conspicuously synthetic software-test PDF through real independent roles."""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.tp.catalogue import LOCAL_SECTIONS
from app.modules.tp.models import TPRun
from sqlalchemy import select


async def main():
    root = Path(__file__).resolve().parents[1]
    tp = json.loads((root / "docs/phase-8/demo-manifest.json").read_text())
    base_manifest = json.loads((root / "docs/phase-7/demo-manifest.json").read_text())
    entry = next(
        x for x in base_manifest["engagements"] if x["id"] == tp["engagement_id"]
    )
    eid = uuid.UUID(tp["engagement_id"])
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        source = {
            x.reference: x
            for x in (
                await db.scalars(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == DEMO_TENANT,
                        AuditRecord.engagement_id == eid,
                        AuditRecord.kind.in_(
                            ["tp-far", "tp-method", "tp-segmentation"]
                        ),
                    )
                )
            ).all()
        }
        segmentation = await db.scalar(
            select(TPRun)
            .where(
                TPRun.tenant_id == DEMO_TENANT,
                TPRun.record_id == source["P8-SEGMENTATION"].id,
            )
            .order_by(TPRun.created_at.desc())
            .limit(1)
        )
    from app.main import app

    path = f"tp/engagements/{eid}"
    audit = f"engagements/{eid}/audit"
    users = tp["users"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=120,
    ) as c:

        async def call(route, body=None, who=0, method="POST"):
            r = await c.request(
                method,
                "/api/v1/" + route,
                headers={
                    "Authorization": "Bearer "
                    + access_token(uuid.UUID(users[who]["id"])),
                    "X-Tenant-ID": str(DEMO_TENANT),
                },
                **({"json": body} if body is not None else {}),
            )
            assert r.status_code < 400, (route, r.text)
            return r.json()

        async def ready(kind, body, reference):
            listing = await call(
                path + f"/records/{kind}?search={reference}", method="GET"
            )
            paper = next(
                (x for x in listing["items"] if x["reference"] == reference), None
            )
            if not paper:
                paper = await call(
                    path + "/records/" + kind,
                    {
                        "reference": reference,
                        "title": "SYNTHETIC SOFTWARE TEST ONLY — " + reference,
                        "body": body,
                    },
                )
            if paper["status"] == "APPROVED":
                return paper

            async def action(value, who):
                return await call(
                    audit + f"/records/{paper['id']}/actions",
                    {
                        "version": paper["version"],
                        "action": value,
                        "comments": "SYNTHETIC test actor review only; no human professional opinion or client advice",
                    },
                    who,
                )

            if paper["status"] == "IN_PROGRESS":
                paper = await action("submit", 0)
            if not paper["body"].get("review_stage"):
                paper = await action("approve", 1)
            if paper["status"] == "REVIEW_REQUIRED":
                paper = await action("approve", 2)
            assert paper["status"] == "APPROVED"
            return paper

        common = {
            "profile_id": tp["profile_id"],
            "evidence_record_ids": [entry["source_note_id"]],
            "rationale": "SYNTHETIC software-only workflow example; not a tax opinion or real client issue",
        }
        matrix = await call(path + f"/matrix/{tp['profile_id']}")
        sections = []
        for key in LOCAL_SECTIONS:
            evidence = (
                [str(source["P8-FAR"].id)]
                if key == "far"
                else [str(source["P8-METHOD-operating_margin"].id)]
                if key == "method"
                else [entry["source_note_id"]]
            )
            runs = (
                [tp["studies"][0]]
                if key == "benchmarking"
                else [matrix["id"]]
                if key == "controlled_transactions"
                else []
            )
            sections.append(
                {
                    "key": key,
                    "narrative": "SYNTHETIC SOFTWARE TEST ONLY. This section exercises source lineage and document approval: "
                    + key.replace("_", " ")
                    + ". The 100 controlled classifications and generated comparable observations are fictional fixtures. This document supplies no real market evidence, legal conclusion, arm's length assurance or tax advice. Test-role verification is not real professional sign-off.",
                    "evidence_ids": evidence,
                    "run_ids": runs,
                    "human_verified": True,
                }
            )
        document = await ready(
            "localfile",
            {
                **common,
                "sections": sections,
                "checklist_complete": True,
                "financial_reconciliation_run_id": str(segmentation.id),
                "license_review": "Synthetic derived figures only; no raw companies or licensed observations",
                "annual_version": 1,
            },
            "P8-SOFTWARE-ISSUE-LOCALFILE",
        )
        runs = await call(path + "/runs?limit=100", method="GET")
        existing = next(
            (x for x in runs["items"] if x.get("record_id") == document["id"]), None
        )
        run = existing or await call(path + f"/calculate/{document['id']}")
        release = await ready(
            "release",
            {
                **common,
                "document_run_id": run["id"],
                "client_visible": True,
                "confidential_notes_excluded": True,
                "disclosure_authorization": "SYNTHETIC nonproduction client viewer may download this software demonstration only",
            },
            "P8-SOFTWARE-ISSUE-RELEASE",
        )
        result = {
            "synthetic": True,
            "document_id": document["id"],
            "run_id": run["id"],
            "release_id": release["id"],
            "client_id": entry["client_id"],
            "status": release["status"],
            "scope": "Software-test issued PDF only; not a completed real Local File",
        }
        (root / "docs/phase-8/issued-demo.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        print(json.dumps(result))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
