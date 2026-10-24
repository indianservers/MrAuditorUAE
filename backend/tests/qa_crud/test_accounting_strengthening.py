"""Synthetic connected accounting workflows in the dedicated migrated test database."""

import json
import os
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import action, actor, approve, create, grant
from tests.phase5.test_reporting import prepared
from tests.phase6.test_workflows import compute, release
from tests.unit.test_accounting_strengthening import ASSET, BENEFITS, STOCK

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated disposable database"
)
ARTIFACTS = Path(__file__).resolve().parents[3] / "docs/engine-strengthening/phase3"


async def post(c, h, path, body=None, status=201):
    response = await c.post(path, headers=h, json=body)
    assert response.status_code == status, response.text
    return response.json()


async def revise(c, h, reviewer, base, obj, body):
    obj = await action(c, reviewer, base, obj, "reopen")
    response = await c.patch(
        base + "/records/" + obj["id"],
        headers=h,
        json={
            "version": obj["version"],
            "reference": obj["reference"],
            "title": obj["title"],
            "body": body,
        },
    )
    assert response.status_code == 200, response.text
    return await approve(c, h, reviewer, base, response.json())


async def test_operating_company_schedules_approved_overlays_and_tax_bridge(environment):
    c = environment
    h, eid, base, manager, partner, profile, mapping, note, ready = await prepared(c, scale=40000)
    api = f"/api/v1/ifrs/engagements/{eid}"
    eng = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    entity = (await c.get("/api/v1/entities/" + eng["entity_id"], headers=h)).json()
    accounts = [
        ("140", "Inventory", "assets"),
        ("149", "Inventory allowance", "assets"),
        ("150", "Equipment", "assets"),
        ("159", "Accumulated depreciation", "assets"),
        ("160", "ROU", "assets"),
        ("210", "Lease liability", "liabilities"),
        ("220", "Benefit provision", "liabilities"),
        ("230", "Current tax payable", "liabilities"),
        ("240", "Deferred tax liability", "liabilities"),
        ("510", "Tax expense", "expenses"),
    ]
    coa = "Account Code,Account Name,Source ID\n" + "".join(
        f"{code},{label},SYN-{code}\n" for code, label, _ in accounts
    )
    await committed(
        c,
        h,
        {
            "client_id": entity["client_id"],
            "entity_id": entity["id"],
            "period_id": eng["period_id"],
            "kind": "coa",
            "source_complete": True,
            "expected_rows": len(accounts),
            "expected_debit": "0",
            "expected_credit": "0",
        },
        coa.encode(),
    )
    mapping_body = {k: v for k, v in mapping["body"].items() if not k.startswith("review_")}
    mapping_body["accounts"] += [
        {
            "account_code": code,
            "allocations": [
                {
                    "line_code": code,
                    "label": label,
                    "section": section,
                    "note": "N1",
                    "category": "tax" if code == "510" else "operating",
                }
            ],
        }
        for code, label, section in accounts
    ]
    mapping = await revise(c, h, manager[0], base, mapping, mapping_body)
    note_body = {k: v for k, v in note["body"].items() if not k.startswith("review_")}
    note_body["linked_line_codes"] += [code for code, _, _ in accounts]
    note = await revise(c, h, manager[0], base, note, note_body)
    for disclosure in (await c.get(api + "/records/disclosure?limit=100", headers=h)).json()[
        "items"
    ]:
        await revise(
            c,
            h,
            manager[0],
            base,
            disclosure,
            {k: v for k, v in disclosure["body"].items() if not k.startswith("review_")},
        )
    overlays = []

    async def manual(reference, debit, credit, amount):
        obj = await ready(
            "adjustment",
            {
                "profile_id": profile["id"],
                "adjustment_date": "2026-01-01",
                "currency": "AED",
                "standard": "IAS 16" if debit == "150" else "IAS 2",
                "narration": reference
                + ": synthetic acquisition from supplied invoice; reporting overlay only",
                "legs": [
                    {"account_code": debit, "debit": amount},
                    {"account_code": credit, "credit": amount},
                ],
            },
        )
        overlays.append(obj)

    await manual("SYN acquired equipment", "150", "100", "3650")
    await manual("SYN purchased inventory", "140", "100", "176")
    asset = await ready(
        "fixed-assets",
        {
            "profile_id": profile["id"],
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "assets": [{**ASSET, "available_for_use_date": "2026-01-01"}],
        },
    )
    inventory_body = deepcopy(STOCK)
    inventory_body["profile_id"] = profile["id"]
    inventory_body["items"][0].update(
        opening_quantity="0",
        opening_unit_cost="0",
        issues=[],
        receipts=[
            {
                "reference": "SYN-R",
                "date": "2026-02-01",
                "quantity": "8",
                "unit_cost": "22",
                "evidence": "SYN invoice",
            }
        ],
    )
    stock = await ready("inventory", inventory_body)
    benefit_body = {
        **BENEFITS,
        "profile_id": profile["id"],
        "opening_obligation": "0",
        "net_interest": "0",
        "remeasurement_oci": "0",
        "settlements": "0",
        "closing_ledger_provision": "20",
        "payroll_expense": "0",
        "opening_payroll_payable": "0",
        "payroll_deductions": "0",
        "confirmed_bank_payments": "0",
        "closing_payroll_ledger_payable": "0",
        "leave_bonus_accrual": "0",
    }
    benefit = await ready("employee-benefits", benefit_body)
    lease = await ready(
        "lease",
        {
            "profile_id": profile["id"],
            "commencement": "2026-12-31",
            "end_date": "2027-12-31",
            "annual_discount_rate": "0.1",
            "payments": [{"date": "2027-12-31", "amount": "1100"}],
            "recognition_assessment": "SYN approved lessee identification",
            "options_assessment": "SYN one-year approved accounting term",
        },
    )
    calculations = {}
    for kind, source, debit, credit in [
        ("fixed-assets", asset, "500", "159"),
        ("inventory", stock, "500", "149"),
        ("employee-benefits", benefit, "500", "220"),
        ("lease", lease, "160", "210"),
    ]:
        run = await post(c, h, api + "/calculate/" + source["id"])
        calculations[kind] = run
        assert run["results"]["execution"]["framework"] == "full_ifrs"
        proposal = await post(
            c,
            h,
            api + f"/runs/{run['id']}/propose-journal",
            {
                "profile_id": profile["id"],
                "reference": "SYN-" + kind,
                "debit_account": debit,
                "credit_account": credit,
                "adjustment_date": "2026-12-31",
                "rationale": "SYN human accounts and recognition assessed",
            },
        )
        assert proposal["status"] == "IN_PROGRESS"
        approved_proposal = await approve(c, h, manager[0], base, proposal)
        overlays.append(approved_proposal)
        if kind == "fixed-assets":
            bypass = await create(
                c,
                h,
                base,
                "ifrs-adjustment",
                {k: v for k, v in approved_proposal["body"].items() if not k.startswith("review_")},
            )
            await action(c, h, base, bypass, "submit", expected=409)
    cash = await ready(
        "cash-flow",
        {
            "profile_id": profile["id"],
            "noncash_adjustments": "401",
            "investing": "-3826",
            "policy": "SYN depreciation365, stock allowance16 and benefit20 are noncash; acquisitions3826 are investing",
            "movement_schedule_source": "SYN imported cash ledger plus individually approved acquisition overlays",
        },
    )
    # Remove the older approved cash policy, preserving its history.
    previous = (await c.get(api + "/records/cash-flow", headers=h)).json()["items"]
    old_cash = next(item for item in previous if item["id"] != cash["id"])
    await action(c, manager[0], base, old_cash, "reopen")
    financial = await post(c, h, api + "/financial-statements/" + profile["id"])
    assert financial["results"]["validation"]["ready"], financial["results"]["validation"]
    assert D(financial["results"]["totals"]["profit"]) == 1199599
    assert D(financial["results"]["cash_flow"]["difference"]) == 0

    async def release_financial(run):
        package = await create(
            c,
            h,
            base,
            "ifrs-financials",
            {"run_id": run["id"], "release_rationale": "SYN reconciled package"},
        )
        package = await action(c, h, base, package, "submit")
        package = await action(c, manager[0], base, package, "approve")
        return await action(c, partner[0], base, package, "approve")

    await release_financial(financial)
    tax_manager = await actor(h, "Tax Manager", "phase3-tax-manager")
    tax_partner = await actor(h, "Tax Partner", "phase3-tax-partner")
    for user in [tax_manager, tax_partner]:
        await grant(c, h, base, user)
    rules = {}
    for category, source, article in [
        ("standard", "CT-RATES", ""),
        ("adjustments", "CT-LAW", "29"),
        ("losses", "CT-LAW", "37"),
        ("deadline", "CT-LAW", "53"),
    ]:
        obj = await create(
            c,
            h,
            base,
            "tax-rule",
            {
                "rule_key": "SYN-" + category,
                "rule_version": 1,
                "category": category,
                "source_id": source,
                "article": article,
                "decision_number": "SYN reviewed reference",
                "effective_from": "2023-06-01",
                "known_from": "2023-06-01",
                "source_document_version": "SYN technical fixture only",
                "conditions": "SYN ordinary resident case",
                "exceptions": "SYN no special relief",
                "technical_review": "SYN independent rule review",
            },
        )
        rules[category] = (await approve(c, h, tax_partner[0], base, obj))["id"]
    tp = await create(
        c,
        h,
        base,
        "tax-profile",
        {
            "financial_run_id": financial["id"],
            "classification": "resident_juridical",
            "legal_form": "SYN LLC",
            "registration_details": "SYN",
            "residence_assessment": "SYN resident",
            "resident": True,
            "licensed_activities": "SYN ordinary trading",
            "ownership_assessment": "SYN stable",
            "tax_start": "2026-01-01",
            "tax_end": "2026-12-31",
            "legal_as_of": "2026-10-18",
            "rules": rules,
            "revenue": "2000000",
            "revenue_source": "Approved revenue line400",
            "scope_assessment": "SYN all expenses separately reviewed; ordinary deductible case",
            "pillar_two_in_scope": False,
            "audited_financials_required": False,
        },
    )
    tp = await approve(c, h, tax_manager[0], base, tp)
    ct = await compute(c, h, eid, tp)
    assert D(ct["results"]["current_tax"]) == D("74213.91")
    await release(c, h, eid, base, tax_manager, tax_partner, ct)
    # A distinct presentation profile retains the approved E05 base without a tax/reporting cycle.
    p2 = await ready(
        "profile", {k: v for k, v in profile["body"].items() if not k.startswith("review_")}
    )
    await ready("mapping", {**mapping_body, "profile_id": p2["id"]})
    for overlay in overlays:
        await ready(
            "adjustment",
            {
                **{k: v for k, v in overlay["body"].items() if not k.startswith("review_")},
                "profile_id": p2["id"],
            },
        )
    n2 = await ready(
        "note",
        {
            **{k: v for k, v in note["body"].items() if not k.startswith("review_")},
            "profile_id": p2["id"],
        },
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
            "disclosure",
            {
                "profile_id": p2["id"],
                "standard": "IAS 1",
                "category": category,
                "applicability": "applicable",
                "rationale": "SYN reviewed facts",
                "note_id": n2["id"],
            },
        )
    dt = await ready(
        "deferred-tax",
        {
            "profile_id": p2["id"],
            "current_tax_run_id": ct["id"],
            "current_tax": "74213.91",
            "current_tax_source": "Approved E05 release",
            "differences": [
                {
                    "reference": "SYN-equipment",
                    "jurisdiction": "AE",
                    "rate_source": "SYN reviewed enacted ordinary rate; technical fixture only",
                    "rate_effective_date": "2026-01-01",
                    "carrying_amount": "3285",
                    "tax_base": "3000",
                    "item_type": "asset",
                    "tax_rate": "0.09",
                    "recognition_rationale": "SYN taxable recovery",
                    "expected_recovery_or_settlement": "SYN use through remaining life",
                }
            ],
        },
    )
    deferred = await post(c, h, api + "/calculate/" + dt["id"])
    assert D(deferred["results"]["dtl"]) == D("25.65")
    for component, credit in [("primary", "240"), ("current_tax", "230")]:
        proposal = await post(
            c,
            h,
            api + f"/runs/{deferred['id']}/propose-journal",
            {
                "profile_id": p2["id"],
                "reference": "SYN-tax-" + component,
                "debit_account": "510",
                "credit_account": credit,
                "adjustment_date": "2026-12-31",
                "rationale": "SYN reviewed tax accounting bridge",
                "component": component,
            },
        )
        if component == "primary":
            submitted = await action(c, h, base, proposal, "submit")
            await action(c, manager[0], base, submitted, "approve", expected=403)
            # Tax-source access is an explicit engagement assignment, not implied by accounting approval.
            await grant(c, h, base, (manager[0], manager[1], tax_manager[2], manager[3]))
            await grant(c, h, base, (partner[0], partner[1], tax_partner[2], partner[3]))
            await action(c, manager[0], base, submitted, "approve")
        else:
            await approve(c, h, manager[0], base, proposal)
    await ready(
        "cash-flow",
        {
            "profile_id": p2["id"],
            "noncash_adjustments": "74640.56",
            "investing": "-3826",
            "policy": "SYN401 operating noncash plus unpaid current-tax74213.91 and deferred25.65; no tax paid",
            "movement_schedule_source": "SYN source cash, approved overlays and E05 release",
        },
    )
    final = await post(c, h, api + "/financial-statements/" + p2["id"])
    assert final["results"]["validation"]["ready"], final["results"]["validation"]
    assert D(final["results"]["totals"]["profit"]) == D("1125359.44")
    assert D(final["results"]["cash_flow"]["difference"]) == 0
    assert (await release_financial(final))["status"] == "APPROVED"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "operating-company-workflow.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "schedules": calculations,
                "before_tax_financials": financial,
                "e05": ct,
                "e09_deferred_tax": deferred,
                "approved_reporting_output": final,
                "posting": "All adjustments are approved reporting overlays; no journal was posted to the source ledger",
            },
            indent=2,
        )
    )


