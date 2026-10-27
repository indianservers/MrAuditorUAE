"""Synthetic UAE tax workflows use actual import, IFRS, reviews, RLS and ledger."""

import os
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant
from tests.phase5.test_reporting import prepared as ifrs_prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def prepared(c, scope_data=None, suffix="", scale=40000):
    h, eid, base, manager, partner, p, mapping, note, ready_ifrs = await ifrs_prepared(
        c, scope_data, suffix, scale
    )
    response = await c.post(
        f"/api/v1/ifrs/engagements/{eid}/financial-statements/{p['id']}", headers=h
    )
    assert response.status_code == 201, response.text
    financial = response.json()
    package = await create(
        c,
        h,
        base,
        "ifrs-financials",
        {
            "run_id": financial["id"],
            "release_rationale": "Synthetic independently reconciled statements",
        },
    )
    package = await action(c, h, base, package, "submit")
    package = await action(c, manager[0], base, package, "approve")
    await action(c, partner[0], base, package, "approve")
    manager = await actor(h, "Tax Manager", "tax-manager" + suffix)
    partner = await actor(h, "Tax Partner", "tax-partner" + suffix)
    await grant(c, h, base, manager)
    await grant(c, h, base, partner)

    async def ready(kind, body):
        obj = await create(c, h, base, "tax-" + kind, body)
        return await approve(
            c,
            h,
            partner[0] if kind in {"rule", "loss", "loss-transfer", "group"} else manager[0],
            base,
            obj,
        )

    rule_ids = {}
    definitions = {
        "standard": ("CT-RATES", "", "CT rate bands"),
        "adjustments": ("CT-LAW", "29", "Entertainment deduction"),
        "losses": ("CT-LAW", "37", "Tax losses"),
        "deadline": ("CT-LAW", "53", "Tax return filing"),
        "interest": ("MD126-2023", "8", "Interest limitation"),
        "qfzp": ("MD229-2025", "3", "Free Zone de minimis"),
        "sbr": ("MD131-2026", "One", "Small Business Relief amended"),
        "group": ("CT-LAW", "40", "Tax Group conditions"),
        "exemption": ("CT-LAW", "22", "Domestic dividend assessment"),
    }
    for category, (source, article, title) in definitions.items():
        obj = await ready(
            "rule",
            {
                "rule_key": category,
                "rule_version": 1,
                "category": category,
                "source_id": source,
                "article": article,
                "decision_number": title,
                "effective_from": "2023-06-01",
                "known_from": "2026-10-18"
                if category == "sbr"
                else "2025-09-03"
                if category == "qfzp"
                else "2023-06-01",
                "source_document_version": "Synthetic technical validation of official metadata, not production legal approval",
                "conditions": "Synthetic explicit scope; verify all applicable statutory conditions",
                "exceptions": "Unsupported cases require professional review",
                "technical_review": "Synthetic technical review recorded by independent test actor",
                "parameters": {"sbr_last_period_end": "2029-12-31"} if category == "sbr" else {},
                # Synthetic commencement attestation exercises controls; not a Gazette claim.
                **(
                    {
                        "publication_date": "2026-08-01",
                        "publication_evidence_id": note["id"],
                        "source_sha256": "a" * 64,
                    }
                    if category == "sbr"
                    else {}
                ),
            },
        )
        rule_ids[category] = obj["id"]
    profile = await ready(
        "profile",
        {
            "financial_run_id": financial["id"],
            "classification": "resident_juridical",
            "legal_form": "Synthetic LLC",
            "registration_details": "Synthetic registration",
            "residence_assessment": "Synthetic UAE resident juridical person",
            "resident": True,
            "licensed_activities": "Synthetic commercial services",
            "ownership_assessment": "Synthetic ownership continuity reviewed",
            "tax_start": "2026-01-01",
            "tax_end": "2026-12-31",
            "legal_as_of": "2026-10-18",
            "rules": rule_ids,
            "revenue": str(50 * scale),
            "revenue_source": "Approved IFRS revenue line400",
            "scope_assessment": "Synthetic mainland UAE business, no foreign PE or other special tax treatment",
            "pillar_two_in_scope": False,
            "audited_financials_required": False,
        },
    )
    adjustment = await ready(
        "adjustment",
        {
            "profile_id": profile["id"],
            "rule_id": rule_ids["adjustments"],
            "category": "entertainment",
            "entertainment_scope": "customers_suppliers_partners",
            "account_codes": ["500"],
            "accounting_amount": str(20 * scale),
            "proposed_adjustment": str(10 * scale),
            "treatment": "partial_deduction",
            "rationale": "Synthetic customer entertainment expenditure supported and reviewed",
            "evidence_record_ids": [note["id"]],
        },
    )
    return h, eid, base, manager, partner, profile, adjustment, note, rule_ids, ready, financial


