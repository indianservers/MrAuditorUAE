"""One synthetic entity, one ledger: reviewed zero-rated exports and ordinary CT.

Zero-rating is an explicit reviewed fixture fact, never inferred from income or location.
"""

import json
import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.session import Session, tenant_context
from app.modules.accounting.models import Account, JournalLine
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import action, approve, create, setup
from tests.phase6.test_workflows import compute, prepared, release
from tests.phase7.test_vat_calculations import invoice, rule

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated disposable migrated database"
)


async def test_one_entity_vat_reconciliation_to_current_tax_and_connected_review(environment):
    c = environment
    h, options, eid, base = await setup(c)
    eng = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    entity = (await c.get("/api/v1/entities/" + eng["entity_id"], headers=h)).json()
    # Retained chart data establishes genuine zero-balance VAT controls, not a balancing entry.
    await committed(
        c,
        h,
        {
            "client_id": entity["client_id"],
            "entity_id": eng["entity_id"],
            "period_id": eng["period_id"],
            "kind": "coa",
            "source_complete": True,
            "expected_rows": 2,
            "expected_debit": "0",
            "expected_credit": "0",
        },
        b"Account Code,Account Name,Source ID\n240,VAT Output,SYNTHETIC-VAT-OUT\n180,VAT Input,SYNTHETIC-VAT-IN\n",
    )
    # Establish the chart before preparing/reviewing IFRS and tax inputs. A later
    # chart change correctly invalidates the earlier approved financial package.
    (
        h, eid, base, manager, partner, tax_profile, adj, evidence, tax_rules, ready, financial,
    ) = await prepared(c, scope_data=(h, options, eid, base))
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        line = await db.scalar(
            select(JournalLine)
            .join(Account, Account.id == JournalLine.account_id)
            .where(
                JournalLine.tenant_id == uuid.UUID(h["X-Tenant-ID"]),
                JournalLine.entity_id == uuid.UUID(eng["entity_id"]),
                Account.code == "400",
            )
        )
        amount = line.base_credit - line.base_debit
        line_id, supply_date = str(line.id), line.posting_date

    async def vat_ready(kind, body):
        return await approve(c, h, manager[0], base, await create(c, h, base, "vat-" + kind, body))

    rules = {}
    for category in ["output", "input", "invoice", "return"]:
        body = rule(
            rule_key="SYNTHETIC-" + category,
            category=category,
            source_id="VAT201" if category == "return" else "VAT-LAW",
            article="" if category == "return" else "45" if category == "output" else "3",
            effective_from=date(2022, 10, 1) if category == "return" else date(2018, 1, 1),
            known_from=date(2022, 10, 1) if category == "return" else date(2018, 1, 1),
        ).model_dump(mode="json")
        rules[category] = (await vat_ready("rule", body))["id"]
    month = ((supply_date.month - 1) // 3) * 3 + 1
    end = date(supply_date.year + 1, 1, 1) if month == 10 else date(supply_date.year, month + 3, 1)
    from datetime import timedelta

    profile = await vat_ready(
        "profile",
        {
            "trn": "100000000000001",
            "registration_status": "REGISTERED",
            "registered_from": "2018-01-01",
            "filing_frequency": "quarterly",
            "period_start": date(supply_date.year, month, 1).isoformat(),
            "period_end": (end - timedelta(days=1)).isoformat(),
            "legal_as_of": "2026-10-18",
            "activities": "SYNTHETIC trading entity; documented zero-rated export",
            "input_recovery_assessment": "No VAT input recovery claimed in this synthetic case",
            "jurisdictions": ["AE", "GB"],
            "rules": rules,
            "output_control_codes": ["240"],
            "input_control_codes": ["180"],
            "filing_obligations": "Synthetic quarterly draft only",
            "calendar_review": "Synthetic calendar reviewed; no filing performed",
        },
    )
    body = invoice(
        profile_id=profile["id"],
        rule_id=rules["output"],
        invoice_rule_id=rules["invoice"],
        invoice_number="SYNTHETIC-EXPORT-1",
        sequence=1,
        issue_date=supply_date,
        supply_date=supply_date,
        tax_point=supply_date,
        treatment="zero",
        tax_rate=0,
        amount=amount,
        unit_price=amount,
        quantity=1,
        discount=0,
        declared_net=amount,
        declared_tax=0,
        declared_gross=amount,
        customer_jurisdiction="GB",
        customer_registered=False,
        currency="AED",
        exchange_rate=1,
        net_line_ids=[line_id],
        output_tax_line_ids=[],
        input_tax_line_ids=[],
        evidence_record_ids=[evidence["id"]],
        supply_type="goods",
        recovery_treatment="blocked",
        place_of_supply_assessment="Synthetic documented export; statutory conditions independently assessed, not inferred",
        treatment_facts_complete=True,
    ).model_dump(mode="json")
    await vat_ready("invoice", body)
    vat_response = await c.post(
        f"/api/v1/vat/engagements/{eid}/computations/{profile['id']}", headers=h
    )
    assert vat_response.status_code == 201, vat_response.text
    vat_run = vat_response.json()
    assert vat_run["results"]["validation"]["ready"] and Decimal(vat_run["results"]["net_vat"]) == 0
    vat_return = await create(c, h, base, "vat-return", {
        "run_id": vat_run["id"], "filing_state": "PREPARED", "checklist_complete": True,
        "rationale": "Synthetic reviewed export evidence, ledger and zero-control reconciliation; draft only"})
    vat_return = await action(c, h, base, vat_return, "submit")
    vat_return = await action(c, manager[0], base, vat_return, "approve")
    vat_return = await action(c, partner[0], base, vat_return, "approve")
    assert vat_return["status"] == "APPROVED"
    ct_run = await compute(c, h, eid, tax_profile)
    assert Decimal(ct_run["results"]["current_tax"]) == 110250
    await release(c, h, eid, base, manager, partner, ct_run)
    connected = await c.post(
        f"/api/v1/tax/engagements/{eid}/connected-assessments",
        headers=h,
        json={
            "ct_run_id": ct_run["id"],
            "vat_run_id": vat_run["id"],
            "rationale": "Synthetic same-ledger VAT and CT reconciliation, independent tax bases",
        },
    )
    assert connected.status_code == 201, connected.text
    obj = connected.json()
    assert obj["body"]["completeness"] == "complete_for_selected_controls"
    reviewed = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{obj['id']}/review",
        headers=partner[0],
        json={
            "expected_version": obj["version"],
            "action": "approve",
            "comments": "Synthetic independently reviewed connected trading controls",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    target = (
        Path(__file__).resolve().parents[3]
        / "docs/engine-strengthening/phase2/trading-workflow.json"
    )
    target.write_text(
        json.dumps(
            {
                "fixture": "SYNTHETIC reviewed zero-rated export; no inference from account names",
                "engagement_id": eid,
                "vat_run_id": vat_run["id"],
                "ct_run_id": ct_run["id"],
                "approved_connected_assessment_id": reviewed.json()["id"],
                "draft_vat": "0",
                "approved_vat_return_id": vat_return["id"],
                "draft_ct": "110250",
                "posting_or_filing_performed": False,
            },
            indent=2,
        )
        + "\n"
    )
