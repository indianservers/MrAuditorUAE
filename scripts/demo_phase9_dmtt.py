"""Eight source-backed, conspicuously synthetic DMTT scenarios in guarded demo only."""

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
from app.main import app
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard

ROOT = Path(__file__).resolve().parents[1]


async def main():
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    entries = [x for x in m["engagements"] if x["year"] == 2026]
    entry = entries[0]
    eid = entry["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        note = await db.scalar(
            select(AuditRecord)
            .where(
                AuditRecord.engagement_id == uuid.UUID(eid),
                AuditRecord.kind == "ifrs-note",
                AuditRecord.status.in_(["APPROVED", "LOCKED"]),
            )
            .limit(1)
        )
        if not note:
            raise ValueError("Existing approved synthetic IFRS note required")
        existing = (
            await db.scalars(
                select(AuditRecord).where(
                    AuditRecord.engagement_id == uuid.UUID(eid),
                    AuditRecord.reference.like("P9-%"),
                )
            )
        ).all()
        cache = {x.reference: x for x in existing}

    def headers(i):
        return {
            "Authorization": "Bearer " + access_token(m["users"][i]["id"]),
            "X-Tenant-ID": str(DEMO_TENANT),
        }

    output = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:

        async def ready(kind, ref, body):
            if ref in cache:
                return {
                    "id": str(cache[ref].id),
                    "version": cache[ref].version,
                    "status": cache[ref].status,
                }
            r = await c.post(
                f"/api/v1/dmtt/engagements/{eid}/records/{kind}",
                headers=headers(1),
                json={
                    "reference": ref,
                    "title": "SYNTHETIC SOFTWARE TEST " + ref,
                    "body": body,
                },
            )
            assert r.status_code == 201, r.text
            obj = r.json()
            for action, who in [("submit", 1), ("approve", 9)]:
                r = await c.post(
                    base + f"/records/{obj['id']}/actions",
                    headers=headers(who),
                    json={
                        "version": obj["version"],
                        "action": action,
                        "comments": "Synthetic independent technical evidence review; not a genuine tax opinion",
                    },
                )
                assert r.status_code == 200, r.text
                obj = r.json()
            return obj

        for i, name in enumerate(
            [
                "below_threshold",
                "above_threshold",
                "uae_and_foreign_parent",
                "globe_loss",
                "transition_deferred",
                "substantial_substance",
                "safe_harbour",
                "no_safe_harbour",
            ]
        ):
            g = await ready(
                "group",
                "P9-G-" + name,
                {
                    "fiscal_start": "2026-01-01",
                    "fiscal_end": "2026-12-31",
                    "upe_name": "SYNTHETIC " + name,
                    "upe_jurisdiction": "GB",
                    "multinational": True,
                    "constituent_entity_ids": [entry["entity_id"]],
                    "preceding_revenues": [
                        {
                            "year": y,
                            "eur": "600000000" if i == 0 else "800000000",
                            "evidence_id": str(note.id),
                        }
                        for y in range(2022, 2026)
                    ],
                    "rule_version": "UAE-CD142-MD96/v2",
                    "technical_evidence_id": str(note.id),
                    "synthetic": True,
                },
            )
            e = {
                "group_id": g["id"],
                "entity_id": entry["entity_id"],
                "source_engagement_id": eid,
                "financial_run_id": entry["ifrs_run_id"],
                "jurisdiction": "AE",
                "classification": "ordinary",
                "classification_evidence_id": str(note.id),
                "fx_to_calculation": "1",
                "fx_evidence_id": str(note.id),
                "current_tax": "90000",
                "covered_tax_evidence_id": str(note.id),
                "substance_evidence_id": str(note.id),
                "eligible_payroll": "1000000" if i == 5 else "100000",
                "eligible_tangible_assets": "2000000" if i == 5 else "200000",
            }
            if i == 3:
                e["adjustments"] = [
                    {
                        "category": "other",
                        "amount": "-999999999",
                        "article": "3.2",
                        "evidence_id": str(note.id),
                        "rationale": "Synthetic controlled GloBE loss fixture, no real group tax effect",
                    }
                ]
            if i == 4:
                e["deferred"] = [
                    {
                        "amount": "9000",
                        "recorded_rate": ".09",
                        "treatment": "transition",
                        "evidence_id": str(note.id),
                        "transition_exclusions_checked": True,
                    }
                ]
            await ready("entity", "P9-E-" + name, e)
            if i in [6, 7]:
                await ready(
                    "election",
                    "P9-SH-" + name,
                    {
                        "group_id": g["id"],
                        "type": "transitional_cbcr",
                        "evidence_id": str(note.id),
                        "qualified_sources": True,
                        "all_conditions_reviewed": True,
                        "once_out_history_clear": True,
                        "cbcr_revenue_eur": "20000000",
                        "cbcr_profit_eur": "10000000",
                        "simplified_taxes_eur": "1700000" if i == 6 else "500000",
                        "cbcr_sbie_eur": "10000",
                    },
                )
            r = await c.post(
                f"/api/v1/dmtt/engagements/{eid}/groups/{g['id']}/calculate",
                headers=headers(1),
            )
            assert r.status_code == 201, r.text
            output.append(
                {
                    "scenario": name,
                    "group_id": g["id"],
                    "run_id": r.json()["id"],
                    "result": r.json()["body"]["results"],
                }
            )
    (ROOT / "docs/phase-9/dmtt-demo-results.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps({"groups": len(output), "engagement_id": eid, "synthetic": True}))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
