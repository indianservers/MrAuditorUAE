"""Versioned, guarded synthetic fixtures using normal ORM models and real import APIs."""

import asyncio
import io
import json
import os
import platform
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from sqlalchemy import func, select

from app.core.dependencies import Context
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import access_token, hash_password
from app.db.models.platform import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
)
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import Account, JournalLine, SourceRecord
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import (
    AuditRecord,
    ClientAccess,
    EvidenceVersion,
    ReviewDecision,
)
from app.modules.demo.generator import ACCOUNTS, CLIENTS, VERSION, generate, identifier
from app.modules.demo.guard import DEMO_NAME, DEMO_TENANT, guard
from app.modules.lineage.storage import ObjectStore
from app.modules.vat.calculations import transaction
from app.modules.vat.models import DemoDataset
from app.modules.vat.schemas import Invoice
from app.modules.vat.schemas import Rule as VATRule

ROLES = [
    "Platform Super Admin",
    "Firm Administrator",
    "Managing Partner",
    "Chartered Accountant",
    "Audit Manager",
    "Senior Auditor",
    "Auditor",
    "Audit Trainee",
    "Tax Director",
    "Tax Manager",
    "Tax Consultant",
    "Financial Reporting Manager",
    "Consolidation Specialist",
    "Quality Reviewer",
    "Client Administrator",
    "Client Finance Manager",
    "Client Accountant",
    "Client Document Contributor",
    "Client Viewer",
    "Read-only Reviewer",
    "VAT Analyst",
    "VAT Manager",
    "VAT Read-only Reviewer",
    "Auditor",
    "Auditor",
]


async def identities(password):
    users: list[dict[str, Any]] = []
    async with Session() as db, db.begin():
        tenant = await guard(db, allow_new=True)
        if not tenant:
            db.add(Tenant(id=DEMO_TENANT, name=DEMO_NAME))
            await db.flush()
        await tenant_context(db, str(DEMO_TENANT))
        await db.execute(__import__("sqlalchemy").text("SELECT pg_advisory_xact_lock(7070707)"))
        dataset = await db.scalar(
            select(DemoDataset).where(
                DemoDataset.tenant_id == DEMO_TENANT, DemoDataset.seed_version == VERSION
            )
        )
        if dataset and dataset.status == "COMPLETE":
            return None, dataset.manifest
        if dataset:
            if dataset.status != "BUILDING" or not dataset.manifest.get("synthetic"):
                raise ValueError("Unexpected synthetic manifest state")
            return dataset.manifest["users"], None
        # Install the same application role defaults, without bootstrapping over existing identities.
        for name, codes in ROLE_PERMISSIONS.items():
            role = await db.scalar(select(Role).where(Role.name == name))
            if not role:
                role = Role(name=name)
                db.add(role)
                await db.flush()
            for code in codes:
                permission = await db.scalar(select(Permission).where(Permission.code == code))
                if not permission:
                    permission = Permission(code=code)
                    db.add(permission)
                    await db.flush()
                if not await db.get(RolePermission, (role.id, permission.id)):
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        for n, name in enumerate(ROLES):
            uid = identifier("user/" + str(n))
            email = f"synthetic.user{n:02d}@auditos.test"
            if await db.get(User, uid) or await db.scalar(
                select(User.id).where(User.email == email)
            ):
                raise ValueError(
                    "Synthetic user identity already exists outside this seed manifest"
                )
            user = User(
                id=uid,
                email=email,
                password_hash=hash_password(password),
                status="disabled" if n == 24 else "active",
            )
            db.add(user)
            await db.flush()
            member = Membership(
                id=identifier("member/" + str(n)), tenant_id=DEMO_TENANT, user_id=uid
            )
            db.add(member)
            await db.flush()
            role = await db.scalar(select(Role).where(Role.name == name))
            assert role is not None
            db.add(MembershipRole(membership_id=member.id, role_id=role.id))
            if n == 3:
                partner_role = await db.scalar(select(Role).where(Role.name == "Audit Partner"))
                assert partner_role is not None
                db.add(MembershipRole(membership_id=member.id, role_id=partner_role.id))
            users.append(
                {
                    "id": str(uid),
                    "membership_id": str(member.id),
                    "role_id": str(role.id),
                    "role": name,
                    "email": email,
                    "disabled": n == 24,
                    "expired": n == 23,
                }
            )
        db.add(
            DemoDataset(
                tenant_id=DEMO_TENANT,
                created_by=uuid.UUID(users[1]["id"]),
                seed_version=VERSION,
                status="BUILDING",
                manifest={
                    "synthetic": True,
                    "seed_version": VERSION,
                    "users": users,
                    "generated_at": datetime.now(UTC).isoformat(),
                },
            )
        )
    return users, None


