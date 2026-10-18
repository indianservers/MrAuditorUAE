"""Creates explicitly synthetic Phase 5 fixtures without resetting existing data."""
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
    from tests.phase5.test_reporting import prepared, create, LEASE, ECL_INPUT
    from app.db.session import engine
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as c:
        token=(await c.post("/api/v1/auth/login",data={"username":"admin@example.com","password":"test-strong-password-123"})).json()["access_token"]
        tenant=(await c.get("/api/v1/tenants",headers={"Authorization":"Bearer "+token})).json()[0]["id"]
        h={"Authorization":"Bearer "+token,"X-Tenant-ID":tenant}
        async def post(path,body):
            response=await c.post("/api/v1/"+path,headers=h,json=body)
            assert response.status_code<400,response.text
            return response.json()
        client=await post("clients",{"code":"P5-"+uuid.uuid4().hex[:8],"name":"SYNTHETIC Phase 5 Reporting Demo"})
        entity=await post("entities",{"client_id":client["id"],"name":"SYNTHETIC Gulf Reporting LLC","country":"AE","jurisdiction":"Synthetic UAE","functional_currency":"AED","presentation_currency":"AED"})
        period=await post("financial-periods",{"entity_id":entity["id"],"start_date":"2026-01-01","end_date":"2026-12-31"})
        eng=await post("engagements",{"entity_id":entity["id"],"period_id":period["id"],"name":"SYNTHETIC FY2026 IFRS reporting","engagement_type":"External Audit"})
        eid=eng["id"];base=f"/api/v1/engagements/{eid}/audit"
        opts={"client_id":client["id"],"entity_id":entity["id"],"period_id":period["id"],"source_complete":True}
        values=await prepared(c,(h,opts,eid,base),uuid.uuid4().hex[:6])
        _,_,_,reviewer,partner,profile,mapping,note,ready=values
        lease=await ready("lease",LEASE)
        ecl=await ready("ecl",ECL_INPUT)
        run=await post(f"ifrs/engagements/{eid}/financial-statements/{profile['id']}",None)
        for obj in [lease,ecl]:
            await post(f"ifrs/engagements/{eid}/calculate/{obj['id']}",None)
        fixture={"engagement_id":eid,"tenant_id":tenant,"client_id":client["id"],"entity_id":entity["id"],"period_id":period["id"],"profile_id":profile["id"],"run_id":run["id"],"note_id":note["id"],"lease_id":lease["id"],"ecl_id":ecl["id"],"synthetic":True}
        target=Path(__file__).resolve().parents[1]/"docs/phase-5/browser-fixture.json"
        target.write_text(json.dumps(fixture,indent=2))
        print(json.dumps(fixture))
    await engine.dispose()


if __name__=="__main__":
    asyncio.run(main())
