"""Retained originals, independent review, VAT matching/export and replacement staleness."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import (
    csv_bytes,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_vat_box_scope import full_filed_boxes

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def test_composed_vat201_review_roles_export_and_original_staleness(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "vat-composition-reviewer")
    await grant(c, h, base, reviewer)
    rows = full_filed_boxes()
    components = []
    for index, selected in enumerate(
        (
            [r for r in rows if r["box"] in {"6", "7"}],
            [r for r in rows if r["box"] not in {"6", "7"}],
        )
    ):
        prepared = await source(
            c,
            h,
            eid,
            selected,
            "Synthetic VAT component " + str(index),
            "return-boxes",
            {"AED": "45" if index == 0 else "185"},
        )
        components.append(prepared)
    path = f"/api/v1/intelligence/engagements/{eid}"
    payload = {
        "source_ids": [r["id"] for r in components],
        "taxable_amount": "2400",
        "tax": "230",
        "adjustment": "0",
        "label": "Synthetic composed VAT201 books",
        "assessment": "Independent complete disjoint book schedules; no missing box or filed-return inference",
    }
    denied = await c.post(path + "/vat201-composition-source", headers=h, json=payload)
    assert denied.status_code == 409
    for index, item in enumerate(components):
        approved = await decision(c, reviewer[0], eid, item)
        assert approved.status_code == 201, approved.text
        payload["source_ids"][index] = approved.json()["id"]
    composed = await c.post(path + "/vat201-composition-source", headers=h, json=payload)
    assert composed.status_code == 201, composed.text
    composed = composed.json()
    assert composed["body"]["row_count"] == 14
    assert composed["body"]["allowed_source_roles"] == ["books"]
    assert len(composed["dependencies"]) >= 2
    assert (await decision(c, h, eid, composed)).status_code == 403
    filed = await source(
        c,
        h,
        eid,
        [{**r, "id": "INDEPENDENT-" + r["box"]} for r in rows],
        "Synthetic separately retained filed VAT201",
        "return-boxes",
        {"AED": "230"},
    )
    compare = {
        "workflow": "uae-vat-return",
        "source_ids": {"books": composed["id"], "return": filed["id"]},
        "as_of": "2026-06-30",
        "currency": "AED",
        "required_boxes": [str(i) for i in range(1, 15)],
        "title": "Synthetic composed VAT comparison",
        "rationale": "Compare controlled composed books to separately retained filed evidence",
    }
    await execute(c, h, eid, "country-workflow", compare, failed="review the composed VAT201")
    approved = await decision(c, reviewer[0], eid, composed)
    assert approved.status_code == 201, approved.text
    compare["source_ids"]["books"] = approved.json()["id"]
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **compare,
            "source_ids": {"books": approved.json()["id"], "return": payload["source_ids"][0]},
        },
        failed="share underlying source evidence",
    )
    copied_original = await source(
        c,
        h,
        eid,
        [r for r in rows if r["box"] in {"6", "7"}],
        "Synthetic copied import schedule posing as filed evidence",
        "return-boxes",
        {"AED": "45"},
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **compare,
            "source_ids": {"books": approved.json()["id"], "return": copied_original["id"]},
        },
        failed="share underlying source evidence",
    )
    result = await execute(c, h, eid, "country-workflow", compare)
    assert result["body"]["exception_count"] == 0 and len(result["body"]["rows"]) == 14
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**compare, "source_ids": {"books": filed["id"], "return": approved.json()["id"]}},
        failed="only books",
    )
    export = await c.get(path + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert export.status_code == 200 and export.content[:2] == b"PK"
    original = next(d for d in components[0]["dependencies"] if d["type"] == "evidence")
    replaced = await c.post(
        base + "/evidence-files/" + original["record_id"],
        headers=h,
        files={"file": ("SYNTHETIC-updated-import.csv", csv_bytes([rows[5]]), "text/csv")},
    )
    assert replaced.status_code == 201
    for identifier in (composed["id"], result["id"]):
        stale = await c.get(path + "/events/" + identifier, headers=h)
        assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
    refused = await c.post(path + "/vat201-composition-source", headers=h, json=payload)
    assert refused.status_code == 409


async def test_vat201_composition_is_unavailable_in_india(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, _ = await india_context(c)
    import uuid

    response = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/vat201-composition-source",
        headers=h,
        json={
            "source_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "taxable_amount": "0",
            "tax": "0",
            "adjustment": "0",
            "label": "Synthetic wrong-country request",
            "assessment": "UAE-only domestic composition must not activate in India",
        },
    )
    assert response.status_code == 422 and "UAE engagement" in response.text