async def fixture_record(db, eid, kind, reference, body, users, state="APPROVED", reviewer=4):
    """Synthetic review histories are explicit fixtures, never represented as real professional sign-off."""
    from app.modules.audit_execution.schemas import BODIES

    existing = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == DEMO_TENANT,
            AuditRecord.id == identifier(str(eid) + "/" + reference),
        )
    )
    if existing:
        return existing

    if kind in BODIES:
        body = BODIES[kind].model_validate(body).model_dump(mode="json")
    uid = uuid.UUID(users[6]["id"])
    obj = AuditRecord(
        id=identifier(str(eid) + "/" + reference),
        tenant_id=DEMO_TENANT,
        created_by=uid,
        prepared_by=uid,
        engagement_id=uuid.UUID(str(eid)),
        kind=kind,
        reference=reference,
        title="SYNTHETIC " + reference,
        status=state,
        body=body,
    )
    db.add(obj)
    await audit.revision(
        db,
        Context(uid, DEMO_TENANT, frozenset()),
        obj,
        "demo-seed-" + VERSION,
        "demo.fixture.created",
    )
    if state == "APPROVED":
        db.add(
            ReviewDecision(
                tenant_id=DEMO_TENANT,
                created_by=uuid.UUID(users[reviewer]["id"]),
                record_id=obj.id,
                version=obj.version,
                stage=1,
                decision="approve",
                comments="Synthetic fixture review; not real professional certification",
                prior_status="REVIEW_REQUIRED",
            )
        )
    return obj


