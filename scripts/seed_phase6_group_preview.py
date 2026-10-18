"""Add a genuine two-member group to the existing synthetic browser fixture."""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def main():
    raise SystemExit("Legacy preview seeding is disabled: use the guarded Phase 7 seed-demo command against its explicit demo database and tenant.")
    if os.getenv("DEMO_SEED") != "1":
        raise SystemExit("Set DEMO_SEED=1")
    import httpx
    from app.main import app
    from app.db.session import engine
    from tests.phase6.test_workflows import second_entity
    from tests.phase4.test_workflows import approve, create, grant
    target = Path(__file__).resolve().parents[1] / "docs/phase-6/browser-fixture.json"
    f = json.loads(target.read_text())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        token = (await c.post("/api/v1/auth/login", data={"username": "admin@example.com", "password": "test-strong-password-123"})).json()["access_token"]
        h = {"Authorization": "Bearer " + token, "X-Tenant-ID": f["tenant_id"]}
        eid = f["engagement_id"]
        base = f"/api/v1/engagements/{eid}/audit"
        _, eid2, base2, manager2, partner2, p2, adj2, note2, rules2, ready2, fin2 = await second_entity(c, h, "-preview-group-" + uuid.uuid4().hex[:8])
        await grant(c, h, base, partner2)
        p = next(x for x in (await c.get(base + "/tax-profile", headers=h)).json()["items"] if x["id"] == f["profile_id"])
        adj = next(x for x in (await c.get(base + "/tax-adjustment", headers=h)).json()["items"] if x["id"] == f["adjustment_id"])
        note = adj["body"]["evidence_record_ids"][0]
        adjustments = []
        for en, source in [(eid, adj), (eid2, adj2)]:
            body = {k:v for k,v in source["body"].items() if not k.startswith("review_")}
            body.update(profile_id=p["id"], rule_id=p["body"]["rules"]["adjustments"], source_engagement_id=en)
            adjustments.append(body)
        body = {"profile_id": p["id"], "members": [{"engagement_id": en, "profile_id": pr["id"], "share_capital": "1" if en == eid else "0.95", "voting_rights": "1" if en == eid else "0.95", "profit_net_asset_rights": "1" if en == eid else "0.95", "resident_juridical": True, "exempt_or_qfzp": False, "entry_date": "2026-01-01"} for en,pr in [(eid,p),(eid2,p2)]], "fta_application_evidence_id": note, "fta_approval_evidence_id": note, "special_purpose_audit_evidence_id": note, "group_adjustments": adjustments, "pre_group_losses_interest_assessment": "Synthetic no restricted pre-group attributes", "no_restricted_pre_group_attributes": True, "conditions": [{"requirement": key, "assessment": "PASS", "rationale": "Synthetic reviewed group", "evidence_record_ids": [note]} for key in ["fta_approval", "financial_alignment", "accounting_alignment", "group_boundary"]]}
        obj = await approve(c, h, partner2[0], base, await create(c, h, base, "tax-group", body))
        f["group_id"] = obj["id"]
        target.write_text(json.dumps(f, indent=2))
        print("Synthetic group added", obj["id"])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
