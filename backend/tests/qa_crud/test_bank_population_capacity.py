"""Actual bounded CSV/storage/review/matching/export path, not a load qualification."""

import io
import json
import os
import time
from contextlib import closing

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_generic_candidates import context
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_full_csv_population_survives_review_pagination_and_export(
    environment, monkeypatch, country, record_property
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await context(c, country)
    reviewer = await actor(h, "Firm Administrator", f"population-reviewer-{country}")
    await grant(c, h, audit, reviewer)
    currency = "AED" if country == "AE" else "INR"
    count = 5000
    party = "SYNTHETIC شركة ألف" if country == "AE" else "SYNTHETIC भारत आपूर्तिकर्ता"
    timings = {}
    started = time.perf_counter()
    sources = {}
    for role, prefix in (("books", "L"), ("statement", "R")):
        phase = time.perf_counter()
        # Equal amounts exercise the reference index rather than an amount shortcut.
        rows = [
            transaction(
                id=f"{prefix}{i:05}",
                reference=f"SYNTHETIC-{i:05}",
                amount="1",
                currency=currency,
                counterparty=party,
            )
            for i in range(count)
        ]
        event = await source(
            c,
            h,
            eid,
            rows,
            f"SYNTHETIC {country} {role} full CSV bound",
            totals={currency: str(count)},
        )
        assert event["collection_totals"]["rows"] == count
        approved = await decision(c, reviewer[0], eid, event)
        assert approved.status_code == 201, approved.text
        sources[role] = approved.json()
        path = f"/api/v1/intelligence/engagements/{eid}/events/{event['id']}"
        tail = await c.get(path, headers=h, params={"offset": 4900, "limit": 100})
        assert tail.status_code == 200, tail.text
        actual = tail.json()["body"]["rows"]
        assert [r["id"] for r in actual] == [f"{prefix}{i:05}" for i in range(4900, count)]
        assert all(r["counterparty"] == party and r["currency"] == currency for r in actual)
        timings[f"{role}_upload_parse_review_tail_seconds"] = time.perf_counter() - phase
    phase = time.perf_counter()
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(
            sources["books"],
            sources["statement"],
            currency=currency,
            book_closing=str(count),
            statement_closing=str(count),
        ),
    )
    assert result["freshness"] == "CURRENT"
    assert result["collection_totals"]["matches"] == count
    assert result["body"]["exception_count"] == 0 and not result["body"]["blocked"]
    assert result["body"]["control_comparison"]["unexplained_bridge_residual"] == "0"
    timings["reconciliation_seconds"] = time.perf_counter() - phase
    path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    phase = time.perf_counter()
    observed = []
    for offset in range(0, count, 500):
        response = await c.get(path, headers=h, params={"offset": offset, "limit": 500})
        assert response.status_code == 200, response.text
        assert response.json()["collection_totals"]["matches"] == count
        observed.extend(response.json()["body"]["matches"])
    expected = {(f"L{i:05}", f"R{i:05}") for i in range(count)}
    assert len(observed) == count
    assert {(m["left_ids"][0], m["right_ids"][0]) for m in observed} == expected
    timings["all_match_pages_seconds"] = time.perf_counter() - phase
    phase = time.perf_counter()
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    with closing(load_workbook(io.BytesIO(exported.content), read_only=True)) as workbook:
        values = list(workbook["Matched proposals"].values)
        assert values[0][:2] == ("left_ids", "right_ids")
        assert len(values) == count + 1
        assert {(json.loads(r[0])[0], json.loads(r[1])[0]) for r in values[1:]} == expected
    timings["export_and_readback_seconds"] = time.perf_counter() - phase
    phase = time.perf_counter()
    # A deliberately understated control must not make the parser truncate input.
    excessive = [
        transaction(id=f"X{i:05}", currency=currency, amount="1") for i in range(count + 1)
    ]
    await source(
        c,
        h,
        eid,
        excessive,
        f"SYNTHETIC {country} rejected over-bound CSV",
        totals={currency: str(count)},
        expected_rows=count,
        failed="5,000-row bound exceeded",
    )
    timings["over_bound_rejection_seconds"] = time.perf_counter() - phase
    timings["total_seconds"] = time.perf_counter() - started
    record_property("synthetic", "true")
    record_property("rows_per_source", count)
    record_property("phase_timings", json.dumps(timings, sort_keys=True))