async def test_revision_duplicate_proposal_and_period_lock(environment):
    c = environment
    h, eid, base, manager, _, profile, _, _, ready = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    body = {
        "profile_id": profile["id"],
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "assets": [{**ASSET, "available_for_use_date": "2026-01-01"}],
    }
    source = await ready("fixed-assets", body)
    first = await post(c, h, api + "/calculate/" + source["id"])
    proposal_body = {
        "profile_id": profile["id"],
        "reference": "SYN-revision",
        "debit_account": "500",
        "credit_account": "100",
        "adjustment_date": "2026-12-31",
        "rationale": "Technical approval controls test; not a compliant asset journal demonstration",
    }
    proposal = await post(c, h, api + f"/runs/{first['id']}/propose-journal", proposal_body)
    repeated = await post(c, h, api + "/calculate/" + source["id"])
    assert repeated["sha256"] == first["sha256"]
    await post(
        c,
        h,
        api + f"/runs/{repeated['id']}/propose-journal",
        {**proposal_body, "reference": "SYN-identical-rerun"},
        status=409,
    )
    await post(
        c,
        h,
        api + f"/runs/{first['id']}/propose-journal",
        {**proposal_body, "reference": "SYN-duplicate"},
        status=409,
    )
    submitted = await action(c, h, base, proposal, "submit")
    revised_body = deepcopy(body)
    revised_body["assets"][0]["useful_life_years"] = "5"
    source = await revise(c, h, manager[0], base, source, revised_body)
    old = (await c.get(api + "/runs/" + first["id"], headers=h)).json()
    assert not old["dependencies_current"]
    assert D(old["results"]["total_depreciation"]) == 365
    await action(c, manager[0], base, submitted, "approve", expected=409)
    second = await post(c, h, api + "/calculate/" + source["id"])
    assert D(second["results"]["total_depreciation"]) == 730
    assert second["id"] != first["id"]
    pending = await post(
        c,
        h,
        api + f"/runs/{second['id']}/propose-journal",
        {**proposal_body, "reference": "SYN-lock-approval"},
    )
    pending = await action(c, h, base, pending, "submit")
    reapproved = await action(c, manager[0], base, pending, "approve")
    assert reapproved["status"] == "APPROVED"
    pending = await action(c, manager[0], base, reapproved, "reopen")
    pending = await action(c, h, base, pending, "submit")
    await post(
        c,
        h,
        f"/api/v1/intelligence/engagements/{eid}/period-actions",
        {"action": "lock", "expected_version": 1, "reason": "SYN closed reporting period"},
        status=200,
    )
    await action(c, manager[0], base, pending, "approve", expected=409)
    await post(
        c,
        h,
        base + "/ifrs-adjustment",
        {
            "reference": "SYN-locked",
            "title": "SYN locked-period manual proposal",
            "body": {
                "profile_id": profile["id"],
                "adjustment_date": "2026-12-31",
                "currency": "AED",
                "standard": "IAS 16",
                "narration": "SYN locked-period authorization test",
                "legs": [
                    {"account_code": "500", "debit": "1"},
                    {"account_code": "100", "credit": "1"},
                ],
            },
        },
        status=409,
    )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "controlled-revision-workflow.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "original_run_read_after_revision": old,
                "recalculated_run": second,
                "independently_reapproved_control_journal": reapproved,
                "blocked": {
                    "duplicate_reference_or_component": 409,
                    "identical_input_rerun": 409,
                    "stale_calculation_approval": 409,
                    "locked_period_approval": 409,
                    "locked_period_creation": 409,
                },
                "scope": "Technical approval/version/lock controls; no financial statements or compliant asset-account selection are asserted by this control-only fixture",
            },
            indent=2,
        )
    )


async def test_entity_currency_change_invalidates_prior_reporting_execution(environment):
    import uuid

    from app.db.models.platform import LegalEntity
    from app.db.session import Session, tenant_context

    c = environment
    h, eid, _, _, _, profile, _, _, _ = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    result = await post(c, h, api + "/financial-statements/" + profile["id"])
    assert (await c.get(api + "/runs/" + result["id"], headers=h)).json()["dependencies_current"]
    entity_id = result["results"]["execution"]["entity_id"]
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        entity = await db.get(LegalEntity, uuid.UUID(entity_id))
        entity.functional_currency = "USD"
    response = (await c.get(api + "/runs/" + result["id"], headers=h)).json()
    assert not response["dependencies_current"]
    assert response["results"]["execution"]["functional_currency"] == "AED"
