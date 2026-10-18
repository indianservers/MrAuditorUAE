"""Create synthetic tax demo through actual import, IFRS approval and tax APIs."""
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
        raise SystemExit("Set DEMO_SEED=1 for the disposable preview database")
    import httpx
    from app.main import app
    from app.db.session import engine
    from tests.phase6.test_workflows import second_entity, compute, release
    from app.modules.tax.calculations import CORE_QFZP, QFZP_REQUIRED

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        token = (await c.post("/api/v1/auth/login", data={"username": "admin@example.com", "password": "test-strong-password-123"})).json()["access_token"]
        tenant = (await c.get("/api/v1/tenants", headers={"Authorization": "Bearer " + token})).json()[0]["id"]
        h = {"Authorization": "Bearer " + token, "X-Tenant-ID": tenant}
        h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await second_entity(c, h, "-preview-" + uuid.uuid4().hex[:8])
        run = await compute(c, h, eid, p)
        await release(c, h, eid, base, manager, partner, run)
        interest = await ready("interest", {
            "profile_id": p["id"], "source_account_codes": ["500"], "evidence_record_ids": [note["id"]],
            "interest_expense": "400000", "interest_income": "0", "depreciation_tax_deductible": "0", "taxable_before_gidlr_losses": "1600000",
            "period_months": "12", "period_index": 3, "statutory_bridge": "Synthetic reviewed statutory bridge",
            "loan_and_tp_review": "Synthetic loan purpose and arm's-length review; no automatic benchmarking conclusion"
        })
        body = {k: v for k, v in p["body"].items() if not k.startswith("review_")}
        body.update(classification="qfzp", free_zone=True, audited_financials_required=True, audited_financials_evidence_id=note["id"])
        qp = await ready("profile", body)
        common = {"source_line_code": "400", "counterparty": "Synthetic industrial buyer", "counterparty_type": "non_free_zone", "activity": "Reviewed manufacturing contract", "jurisdiction": "AE", "contract_evidence_id": note["id"], "rationale": "Synthetic reviewed segmentation"}
        q = await ready("qfzp", {
            "profile_id": qp["id"], "conditions": [{"requirement": key, "assessment": "PASS" if key in CORE_QFZP else "NOT_APPLICABLE", "rationale": "Synthetic reviewed fact", "evidence_record_ids": [note["id"]] if key in CORE_QFZP else []} for key in sorted(QFZP_REQUIRED)],
            "segments": [{**common, "reference": "Q", "revenue": "1900000", "taxable_profit": "1140000", "classification": "qualifying"}, {**common, "reference": "N", "revenue": "100000", "taxable_profit": "60000", "classification": "nonqualifying"}],
            "procedures_applicability_basis": "No distribution activity in this synthetic fixture"
        })
        fixture = {"engagement_id": eid, "tenant_id": tenant, "profile_id": p["id"], "qfzp_profile_id": qp["id"], "qfzp_id": q["id"], "interest_id": interest["id"], "adjustment_id": adj["id"], "run_id": run["id"], "synthetic": True}
        target = Path(__file__).resolve().parents[1] / "docs/phase-6/browser-fixture.json"
        target.write_text(json.dumps(fixture, indent=2))
        print(json.dumps(fixture))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
