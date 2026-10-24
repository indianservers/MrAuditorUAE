"""Actual HTTP, reviewed financial sources and immutable connected tax receipts."""

import json
import os
import uuid
from pathlib import Path

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.phase6.test_workflows import compute, prepared, release

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated disposable migrated database"
)


async def test_connected_current_tax_review_and_source_invalidation(environment):
    c = environment
    (
        h,
        eid,
        base,
        manager,
        partner,
        profile,
        adjustment,
        note,
        rules,
        ready,
        financial,
    ) = await prepared(c)
    run = await compute(c, h, eid, profile)
    receipt = run["results"]["tax_execution"]
    assert receipt["schema_version"] == "tax/1" and receipt["source_snapshots"]
    assert receipt["calculated_liability"] == "110250.00000000"
    assert receipt["filing_status"] == "NOT_SUBMITTED"
    await release(c, h, eid, base, manager, partner, run)
    response = await c.post(
        f"/api/v1/tax/engagements/{eid}/connected-assessments",
        headers=h,
        json={
            "ct_run_id": run["id"],
            "rationale": "SYNTHETIC current-tax and accounting reconciliation review",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    payload = {
        "expected_version": result["version"],
        "action": "approve",
        "comments": "Synthetic independent connected-tax review",
    }
    assert (await c.post(prefix + "/review", headers=h, json=payload)).status_code == 403
    reviewed = await c.post(prefix + "/review", headers=partner[0], json=payload)
    assert reviewed.status_code == 201, reviewed.text
    reviewed_id = reviewed.json()["id"]
    assert (await c.get(prefix, headers={**h, "X-Tenant-ID": str(uuid.uuid4())})).status_code == 403
    await ready(
        "adjustment",
        {
            **{
                key: value
                for key, value in adjustment["body"].items()
                if not key.startswith("review_")
            },
            "accounting_amount": "200",
            "proposed_adjustment": "100",
        },
    )
    stale = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{reviewed_id}", headers=h)
    ).json()
    assert stale["freshness"] == "STALE"
    assert (
        await c.post(
            f"/api/v1/tax/engagements/{eid}/connected-assessments",
            headers=h,
            json={
                "ct_run_id": run["id"],
                "rationale": "Synthetic stale calculation must be refused",
            },
        )
    ).status_code == 409
    path = (
        Path(__file__).resolve().parents[3]
        / "docs/engine-strengthening/phase2/connected-workflow.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "fixture": "SYNTHETIC",
                "tax_run_id": run["id"],
                "approved_connected_assessment_id": reviewed_id,
                "source_change_stales_approved_output": True,
                "self_approval_blocked": True,
                "filing_submitted": False,
                "authority_acceptance_asserted": False,
            },
            indent=2,
        )
        + "\n"
    )


async def test_missing_dmtt_group_information_is_explicitly_unresolved(environment):
    c = environment
    h, eid, base, *_ = await prepared(c)
    response = await c.post(
        f"/api/v1/dmtt/engagements/{eid}/scope-assessment",
        headers=h,
        json={"fiscal_start": "2026-01-01"},
    )
    assert response.status_code == 201, response.text
    result = response.json()["body"]["results"]
    assert result["in_scope"] is None and result["status"] == "INCOMPLETE_SCOPE"
    auditor = await actor(h, "Auditor", "connected-tax-auditor")
    await grant(c, h, base, auditor)
    assert (
        await c.post(
            f"/api/v1/dmtt/engagements/{eid}/scope-assessment",
            headers=auditor[0],
            json={"fiscal_start": "2026-01-01"},
        )
    ).status_code == 403


async def test_sbr_extension_cannot_be_adopted_without_publication_evidence(environment):
    c = environment
    h, eid, base, manager, partner, profile, adjustment, note, rules, *_ = await prepared(c)
    obj = (await c.get(base + "/records/" + rules["sbr"], headers=h)).json()
    body = {key: value for key, value in obj["body"].items() if not key.startswith("review_")}
    body.update(
        rule_key="SYNTHETIC-UNVERIFIED-SBR", publication_date=None, publication_evidence_id=None
    )
    result = await c.post(
        base + "/tax-rule",
        headers=h,
        json={
            "reference": "UNVERIFIED-SBR",
            "title": "Synthetic extension lacking commencement evidence",
            "body": body,
        },
    )
    assert result.status_code == 409 and "publication" in result.text


async def test_excess_credit_note_blocks_draft_vat_return(environment):
    from decimal import Decimal

    from tests.phase7.test_vat_workflows import prepared as vat_prepared

    c = environment
    h, eid, base, manager, partner, profile, invoices, evidence, rules, ready = await vat_prepared(
        c
    )
    original = next(item for item in invoices if item["body"]["direction"] == "sale")
    body = {key: value for key, value in original["body"].items() if not key.startswith("review_")}
    body.update(
        document_type="credit_note",
        document_label="Tax Credit Note",
        original_invoice_id=original["id"],
        invoice_number="SYNTHETIC-EXCESS-CREDIT",
        sequence=999,
    )
    for key in ["amount", "unit_price", "discount"]:
        body[key] = str(Decimal(str(body[key])) * 2)
    for key in ["declared_net", "declared_tax", "declared_gross"]:
        # Credit-note source documents state positive magnitudes; document type reverses them.
        body[key] = str(Decimal(str(body[key])) * 2)
    await ready("vat-invoice", body)
    result = await c.post(f"/api/v1/vat/engagements/{eid}/computations/{profile['id']}", headers=h)
    assert result.status_code == 201, result.text
    data = result.json()["results"]
    assert not data["validation"]["ready"]
    assert any("Cumulative credit notes exceed" in row["message"] for row in data["exceptions"])
