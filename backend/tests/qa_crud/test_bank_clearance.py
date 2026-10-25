"""Retained schedules and independent approval of subsequent bank clearance."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_bank_clearance import population

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_subsequent_clearance_retained_sources_independent_review(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "bank-clearance-reviewer")
    await grant(c, h, base, reviewer)
    p = population(currency)
    p["allocations"][0]["amount"] = "100"
    selected = {}
    for role, kind in [
        ("outstanding", "bank-outstanding"),
        ("statement", "transactions"),
        ("allocations", "bank-clearances"),
    ]:
        imported = await source(
            c,
            h,
            eid,
            p[role],
            "SYNTHETIC " + role,
            table_type=kind,
            totals={currency: "100" if role == "allocations" else "-100"},
        )
        assert (await decision(c, h, eid, imported)).status_code == 403
        response = await decision(c, reviewer[0], eid, imported)
        assert response.status_code == 201, response.text
        selected[role] = response.json()["id"]
    payload = {
        "workflow": "bank-subsequent-clearance",
        "source_ids": selected,
        "account": "BANK-1",
        "currency": currency,
        "as_of": "2026-06-30",
        "review_through": "2026-07-31",
        "title": "SYNTHETIC subsequent cheque clearance",
        "rationale": "Retained reporting-date outstanding cheque explicitly allocated to later bank evidence",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["exception_count"] == 0
    assert result["body"]["reporting_date_population_changed"] is False
    assert result["body"]["rows"][0]["reporting_date_amount"] == "-100"
    assert result["body"]["rows"][0]["remaining_after_review"] == "0"
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{approved.json()['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "review_through": "2026-07-01"},
        failed="review window",
    )


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_reviewed_brs_bridge_keeps_original_lineage_and_recursive_staleness(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "brs-outstanding-reviewer")
    await grant(c, h, base, reviewer)
    common = {
        "id": "MATCH",
        "account": "BANK-1",
        "currency": currency,
        "date": "2026-06-10",
        "reference": "SYN-MATCH",
        "amount": "50",
        "counterparty": "",
    }
    outstanding = {
        **common,
        "id": "O1",
        "reference": "SYN-CHEQUE",
        "date": "2026-06-20",
        "amount": "-100",
    }
    books = await source(
        c, h, eid, [common, outstanding], "SYNTHETIC original cashbook", totals={currency: "-50"}
    )
    statement = await source(
        c,
        h,
        eid,
        [{**common, "id": "BANK-MATCH"}],
        "SYNTHETIC original bank",
        totals={currency: "50"},
    )
    reviewed_sources = []
    for imported in (books, statement):
        response = await decision(c, reviewer[0], eid, imported)
        assert response.status_code == 201, response.text
        reviewed_sources.append(response.json())
    books, statement = reviewed_sources
    brs = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(
            books, statement, currency=currency, book_closing="-50", statement_closing="50"
        ),
    )
    assert not brs["body"]["blocked"] and brs["body"]["exception_count"] == 1
    url = f"/api/v1/intelligence/engagements/{eid}/events/{brs['id']}/bank-outstanding-source"
    payload = {
        "exception_ids": ["books:O1"],
        "expected_rows": 1,
        "signed_total": "-100",
        "label": "SYNTHETIC selected BRS outstanding",
        "assessment": "Original reporting-date cheque selected for later clearance evidence assessment",
    }
    assert (await c.post(url, headers=h, json=payload)).status_code == 409
    disposition = await decision(c, h, eid, brs, action="accept", item_id="books:O1")
    assert disposition.status_code == 201, disposition.text
    reviewed_brs = await decision(c, reviewer[0], eid, disposition.json())
    assert reviewed_brs.status_code == 201, reviewed_brs.text
    url = f"/api/v1/intelligence/engagements/{eid}/events/{reviewed_brs.json()['id']}/bank-outstanding-source"
    wrong = await c.post(url, headers=h, json={**payload, "signed_total": "100"})
    assert wrong.status_code == 422, wrong.text
    created = await c.post(url, headers=h, json=payload)
    assert created.status_code == 201, created.text
    bridge = created.json()
    assert bridge["body"]["rows"][0]["source_book_row_id"] == "O1"
    assert (
        bridge["body"]["native_metadata"]["clearance_status"] == "NOT_DETERMINED_BY_BRS_EXCEPTION"
    )
    assert any(dep["id"] == reviewed_brs.json()["id"] for dep in bridge["dependencies"])
    assert (await decision(c, h, eid, bridge)).status_code == 403
    approved = await decision(c, reviewer[0], eid, bridge)
    assert approved.status_code == 201, approved.text
    later = population(currency)
    later["allocations"][0].update(outstanding_id="books:O1", amount="100")
    inputs = {"outstanding": approved.json()["id"]}
    for role, kind in [("statement", "transactions"), ("allocations", "bank-clearances")]:
        imported = await source(
            c,
            h,
            eid,
            later[role],
            "SYNTHETIC later " + role,
            table_type=kind,
            totals={currency: "100" if role == "allocations" else "-100"},
        )
        response = await decision(c, reviewer[0], eid, imported)
        assert response.status_code == 201, response.text
        inputs[role] = response.json()["id"]
    output = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "bank-subsequent-clearance",
            "source_ids": inputs,
            "account": "BANK-1",
            "currency": currency,
            "as_of": "2026-06-30",
            "review_through": "2026-07-31",
            "title": "SYNTHETIC reviewed BRS to clearance",
            "rationale": "Original retained BRS population explicitly cleared against later bank evidence",
        },
    )
    assert output["body"]["exception_count"] == 0
    assert output["body"]["rows"][0]["reporting_date_amount"] == "-100"
    from app.core import operations_contracts

    events = (approved.json(), output)
    for event in events:
        assert (
            event["body"]["operations_execution"]["implementation_scope"] == "country-workflows/1"
        )
    with monkeypatch.context() as rollout:
        rollout.setattr(
            operations_contracts,
            "country_workflow_hash",
            lambda: "synthetic-country-reader-upgrade",
        )
        for event in events:
            response = await c.get(
                f"/api/v1/intelligence/engagements/{eid}/events/{event['id']}", headers=h
            )
            assert response.json()["freshness"] == "STALE"
        denied = await c.post(url, headers=h, json=payload)
        assert denied.status_code == 409, denied.text
    for event in events:
        response = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{event['id']}", headers=h
        )
        assert response.json()["freshness"] == "CURRENT"
    rejected = await decision(c, reviewer[0], eid, books, action="reject")
    assert rejected.status_code == 201, rejected.text
    for event in (approved.json(), output):
        response = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{event['id']}", headers=h
        )
        assert response.json()["freshness"] == "STALE"
