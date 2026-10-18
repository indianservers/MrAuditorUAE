"""Guarded local read-load and generated in-process financial workloads."""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import psutil
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.security import access_token, hash_password
from app.db.models.platform import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    User,
)
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.calculations import trial_balance
from app.modules.audit_analytics.engine import AnalyticsEngine
from app.modules.audit_analytics.schemas import AnalyticsRequest
from app.modules.demo.guard import DEMO_TENANT, guard


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * p))]


async def main():
    receipts = {
        "scope": "Local development loopback HTTP; real distinct synthetic identities; not a production capacity or SLO qualification",
        "api_workloads": [],
        "financial_workloads": [],
    }
    identities = []
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        role = await db.scalar(select(Role).where(Role.name == "Synthetic Performance Reader"))
        if not role:
            role = Role(name="Synthetic Performance Reader")
            db.add(role)
            await db.flush()
            for code in ["clients.read", "accounting.read"]:
                permission = await db.scalar(select(Permission).where(Permission.code == code))
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        encoded = hash_password(
            str(uuid.uuid4())
        )  # Generated, discarded password; no login credentials saved.
        for index in range(100):
            email = f"synthetic.p12.load{index:03}@auditos.test"
            user = await db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, password_hash=encoded)
                db.add(user)
                await db.flush()
                member = Membership(tenant_id=DEMO_TENANT, user_id=user.id)
                db.add(member)
                await db.flush()
                db.add(MembershipRole(membership_id=member.id, role_id=role.id))
            user.status = "active"
            identities.append(user.id)
    # Only development accepts these direct signed fixture sessions. Production requires
    # session-bound tokens plus MFA, tested separately; never label this an auth load test.
    try:
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:58007",
            timeout=120,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=100),
        ) as client:
            for concurrent in [10, 50, 100]:
                for endpoint in ["/api/v1/clients?limit=25", "/api/v1/accounting/ledger?limit=50"]:
                    latencies = []
                    statuses = []
                    totals = []

                    async def request(uid):
                        started = time.perf_counter()
                        response = await client.get(
                            endpoint,
                            headers={
                                "Authorization": "Bearer " + access_token(uid),
                                "X-Tenant-ID": str(DEMO_TENANT),
                            },
                        )
                        latencies.append(time.perf_counter() - started)
                        statuses.append(response.status_code)
                        if response.status_code == 200:
                            totals.append(response.json().get("total"))

                    started = time.perf_counter()
                    await asyncio.gather(*(request(uid) for uid in identities[:concurrent]))
                    elapsed = time.perf_counter() - started
                    receipts["api_workloads"].append(
                        {
                            "concurrent_distinct_users": concurrent,
                            "requests": concurrent,
                            "endpoint": endpoint,
                            "p50_seconds": percentile(latencies, 0.5),
                            "p95_seconds": percentile(latencies, 0.95),
                            "p99_seconds": percentile(latencies, 0.99),
                            "elapsed_seconds": elapsed,
                            "throughput_rps": concurrent / elapsed,
                            "errors": sum(code != 200 for code in statuses),
                            "status_codes": sorted(set(statuses)),
                            "population_totals": sorted({x for x in totals if x is not None}),
                        }
                    )
    finally:
        async with Session() as db, db.begin():
            await guard(db)
            for uid in identities:
                user = await db.get(User, uid)
                user.status = "disabled"
    for count in [10000, 100000, 250000, 1000000]:

        def rows():
            for index in range(count):
                debit = "10.01" if index % 2 == 0 else "0"
                credit = "0" if index % 2 == 0 else "10.01"
                yield {
                    "id": str(uuid.UUID(int=index + 1)),
                    "account_code": "A" if index % 2 == 0 else "B",
                    "journal_ref": str(index // 2),
                    "posting_date": "2026-01-01",
                    "debit": debit,
                    "credit": credit,
                    "base_debit": debit,
                    "base_credit": credit,
                    "functional_currency": "AED",
                    "description": "Synthetic performance fixture",
                }

        started = time.perf_counter()
        tb = trial_balance(rows(), "AED")
        tb_seconds = time.perf_counter() - started
        started = time.perf_counter()
        analysis = AnalyticsEngine(rows())
        try:
            results = analysis.evaluate(AnalyticsRequest(snapshot_id=uuid.UUID(int=1)))
            receipts["financial_workloads"].append(
                {
                    "rows": count,
                    "trial_balance_seconds": tb_seconds,
                    "trial_balance_sum": str(sum(x["closing"] for x in tb)),
                    "analytics_seconds": time.perf_counter() - started,
                    "rule_statuses": {r["rule_id"]: r["status"] for r in results},
                    "driver_rss_after_bytes": psutil.Process().memory_info().rss,
                    "memory_measurement": "driver point-in-time RSS, not sampled peak API/worker/DB memory",
                }
            )
        finally:
            analysis.close()
    receipts["not_measured"] = [
        "production network latency",
        "database CPU and peak RSS",
        "worker queue saturation",
        "100-user professional write mix",
        "end-to-end authentication load",
        "all specialist engine load",
        "cloud cost per file",
    ]
    (ROOT / "docs/phase-12/performance.json").write_text(
        json.dumps(receipts, indent=2), encoding="utf-8"
    )
    print(json.dumps(receipts, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