async def compute(c, h, eid, profile):
    r = await c.post(f"/api/v1/tax/engagements/{eid}/computations/{profile['id']}", headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def release(c, h, eid, base, manager, partner, run):
    obj = await create(
        c,
        h,
        base,
        "tax-computation",
        {
            "tax_run_id": run["id"],
            "rationale": "Synthetic reviewed tax bridge and statutory assumptions",
        },
    )
    obj = await action(c, h, base, obj, "submit")
    obj = await action(c, manager[0], base, obj, "approve")
    assert obj["status"] == "REVIEW_REQUIRED"
    return await action(c, partner[0], base, obj, "approve")


async def test_mainland_approved_vs_proposed_and_exports(environment, tmp_path):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    await create(
        c,
        h,
        base,
        "tax-adjustment",
        {
            **{k: v for k, v in adj["body"].items() if not k.startswith("review_")},
            "accounting_amount": "200",
            "proposed_adjustment": "100",
        },
    )
    run = await compute(c, h, eid, p)
    data = run["results"]
    assert D(data["accounting_profit"]) == 1200000 and D(data["net_adjustments"]) == 400000
    assert D(data["taxable_income"]) == 1600000 and D(data["current_tax"]) == 110250
    assert len(data["lines"]) == 1 and data["validation"]["ready"]
    approved = await release(c, h, eid, base, manager, partner, run)
    await action(c, h, base, approved, "approve", 403)
    for fmt, signature in [("pdf", b"%PDF"), ("xlsx", b"PK"), ("json", b"{")]:
        response = await c.get(
            f"/api/v1/tax/engagements/{eid}/runs/{run['id']}/export/{fmt}", headers=h
        )
        assert response.status_code == 200, response.text
        assert response.content.startswith(signature)
        if os.getenv("PHASE6_ARTIFACT_DIR"):
            folder = Path(os.environ["PHASE6_ARTIFACT_DIR"])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"synthetic-corporate-tax.{fmt}").write_bytes(response.content)
    history = await c.get(base + f"/records/{approved['id']}/history", headers=h)
    assert history.status_code == 200
    await action(c, manager[0], base, adj, "reopen")
    exported = (
        await c.get(f"/api/v1/tax/engagements/{eid}/runs/{run['id']}/export/json", headers=h)
    ).json()
    assert not exported["released"]


