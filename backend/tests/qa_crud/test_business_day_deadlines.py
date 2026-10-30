"""Retained-calendar approval and staleness through real API/DB; synthetic holidays."""

import os
from copy import deepcopy

import pytest

from app.core.security import decode_token
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_business_day_deadlines import parameters

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated database required"
)


@pytest.mark.parametrize("country,timezone", [("AE", "Asia/Dubai"), ("IN", "Asia/Kolkata")])
@pytest.mark.parametrize("calendar_mode", ["count_business_days", "roll_calendar_date"])
async def test_business_calendar_requires_independent_evidence_and_stales_filing(
    environment, monkeypatch, country, timezone, calendar_mode
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, audit_base = await setup(c)
    else:
        h, eid, audit_base = await india_context(c)
    engagement = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    reviewer = await actor(h, "Firm Administrator", "business-calendar-reviewer")
    await grant(c, h, audit_base, reviewer)
    originals = {}
    for role in ("rule", "facts", "calendar", "readiness"):
        record = await create(
            c, h, audit_base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            audit_base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-{role}.txt",
                    f"SYNTHETIC independently assessed {role}, not national holiday or legal qualification".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        record = (await c.get(audit_base + "/records/" + record["id"], headers=h)).json()
        originals[role] = (
            record if role == "calendar" else await approve(c, h, reviewer[0], audit_base, record)
        )
    base = f"/api/v1/grc/engagements/{eid}"
    body = {
        "owner_id": str(decode_token(h["Authorization"].split()[1])),
        "entity_id": engagement["entity_id"],
        "module": "policy",
        "source_url": "https://synthetic.invalid/business-day-policy",
        "jurisdiction": country,
        "jurisdiction_scope": {
            "entity_country": country,
            "obligation_country": country,
            "relationship": "domestic",
            "applicability": "assessed_applicable",
            "assessment": "SYNTHETIC exact country and calendar assessment only",
        },
        "effective_from": "2026-01-01",
        "deadline_rule": parameters(timezone=timezone),
        "deadline_kind": "firm_internal",
        "rule_evidence_id": originals["rule"]["id"],
        "calendar_evidence_id": originals["calendar"]["id"],
        "fact_evidence_ids": [originals["facts"]["id"]],
        "entity_facts": {
            "trigger": "2026-06-26",
            "calendar_scope": "SYNTHETIC explicitly declared working week and holiday",
        },
        "reviewer_id": reviewer[3],
        "readiness_evidence_ids": [originals["readiness"]["id"]],
        "required_evidence": "Separate original policy, event facts and complete assessed calendar",
        "compliance_assessment": "pending",
        "filing_stage": "preparing",
    }

    expected = "2026-07-06"
    if calendar_mode == "roll_calendar_date":
        body["deadline_rule"] = {
            "identifier": "SYNTHETIC-five-calendar-days-then-roll",
            "version": 1,
            "effective_from": "2026-01-01",
            "trigger": "2026-06-26",
            "date_basis": "specified_event",
            "days_after": 5,
            "timezone": timezone,
            "convention": "following",
            "rolling_calendar": {
                "coverage_start": "2026-06-01",
                "coverage_end": "2026-07-31",
                "weekend_days": [5, 6],
                "holidays": ["2026-07-01", "2026-07-02"],
                "independent_holiday_count": 2,
                "assessment": "SYNTHETIC independently assessed rolling calendar only",
            },
        }
        expected = "2026-07-03"

    async def post(value):
        return await c.post(
            base + "/records/obligation",
            headers=h,
            json={
                "reference": "SYN-BUSINESS-CALENDAR",
                "title": "SYNTHETIC five working day obligation",
                "body": value,
            },
        )

    if calendar_mode == "roll_calendar_date":
        assert (await post({**body, "calendar_evidence_id": None})).status_code == 422
        assert (
            await post({**body, "calendar_evidence_id": originals["rule"]["id"]})
        ).status_code == 422
    denied = await post(body)
    assert denied.status_code == 409, denied.text
    originals["calendar"] = await approve(c, h, reviewer[0], audit_base, originals["calendar"])
    created = await post(body)
    assert created.status_code == 201, created.text
    obj = created.json()
    assert obj["body"]["deadline"] == expected
    staged = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "under_review"},
    )
    assert staged.status_code == 200, staged.text
    obj = await approve(c, h, reviewer[0], base, staged.json())
    advanced = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=reviewer[0],
        json={"version": obj["version"], "stage": "approved_for_submission"},
    )
    assert advanced.status_code == 200, advanced.text
    obj = advanced.json()
    retained = deepcopy(obj["body"])
    await action(c, reviewer[0], audit_base, originals["calendar"], "reopen")
    unchanged = (await c.get(audit_base + f"/records/{obj['id']}", headers=h)).json()
    assert unchanged["body"] == retained
    calendar = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert calendar.status_code == 200, calendar.text
    assert calendar.json()["items"][0]["freshness"] == "STALE"
    assert calendar.json()["items"][0]["deadline"] == expected
    assert calendar.json()["items"][0]["reassessment_required"] is True
    denied = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={
            "version": obj["version"],
            "stage": "submitted",
            "submission_evidence_id": originals["readiness"]["id"],
        },
    )
    assert denied.status_code == 409, denied.text
