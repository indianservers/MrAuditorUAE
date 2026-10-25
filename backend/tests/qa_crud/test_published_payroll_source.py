"""Whole-month published India profiles, real storage/API/job processor; synthetic rates."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.qa_crud.test_regulatory_sources import decide, propose
from tests.unit.test_payroll_profiles import profile
from tests.unit.test_payroll_rule_workflow import basis, reported

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned test DB required"
)


async def publish(c, h, reviewer, *, sequence=0, start="2026-01-01", end="2026-12-31", rate="0.1"):
    payload = profile().model_dump(mode="json")
    payload.update(
        expected_sequence=sequence,
        effective_from=start,
        effective_to=end,
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-24",
    )
    payload["payroll_parameters"]["rate"] = rate
    payload["citations"][0]["url"] = "https://incometax.gov.in/"
    document = await retain(c, h, payload)
    identifier = await propose(c, h, payload)
    approved = await decide(c, reviewer, identifier, sequence=sequence + 1)
    assert approved.status_code == 201, approved.text
    published = await decide(c, h, identifier, action="publish", sequence=sequence + 2)
    assert published.status_code == 201, published.text
    return identifier, document


async def test_published_payroll_whole_month_selection_and_interior_amendment_staleness(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "published-payroll-reviewer")
    final_reviewer = await actor(h, "Firm Administrator", "published-payroll-final")
    for participant in (reviewer, final_reviewer):
        await grant(c, h, base, participant)
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    response = await c.post(
        path,
        headers=h,
        json={
            "country": "IN",
            "framework": "Ind AS",
            "entity_type": "company",
            "as_of": "2027-03-31",
            "base_version": 0,
            "reason": "Synthetic published payroll reporting context",
        },
    )
    assert response.status_code == 201, response.text
    reviewed_context = await c.post(
        path + "/decision",
        headers=reviewer[0],
        json={
            "request_id": response.json()["id"],
            "approve": True,
            "comments": "Independent synthetic payroll context assessment",
        },
    )
    assert reviewed_context.status_code == 201, reviewed_context.text
    old, old_copy = await publish(c, h, reviewer[0])
    new, new_copy = await publish(c, h, reviewer[0], sequence=3, start="2026-06-01", rate="0.2")
    wages = await source(
        c,
        h,
        eid,
        [basis(id="MAY", period="2026-05"), basis(id="JUNE")],
        "SYNTHETIC mixed wage months",
        "payroll-bases",
        {"INR": "40000"},
    )
    endpoint = f"/api/v1/intelligence/engagements/{eid}/payroll-rule-source"
    request = {
        "basis_source_id": wages["id"],
        "rule_version_ids": [old, new],
        "expected_basis_rows": 2,
        "label": "SYNTHETIC published payroll profiles",
        "assessment": "Synthetic jurisdiction, assessed bases, membership and whole-month rules assessed",
    }
    assert (await c.post(endpoint, headers=h, json=request)).status_code == 409
    reviewed = await decision(c, reviewer[0], eid, wages)
    assert reviewed.status_code == 201, reviewed.text
    request["basis_source_id"] = reviewed.json()["id"]
    assert (
        await c.post(endpoint, headers=h, json={**request, "rule_version_ids": [old]})
    ).status_code == 409
    assert (
        await c.post(endpoint, headers=h, json={**request, "expected_basis_rows": 3})
    ).status_code == 422
    created = await c.post(endpoint, headers=h, json=request)
    assert created.status_code == 201, created.text
    rules = created.json()
    by_id = {row["id"]: row for row in rules["body"]["rows"]}
    assert by_id[old]["selected_wage_months"] == ["2026-05"]
    assert by_id[new]["selected_wage_months"] == ["2026-06"]
    assert by_id[old]["source_document_id"] == old_copy["id"]
    assert (await decision(c, h, eid, rules)).status_code == 403
    approved_rules = await decision(c, reviewer[0], eid, rules)
    assert approved_rules.status_code == 201, approved_rules.text
    returns = await source(
        c,
        h,
        eid,
        [reported(id="MAY", period="2026-05", amount="1500"), reported(id="JUNE", amount="3000")],
        "SYNTHETIC reported contributions",
        "obligations",
        {"INR": "4500"},
    )
    approved_returns = await decision(c, reviewer[0], eid, returns)
    assert approved_returns.status_code == 201, approved_returns.text
    payload = {
        "workflow": "india-payroll-rules",
        "source_ids": {
            "bases": reviewed.json()["id"],
            "rules": approved_rules.json()["id"],
            "reported": approved_returns.json()["id"],
        },
        "as_of": "2026-06-30",
        "currency": "INR",
        "title": "SYNTHETIC published payroll review",
        "rationale": "Synthetic independent expected and reported contributions with source-bound profiles",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    by_month = {row["period"]: row for row in result["body"]["rows"]}
    assert by_month["2026-05"]["expected_amount"] == "1500"
    assert by_month["2026-06"]["expected_amount"] == "3000"
    assert by_month["2026-06"]["published_rule_version_id"] == new
    assert by_month["2026-06"]["rule_source_document_id"] == new_copy["id"]
    assert result["body"]["expected_total"] == "4500" and not result["body"]["blocked"]
    final = await decision(c, final_reviewer[0], eid, result)
    assert final.status_code == 201, final.text
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{final.json()['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    # Both endpoints of June still select v2; the interior June 10–20 amendment must nevertheless invalidate it.
    interior, _ = await publish(
        c, h, reviewer[0], sequence=6, start="2026-06-10", end="2026-06-20", rate="0.3"
    )
    for saved in (approved_rules.json(), final.json()):
        history = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}", headers=h
        )
        assert history.status_code == 200, history.text
        assert history.json()["freshness"] == "STALE"
        assert history.json()["sha256"] == saved["sha256"]
    refused = await c.post(
        endpoint, headers=h, json={**request, "rule_version_ids": [old, new, interior]}
    )
    assert refused.status_code == 409 and "entire wage month" in refused.text