async def seed():
    password = os.getenv("PHASE7_DEMO_PASSWORD", "")
    if len(password) < 16:
        raise ValueError(
            "Supply PHASE7_DEMO_PASSWORD (16+ characters) through the environment; never commit it"
        )
    users, existing = await identities(password)
    if existing:
        await verify(existing, finish=True)
        Path(__file__).resolve().parents[1].joinpath("docs/phase-7/demo-manifest.json").write_text(
            json.dumps(existing, indent=2)
        )
        print(json.dumps({"replayed": True, "counts": existing["counts"]}))
        return existing
    started = time.perf_counter()
    manifest = {
        "synthetic": True,
        "seed_version": VERSION,
        "tenant_id": str(DEMO_TENANT),
        "users": users,
        "generated_at": datetime.now(UTC).isoformat(),
        "engagements": [],
        "benchmarks": [],
        "counts": {},
        "hardware": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
    }
    headers = {
        "Authorization": "Bearer " + access_token(uuid.UUID(users[1]["id"])),
        "X-Tenant-ID": str(DEMO_TENANT),
    }
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=300
    ) as c:

        async def call(method, path, **kwargs):
            if method == "POST" and path in {
                "clients",
                "entities",
                "financial-periods",
                "engagements",
            }:
                from app.db.models.platform import Client, Engagement, FinancialPeriod, LegalEntity

                body = kwargs["json"]
                model: Any = {
                    "clients": Client,
                    "entities": LegalEntity,
                    "financial-periods": FinancialPeriod,
                    "engagements": Engagement,
                }[path]
                fields = {
                    "clients": ["code"],
                    "entities": ["client_id", "name"],
                    "financial-periods": ["entity_id", "start_date", "end_date"],
                    "engagements": ["entity_id", "period_id", "name"],
                }[path]
                clauses = [model.tenant_id == DEMO_TENANT]
                for field in fields:
                    value = body[field]
                    if field.endswith("_id"):
                        value = uuid.UUID(value)
                    if field.endswith("_date"):
                        value = __import__("datetime").date.fromisoformat(value)
                    clauses.append(getattr(model, field) == value)
                async with Session() as reuse_db, reuse_db.begin():
                    await guard(reuse_db)
                    await tenant_context(reuse_db, str(DEMO_TENANT))
                    existing = await reuse_db.scalar(select(model).where(*clauses))
                    if existing:
                        return audit.serialize(existing)
            response = await c.request(method, "/api/v1/" + path, headers=headers, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(path + " " + response.text)
            return response.json() if response.content else None

        for ci, name in enumerate(CLIENTS):
            client = await call(
                "POST", "clients", json={"code": f"SYN-P7-{ci:02d}", "name": "SYNTHETIC — " + name}
            )
            entity = await call(
                "POST",
                "entities",
                json={
                    "client_id": client["id"],
                    "name": "SYNTHETIC — " + name,
                    "country": "AE",
                    "jurisdiction": "Synthetic UAE test jurisdiction",
                    "functional_currency": "AED",
                    "presentation_currency": "AED",
                },
            )
            for year, count in [(2024, 167), (2025, 167), (2026, 166)]:
                period = await call(
                    "POST",
                    "financial-periods",
                    json={
                        "entity_id": entity["id"],
                        "start_date": f"{year}-01-01",
                        "end_date": f"{year}-12-31",
                    },
                )
                eng = await call(
                    "POST",
                    "engagements",
                    json={
                        "entity_id": entity["id"],
                        "period_id": period["id"],
                        "name": f"SYNTHETIC {name} FY{year}",
                        "engagement_type": [
                            "External Audit",
                            "Internal Audit",
                            "IFRS Review",
                            "Corporate Tax",
                            "VAT",
                            "Transfer Pricing",
                        ][(ci + year) % 6],
                    },
                )
                eid = eng["id"]
                async with Session() as reuse_db, reuse_db.begin():
                    from app.modules.accounting.models import ImportBatch, ImportSnapshot
                    from app.modules.vat.models import VATRun

                    await guard(reuse_db)
                    await tenant_context(reuse_db, str(DEMO_TENANT))
                    saved_profile_id = identifier(eid + "/VAT-PROFILE")
                    saved_run = await reuse_db.scalar(
                        select(VATRun)
                        .where(
                            VATRun.tenant_id == DEMO_TENANT,
                            VATRun.engagement_id == uuid.UUID(eid),
                            VATRun.kind == "vat201",
                            VATRun.inputs["profile_id"].astext == str(saved_profile_id),
                        )
                        .order_by(VATRun.created_at.desc())
                        .limit(1)
                    )
                    saved_snapshot = await reuse_db.scalar(
                        select(ImportSnapshot)
                        .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
                        .where(
                            ImportSnapshot.tenant_id == DEMO_TENANT,
                            ImportSnapshot.entity_id == uuid.UUID(entity["id"]),
                            ImportSnapshot.period_id == uuid.UUID(period["id"]),
                            ImportBatch.status == "active",
                        )
                    )
                    if (
                        saved_run
                        and saved_snapshot
                        and saved_run.results["validation"]["ready"]
                        and saved_run.results["invoice_count"] == count
                    ):
                        expected = generate(ci, year, count)
                        manifest["engagements"].append(
                            {
                                "id": eid,
                                "client_id": client["id"],
                                "entity_id": entity["id"],
                                "period_id": period["id"],
                                "year": year,
                                "snapshot_id": str(saved_snapshot.id),
                                "vat_profile_id": str(saved_profile_id),
                                "vat_run_id": str(saved_run.id),
                                "invoice_id": str(identifier(eid + "/VAT-INVOICE-0")),
                                "request_id": str(identifier(eid + "/PBC-REQUEST")),
                                "expected_net_vat": expected["expected_net_vat"],
                                "expected_balances": expected["balances"],
                            }
                        )
                        print(f"Reused completed SYNTHETIC client{ci} FY{year}", flush=True)
                        continue
                for n in [3, 4, 6, 9, 10, 11, 13, 20, 21, 22, 23]:
                    expiry = (
                        (datetime.now(UTC) - timedelta(days=1)).isoformat() if n == 23 else None
                    )
                    await call(
                        "POST",
                        f"engagements/{eid}/audit/team",
                        json={
                            "membership_id": users[n]["membership_id"],
                            "role_id": users[n]["role_id"],
                            "expires_at": expiry,
                        },
                    )
                generated = generate(ci, year, count)
                phase = time.perf_counter()
                opts = {
                    "client_id": client["id"],
                    "entity_id": entity["id"],
                    "period_id": period["id"],
                    "expected_rows": generated["rows"],
                    "expected_debit": generated["debit"],
                    "expected_credit": generated["credit"],
                    "source_complete": True,
                }
                batch = await call(
                    "POST",
                    "accounting/imports",
                    data={"options": json.dumps(opts)},
                    files={"file": ("SYNTHETIC.csv", generated["csv"], "text/csv")},
                )
                uploaded = time.perf_counter()
                checked = await call("POST", f"accounting/imports/{batch['id']}/validate")
                if checked["status"] not in {"validated", "active"}:
                    raise ValueError("Synthetic normal source failed validation")
                validated = time.perf_counter()
                await call("POST", f"accounting/imports/{batch['id']}/commit")
                committed = time.perf_counter()
                details = await call("GET", f"accounting/imports/{batch['id']}")
                sid = details["snapshot_id"]
                tb = await call("GET", "accounting/trial-balance", params={"snapshot_id": sid})
                if not tb["balanced"]:
                    raise ValueError("Synthetic ledger/TB imbalance")
                tb_end = time.perf_counter()
                async with Session() as db, db.begin():
                    await guard(db)
                    await tenant_context(db, str(DEMO_TENANT))
                    lines = (
                        await db.execute(
                            select(SourceRecord.source_id, JournalLine.id)
                            .join(JournalLine, JournalLine.source_record_id == SourceRecord.id)
                            .where(
                                SourceRecord.tenant_id == DEMO_TENANT,
                                SourceRecord.batch_id == uuid.UUID(batch["id"]),
                            )
                        )
                    ).all()
                    source_ids = {key: str(rid) for key, rid in lines}
                    existing_accounts = set(
                        (
                            await db.scalars(
                                select(Account.code).where(
                                    Account.tenant_id == DEMO_TENANT,
                                    Account.entity_id == uuid.UUID(entity["id"]),
                                )
                            )
                        ).all()
                    )
                    for code, label in ACCOUNTS.items():
                        if code not in existing_accounts:
                            db.add(
                                Account(
                                    tenant_id=DEMO_TENANT,
                                    created_by=uuid.UUID(users[1]["id"]),
                                    client_id=uuid.UUID(client["id"]),
                                    entity_id=uuid.UUID(entity["id"]),
                                    period_id=uuid.UUID(period["id"]),
                                    code=code,
                                    name=label,
                                )
                            )
                    for u in users:
                        if u["role"].startswith("Client"):
                            if not await db.scalar(
                                select(ClientAccess.id).where(
                                    ClientAccess.tenant_id == DEMO_TENANT,
                                    ClientAccess.client_id == uuid.UUID(client["id"]),
                                    ClientAccess.membership_id == uuid.UUID(u["membership_id"]),
                                )
                            ):
                                # Client identities are deliberately restricted to the first client only.
                                if ci == 0:
                                    db.add(
                                        ClientAccess(
                                            tenant_id=DEMO_TENANT,
                                            created_by=uuid.UUID(users[1]["id"]),
                                            client_id=uuid.UUID(client["id"]),
                                            membership_id=uuid.UUID(u["membership_id"]),
                                        )
                                    )
                    wp = await fixture_record(
                        db,
                        eid,
                        "working-papers",
                        f"P7-SOURCE-{year}",
                        {
                            "folder": "Synthetic VAT evidence",
                            "sections": [
                                {
                                    "heading": "Source and judgment",
                                    "text": "Synthetic reviewed invoice/source allocation; nonproduction only",
                                }
                            ],
                            "conclusion": "Synthetic evidence, no real audit opinion",
                        },
                        users,
                    )
                    rule_ids = {}
                    rule_bodies = {}
                    definitions = {
                        "output": ("VAT-LAW", "3", "2018-01-01"),
                        "input": ("VAT-LAW", "54", "2018-01-01"),
                        "invoice": ("VAT-ER", "59", "2018-01-01"),
                        "return": ("VAT201", "", "2022-10-01"),
                        "einvoice": ("MD66-2026", "One", "2026-05-14"),
                    }
                    if year == 2026:
                        definitions.update(
                            integrity=("FTA13-2026", "5", "2026-10-01"),
                            employee=("FTA17-2026", "2", "2026-10-01"),
                        )
                    for category, (source, article, effective) in definitions.items():
                        rulebody = {
                            "rule_key": category,
                            "rule_version": 1,
                            "category": category,
                            "source_id": source,
                            "article": article,
                            "effective_from": effective,
                            "known_from": effective,
                            "source_document_version": "Synthetic technical fixture; historical invoice requirements reviewed for applicable year",
                            "technical_review": "Synthetic independent technical fixture review",
                            "conditions": "Explicit synthetic scope; facts and legislation require production professional review",
                            "exceptions": "No automatic legal compliance conclusion",
                        }
                        obj = await fixture_record(
                            db, eid, "vat-rule", "VAT-RULE-" + category, rulebody, users, reviewer=9
                        )
                        rule_ids[category] = str(obj.id)
                        rule_bodies[category] = VATRule.model_validate(rulebody)
                    profilebody = {
                        "trn": "999999999999999",
                        "registration_status": "REGISTERED",
                        "registered_from": "2024-01-01",
                        "filing_frequency": "monthly",
                        "period_start": f"{year}-10-01",
                        "period_end": f"{year}-10-31",
                        "legal_as_of": "2026-10-18",
                        "activities": "Synthetic UAE commercial activities",
                        "input_recovery_assessment": "Synthetic full taxable business use; no unsupported employee recovery",
                        "jurisdictions": ["AE", "GB"],
                        "rules": rule_ids,
                        "output_control_codes": ["240"],
                        "input_control_codes": ["180"],
                        "filing_obligations": "Synthetic assigned October monthly period",
                        "calendar_review": "Synthetic Sat/Sun business calendar; actual public holidays need review",
                    }
                    profile_obj = await fixture_record(
                        db, eid, "vat-profile", "VAT-PROFILE", profilebody, users, reviewer=9
                    )
                    for i, item in enumerate(generated["invoices"]):
                        inv = dict(item)
                        sources = inv.pop("source_ids")
                        original_index = inv.pop("original_index")
                        inv.pop("expected_output")
                        inv.pop("expected_input")
                        inv.update(
                            profile_id=str(profile_obj.id),
                            rule_id=rule_ids["output" if inv["direction"] == "sale" else "input"],
                            invoice_rule_id=rule_ids["invoice"],
                            evidence_record_ids=[str(wp.id)],
                            recovery_evidence_ids=[str(wp.id)]
                            if inv["direction"] == "purchase"
                            else [],
                            integrity_review_evidence_id=str(wp.id) if year == 2026 else None,
                            net_line_ids=[
                                source_ids[sources["400" if inv["direction"] == "sale" else "500"]]
                            ],
                            output_tax_line_ids=[source_ids[sources["240"]]]
                            if "240" in sources
                            else [],
                            input_tax_line_ids=[source_ids[sources["180"]]]
                            if "180" in sources
                            else [],
                        )
                        if original_index is not None:
                            inv["original_invoice_id"] = str(
                                identifier(eid + "/VAT-INVOICE-" + str(original_index))
                            )
                        parsed = Invoice.model_validate(inv)
                        outcome = transaction(
                            parsed,
                            rule_bodies["output" if inv["direction"] == "sale" else "input"],
                            rule_bodies["invoice"],
                        )
                        if not outcome["valid"]:
                            raise ValueError(outcome["issues"])
                        await fixture_record(
                            db, eid, "vat-invoice", "VAT-INVOICE-" + str(i), inv, users, reviewer=9
                        )
                    for n in range(4):
                        await fixture_record(
                            db,
                            eid,
                            "working-papers",
                            f"WP-{n}",
                            {
                                "folder": "Synthetic audit",
                                "sections": [
                                    {"heading": "Test", "text": "Trace actual source transaction"}
                                ],
                                "conclusion": "Synthetic review",
                                "sources": [
                                    {"kind": "journal", "id": next(iter(source_ids.values()))}
                                ],
                            },
                            users,
                            state="APPROVED" if n % 2 == 0 else "REVIEW_REQUIRED",
                        )
                        await fixture_record(
                            db,
                            eid,
                            "procedures",
                            f"PROC-{n}",
                            {
                                "methodology_version": VERSION,
                                "objective": "Inspect synthetic journal source",
                                "required_evidence": "Synthetic voucher",
                                "instructions": "Trace selected amount and approval",
                                "sources": [
                                    {"kind": "journal", "id": next(iter(source_ids.values()))}
                                ],
                            },
                            users,
                            state="IN_PROGRESS",
                        )
                    for n in range(2):
                        await fixture_record(
                            db,
                            eid,
                            "findings",
                            f"FIND-{n}",
                            {
                                "finding_type": "reconciliation",
                                "severity": "medium",
                                "narrative": "Synthetic exception linked to an actual source",
                                "sources": [
                                    {"kind": "journal", "id": next(iter(source_ids.values()))}
                                ],
                                "management_response": "Awaiting synthetic response",
                            },
                            users,
                            state="OPEN" if n == 0 else "RESOLVED",
                        )
                    for n in range(4):
                        evidence_obj = await fixture_record(
                            db,
                            eid,
                            "evidence",
                            f"EVID-{n}",
                            {"category": "Synthetic voucher", "retain_until": "2036-12-31"},
                            users,
                            state="IN_PROGRESS",
                        )
                        if await db.scalar(
                            select(EvidenceVersion.id).where(
                                EvidenceVersion.tenant_id == DEMO_TENANT,
                                EvidenceVersion.record_id == evidence_obj.id,
                            )
                        ):
                            continue
                        metadata = ObjectStore().put(
                            str(DEMO_TENANT),
                            io.BytesIO(b"SYNTHETIC TEST VOUCHER - unscanned, not approved"),
                        )
                        db.add(
                            EvidenceVersion(
                                tenant_id=DEMO_TENANT,
                                created_by=uuid.UUID(users[6]["id"]),
                                record_id=evidence_obj.id,
                                number=1,
                                filename="synthetic-voucher.txt",
                                media_type="text/plain",
                                object_key=metadata["object_key"],
                                object_version=metadata["object_version"],
                                sha256=metadata["sha256"],
                                size=metadata["size"],
                                scan_status="QUARANTINED",
                            )
                        )
                    req = await fixture_record(
                        db,
                        eid,
                        "requests",
                        "PBC-REQUEST",
                        {
                            "client_id": client["id"],
                            "question": "Upload the synthetic requested invoice evidence",
                        },
                        users,
                        state="SENT",
                    )
                # The actual VAT engine, not the fixture generator, must independently reconcile stored source facts.
                phase_vat = time.perf_counter()
                computed = await call(
                    "POST", f"vat/engagements/{eid}/computations/{profile_obj.id}"
                )
                if not computed["results"]["validation"]["ready"] or Decimal(
                    computed["results"]["net_vat"]
                ) != Decimal(generated["expected_net_vat"]):
                    raise ValueError(computed["results"]["exceptions"])
                for sample in range(2):
                    await call(
                        "POST",
                        "sampling/runs",
                        json={
                            "snapshot_id": sid,
                            "method": "random",
                            "size": 5,
                            "seed": year + sample,
                        },
                    )
                if ci == 0:
                    await call(
                        "POST",
                        "analytics/runs",
                        json={
                            "snapshot_id": sid,
                            "materiality": "100000",
                        },
                    )
                manifest["engagements"].append(
                    {
                        "id": eid,
                        "client_id": client["id"],
                        "entity_id": entity["id"],
                        "period_id": period["id"],
                        "year": year,
                        "snapshot_id": sid,
                        "vat_profile_id": str(profile_obj.id),
                        "vat_run_id": computed["id"],
                        "invoice_id": str(identifier(eid + "/VAT-INVOICE-0")),
                        "request_id": str(req.id),
                        "expected_net_vat": generated["expected_net_vat"],
                        "expected_balances": generated["balances"],
                    }
                )
                manifest["benchmarks"].append(
                    {
                        "client": ci,
                        "year": year,
                        "rows": generated["rows"],
                        "upload_seconds": uploaded - phase,
                        "validation_seconds": validated - uploaded,
                        "commit_seconds": committed - validated,
                        "tb_seconds": tb_end - committed,
                        "vat_seconds": time.perf_counter() - phase_vat,
                    }
                )
                print(
                    f"SYNTHETIC {ci + 1}/10 FY{year}: {generated['rows']} journal lines, {count} invoices, VAT reconciled",
                    flush=True,
                )
    manifest["generation_seconds"] = time.perf_counter() - started
    await verify(manifest, finish=True)
    target = Path(__file__).resolve().parents[1] / "docs/phase-7/demo-manifest.json"
    target.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"counts": manifest["counts"], "seconds": manifest["generation_seconds"]}))
    return manifest


