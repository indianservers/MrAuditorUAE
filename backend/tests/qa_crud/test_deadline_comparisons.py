"""Multiple-event deadlines preserve country, original facts and filing review controls."""

import os
from copy import deepcopy

import pytest

from app.core.security import decode_token
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated database required"
)


@pytest.mark.parametrize("country,timezone", [("AE", "Asia/Dubai"), ("IN", "Asia/Kolkata")])
async def test_later_of_dates_retain_independent_review_period_controls_and_source_staleness(
    environment, monkeypatch, country, timezone
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, audit_base = await setup(c)
    else:
        h, eid, audit_base = await india_context(c)
    eng = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    reviewer = await actor(h, "Firm Administrator", "later-of-reviewer")
    await grant(c, h, audit_base, reviewer)
    originals = {}
    for role in ("rule", "facts", "readiness"):
        record = await create(
            c,
            h,
            audit_base,
            "evidence",
            {
                "category": "Other",
                "retain_until": "2036-12-31",
            },
        )
        upload = await c.post(
            audit_base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-{role}.txt",
                    f"SYNTHETIC independently assessed {role} for multiple dated policy events, not legal qualification".encode(),
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 201, upload.text
        record = (await c.get(audit_base + "/records/" + record["id"], headers=h)).json()
        originals[role] = await approve(c, h, reviewer[0], audit_base, record)
    base = f"/api/v1/grc/engagements/{eid}"
    body = {
        "owner_id": str(decode_token(h["Authorization"].split()[1])),
        "entity_id": eng["entity_id"],
        "module": "policy",
        "source_url": "https://synthetic.invalid/later-of-policy",
        "jurisdiction": country,
        "jurisdiction_scope": {
            "entity_country": country,
            "obligation_country": country,
            "relationship": "domestic",
            "applicability": "assessed_applicable",
            "assessment": "SYNTHETIC separate policy and dated facts assessment",
        },
        "effective_from": "2026-01-01",
        "obligation_period_start": "2026-01-01",
        "obligation_period_end": "2026-12-31",
        "deadline_kind": "firm_internal",
        "deadline_rule": {
            "identifier": "SYN-notice",
            "version": 1,
            "effective_from": "2026-01-01",
            "trigger": "2026-12-01",
            "date_basis": "specified_event",
            "months_after": 1,
            "timezone": timezone,
            "later_of": [
                {
                    "identifier": "SYN-period",
                    "trigger": "2026-12-31",
                    "date_basis": "period_end",
                    "months_after": 3,
                }
            ],
        },
        "rule_evidence_id": originals["rule"]["id"],
        "fact_evidence_ids": [originals["facts"]["id"]],
        "entity_facts": {"notice": "2026-12-01", "period_end": "2026-12-31"},
        "reviewer_id": reviewer[3],
        "readiness_evidence_ids": [originals["readiness"]["id"]],
        "required_evidence": "Independent original policy and both dated triggering events",
        "compliance_assessment": "pending",
        "filing_stage": "preparing",
    }

    async def post(value):
        return await c.post(
            base + "/records/obligation",
            headers=h,
            json={
                "reference": "SYN-LATER-OF",
                "title": "SYNTHETIC multiple-event deadline",
                "body": value,
            },
        )

    wrong = deepcopy(body)
    wrong["deadline_rule"]["later_of"][0]["trigger"] = "2026-12-30"
    rejected = await post(wrong)
    assert rejected.status_code == 422 and "period end" in rejected.text
    wrong = deepcopy(body)
    wrong["deadline"] = "2027-01-01"
    assert (await post(wrong)).status_code == 422
    response = await post(body)
    assert response.status_code == 201, response.text
    obj = response.json()
    assert obj["body"]["deadline"] == "2027-03-31"
    assert obj["body"]["deadline_rule"]["later_of"] == [
        {
            **body["deadline_rule"]["later_of"][0],
            "days_after": 0,
        }
    ]
    staged = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "under_review"},
    )
    assert staged.status_code == 200, staged.text
    obj = await approve(c, h, reviewer[0], base, staged.json())
    approved = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=reviewer[0],
        json={"version": obj["version"], "stage": "approved_for_submission"},
    )
    assert approved.status_code == 200, approved.text
    obj = approved.json()
    retained = deepcopy(obj["body"])
    before = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert before.status_code == 200, before.text
    projection = before.json()["items"][0]
    trace = projection["deadline_comparison"]
    assert projection["freshness"] == "CURRENT" and not projection["reassessment_required"]
    assert trace["state"] == "CONSISTENT_WITH_SAVED_RULE"
    assert [(row["unadjusted_date"], row["selected"]) for row in trace["candidates"]] == [
        ("2027-01-01", False),
        ("2027-03-31", True),
    ]
    assert trace["rule_evidence_id"] == originals["rule"]["id"]
    assert trace["fact_evidence_ids"] == [originals["facts"]["id"]]
    await action(c, reviewer[0], audit_base, originals["facts"], "reopen")
    saved = (await c.get(audit_base + f"/records/{obj['id']}", headers=h)).json()
    assert saved["body"] == retained
    calendar = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert calendar.status_code == 200, calendar.text
    item = calendar.json()["items"][0]
    assert item["deadline"] == "2027-03-31" and item["freshness"] == "STALE"
    assert item["reassessment_required"] is True
    assert item["deadline_comparison"] == trace
