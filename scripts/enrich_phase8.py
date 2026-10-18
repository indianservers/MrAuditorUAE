"""Guarded Phase 8 synthetic overlays; preserves every Phase 7 ledger and source run.

All economic classifications are explicit software fixtures, never market evidence.
Remuneration examples remain draft because existing purchase postings are not payroll.
"""

import asyncio
import csv
import io
import json
import os
import sys
import uuid
from collections import Counter
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from app.core.security import access_token, hash_password
from app.db.models.platform import Membership, MembershipRole, Role, User
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import Account, JournalLine
from app.modules.audit_execution.models import AuditAccess, AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.ifrs.models import CalculationRun as IFRSRun
from app.modules.tp.catalogue import LOCAL_SECTIONS, MASTER_SECTIONS
from app.modules.tp.models import TPRun
from app.modules.vat.models import DemoDataset
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]


async def enrich():
    manifest = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    password = os.getenv("PHASE7_DEMO_PASSWORD", "")
    if len(password) < 16:
        raise ValueError(
            "Supply the existing isolated demo password through PHASE7_DEMO_PASSWORD"
        )
    tp_users = []
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        entry = next(x for x in manifest["engagements"] if x["year"] == 2026)
        for name in [
            "TP Analyst",
            "TP Manager",
            "Transfer Pricing Director",
            "TP Economist",
            "Financial Analyst",
            "TP Read-only Reviewer",
        ]:
            uid = uuid.uuid5(DEMO_TENANT, "phase8-user/" + name)
            mid = uuid.uuid5(DEMO_TENANT, "phase8-member/" + name)
            role = await db.scalar(select(Role).where(Role.name == name))
            if not role:
                raise ValueError("Apply migration 0008 before provisioning TP roles")
            email = "synthetic." + name.lower().replace(" ", ".") + "@auditos.test"
            if not await db.get(User, uid):
                db.add(User(id=uid, email=email, password_hash=hash_password(password)))
                await db.flush()
                db.add(Membership(id=mid, tenant_id=DEMO_TENANT, user_id=uid))
                await db.flush()
                db.add(MembershipRole(membership_id=mid, role_id=role.id))
                db.add(
                    AuditAccess(
                        id=uuid.uuid5(DEMO_TENANT, "phase8-grant/" + name),
                        tenant_id=DEMO_TENANT,
                        created_by=uuid.UUID(manifest["users"][1]["id"]),
                        engagement_id=uuid.UUID(entry["id"]),
                        membership_id=mid,
                        role_id=role.id,
                    )
                )
            tp_users.append(
                {
                    "id": str(uid),
                    "membership_id": str(mid),
                    "role": name,
                    "email": email,
                }
            )
        financial = await db.get(IFRSRun, uuid.UUID(entry["ifrs_run_id"]))
        financial_lines = financial.results["lines"]
        rows = (
            await db.execute(
                select(Account.code, JournalLine)
                .join(JournalLine, JournalLine.account_id == Account.id)
                .where(
                    JournalLine.period_id == uuid.UUID(entry["period_id"]),
                    Account.code.in_(["400", "500"]),
                )
                .order_by(JournalLine.posting_date, JournalLine.id)
                .limit(110)
            )
        ).all()
    from app.main import app

    eid = entry["id"]
    base = f"engagements/{eid}/audit"
    tp = f"tp/engagements/{eid}"
    users = manifest["users"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=300,
    ) as c:

        def headers(who):
            return {
                "Authorization": "Bearer " + access_token(uuid.UUID(users[who]["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            }

        async def call(path, body=None, who=1, method="POST", files=None):
            r = await c.request(
                method,
                "/api/v1/" + path,
                headers=headers(who),
                **({"json": body} if body is not None else {}),
                **({"files": files} if files else {}),
            )
            if r.status_code >= 400:
                raise RuntimeError(path + " " + r.text)
            return r.json()

        async def paper(kind, body, reference, approve=True, stages=False):
            reference = "P8-" + reference
            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                obj = await db.scalar(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == DEMO_TENANT,
                        AuditRecord.engagement_id == uuid.UUID(eid),
                        AuditRecord.kind == "tp-" + kind,
                        AuditRecord.reference == reference,
                    )
                )
                if obj:
                    from app.modules.audit_execution.service import serialize
                    from app.modules.tp.schemas import BODIES
                    from app.modules.tp.service import clean

                    result = serialize(obj)
                    if BODIES[kind].model_validate(clean(result["body"])).model_dump(mode="json") != BODIES[kind].model_validate(
                        body
                    ).model_dump(mode="json"):
                        raise ValueError(
                            "Existing fixture facts differ; use a new seed version: "
                            + reference
                        )
                else:
                    result = None
            if not result:
                result = await call(
                    tp + "/records/" + kind,
                    {
                        "reference": reference,
                        "title": "SYNTHETIC " + reference,
                        "body": body,
                    },
                )
            if not approve or result["status"] == "APPROVED":
                return result

            async def action(action, who):
                return await call(
                    base + f"/records/{result['id']}/actions",
                    {
                        "version": result["version"],
                        "action": action,
                        "comments": "SYNTHETIC software fixture reviewed; no market or legal opinion",
                    },
                    who,
                )

            if result["status"] == "IN_PROGRESS":
                result = await action("submit", 1)
            if result["status"] == "REVIEW_REQUIRED" and result["body"].get(
                "review_stage", 0
            ):
                result = await action("approve", 3)
            else:
                result = await action("approve", 9)
                if stages and result["status"] == "REVIEW_REQUIRED":
                    result = await action("approve", 3)
            return result

        async def calculate(record):
            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                old = await db.scalar(
                    select(TPRun)
                    .where(
                        TPRun.tenant_id == DEMO_TENANT,
                        TPRun.record_id == uuid.UUID(record["id"]),
                    )
                    .order_by(TPRun.created_at.desc())
                    .limit(1)
                )
                if old:
                    return {"id": str(old.id), "results": old.results}
            return await call(tp + "/calculate/" + record["id"])

        rules = {}
        for category, source, article, known in [
            ("relationships", "CT-LAW", "35", "2022-10-10"),
            ("documentation", "MD97-2023", "2", "2023-05-15"),
            ("disclosure", "CTGTXR1", "16.1", "2024-11-11"),
            ("methodology", "OECD2022", "II", "2022-01-20"),
            ("apa", "CTGAPA1", "3", "2025-12-30"),
        ]:
            r = await paper(
                "rule",
                {
                    "source_id": source,
                    "article": article,
                    "category": category,
                    "rule_key": category,
                    "rule_version": 1,
                    "effective_from": "2025-12-30"
                    if category == "apa"
                    else "2023-06-01",
                    "known_from": known,
                    "document_version": "Synthetic adoption of official source metadata",
                    "technical_review": "Synthetic independent adoption; production review still required",
                    "conditions": "Synthetic reviewed fact patterns only",
                },
                "RULE-" + category,
            )
            rules[category] = r["id"]
        profile = await paper(
            "profile",
            {
                "financial_run_id": entry["ifrs_run_id"],
                "tax_start": "2026-01-01",
                "tax_end": "2026-12-31",
                "legal_as_of": "2026-10-18",
                "rules": rules,
                "mne_member": True,
                "group_revenue": "4000000000",
                "group_facts": "SYNTHETIC fictional MNE structure; not original client ownership evidence",
                "financial_classification": "Existing approved Phase 7 IFRS statement source preserved",
            },
            "PROFILE",
        )
        common = {
            "profile_id": profile["id"],
            "evidence_record_ids": [entry["source_note_id"]],
            "rationale": "SYNTHETIC explicit economic fixture overlay; original imported source preserved",
        }
        parties = []
        for i, entity in enumerate(
            [x for x in manifest["engagements"] if x["year"] == 2026]
        ):
            parties.append(
                await paper(
                    "party",
                    {
                        **common,
                        "name": f"SYNTHETIC UAE group company {i + 1}",
                        "entity_id": entity["entity_id"],
                        "jurisdiction": "AE",
                        "party_type": "company",
                        "synthetic": True,
                    },
                    f"PARTY-{i + 1}",
                )
            )
        foreign = await paper(
            "party",
            {
                **common,
                "name": "SYNTHETIC overseas common parent",
                "jurisdiction": "GB",
                "party_type": "company",
                "synthetic": True,
            },
            "FOREIGN",
        )
        relationship = None
        for i, party in enumerate(parties):
            relation = await paper(
                "relationship",
                {
                    **common,
                    "from_party_id": foreign["id"],
                    "to_party_id": party["id"],
                    "relationship_type": "ownership",
                    "ownership": ".8",
                    "effective_from": "2026-01-01",
                    "control_facts": "Synthetic common control fixture reviewed separately from financial source",
                    "decision": "RELATED",
                    "rule_id": rules["relationships"],
                },
                f"RELATION-{i + 1}",
            )
            if i == 0:
                relationship = relation
        transactions = []
        for i, (code, row) in enumerate(rows[:100]):
            transactions.append(
                await paper(
                    "transaction",
                    {
                        **common,
                        "relationship_id": relationship["id"],
                        "counterparty_id": foreign["id"],
                        "transaction_date": str(row.posting_date),
                        "category": "goods",
                        "nature": "sales" if code == "400" else "purchases",
                        "side": "revenue" if code == "400" else "expense",
                        "economic_key": "P8-" + str(row.id),
                        "journal_line_ids": [str(row.id)],
                        "source_amount": str(row.debit - row.credit),
                        "source_currency": row.currency,
                        "base_amount": str(row.base_debit - row.base_credit),
                        "exchange_rate": str(row.exchange_rate),
                        "contract_reference": "SYNTHETIC fictional affiliate overlay "
                        + str(i + 1),
                    },
                    f"TRANSACTION-{i + 1}",
                )
            )
        far = await paper(
            "far",
            {
                **common,
                "party_id": parties[0]["id"],
                "functions": ["Synthetic distribution"],
                "assets": ["Working capital"],
                "risks": ["Market risk"],
                "actual_conduct": "Synthetic contract/conduct fixture",
                "risk_control": "Synthetic capable decision makers",
                "tested_party_considerations": "Synthetic least complex party; professional assessment required",
            },
            "FAR",
        )
        methods = {}
        for pli, method in [("operating_margin", "TNMM"), ("value", "CUP")]:
            methods[pli] = await paper(
                "method",
                {
                    **common,
                    "transaction_ids": [x["id"] for x in transactions],
                    "far_id": far["id"],
                    "method": method,
                    "tested_party_id": parties[0]["id"],
                    "pli": pli,
                    "economic_characteristics": "SYNTHETIC software-test comparability",
                    "available_comparables": "Synthetic generated observations; not licensed market evidence",
                    "rejected_alternatives": {
                        x: "Synthetic alternative method assessment"
                        for x in [
                            "CUP",
                            "RPM",
                            "COST_PLUS",
                            "TNMM",
                            "PROFIT_SPLIT",
                            "OTHER",
                        ]
                        if x != method
                    },
                },
                "METHOD-" + pli,
            )
        studies = []
        for index, purpose in enumerate(
            ["profitability", "interest", "remuneration", "royalty", "profitability"]
        ):
            dataset = await paper(
                "dataset",
                {
                    **common,
                    "source_name": "SYNTHETIC software test observations",
                    "license_type": "synthetic",
                    "license_reference": "Generated software fixture; never real comparables",
                    "valid_until": "2029-12-31",
                    "authorized_use": True,
                    "allow_raw_export": False,
                    "allow_derived_export": True,
                    "allow_ai": False,
                    "observation_date": "2026-10-18",
                    "data_version": "phase8-v1",
                },
                f"DATASET-{index + 1}",
            )
            stream = io.StringIO()
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "company_key",
                    "name",
                    "country",
                    "industry",
                    "fiscal_year",
                    "currency",
                    "revenue",
                    "cost_sales",
                    "opex",
                    "assets",
                    "value",
                    "activity",
                    "independence",
                    "related_party_exposure",
                    "extraordinary_events",
                    "observation_date",
                ],
            )
            writer.writeheader()
            for n in range(5000 if index == 0 else 5):
                rate = D(".03") + D(n % 9) / 100
                writer.writerow(
                    {
                        "company_key": f"SYN-{index}-{n}",
                        "name": f"SYNTHETIC comparable {index}-{n}",
                        "country": "AE",
                        "industry": "Synthetic",
                        "fiscal_year": 2026,
                        "currency": "AED",
                        "revenue": 10000000,
                        "cost_sales": str(D(10000000) * (1 - rate)),
                        "opex": 0,
                        "assets": 4000000,
                        "value": str(
                            rate if purpose != "remuneration" else rate * 10000000
                        ),
                        "activity": "Synthetic fixture",
                        "independence": "Synthetic reviewed",
                        "related_party_exposure": "Synthetic none",
                        "extraordinary_events": "Synthetic none",
                        "observation_date": "2026-10-18",
                    }
                )
            imported = await call(
                tp + f"/datasets/{dataset['id']}/import",
                files={
                    "file": ("synthetic.csv", stream.getvalue().encode(), "text/csv")
                },
            )
            pli = "operating_margin" if purpose == "profitability" else "value"
            study = await paper(
                "study",
                {
                    **common,
                    "dataset_ids": [dataset["id"]],
                    "method_id": methods[pli]["id"],
                    "pli": pli,
                    "currency": "AED",
                    "fiscal_years": [2026],
                    "aggregation": "year_specific",
                    "quantile": "inclusive",
                    "purpose": purpose,
                    "screening_criteria": "Synthetic geography/function/independence/loss/event review",
                    "comparability_review": "SOFTWARE TEST ONLY; not real market observations",
                },
                f"STUDY-{index + 1}",
                stages=True,
            )
            for offset in range(0, imported["imported"], 200):
                obs = await call(
                    tp
                    + f"/observations?dataset_id={dataset['id']}&offset={offset}&limit=100",
                    method="GET",
                )
                obs2 = (
                    await call(
                        tp
                        + f"/observations?dataset_id={dataset['id']}&offset={offset + 100}&limit=100",
                        method="GET",
                    )
                    if offset + 100 < imported["imported"]
                    else {"items": []}
                )
                await paper(
                    "screening",
                    {
                        **common,
                        "study_id": study["id"],
                        "decisions": [
                            {
                                "observation_id": x["id"],
                                "decision": "ACCEPT",
                                "reason": "Synthetic eligible software fixture",
                                "independence_review": "Synthetic reviewed",
                                "loss_review": "Synthetic reviewed",
                                "functional_review": "Synthetic reviewed",
                            }
                            for x in obs["items"] + obs2["items"]
                        ],
                    },
                    f"SCREEN-{index + 1}-{offset}",
                )
            studies.append(await calculate(study))
        for i in range(20):
            body = {
                **common,
                "relationship_id": relationship["id"],
                "lender_id": foreign["id"],
                "borrower_id": parties[0]["id"],
                "currency": "AED",
                "exchange_rate_source": "Same-currency synthetic agreement",
                "principal": str(100000 + i * 1000),
                "drawdown_date": "2026-01-01",
                "maturity": "2027-01-01",
                "calculation_end": "2027-01-01",
                "annual_rate": ".1",
                "interest_type": "fixed",
                "day_count": ["ACT/365", "ACT/360", "30E/360"][i % 3],
                "payment_frequency": "Synthetic bullet",
                "security": "Synthetic unsecured",
                "guarantees": "Synthetic none",
                "covenants": "Synthetic reviewed",
                "seniority": "Senior",
                "credit_characteristics": "Synthetic internal facts",
                "prepayment_options": "Synthetic permitted",
                "subordination": "None",
                "purpose": "SYNTHETIC funding fixture",
            }
            loan = await paper("loan", body, f"LOAN-{i + 1}")
            await calculate(loan)
        costs = [(code, row) for code, row in rows if code == "500"][:10]
        for i, (_, row) in enumerate(costs):
            service = await paper(
                "service",
                {
                    **common,
                    "transaction_ids": [transactions[0]["id"]],
                    "cost_line_ids": [str(row.id)],
                    "cost_pool": str(row.base_debit - row.base_credit),
                    "allocations": [{"segment": parties[1]["id"], "weight": 1}],
                    "allocation_driver": "Synthetic direct recipient",
                    "methodology": "Synthetic allocation of an actual source cost; not a market markup",
                    "markup": ".05",
                    "benefit_test": "Synthetic benefit-test fixture",
                    "provider_id": parties[0]["id"],
                    "recipients": [parties[1]["id"]],
                    "legal_conditions": "No automatic simplified method",
                },
                f"SERVICE-{i + 1}",
            )
            await calculate(service)
            await paper(
                "remuneration",
                {
                    **common,
                    "party_id": foreign["id"],
                    "transaction_ids": [transactions[0]["id"]],
                    "base_salary": "500000",
                    "bonus": "50000",
                    "allowances": "20000",
                    "benefits": "10000",
                    "management_fees": 0,
                    "responsibilities": "SYNTHETIC draft; actual director/payroll evidence missing",
                    "time_commitment": "Draft full time assumption",
                    "experience": "Draft experience assumption",
                    "size_performance": "Draft scale assumption",
                    "adjustment_basis": "Draft requires CP classification and actual payroll source; cannot conclude",
                },
                f"REMUNERATION-{i + 1}",
                approve=False,
            )
        segment = await paper(
            "segmentation",
            {
                **common,
                "lines": [
                    {
                        "financial_line_code": x["line_code"],
                        "metric": "revenue"
                        if x["section"] == "income"
                        else "cost_sales"
                        if x["section"] == "expenses"
                        else "assets"
                        if x["section"] == "assets"
                        else "other",
                        "classification": "shared",
                        "driver": "direct",
                        "allocation": [{"segment": "synthetic_reviewed", "weight": 1}],
                        "methodology": "Complete source allocation; no assertion all activity is controlled",
                    }
                    for x in financial_lines
                ],
            },
            "SEGMENTATION",
        )
        reconciliation = await calculate(segment)
        for kind, keys, count in [
            ("localfile", LOCAL_SECTIONS, 3),
            ("masterfile", MASTER_SECTIONS, 1),
        ]:
            for i in range(count):
                await paper(
                    kind,
                    {
                        **common,
                        "sections": [
                            {
                                "key": key,
                                "narrative": "SYNTHETIC DRAFT. Source-backed preparation template requiring section-specific professional analysis: "
                                + key,
                                "evidence_ids": [entry["source_note_id"]],
                                "human_verified": False,
                            }
                            for key in keys
                        ],
                        "checklist_complete": False,
                        "financial_reconciliation_run_id": reconciliation["id"],
                        "license_review": "Synthetic only; no licensed market data",
                        "annual_version": i + 1,
                    },
                    f"{kind.upper()}-{i + 1}",
                    approve=False,
                )
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            inventory = (
                await db.scalars(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == DEMO_TENANT,
                        AuditRecord.engagement_id == uuid.UUID(eid),
                        AuditRecord.kind.like("tp-%"),
                    )
                )
            ).all()
        result = {
            "synthetic": True,
            "seed_version": "phase8-v1",
            "users": tp_users,
            "tenant_id": str(DEMO_TENANT),
            "engagement_id": eid,
            "profile_id": profile["id"],
            "counts": dict(Counter(x.kind for x in inventory)),
            "studies": [x["id"] for x in studies],
            "base_sources_preserved": True,
            "remuneration": "10 draft incomplete evidence cases, not approved CP/payroll conclusions",
            "documents": "3 Local File and 1 Master File drafts require human-authored section completion",
        }
        result["record_inventory"] = [
            {
                "id": str(x.id),
                "kind": x.kind,
                "reference": x.reference,
                "status": x.status,
                "version": x.version,
            }
            for x in inventory
        ]
        async with Session() as db, db.begin():
            await guard(db)
            await tenant_context(db, str(DEMO_TENANT))
            dataset = await db.scalar(
                select(DemoDataset).where(
                    DemoDataset.tenant_id == DEMO_TENANT,
                    DemoDataset.seed_version == "phase8-v1",
                )
            )
            if not dataset:
                dataset = DemoDataset(
                    id=uuid.uuid5(DEMO_TENANT, "phase8-dataset/v1"),
                    tenant_id=DEMO_TENANT,
                    created_by=uuid.UUID(users[1]["id"]),
                    seed_version="phase8-v1",
                    status="COMPLETE",
                    manifest=result,
                )
                db.add(dataset)
            else:
                dataset.manifest = result
                dataset.status = "COMPLETE"
        (ROOT / "docs/phase-8/demo-manifest.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key != "record_inventory"
                }
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(enrich())
