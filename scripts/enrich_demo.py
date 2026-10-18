"""Real-API IFRS and Corporate Tax demonstration on the seeded ledger snapshots."""

import asyncio
import json
import sys
import uuid
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from seed_demo import verify
from sqlalchemy import select

from app.core.security import access_token
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.generator import ACCOUNTS, VERSION, identifier
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.vat.models import DemoDataset


async def enrich():
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        dataset = await db.scalar(
            select(DemoDataset).where(
                DemoDataset.tenant_id == DEMO_TENANT,
                DemoDataset.seed_version == VERSION,
                DemoDataset.status == "COMPLETE",
            )
        )
        if not dataset:
            raise ValueError("Complete guarded base dataset required")
        manifest = json.loads(json.dumps(dataset.manifest))
    users = manifest["users"]
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=300,
    ) as c:

        async def call(path, body=None, who=1, method="POST"):
            h = {
                "Authorization": "Bearer " + access_token(uuid.UUID(users[who]["id"])),
                "X-Tenant-ID": str(DEMO_TENANT),
            }
            r = await c.request(
                method,
                "/api/v1/" + path,
                headers=h,
                **({"json": body} if body is not None else {}),
            )
            if r.status_code >= 400:
                raise RuntimeError(path + " " + r.text)
            return r.json()

        for entry in [x for x in manifest["engagements"] if x["year"] == 2026]:
            eid = entry["id"]
            base = f"engagements/{eid}/audit"

            async def ready(kind, body, reference, reviewer=11, stages=False):
                async with Session() as db, db.begin():
                    await tenant_context(db, str(DEMO_TENANT))
                    existing = await db.scalar(
                        select(AuditRecord).where(
                            AuditRecord.tenant_id == DEMO_TENANT,
                            AuditRecord.engagement_id == uuid.UUID(eid),
                            AuditRecord.kind == kind,
                            AuditRecord.reference == reference,
                        )
                    )
                    if existing:
                        obj = __import__(
                            "app.modules.audit_execution.service",
                            fromlist=["serialize"],
                        ).serialize(existing)
                    else:
                        obj = None
                if not obj:
                    obj = await call(
                        base + "/" + kind,
                        {
                            "reference": reference,
                            "title": "SYNTHETIC " + reference,
                            "body": body,
                        },
                    )
                if obj["status"] in {"APPROVED", "LOCKED"}:
                    return obj
                if obj["status"] == "IN_PROGRESS":
                    obj = await call(
                        base + f"/records/{obj['id']}/actions",
                        {
                            "version": obj["version"],
                            "action": "submit",
                            "comments": "Synthetic fixture submitted through actual workflow",
                        },
                    )
                obj = await call(
                    base + f"/records/{obj['id']}/actions",
                    {
                        "version": obj["version"],
                        "action": "approve",
                        "comments": "Synthetic independently reviewed fixture",
                    },
                    who=reviewer,
                )
                if stages:
                    obj = await call(
                        base + f"/records/{obj['id']}/actions",
                        {
                            "version": obj["version"],
                            "action": "approve",
                            "comments": "Synthetic independent CA final review",
                        },
                        who=3,
                    )
                return obj

            if entry.get("ifrs_run_id"):
                continue
            profile = await ready(
                "ifrs-profile",
                {
                    "snapshot_id": entry["snapshot_id"],
                    "presentation_currency": "AED",
                    "technical_validation": "Synthetic source population, framework and presentation reviewed",
                },
                "P7-IFRS-PROFILE",
            )
            mappings = []
            used_codes = {"100", "101", "110", "180", "200", "240", "300", "400", "500"}
            for code, label in ACCOUNTS.items():
                if code not in used_codes:
                    continue
                section = (
                    "assets"
                    if int(code) < 200
                    else "liabilities"
                    if int(code) < 300
                    else "equity"
                    if int(code) < 400
                    else "income"
                    if int(code) < 500
                    else "expenses"
                )
                mappings.append(
                    {
                        "account_code": code,
                        "allocations": [
                            {
                                "line_code": code,
                                "label": label,
                                "section": section,
                                "note": "N1",
                                "is_cash": code in {"100", "101"},
                                "cash_flow_role": "working_capital_asset"
                                if code in {"110", "180"}
                                else "working_capital_liability"
                                if code in {"200", "240"}
                                else "none",
                                "category": "tax" if code == "540" else "operating",
                            }
                        ],
                    }
                )
            await ready(
                "ifrs-mapping",
                {
                    "profile_id": profile["id"],
                    "accounts": mappings,
                    "rationale": "Synthetic original chart-to-statement mapping",
                },
                "P7-IFRS-MAPPING",
            )
            await ready(
                "ifrs-cash-flow",
                {
                    "profile_id": profile["id"],
                    "method": "indirect",
                    "policy": "Synthetic reviewed interest policy",
                    "movement_schedule_source": "Actual imported movements and working-capital roles",
                },
                "P7-IFRS-CASH-FLOW",
            )
            note = await ready(
                "ifrs-note",
                {
                    "profile_id": profile["id"],
                    "note_reference": "N1",
                    "text": "Synthetic source population and nonproduction accounting judgments. No compliance certification.",
                    "linked_line_codes": sorted(used_codes),
                },
                "P7-IFRS-NOTE",
            )
            for category in [
                "presentation",
                "policies",
                "judgments",
                "events_after_reporting",
                "going_concern",
                "N1",
            ]:
                await ready(
                    "ifrs-disclosure",
                    {
                        "profile_id": profile["id"],
                        "standard": "IAS 1",
                        "category": category,
                        "applicability": "applicable",
                        "rationale": "Synthetic independent disclosure assessment",
                        "note_id": note["id"],
                    },
                    "P7-DISCLOSURE-" + category,
                )
            await ready(
                "ifrs-adjustment",
                {
                    "profile_id": profile["id"],
                    "adjustment_date": "2026-12-31",
                    "currency": "AED",
                    "standard": "IAS 1",
                    "narration": "Synthetic accrued expense100, separately approved overlay",
                    "legs": [
                        {"account_code": "500", "debit": "100"},
                        {"account_code": "200", "credit": "100"},
                    ],
                },
                "P7-APPROVED-ADJUSTMENT",
            )
            fs = await call(f"ifrs/engagements/{eid}/financial-statements/{profile['id']}")
            expected_profit = (
                -D(entry["expected_balances"]["400"]) - D(entry["expected_balances"]["500"]) - 100
            )
            if (
                not fs["results"]["validation"]["ready"]
                or D(fs["results"]["totals"]["profit"]) != expected_profit
            ):
                raise ValueError(fs["results"]["validation"])
            await ready(
                "ifrs-financials",
                {
                    "run_id": fs["id"],
                    "release_rationale": "Synthetic actual ledger and approved overlay independently reconciled",
                },
                "P7-FINANCIALS-APPROVAL",
                stages=True,
            )
            tax_rules = {}
            for category, source, article in [
                ("standard", "CT-RATES", ""),
                ("adjustments", "CT-LAW", "29"),
                ("losses", "CT-LAW", "37"),
                ("deadline", "CT-LAW", "53"),
                ("interest", "MD126-2023", "8"),
                ("qfzp", "MD229-2025", "3"),
                ("sbr", "MD131-2026", "One"),
                ("group", "CT-LAW", "40"),
                ("exemption", "CT-LAW", "22"),
            ]:
                obj = await ready(
                    "tax-rule",
                    {
                        "rule_key": category,
                        "rule_version": 1,
                        "category": category,
                        "source_id": source,
                        "article": article,
                        "decision_number": "Synthetic approved official-source rule",
                        "effective_from": "2023-06-01",
                        "known_from": "2026-10-18"
                        if category == "sbr"
                        else "2025-09-03"
                        if category == "qfzp"
                        else "2023-06-01",
                        "source_document_version": "Synthetic independent technical fixture",
                        "conditions": "Professionally reviewed synthetic scope only",
                        "exceptions": "Unsupported positions remain review required",
                        "technical_review": "Synthetic independent rule adoption",
                        "parameters": {"sbr_last_period_end": "2029-12-31"}
                        if category == "sbr"
                        else {},
                    },
                    "P7-CT-RULE-" + category,
                    reviewer=9,
                )
                tax_rules[category] = obj["id"]
            revenue = -D(entry["expected_balances"]["400"])
            tax_profile = await ready(
                "tax-profile",
                {
                    "financial_run_id": fs["id"],
                    "classification": "resident_juridical",
                    "legal_form": "Synthetic LLC",
                    "registration_details": "Synthetic nonproduction registration",
                    "resident": True,
                    "residence_assessment": "Synthetic UAE juridical residence facts",
                    "licensed_activities": "Synthetic commercial activities",
                    "ownership_assessment": "Synthetic continuity reviewed",
                    "tax_start": "2026-01-01",
                    "tax_end": "2026-12-31",
                    "legal_as_of": "2026-10-18",
                    "rules": tax_rules,
                    "revenue": str(revenue),
                    "revenue_source": "Approved IFRS revenue line400",
                    "scope_assessment": "Synthetic mainland juridical business; special rules separately assessed",
                    "pillar_two_in_scope": False,
                    "audited_financials_required": False,
                },
                "P7-CT-PROFILE",
                reviewer=9,
            )
            tax = await call(f"tax/engagements/{eid}/computations/{tax_profile['id']}")
            independent_tax = (max(D(0), expected_profit - D(375000)) * D("0.09")).quantize(
                D("0.00000001")
            )
            if (
                not tax["results"]["validation"]["ready"]
                or D(tax["results"]["current_tax"]) != independent_tax
            ):
                raise ValueError("Independent Corporate Tax mismatch")
            await ready(
                "tax-computation",
                {
                    "tax_run_id": tax["id"],
                    "rationale": "Synthetic accounting-to-tax bridge checked",
                },
                "P7-CT-APPROVAL",
                reviewer=9,
                stages=True,
            )
            await ready(
                "vat-einvoicing",
                {
                    "profile_id": entry["vat_profile_id"],
                    "rule_id": str(identifier(eid + "/VAT-RULE-einvoice")),
                    "annual_revenue": str(revenue),
                    "government_entity": False,
                    "in_scope_b2b_b2g": True,
                    "scope_assessment": "Synthetic B2B phase assessment, no accredited provider appointed",
                    "identifiers_complete": False,
                    "source_mapping_complete": False,
                    "sandbox_tested": False,
                    "evidence_record_ids": [note["id"]],
                },
                "P7-EINVOICE-READINESS",
                reviewer=9,
            )
            entry.update(
                ifrs_profile_id=profile["id"],
                ifrs_run_id=fs["id"],
                tax_profile_id=tax_profile["id"],
                tax_run_id=tax["id"],
                expected_profit=str(expected_profit),
                expected_current_tax=str(independent_tax),
                source_note_id=note["id"],
            )
            await verify(manifest, finish=True)
            print("Enriched actual ledger", eid, "IFRS and CT reconciled", flush=True)
        # Independent specialist examples are not silently posted to the source ledger.
        entry = next(x for x in manifest["engagements"] if x.get("ifrs_profile_id"))
        eid = entry["id"]
        base = f"engagements/{eid}/audit"
        examples = {
            "lease": (
                {
                    "commencement": "2026-01-01",
                    "end_date": "2027-01-01",
                    "annual_discount_rate": "0.1",
                    "payments": [{"date": "2027-01-01", "amount": "1100"}],
                    "recognition_assessment": "Synthetic fixed lease",
                    "options_assessment": "No options",
                },
                {"initial_liability": "1000", "initial_rou": "1000"},
            ),
            "ecl": (
                {
                    "approach": "general",
                    "exposures": [{"reference": "SYN-AR", "amount": "1000", "stage": 1}],
                    "scenarios": [
                        {
                            "name": "base",
                            "probability": "0.7",
                            "pd_12_month": "0.1",
                            "pd_lifetime": "0.3",
                            "lgd": "0.5",
                        },
                        {
                            "name": "stress",
                            "probability": "0.3",
                            "pd_12_month": "0.2",
                            "pd_lifetime": "0.4",
                            "lgd": "0.5",
                        },
                    ],
                    "effective_interest_rate": "0",
                    "historical_data_source": "Synthetic history",
                    "sicr_methodology": "Synthetic criteria",
                    "default_definition": "Synthetic policy",
                    "write_off_policy": "Synthetic reviewed policy",
                },
                {"total_ecl": "65"},
            ),
            "revenue": (
                {
                    "contract_reference": "SYN-SERVICE",
                    "contract_assessment": "Synthetic distinct obligations",
                    "reporting_date": "2026-12-31",
                    "fixed_price": "300",
                    "constraint_rationale": "No variable price",
                    "billed_to_date": "250",
                    "obligations": [
                        {
                            "reference": "services",
                            "standalone_price": "200",
                            "recognition": "over_time",
                            "progress": "0.5",
                            "over_time_justification": "Synthetic measured progress",
                        },
                        {
                            "reference": "goods",
                            "standalone_price": "100",
                            "recognition": "point_in_time",
                            "satisfied_on": "2026-12-31",
                        },
                    ],
                },
                {"recognised_to_date": "200", "contract_liability": "50"},
            ),
            "deferred-tax": (
                {
                    "current_tax_source": "Synthetic current tax provision",
                    "differences": [
                        {
                            "reference": "Asset",
                            "jurisdiction": "AE",
                            "rate_source": "Synthetic approved fixture rate",
                            "rate_effective_date": "2026-01-01",
                            "carrying_amount": "100",
                            "tax_base": "80",
                            "item_type": "asset",
                            "tax_rate": "0.09",
                            "recognition_rationale": "Synthetic temporary difference",
                        }
                    ],
                },
                {"dtl": "1.8"},
            ),
            "fixed-assets": (
                {
                    "period_start": "2026-01-01",
                    "period_end": "2026-12-31",
                    "assets": [
                        {
                            "reference": "SYN-ASSET",
                            "cost": "1200",
                            "residual": "0",
                            "capitalisation_date": "2026-01-01",
                            "useful_life_years": "10",
                            "method": "straight_line",
                        }
                    ],
                },
                {"total_depreciation": "120", "closing_carrying": "1080"},
            ),
        }
        manifest.setdefault("specialists", {})
        for kind, (body, expected) in examples.items():
            if kind in manifest["specialists"]:
                run = await call(
                    f"ifrs/engagements/{eid}/runs/{manifest['specialists'][kind]['run_id']}",
                    method="GET",
                )
                for key, value in expected.items():
                    if D(run["results"][key]) != D(value):
                        raise ValueError("Existing specialist benchmark mismatch:" + kind)
                manifest["specialists"][kind]["expected"] = expected
                continue
            obj = await ready("ifrs-" + kind, body, "P7-SPECIALIST-" + kind)
            run = await call(f"ifrs/engagements/{eid}/calculate/{obj['id']}")
            for key, value in expected.items():
                if D(run["results"][key]) != D(value):
                    raise ValueError("Specialist independent benchmark mismatch:" + kind)
            manifest["specialists"][kind] = {
                "record_id": obj["id"],
                "run_id": run["id"],
                "expected": expected,
            }
        await verify(manifest, finish=True)
        Path(__file__).resolve().parents[1].joinpath("docs/phase-7/demo-manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )
    print("Guarded IFRS/CT enrichment complete")


async def main():
    try:
        await enrich()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
