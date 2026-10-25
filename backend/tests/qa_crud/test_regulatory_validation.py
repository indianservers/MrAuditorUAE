"""Recorded fixture gates use real API/storage; expectations are explicit test inputs."""

import os

import pytest

from app.modules.regulatory import validation
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.qa_crud.test_regulatory_sources import propose, rule_payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned test DB required"
)


async def test_recorded_fixtures_gate_approval_publication_and_engine_freshness(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "fixture-validation-reviewer")
    await grant(c, h, base, reviewer)
    payload = rule_payload(key="SYNTHETIC-FIXTURE-GATE")
    await retain(c, h, payload)
    identifier = await propose(c, h, payload)
    prefix = f"/api/v1/regulatory/rules/{identifier}"
    vectors = [
        {
            "id": "STANDARD",
            "kind": "checklist",
            "expected_reference": "Independent synthetic fixture expected applicability",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "facts": {"entity_type": "company"},
            "expected_applicability": "APPLICABLE",
        }
    ]
    decision = {
        "action": "approve",
        "expected_sequence": 1,
        "comments": "Independent source and explicitly provided fixture assessment",
    }
    missing = await c.post(prefix + "/decisions", headers=reviewer[0], json=decision)
    assert missing.status_code == 409 and "fixture_validation_failed" in missing.text
    failed = await c.post(
        prefix + "/validate",
        headers=reviewer[0],
        json={"cases": [{**vectors[0], "expected_applicability": "NOT_APPLICABLE"}]},
    )
    assert failed.status_code == 200 and failed.json()["passed"] is False
    assert failed.json()["outcomes"][0]["passed"] is False
    checked = await c.post(prefix + "/validate", headers=reviewer[0], json={"cases": vectors})
    assert checked.status_code == 200 and checked.json()["passed"] is True
    # A dry run cannot approve, change lifecycle sequence or supply a publication receipt.
    before = await c.get(prefix, headers=h)
    assert before.json()["current_sequence"] == 1
    assert before.json()["fixture_validation"]["status"] == "NOT_RECORDED"
    own = await c.post(
        prefix + "/decisions", headers=h, json={**decision, "validation_cases": vectors}
    )
    assert own.status_code == 403
    approved = await c.post(
        prefix + "/decisions", headers=reviewer[0], json={**decision, "validation_cases": vectors}
    )
    assert approved.status_code == 201, approved.text
    receipt = approved.json()["body"]["fixture_validation"]
    assert receipt["receipt_sha256"] == checked.json()["receipt_sha256"]
    publish = {
        "action": "publish",
        "expected_sequence": 2,
        "comments": "Publish exactly the independently approved fixture receipt",
    }
    with monkeypatch.context() as changed:
        changed.setattr(validation, "implementation_hash", lambda method: "f" * 64)
        rejected = await c.post(prefix + "/decisions", headers=h, json=publish)
        assert rejected.status_code == 409 and "recorded fixture validation" in rejected.text
    published = await c.post(prefix + "/decisions", headers=h, json=publish)
    assert published.status_code == 201, published.text
    assert published.json()["body"]["fixture_validation"] == receipt
    context_path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    context = await c.post(
        context_path,
        headers=h,
        json={
            "country": "AE",
            "framework": "IFRS",
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic explicit fixture-validation assessment context",
        },
    )
    assert context.status_code == 201, context.text
    reviewed = await c.post(
        context_path + "/decision",
        headers=reviewer[0],
        json={
            "request_id": context.json()["id"],
            "approve": True,
            "comments": "Independent synthetic context selection and fixture reference",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    assessed = await c.post(
        f"/api/v1/regulatory/engagements/{eid}/assessments",
        headers=h,
        json={
            "rule_ids": [identifier],
            "facts": {"entity_type": "company"},
            "rationale": "Synthetic current calculation receipt assessment",
        },
    )
    assert assessed.status_code == 201, assessed.text
    event_path = f"/api/v1/intelligence/engagements/{eid}/events/{assessed.json()['id']}"
    assert (await c.get(event_path, headers=h)).json()["freshness"] == "CURRENT"
    with monkeypatch.context() as changed:
        changed.setattr(validation, "implementation_hash", lambda method: "e" * 64)
        detail = await c.get(prefix, headers=h)
        assert detail.json()["fixture_validation"]["status"] == "STALE"
        stale = await c.get(event_path, headers=h)
        assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
        assert stale.json()["sha256"] == assessed.json()["sha256"]
    assert (await c.get(event_path, headers=h)).json()["freshness"] == "CURRENT"


async def test_rate_validation_returns_unrounded_actual_without_inventing_an_oracle(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, _, _ = await setup(c)
    payload = rule_payload(key="SYNTHETIC-EXACT-FIXTURE")
    payload.update(
        method="flat_rate",
        rate="0.125",
        calculation_currency="AED",
        input_requirements=["tax_base"],
    )
    await retain(c, h, payload)
    identifier = await propose(c, h, payload)
    case = {
        "id": "EXACT",
        "kind": "flat_rate",
        "expected_reference": "Independent literal synthetic Decimal expected amount",
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "facts": {"entity_type": "company", "tax_base": "100.01", "tax_base_currency": "AED"},
        "expected_applicability": "APPLICABLE",
        "expected_amount": "12.50",
    }
    response = await c.post(
        f"/api/v1/regulatory/rules/{identifier}/validate", headers=h, json={"cases": [case]}
    )
    assert response.status_code == 200 and response.json()["passed"] is False
    outcome = response.json()["outcomes"][0]
    assert outcome["expected"]["amount"] == "12.50" and outcome["actual"]["amount"] == "12.50125"
    assert outcome["passed"] is False
    missing_oracle = await c.post(
        f"/api/v1/regulatory/rules/{identifier}/validate",
        headers=h,
        json={"cases": [{**case, "expected_amount": None}]},
    )
    assert missing_oracle.status_code == 422
