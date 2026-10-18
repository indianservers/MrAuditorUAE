"""Bounded local read load with distinct synthetic users; deactivate after use."""

import asyncio
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
import psutil
from app.core.security import access_token, hash_password
from app.db.models.platform import Membership, MembershipRole, Role, User
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import JournalLine
from qa_campaign import guard
from sqlalchemy import func, select


async def main():
    out = ROOT / "docs/qa-campaign"
    data = json.loads((out / "dataset.json").read_text(encoding="utf8"))
    users = []
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, data["tenant_id"])
        count = await db.scalar(select(func.count()).select_from(JournalLine))
        role = await db.scalar(select(Role).where(Role.name == "Firm Administrator"))
        encoded = hash_password(str(uuid.uuid4()))
        for i in range(100):
            uid = uuid.uuid5(uuid.UUID(data["tenant_id"]), f"qa-load/{i}")
            u = await db.get(User, uid)
            if not u:
                u = User(
                    id=uid,
                    email=f"qa.load{i:03}@auditos.example",
                    password_hash=encoded,
                )
                db.add(u)
                await db.flush()
                m = Membership(tenant_id=uuid.UUID(data["tenant_id"]), user_id=uid)
                db.add(m)
                await db.flush()
                db.add(MembershipRole(membership_id=m.id, role_id=role.id))
            else:
                u.status = "active"
            users.append(uid)
    results = []
    try:
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:58009",
            timeout=120,
            limits=httpx.Limits(max_connections=100),
        ) as c:
            for concurrency in [10, 25, 50, 100]:
                started = time.perf_counter()
                before = psutil.cpu_times()
                memory = psutil.virtual_memory().available

                async def read(index):
                    h = {
                        "Authorization": "Bearer " + access_token(users[index]),
                        "X-Tenant-ID": data["tenant_id"],
                    }
                    values = []
                    for path in ["clients?limit=25", "accounting/ledger?limit=50"]:
                        now = time.perf_counter()
                        try:
                            r = await c.get("/api/v1/" + path, headers=h)
                        except httpx.TransportError as exc:
                            values.append(
                                {
                                    "path": path,
                                    "status": 0,
                                    "seconds": time.perf_counter() - now,
                                    "schema_valid": False,
                                    "error": str(exc),
                                }
                            )
                            continue
                        body = r.json()
                        values.append(
                            {
                                "path": path,
                                "status": r.status_code,
                                "seconds": time.perf_counter() - now,
                                "schema_valid": r.status_code == 200
                                and isinstance(body.get("items"), list)
                                and isinstance(body.get("total"), int),
                            }
                        )
                    return values

                rows = [
                    item
                    for group in await asyncio.gather(
                        *(read(i) for i in range(concurrency))
                    )
                    for item in group
                ]
                durations = sorted(r["seconds"] for r in rows)
                after = psutil.cpu_times()
                results.append(
                    {
                        "concurrency": concurrency,
                        "distinct_users": concurrency,
                        "requests": len(rows),
                        "failures": sum(not r["schema_valid"] for r in rows),
                        "p50_seconds": statistics.median(durations),
                        "p95_seconds": durations[
                            min(len(durations) - 1, int(len(durations) * 0.95))
                        ],
                        "elapsed_seconds": time.perf_counter() - started,
                        "host_available_memory_before": memory,
                        "host_available_memory_after": psutil.virtual_memory().available,
                        "host_cpu_user_seconds": after.user - before.user,
                        "journal_lines_at_start": count,
                        "requests_detail": rows,
                    }
                )
                (out / "load-results.json").write_text(
                    json.dumps(results, indent=2), encoding="utf8"
                )
                print(
                    json.dumps(
                        {k: v for k, v in results[-1].items() if k != "requests_detail"}
                    ),
                    flush=True,
                )
    finally:
        async with Session() as db, db.begin():
            await guard(db)
            for uid in users:
                (await db.get(User, uid)).status = "disabled"
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