async def test_sbr_election_and_rule_applicability(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    await ready(
        "sbr",
        {
            "profile_id": p["id"],
            "election_made": True,
            "prior_revenues": ["2000000"],
            "prior_periods_complete": True,
            "is_qfzp": False,
            "excluded_multinational": False,
            "artificial_separation": False,
            "aggregation_review": "Synthetic full historical aggregation reviewed",
            "election_evidence_id": note["id"],
        },
    )
    run = await compute(c, h, eid, p)
    assert run["results"]["sbr"]["eligible_and_elected"]
    assert D(run["results"]["current_tax"]) == 0
    # An old legal as-of date cannot use newly discovered extension metadata.
    body = {k: v for k, v in p["body"].items() if not k.startswith("review_")}
    body["legal_as_of"] = "2025-12-31"
    r = await c.post(
        base + "/tax-profile",
        headers=h,
        json={"reference": "OLD-ASOF", "title": "Synthetic historic knowledge", "body": body},
    )
    assert r.status_code == 409


async def test_loss_utilisation_versions_and_immutable_ledger(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    loss = await ready(
        "loss",
        {
            "profile_id": p["id"],
            "origin_start": "2025-01-01",
            "origin_end": "2025-12-31",
            "amount": "2000000",
            "eligibility": "PASS",
            "ownership_continuity": True,
            "same_or_similar_business": True,
            "excluded_pre_ct_or_exempt": False,
            "source_reference": "Synthetic independently assessed prior-year tax loss, not accounting loss",
        },
    )
    first = await compute(c, h, eid, p)
    assert D(first["results"]["loss_utilised"]) == 1200000
    assert D(first["results"]["current_tax"]) == 2250
    await release(c, h, eid, base, manager, partner, first)
    ledger = (await c.get(f"/api/v1/tax/engagements/{eid}/loss-ledger/{p['id']}", headers=h)).json()
    assert D(ledger["items"][0]["available"]) == 800000
    for _ in range(2):
        rerun = await compute(c, h, eid, p)
        assert D(rerun["results"]["loss_utilised"]) == 1200000
        await release(c, h, eid, base, manager, partner, rerun)
    ledger = (await c.get(f"/api/v1/tax/engagements/{eid}/loss-ledger/{p['id']}", headers=h)).json()
    assert D(ledger["items"][0]["available"]) == 800000
    assert (
        await c.post(
            base + f"/records/{loss['id']}/actions",
            headers=partner[0],
            json={
                "version": loss["version"],
                "action": "reopen",
                "comments": "Synthetic prohibited mutation",
            },
        )
    ).status_code == 409


async def test_qfzp_contract_segmentation_and_incomplete_conditions(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    from app.modules.tax.calculations import CORE_QFZP, QFZP_REQUIRED

    conditions = [
        {
            "requirement": key,
            "assessment": "PASS" if key in CORE_QFZP else "NOT_APPLICABLE",
            "rationale": "Synthetic documented tax fact",
            "evidence_record_ids": [note["id"]] if key in CORE_QFZP else [],
        }
        for key in sorted(QFZP_REQUIRED)
    ]
    body = {k: v for k, v in p["body"].items() if not k.startswith("review_")}
    body.update(
        classification="qfzp",
        free_zone=True,
        audited_financials_required=True,
        audited_financials_evidence_id=note["id"],
    )
    p = await ready("profile", body)
    segment = {
        "source_line_code": "400",
        "counterparty": "Synthetic industrial buyer",
        "counterparty_type": "non_free_zone",
        "activity": "Synthetic reviewed manufacturing contract",
        "jurisdiction": "AE",
        "contract_evidence_id": note["id"],
        "rationale": "Synthetic contract-based reviewed segmentation",
    }
    qfzp = await ready(
        "qfzp",
        {
            "profile_id": p["id"],
            "conditions": conditions,
            "segments": [
                {
                    **segment,
                    "reference": "Q",
                    "revenue": "1900000",
                    "taxable_profit": "1520000",
                    "classification": "qualifying",
                },
                {
                    **segment,
                    "reference": "N",
                    "revenue": "100000",
                    "taxable_profit": "80000",
                    "classification": "nonqualifying",
                },
            ],
            "procedures_applicability_basis": "No distribution activity",
        },
    )
    result = await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{qfzp['id']}", headers=h)
    assert result.status_code == 201, result.text
    assert result.json()["results"]["assessment"] == "PASS"
    assert D(result.json()["results"]["threshold"]) == 100000
    # QFZP profit must match this new profile's actual approved tax bridge (no adjustment yet).
    run = await compute(c, h, eid, p)
    assert not run["results"]["validation"]["ready"]
    qfzp = await action(c, manager[0], base, qfzp, "reopen")
    fixed = {k: v for k, v in qfzp["body"].items() if not k.startswith("review_")}
    fixed["segments"][0]["taxable_profit"] = "1140000"
    fixed["segments"][1]["taxable_profit"] = "60000"
    changed = await c.patch(
        base + "/records/" + qfzp["id"],
        headers=h,
        json={
            "version": qfzp["version"],
            "reference": qfzp["reference"],
            "title": qfzp["title"],
            "body": fixed,
        },
    )
    assert changed.status_code == 200, changed.text
    await approve(c, h, manager[0], base, changed.json())
    run = await compute(c, h, eid, p)
    assert run["results"]["validation"]["ready"] and D(run["results"]["current_tax"]) == 0
    await release(c, h, eid, base, manager, partner, run)


async def second_entity(c, h, suffix="-sub"):
    async def post(path, body):
        r = await c.post("/api/v1/" + path, headers=h, json=body)
        assert r.status_code < 400, r.text
        return r.json()

    customer = await post(
        "clients", {"code": "TAX-" + uuid.uuid4().hex[:8], "name": "SYNTHETIC tax group client"}
    )
    entity = await post(
        "entities",
        {
            "client_id": customer["id"],
            "name": "SYNTHETIC tax subsidiary",
            "country": "AE",
            "jurisdiction": "Synthetic UAE",
            "functional_currency": "AED",
            "presentation_currency": "AED",
        },
    )
    period = await post(
        "financial-periods",
        {"entity_id": entity["id"], "start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    eng = await post(
        "engagements",
        {
            "entity_id": entity["id"],
            "period_id": period["id"],
            "name": "SYNTHETIC subsidiary tax reporting",
            "engagement_type": "External Audit",
        },
    )
    eid = eng["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    options = {
        "client_id": customer["id"],
        "entity_id": entity["id"],
        "period_id": period["id"],
        "source_complete": True,
    }
    return await prepared(c, (h, options, eid, base), suffix)


async def test_tax_group_aggregation_and_ownership_boundaries(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    (
        _,
        eid2,
        base2,
        manager2,
        partner2,
        p2,
        adj2,
        note2,
        rules2,
        ready2,
        financial2,
    ) = await second_entity(c, h)
    await grant(c, h, base2, manager)
    await grant(c, h, base2, partner)
    members = [
        {
            "engagement_id": en,
            "profile_id": pr["id"],
            "share_capital": "1" if en == eid else "0.95",
            "voting_rights": "1" if en == eid else "0.95",
            "profit_net_asset_rights": "1" if en == eid else "0.95",
            "resident_juridical": True,
            "exempt_or_qfzp": False,
            "entry_date": "2026-01-01",
        }
        for en, pr in [(eid, p), (eid2, p2)]
    ]
    adjustments = []
    for en, source in [(eid, adj), (eid2, adj2)]:
        body = {k: v for k, v in source["body"].items() if not k.startswith("review_")}
        body.update(profile_id=p["id"], rule_id=rules["adjustments"], source_engagement_id=en)
        adjustments.append(body)
    data = {
        "profile_id": p["id"],
        "members": members,
        "fta_application_evidence_id": note["id"],
        "fta_approval_evidence_id": note["id"],
        "special_purpose_audit_evidence_id": note["id"],
        "group_adjustments": adjustments,
        "pre_group_losses_interest_assessment": "No restricted pre-group attributes in synthetic scope",
        "no_restricted_pre_group_attributes": True,
        "conditions": [
            {
                "requirement": key,
                "assessment": "PASS",
                "rationale": "Synthetic reviewed group facts",
                "evidence_record_ids": [note["id"]],
            }
            for key in [
                "fta_approval",
                "financial_alignment",
                "accounting_alignment",
                "group_boundary",
            ]
        ],
    }
    group = await ready("group", data)
    r = await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{group['id']}", headers=h)
    assert r.status_code == 201, r.text
    run = r.json()
    assert D(run["results"]["accounting_profit"]) == 2400000
    assert D(run["results"]["taxable_income"]) == 3200000
    assert D(run["results"]["current_tax"]) == 254250  # one group threshold, not one per member
    await release(c, h, eid, base, manager, partner, run)
    data["members"][1]["voting_rights"] = "0.9499"
    invalid = await ready("group", data)
    assert (
        await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{invalid['id']}", headers=h)
    ).status_code == 422


async def test_related_party_loan_uses_reconciled_statutory_bridge(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    reviewed = await ready(
        "related-party",
        {
            "profile_id": p["id"],
            "counterparty": "SYNTHETIC related lender",
            "relationship": "related_party",
            "effective_from": "2026-01-01",
            "transaction_type": "loan interest",
            "amount": "400000",
            "account_codes": ["500"],
            "contract_evidence_id": note["id"],
            "risk_assessment": "Pricing requires professional review; no completed benchmarking",
        },
    )
    interest = await ready(
        "interest",
        {
            "profile_id": p["id"],
            "source_account_codes": ["500"],
            "evidence_record_ids": [note["id"]],
            "interest_expense": "400000",
            "interest_income": "0",
            "depreciation_tax_deductible": "0",
            "taxable_before_gidlr_losses": "1600000",
            "period_months": "12",
            "period_index": 3,
            "statutory_bridge": "Approved profit plus entertainment bridge",
            "loan_and_tp_review": "Synthetic borrowing purpose and ALP reviewed; no automatic TP violation conclusion",
            "sources": [{"kind": "record", "id": reviewed["id"]}],
        },
    )
    result = await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{interest['id']}", headers=h)
    assert result.status_code == 201, result.text
    assert D(result.json()["results"]["current_disallowed"]) == 0
    run = await compute(c, h, eid, p)
    assert run["results"]["validation"]["ready"]
    assert D(run["results"]["current_tax"]) == 110250


async def test_ai_tax_sources_independent_decisions_and_no_direct_posting(environment, monkeypatch):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    from redis.asyncio import Redis

    from app.core.config import settings
    from app.modules.tax.catalogue import AI_TASKS

    monkeypatch.setattr(settings(), "financial_ai_hourly_requests", 100)
    async with Redis.from_url(settings().redis_url) as redis:
        await redis.delete("tax-ai-budget:" + h["X-Tenant-ID"])

    api = f"/api/v1/tax/engagements/{eid}/ai"
    for task in AI_TASKS:
        r = await c.post(
            api,
            headers=h,
            json={
                "profile_id": p["id"],
                "task": task,
                "sources": [{"kind": "record", "id": adj["id"]}],
            },
        )
        assert r.status_code == 201, r.text
        suggestion = r.json()
        assert suggestion["status"] == "SUGGESTED" and suggestion["body"]["output"]["uncertainties"]
        assert not suggestion["body"]["output"]["tax_position_approved"]
        data = {
            "version": suggestion["version"],
            "decision": "ACCEPTED",
            "rationale": "Synthetic independent reviewer checked legal references",
        }
        assert (
            await c.post(api + f"/{suggestion['id']}/decision", headers=h, json=data)
        ).status_code == 403
        accepted = await c.post(
            api + f"/{suggestion['id']}/decision", headers=manager[0], json=data
        )
        assert accepted.status_code == 200, accepted.text
    run = await compute(c, h, eid, p)
    assert len(run["results"]["lines"]) == 1  # accepting AI never posts an adjustment


async def test_tax_permissions_rule_control_and_isolation(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    auditor = await actor(h, "Auditor", "tax-unprivileged")
    await grant(c, h, base, auditor)
    assert (
        await c.get(f"/api/v1/tax/engagements/{eid}/workspace", headers=auditor[0])
    ).status_code == 403
    assert (await c.get(base + "/tax-adjustment", headers=auditor[0])).status_code == 403
    bad = await c.post(
        base + "/ai-actions",
        headers=auditor[0],
        json={
            "task": "financial_statement_risks",
            "sources": [{"kind": "record", "id": adj["id"]}],
        },
    )
    assert bad.status_code == 403
    run = await compute(c, h, eid, p)
    preparer = await actor(h, "Corporate Tax Preparer", "tax-no-export")
    await grant(c, h, base, preparer)
    assert (
        await c.get(
            f"/api/v1/tax/engagements/{eid}/runs/{run['id']}/export/pdf", headers=preparer[0]
        )
    ).status_code == 403
    from sqlalchemy import select, text
    from sqlalchemy.exc import DBAPIError

    from app.db.session import Session, tenant_context
    from app.modules.tax.models import TaxRun

    async with Session() as db, db.begin():
        await tenant_context(db, uuid.uuid4())
        assert not (await db.scalars(select(TaxRun))).all()
    async with Session() as db:
        with pytest.raises(DBAPIError):
            async with db.begin():
                await tenant_context(db, h["X-Tenant-ID"])
                await db.execute(
                    text("UPDATE ct_computation_runs SET current_tax=0 WHERE id=:id"),
                    {"id": uuid.UUID(run["id"])},
                )
