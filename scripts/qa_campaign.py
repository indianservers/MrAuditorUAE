"""Guarded, resumable QA population and actual API execution. No shared DB cleanup."""

import asyncio
import csv
import hashlib
import io
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.core.config import settings
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import hash_password
from app.db.models.platform import Membership, MembershipRole, Role, Tenant, User
from app.db.session import Session, engine, tenant_context
from app.main import app
from app.modules.accounting.models import JournalLine
from app.modules.demo.generator import ACCOUNTS
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

OUT = ROOT / "docs/qa-campaign"
LOCAL = ROOT / ".local-runtime/qa-campaign"
NAME = "AuditOS QA Chartered Accountants [SYNTHETIC]"
DATABASE = "auditos_qa_campaign_demo"
MANIFEST = OUT / "dataset.json"
INDUSTRIES = [
    "General Trading",
    "Manufacturing",
    "Logistics",
    "IT Services",
    "Consulting",
    "Construction",
    "Property Investment",
    "Property Development",
    "Hospitality",
    "Retail",
    "Healthcare",
    "Education",
    "Holding",
    "Free Zone",
    "International Trading",
    "Financial Services",
    "Professional Services",
    "Manufacturing",
    "Logistics",
    "IT Services",
    "Retail",
    "Holding",
    "Free Zone",
    "Foreign Subsidiary",
    "Joint Venture",
]


async def guard(db):
    cfg = settings()
    url = make_url(cfg.database_url)
    if (
        cfg.environment != "development"
        or os.getenv("QA_CAMPAIGN_ENABLED") != "true"
        or not cfg.synthetic_data_enabled
        or url.database != DATABASE
        or url.host != "127.0.0.1"
        or url.port != 55432
        or await db.scalar(text("SELECT current_database()")) != DATABASE
    ):
        raise RuntimeError("QA requires explicit local isolated campaign database")
    tenants = (await db.scalars(select(Tenant))).all()
    if any(t.name != NAME for t in tenants):
        raise RuntimeError("Foreign or unmarked tenant found; population blocked")


def save(data):
    MANIFEST.write_text(json.dumps(data, indent=2), encoding="utf8")


