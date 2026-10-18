"""Execute the financial reporting and tax manager calculations with their actual identities."""

import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from sqlalchemy import select

from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.vat.models import DemoDataset

ROOT = Path(__file__).resolve().parents[1]


async def main():
    async with Session() as db, db.begin():
        await guard(db)
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    e = next(x for x in m["engagements"] if x["year"] == 2026)
    results = m.setdefault("role_calculations", {})
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58003/api/v1", timeout=120) as c:
        for key, who, path in [
            (
                "financial_reporting_manager",
                11,
                f"/ifrs/engagements/{e['id']}/financial-statements/{e['ifrs_profile_id']}",
            ),
            ("tax_manager", 9, f"/tax/engagements/{e['id']}/computations/{e['tax_profile_id']}"),
        ]:
            if key in results:
                continue
            h = {
                "Authorization": "Bearer " + access_token(uuid.UUID(m["users"][who]["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            }
            response = await c.post(path, headers=h)
            assert response.status_code == 201, response.text
            run = response.json()
            assert run["results"]["validation"]["ready"]
            if key == "financial_reporting_manager":
                assert Decimal(run["results"]["totals"]["profit"]) == Decimal(e["expected_profit"])
            else:
                assert Decimal(run["results"]["current_tax"]) == Decimal(e["expected_current_tax"])
            results[key] = {
                "user_id": m["users"][who]["id"],
                "role": m["users"][who]["role"],
                "engagement_id": e["id"],
                "run_id": run["id"],
                "independent_expected": e["expected_profit"]
                if who == 11
                else e["expected_current_tax"],
            }
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        dataset = await db.scalar(select(DemoDataset).where(DemoDataset.tenant_id == DEMO_TENANT))
        dataset.manifest = m
    (ROOT / "docs/phase-7/demo-manifest.json").write_text(json.dumps(m, indent=2))
    print(
        "PASS actual Financial Reporting Manager generated IFRS and Tax Manager prepared CT; independent amounts matched"
    )


async def run():
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