async def verify(manifest, finish=False):
    from app.db.models.platform import Client, Engagement, FinancialPeriod, LegalEntity
    from app.modules.accounting.models import AnalyticsRun, SamplingRun

    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        counts: dict[str, Any] = {}
        models: list[tuple[str, Any]] = [
            ("clients", Client),
            ("entities", LegalEntity),
            ("engagements", Engagement),
            ("journal_lines", JournalLine),
            ("samples", SamplingRun),
            ("financial_periods", FinancialPeriod),
            ("chart_accounts", Account),
            ("users", Membership),
            ("analytics_runs", AnalyticsRun),
        ]
        for label, model in models:
            counts[label] = await db.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == DEMO_TENANT)
            )
        for kind in ["vat-invoice", "working-papers", "findings", "procedures", "evidence"]:
            counts[kind] = await db.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.tenant_id == DEMO_TENANT, AuditRecord.kind == kind)
            )
        if (
            counts["clients"] < 10
            or counts["journal_lines"] < 250000
            or counts["vat-invoice"] < 5000
        ):
            raise ValueError("Demo dataset count/integrity mismatch")
        manifest["counts"] = counts
        manifest["record_inventory"] = [
            {"kind": kind, "status": status, "count": count}
            for kind, status, count in (
                await db.execute(
                    select(AuditRecord.kind, AuditRecord.status, func.count())
                    .where(AuditRecord.tenant_id == DEMO_TENANT)
                    .group_by(AuditRecord.kind, AuditRecord.status)
                    .order_by(AuditRecord.kind, AuditRecord.status)
                )
            ).all()
        ]
        if finish:
            dataset = await db.scalar(
                select(DemoDataset).where(
                    DemoDataset.tenant_id == DEMO_TENANT, DemoDataset.seed_version == VERSION
                )
            )
            assert dataset is not None
            dataset.status = "COMPLETE"
            dataset.manifest = manifest


async def cleanup(confirm):
    if confirm != "ARCHIVE-" + str(DEMO_TENANT):
        raise ValueError("Explicit demo tenant archive confirmation required")
    async with Session() as db, db.begin():
        tenant = await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        tenant.status = "archived"
        for membership in (
            await db.scalars(select(Membership).where(Membership.tenant_id == DEMO_TENANT))
        ).all():
            membership.status = "inactive"
        for dataset in (
            await db.scalars(select(DemoDataset).where(DemoDataset.tenant_id == DEMO_TENANT))
        ).all():
            dataset.status = "ARCHIVED"
    print(
        "Demo tenant archived; immutable history retained. No other tenant or global user modified."
    )


async def main():
    try:
        if os.getenv("DEMO_ARCHIVE_CONFIRM"):
            await cleanup(os.environ["DEMO_ARCHIVE_CONFIRM"])
        else:
            await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
