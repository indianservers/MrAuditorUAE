"""Synthetic published-profile bridge through actual API, storage and job processor."""

import os

import pytest

from app.modules.regulatory.benefit_profiles import BenefitParameters
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_regulatory_sources import decide, propose
from tests.unit.test_benefit_profiles import profile
from tests.unit.test_practice_audit_workflows import benefit_employee, benefit_rule

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned test DB required"
)


async def publish(c, h, reviewer, *, sequence=0, **changes):
    params = {
        key: value for key, value in benefit_rule().items() if key in BenefitParameters.model_fields
    }
    payload = profile(
        benefit_parameters=params,
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-24",
        expected_sequence=sequence,
        **changes,
    ).model_dump(mode="json")
    document = await retain(c, h, payload)
    identifier = await propose(c, h, payload)
    assert (await decide(c, reviewer, identifier, sequence=sequence + 1)).status_code == 201
    result = await decide(c, h, identifier, action="publish", sequence=sequence + 2)
    assert result.status_code == 201, result.text
    return identifier, document, payload


async def test_published_profiles_select_each_service_end_and_preserve_history(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "published-benefit-reviewer")
    final_reviewer = await actor(h, "Firm Administrator", "published-benefit-final")
    for participant in (reviewer, final_reviewer):
        await grant(c, h, base, participant)
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    context = await c.post(
        path,
        headers=h,
        json={
            "country": "AE",
            "framework": "IFRS",
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic benefit profile engagement context",
        },
    )
    assert context.status_code == 201, context.text
    response = await c.post(
        path + "/decision",
        headers=reviewer[0],
        json={
            "request_id": context.json()["id"],
            "approve": True,
            "comments": "Independent synthetic benefit profile context review",
        },
    )
    assert response.status_code == 201, response.text
    old, old_copy, original = await publish(c, h, reviewer[0])
    amended_params = {**original["benefit_parameters"], "first_tier_days": "42"}
    # A June amendment supersedes v1 only for employee service ends from June onward.
    amendment = {
        **original,
        "benefit_parameters": amended_params,
        "expected_sequence": 3,
        "effective_from": "2026-06-01",
    }
    new_copy = await retain(c, h, amendment)
    new = await propose(c, h, amendment)
    assert (await decide(c, reviewer[0], new, sequence=4)).status_code == 201
    assert (await decide(c, h, new, action="publish", sequence=5)).status_code == 201
    employees = await source(
        c,
        h,
        eid,
        [
            benefit_employee(id="MAY", service_start="2025-06-01", service_end="2026-05-31"),
            benefit_employee(id="JUNE", amount="4200"),
        ],
        "SYNTHETIC mixed service ends",
        "benefit-employees",
        {"AED": "6300"},
    )
    endpoint = f"/api/v1/intelligence/engagements/{eid}/benefit-rule-source"
    request = {
        "employee_source_id": employees["id"],
        "rule_version_ids": [old, new],
        "expected_employee_rows": 2,
        "label": "SYNTHETIC published benefits",
        "assessment": "Synthetic assessed cohort and work models at employee service end",
    }
    assert (await c.post(endpoint, headers=h, json=request)).status_code == 409
    reviewed = await decision(c, reviewer[0], eid, employees)
    assert reviewed.status_code == 201, reviewed.text
    request["employee_source_id"] = reviewed.json()["id"]
    assert (
        await c.post(endpoint, headers=h, json={**request, "rule_version_ids": [old]})
    ).status_code == 409
    assert (
        await c.post(endpoint, headers=h, json={**request, "expected_employee_rows": 3})
    ).status_code == 422
    derived = await c.post(endpoint, headers=h, json=request)
    assert derived.status_code == 201, derived.text
    rules = derived.json()
    by_rule = {row["id"]: row for row in rules["body"]["rows"]}
    assert by_rule[old]["selected_service_end_dates"] == ["2026-05-31"]
    assert by_rule[new]["selected_service_end_dates"] == ["2026-06-30"]
    assert by_rule[old]["source_document_id"] == old_copy["id"]
    assert by_rule[new]["source_document_id"] == new_copy["id"]
    assert (await decision(c, h, eid, rules)).status_code == 403
    approved = await decision(c, reviewer[0], eid, rules)
    assert approved.status_code == 201, approved.text
    payload = {
        "workflow": "uae-benefit-review",
        "source_ids": {"employees": reviewed.json()["id"], "rules": approved.json()["id"]},
        "as_of": "2026-06-30",
        "currency": "AED",
        "title": "SYNTHETIC published benefit review",
        "rationale": "Synthetic independently reviewed employees and effective-dated profiles",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    rows = {row["id"]: row for row in result["body"]["rows"]}
    assert rows["MAY"]["expected_benefit"] == "2100.00"
    assert rows["JUNE"]["expected_benefit"] == "4200.00"
    assert rows["MAY"]["published_rule_version_id"] == old
    assert rows["JUNE"]["published_rule_version_id"] == new
    assert rows["JUNE"]["rule_document_version_id"] is None
    assert rows["JUNE"]["rule_source_document_id"] == new_copy["id"]
    assert not result["body"]["blocked"] and result["freshness"] == "CURRENT"
    other_employees = await source(
        c,
        h,
        eid,
        [benefit_employee(id="OTHER", amount="4200")],
        "SYNTHETIC other employee population",
        "benefit-employees",
        {"AED": "4200"},
    )
    other_review = await decision(c, reviewer[0], eid, other_employees)
    assert other_review.status_code == 201, other_review.text
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **payload,
            "source_ids": {**payload["source_ids"], "employees": other_review.json()["id"]},
        },
        failed="bound to their original reviewed employee population",
    )
    final = await decision(c, final_reviewer[0], eid, result)
    assert final.status_code == 201, final.text
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{final.json()['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    # Another legal amendment must invalidate the June result without rewriting its bytes.
    revision = {
        **amendment,
        "expected_sequence": 6,
        "benefit_parameters": {**amended_params, "first_tier_days": "43"},
    }
    await retain(c, h, revision)
    latest = await propose(c, h, revision)
    assert (await decide(c, reviewer[0], latest, sequence=7)).status_code == 201
    assert (await decide(c, h, latest, action="publish", sequence=8)).status_code == 201
    for saved in (approved.json(), final.json()):
        history = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}", headers=h
        )
        assert history.status_code == 200, history.text
        assert history.json()["freshness"] == "STALE"
        assert history.json()["sha256"] == saved["sha256"]
