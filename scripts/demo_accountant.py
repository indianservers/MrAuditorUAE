"""Dedicated internal Accountant import scenario, isolated in an additional synthetic FY2027."""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import httpx
from sqlalchemy import select

from app.core.security import access_token, hash_password
from app.db.models.platform import (
    FinancialPeriod,
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    User,
)
from app.db.session import Session, engine, tenant_context
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.vat.models import DemoDataset

ROOT = Path(__file__).resolve().parents[1]


async def main():
    password = os.environ.get("PHASE7_DEMO_PASSWORD", "")
    if len(password) < 16:
        raise ValueError("Explicit development password required")
    m = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    entry = m["engagements"][0]
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        role = await db.scalar(select(Role).where(Role.name == "Accountant [SYNTHETIC DEMO]"))
        if not role:
            role = Role(name="Accountant [SYNTHETIC DEMO]")
            db.add(role)
            await db.flush()
            for code in [
                "accounting.read",
                "accounting.import",
                "clients.read",
                "entities.read",
                "engagements.read",
            ]:
                permission = await db.scalar(select(Permission).where(Permission.code == code))
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        user = await db.scalar(
            select(User).where(User.email == "synthetic.accountant@auditos.test")
        )
        if not user:
            user = User(
                email="synthetic.accountant@auditos.test", password_hash=hash_password(password)
            )
            db.add(user)
            await db.flush()
            member = Membership(tenant_id=DEMO_TENANT, user_id=user.id)
            db.add(member)
            await db.flush()
            db.add(MembershipRole(membership_id=member.id, role_id=role.id))
        uid = user.id
        period = await db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.tenant_id == DEMO_TENANT,
                FinancialPeriod.entity_id == uuid.UUID(entry["entity_id"]),
                FinancialPeriod.start_date == __import__("datetime").date(2027, 1, 1),
            )
        )
        period_id = str(period.id) if period else None
    async with httpx.AsyncClient(base_url="http://127.0.0.1:58003/api/v1", timeout=90) as c:
        admin = {
            "Authorization": "Bearer " + access_token(uuid.UUID(m["users"][1]["id"])),
            "X-Tenant-ID": str(DEMO_TENANT),
        }
        h = {**admin, "Authorization": "Bearer " + access_token(uid)}
        if not period_id:
            r = await c.post(
                "/financial-periods",
                headers=admin,
                json={
                    "entity_id": entry["entity_id"],
                    "start_date": "2027-01-01",
                    "end_date": "2027-12-31",
                },
            )
            assert r.status_code == 201, r.text
            period_id = r.json()["id"]
        csv = b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n100,Cash,SYN-OPEN,2027-01-01,10.10,0,P7-ACCOUNTANT-1,true,false,Synthetic opening\n300,Equity,SYN-OPEN,2027-01-01,0,10.10,P7-ACCOUNTANT-2,true,false,Synthetic opening\n500,Expense,SYN-ACCRUAL,2027-01-02,100.20,0,P7-ACCOUNTANT-3,false,true,Synthetic expense\n100,Cash,SYN-ACCRUAL,2027-01-02,0,100.20,P7-ACCOUNTANT-4,false,true,Synthetic expense\n"
        options = {
            "client_id": entry["client_id"],
            "entity_id": entry["entity_id"],
            "period_id": period_id,
            "expected_rows": 4,
            "expected_debit": "110.30",
            "expected_credit": "110.30",
            "source_complete": True,
        }
        r = await c.post(
            "/accounting/imports",
            headers=h,
            data={"options": json.dumps(options)},
            files={"file": ("synthetic-accountant.csv", csv, "text/csv")},
        )
        assert r.status_code == 201, r.text
        bid = r.json()["id"]
        for action in ["validate", "commit"]:
            r = await c.post(f"/accounting/imports/{bid}/{action}", headers=h)
            assert r.status_code == 200, r.text
        info = (await c.get(f"/accounting/imports/{bid}", headers=h)).json()
        tb = await c.get(
            "/accounting/trial-balance", headers=h, params={"snapshot_id": info["snapshot_id"]}
        )
        assert tb.status_code == 200, tb.text
        from decimal import Decimal

        assert tb.json()["balanced"]
        expected = {"100": Decimal("-90.10"), "300": Decimal("-10.10"), "500": Decimal("100.20")}
        assert {r["code"]: Decimal(r["closing"]) for r in tb.json()["items"]} == expected
        m["accountant_scenario"] = {
            "email": "synthetic.accountant@auditos.test",
            "user_id": str(uid),
            "role": "Accountant [SYNTHETIC DEMO]",
            "period_id": period_id,
            "year": 2027,
            "batch_id": bid,
            "snapshot_id": info["snapshot_id"],
            "expected_rows": 4,
            "expected_debit": "110.30",
            "trial_balance": tb.json(),
        }
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        dataset = await db.scalar(select(DemoDataset).where(DemoDataset.tenant_id == DEMO_TENANT))
        dataset.manifest = m
    (ROOT / "docs/phase-7/demo-manifest.json").write_text(json.dumps(m, indent=2))
    print(
        "PASS internal Accountant real import/validate/commit/TB; four additional isolated FY2027 journal lines"
    )


async def run():
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
