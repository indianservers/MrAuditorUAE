"""Contribution review to independently controlled bank settlement in both countries."""

import json
import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, execute, source
from tests.qa_crud.test_payroll_rule_workflow import prepared as india_prepared
from tests.qa_crud.test_pension_workflow import prepared as pension_prepared
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_contribution_source import request
from tests.unit.test_payroll_rule_workflow import pf_fixture
from tests.unit.test_pension_workflow import pension_fixture, scope

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_reviewed_contributions_to_bank_allocations_with_independent_due_dates(
    environment, monkeypatch, country
):
    c = environment
    prepared = await (
        pension_prepared(c, monkeypatch) if country == "AE" else india_prepared(c, monkeypatch)
    )
    h, eid, base, reviewer, _, _, _, payload, _ = prepared
    for role, identifier in payload["source_ids"].items():
        item = await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{identifier}", headers=h)
        reviewed = await decision(c, reviewer[0], eid, item.json())
        assert reviewed.status_code == 201, reviewed.text
        payload["source_ids"][role] = reviewed.json()["id"]
    result = await execute(c, h, eid, "country-workflow", payload)
    final = await actor(h, "Firm Administrator", "contribution-settlement-final")
    await grant(c, h, base, final)
    due_record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    document = await c.post(
        base + "/evidence-files/" + due_record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-due-date-reference.txt",
                b"SYNTHETIC: assessed remittance due 15 July 2026",
                "text/plain",
            )
        },
    )
    assert document.status_code == 201, document.text
    data = request(country).model_dump(mode="json")
    data.update(result_id=result["id"], due_date_evidence_version_id=document.json()["id"])
    endpoint = f"/api/v1/intelligence/engagements/{eid}/contribution-obligation-source"
    assert (await c.post(endpoint, headers=h, json=data)).status_code == 409
    parent = await decision(c, final[0], eid, result)
    assert parent.status_code == 201, parent.text
    data["result_id"] = parent.json()["id"]
    wrong = {**data, "groups": [{**data["groups"][0], "amount": "1"}, *data["groups"][1:]]}
    assert (await c.post(endpoint, headers=h, json=wrong)).status_code == 422
    response = await c.post(endpoint, headers=h, json=data)
    assert response.status_code == 201, response.text
    expected = response.json()
    assert expected["body"]["review_status"] == "UNVERIFIED"
    assert expected["body"]["allowed_source_roles"] == ["expected"]
    total, currency = ("2200.00", "AED") if country == "AE" else ("3600", "INR")
    assert expected["body"]["control_totals"] == {currency: total}
    assert len(expected["body"]["rows"]) == (2 if country == "AE" else 3)
    assert all(row["payment_date"] is None for row in expected["body"]["rows"])
    assert (await decision(c, h, eid, expected)).status_code == 403
    if country == "AE":
        reported = [
            {
                key: row[key]
                for key in (
                    "id",
                    "registration",
                    "subject",
                    "period",
                    "component",
                    "currency",
                    "amount",
                )
            }
            for row in pension_fixture()[2]
            if row["component"] != "PENSION:GOVERNMENT"
        ]
        for row in reported:
            row["pension_scope"] = json.dumps(scope())
    else:
        reported = pf_fixture()[2]
    declared = await source(
        c,
        h,
        eid,
        reported,
        "SYNTHETIC independent remittance return",
        "obligations",
        {currency: total},
    )
    bank = await source(
        c,
        h,
        eid,
        [transaction(id="B1", amount="-" + total, date="2026-07-15", currency=currency)],
        "SYNTHETIC bank contribution outflow",
        "transactions",
        {currency: "-" + total},
    )
    by_component = {row["component"]: row["id"] for row in expected["body"]["rows"]}
    links = [
        dict(
            id="A" + str(index),
            expected_id=by_component[row["component"]],
            reported_id=row["id"],
            transaction_id="B1",
            currency=currency,
            amount=row["amount"],
            evidence_reference="SYNTHETIC-REMITTANCE-ADVICE",
            rationale="Independently assessed person and contribution component allocation",
        )
        for index, row in enumerate(reported)
    ]
    allocations = await source(
        c,
        h,
        eid,
        links,
        "SYNTHETIC contribution bank links",
        "obligation-allocations",
        {currency: total},
    )
    ids = {"expected": expected["id"]}
    for role, item in (("reported", declared), ("bank", bank), ("allocations", allocations)):
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        ids[role] = reviewed.json()["id"]
    settlement = dict(
        workflow="obligation-bank-allocations",
        source_ids=ids,
        as_of="2026-07-31",
        title="SYNTHETIC controlled contribution remittance",
        rationale="Independently controlled contributions, authority return, deadline support and bank allocation",
        currency=currency,
        account="BANK-1",
        obligation_month_start="2026-06",
        obligation_month_end="2026-06",
        settlement_start="2026-07-01",
        bank_payment_sign="debit-negative",
    )
    another = await c.post(
        endpoint,
        headers=h,
        json={**data, "label": "Synthetic second expected source, not a return"},
    )
    assert another.status_code == 201, another.text
    another_review = await decision(c, reviewer[0], eid, another.json())
    assert another_review.status_code == 201, another_review.text
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        settlement,
        failed="Independently review derived contribution",
    )
    reviewed = await decision(c, reviewer[0], eid, expected)
    assert reviewed.status_code == 201, reviewed.text
    ids["expected"] = reviewed.json()["id"]
    compared = await execute(c, h, eid, "country-workflow", settlement)
    assert not compared["body"]["blocked"] and compared["body"]["exception_count"] == 0
    assert compared["body"]["allocation_controls"]["outstanding_expected"] in {"0", "0.00"}
    approved = await decision(c, final[0], eid, compared)
    assert approved.status_code == 201, approved.text
    event_path = f"/api/v1/intelligence/engagements/{eid}/events/{approved.json()['id']}"
    exported = await c.get(event_path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**settlement, "source_ids": {**ids, "reported": another_review.json()["id"]}},
        failed="only expected remittances",
    )
    changed = await c.post(
        base + "/evidence-files/" + due_record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-due-date-correction.txt",
                b"SYNTHETIC corrected deadline assessment",
                "text/plain",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    for saved in (reviewed.json(), approved.json()):
        history = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}", headers=h
        )
        assert (
            history.json()["freshness"] == "STALE" and history.json()["sha256"] == saved["sha256"]
        )
    parent_history = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{parent.json()['id']}", headers=h
    )
    assert parent_history.json()["freshness"] == "CURRENT"