def journal_csv(start, count, year=2026):
    """Independent balanced legs with deterministic labels; not detector outputs."""
    stream = io.StringIO()
    w = csv.writer(stream, lineterminator="\n")
    w.writerow(
        [
            "Account Code",
            "Account Name",
            "Journal Number",
            "Posting Date",
            "Debit",
            "Credit",
            "Source ID",
            "Opening",
            "Manual",
            "Narration",
            "Currency",
            "Counterparty",
            "Cost Center",
        ]
    )
    pairs = [
        ("110", "400", "Sales invoice"),
        ("520", "200", "Purchase invoice"),
        ("101", "110", "Cash receipt"),
        ("200", "101", "Supplier payment"),
        ("510", "101", "Payroll"),
        ("120", "200", "Inventory purchase"),
        ("500", "120", "Inventory sale"),
        ("520", "141", "Depreciation"),
        ("530", "210", "Interest accrual"),
        ("101", "230", "Loan drawdown"),
        ("230", "101", "Loan repayment"),
        ("220", "101", "Lease payment"),
        ("180", "240", "VAT transfer"),
        ("540", "210", "Corporate Tax provision"),
        ("170", "250", "Related party"),
        ("101", "400", "Foreign sales"),
        ("520", "210", "Year end accrual"),
        ("210", "520", "Accrual reversal"),
    ]
    debit = Decimal(0)
    for n in range(start // 2, (start + count) // 2):
        a, b, kind = pairs[n % len(pairs)]
        amount = Decimal((n * 7919) % 990000 + 1000) / 100
        if n % 97 == 0:
            amount = Decimal("10000.00")
        reference = f"QA-J-{n:09}"
        day = f"{year}-{n % 12 + 1:02}-{n % 28 + 1:02}"
        for leg, code in enumerate((a, b)):
            w.writerow(
                [
                    code,
                    ACCOUNTS[code],
                    reference,
                    day,
                    str(amount if leg == 0 else 0),
                    str(amount if leg else 0),
                    f"{reference}-{leg}",
                    "false",
                    "true" if n % 97 == 0 else "false",
                    f"SYNTHETIC {kind} vendor-{n % 101:03}",
                    "AED",
                    f"QA-VENDOR-{n % 101:03}",
                    f"QA-CC-{n % 8}",
                ]
            )
        debit += amount
    return stream.getvalue().encode(), str(debit)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with Session() as db:
        await guard(db)
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=900,
    ) as client:
        headers = {}

        async def call(method, path, expected=None, **kw):
            started = time.perf_counter()
            r = await client.request(method, "/api/v1/" + path, headers=headers, **kw)
            receipt = {
                "method": method,
                "path": path,
                "status": r.status_code,
                "seconds": round(time.perf_counter() - started, 4),
                "time": datetime.now(UTC).isoformat(),
            }
            calls.append(receipt)
            with (OUT / "api-execution.jsonl").open("a", encoding="utf8") as f:
                f.write(json.dumps(receipt) + "\n")
            if expected is not None:
                assert r.status_code == expected, (path, r.status_code, r.text[:1000])
            elif r.status_code >= 400:
                raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:1000]}")
            return r.json() if r.content else None

        password = os.environ["QA_PASSWORD"]
        if MANIFEST.exists():
            data = json.loads(MANIFEST.read_text(encoding="utf8"))
        else:
            cfg = settings()
            response = await client.post(
                "/api/v1/auth/bootstrap",
                headers={"X-Bootstrap-Secret": cfg.bootstrap_secret},
                json={
                    "email": "qa.admin@auditos.example",
                    "password": password,
                    "tenant_name": NAME,
                },
            )
            assert response.status_code == 201, response.text
            async with Session() as db:
                tenant = await db.scalar(select(Tenant).where(Tenant.name == NAME))
                tid = str(tenant.id)
            data = {
                "synthetic": True,
                "database": DATABASE,
                "tenant_id": tid,
                "created_at": datetime.now(UTC).isoformat(),
                "companies": [],
                "batches": [],
                "stages": [],
                "users": [],
            }
            save(data)
        login = await call(
            "POST",
            "auth/login",
            data={"username": "qa.admin@auditos.example", "password": password},
        )
        headers.update(
            Authorization="Bearer " + login["access_token"],
            **{"X-Tenant-ID": data["tenant_id"]},
        )
        if not data["users"]:
            async with Session() as db, db.begin():
                await guard(db)
                await tenant_context(db, data["tenant_id"])
                for index, role_name in enumerate(ROLE_PERMISSIONS):
                    role = await db.scalar(select(Role).where(Role.name == role_name))
                    assert role is not None
                    uid = uuid.uuid5(uuid.UUID(data["tenant_id"]), role_name)
                    email = f"qa.role{index:02}@auditos.example"
                    user = User(
                        id=uid, email=email, password_hash=hash_password(password)
                    )
                    db.add(user)
                    await db.flush()
                    member = Membership(
                        tenant_id=uuid.UUID(data["tenant_id"]), user_id=uid
                    )
                    db.add(member)
                    await db.flush()
                    db.add(MembershipRole(membership_id=member.id, role_id=role.id))
                    data["users"].append(
                        {
                            "id": str(uid),
                            "email": email,
                            "role": role_name,
                            "membership_id": str(member.id),
                            "role_id": str(role.id),
                        }
                    )
            save(data)
        for i in range(len(data["companies"]), 25):
            name = f"QA FICTIONAL {i + 1:02} {INDUSTRIES[i]}"
            c = await call(
                "POST", "clients", json={"code": f"QA-{i + 1:02}", "name": name}
            )
            e = await call(
                "POST",
                "entities",
                json={
                    "client_id": c["id"],
                    "name": name,
                    "country": "GB" if i == 23 else "AE",
                    "jurisdiction": "SYNTHETIC Free Zone"
                    if i in {13, 22}
                    else "SYNTHETIC Mainland",
                    "functional_currency": "AED",
                    "presentation_currency": "AED",
                },
            )
            p = await call(
                "POST",
                "financial-periods",
                json={
                    "entity_id": e["id"],
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                },
            )
            engagements = []
            for kind in [
                "External Audit",
                "IFRS Review",
                "Corporate Tax",
                "Internal Audit",
            ]:
                engagements.append(
                    await call(
                        "POST",
                        "engagements",
                        json={
                            "entity_id": e["id"],
                            "period_id": p["id"],
                            "name": f"{name} {kind}",
                            "engagement_type": kind,
                        },
                    )
                )
            data["companies"].append(
                {
                    "client_id": c["id"],
                    "entity_id": e["id"],
                    "period_id": p["id"],
                    "name": name,
                    "industry": INDUSTRIES[i],
                    "engagements": engagements,
                }
            )
            save(data)
        limit = int(os.getenv("QA_TARGET_LINES", "10000"))
        for target in [10000, 100000, 250000, 500000, 1000000]:
            if target > limit or any(s["target"] == target for s in data["stages"]):
                continue
            stage_start = time.perf_counter()
            while sum(b["lines"] for b in data["batches"]) < target:
                current = sum(b["lines"] for b in data["batches"])
                count = min(10000, target - current)
                company = data["companies"][len(data["batches"]) % 25]
                year = 2026 - len(data["batches"]) // 25
                period_id = company["period_id"]
                if year != 2026:
                    company.setdefault("scale_periods", {})
                    if str(year) not in company["scale_periods"]:
                        p = await call(
                            "POST",
                            "financial-periods",
                            json={
                                "entity_id": company["entity_id"],
                                "start_date": f"{year}-01-01",
                                "end_date": f"{year}-12-31",
                            },
                        )
                        company["scale_periods"][str(year)] = p["id"]
                        save(data)
                    period_id = company["scale_periods"][str(year)]
                payload, total = journal_csv(current, count, year)
                options = {
                    k: company[k] for k in ["client_id", "entity_id", "period_id"]
                }
                options["period_id"] = period_id
                options.update(
                    expected_rows=count,
                    expected_debit=total,
                    expected_credit=total,
                    source_complete=True,
                )
                start = time.perf_counter()
                b = await call(
                    "POST",
                    "accounting/imports",
                    data={"options": json.dumps(options)},
                    files={"file": (f"QA-{current}.csv", payload, "text/csv")},
                )
                valid = await call("POST", f"accounting/imports/{b['id']}/validate")
                assert valid["status"] == "validated", valid
                await call("POST", f"accounting/imports/{b['id']}/commit")
                detail = await call("GET", f"accounting/imports/{b['id']}")
                tb = await call(
                    "GET",
                    "accounting/trial-balance",
                    params={"snapshot_id": detail["snapshot_id"]},
                )
                assert tb["balanced"], tb
                data["batches"].append(
                    {
                        "id": b["id"],
                        "snapshot_id": detail["snapshot_id"],
                        "company": company["name"],
                        "lines": count,
                        "debit": total,
                        "credit": total,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "seconds": time.perf_counter() - start,
                        "tb_balanced": True,
                    }
                )
                save(data)
                print(
                    f"Committed and reconciled {current + count} journal lines",
                    flush=True,
                )
            async with Session() as db, db.begin():
                await guard(db)
                await tenant_context(db, data["tenant_id"])
                batch_ids = [uuid.UUID(b["id"]) for b in data["batches"]]
                actual = await db.scalar(
                    select(func.count())
                    .select_from(JournalLine)
                    .where(JournalLine.batch_id.in_(batch_ids))
                )
                sums = (
                    await db.execute(
                        select(
                            func.sum(JournalLine.base_debit),
                            func.sum(JournalLine.base_credit),
                        ).where(JournalLine.batch_id.in_(batch_ids))
                    )
                ).one()
                assert actual == target and sums[0] == sums[1], (actual, sums)
            data["stages"].append(
                {
                    "target": target,
                    "actual": actual,
                    "debit": str(sums[0]),
                    "credit": str(sums[1]),
                    "seconds": time.perf_counter() - stage_start,
                    "passed": True,
                }
            )
            save(data)
        print(
            json.dumps(
                {
                    "companies": len(data["companies"]),
                    "users": len(data["users"]),
                    "journal_lines": sum(b["lines"] for b in data["batches"]),
                }
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
