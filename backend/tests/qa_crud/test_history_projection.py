"""Real history payload equality, SQL work and next-request revocation/staleness."""

import os
from contextlib import nullcontext

import pytest
from sqlalchemy import event

from app.core import read_projection as views
from app.db.session import engine
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    csv_bytes,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


async def test_history_same_results_less_sql_and_no_cross_request_permission_or_freshness_cache(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "history-reviewer")
    await grant(c, h, base, reviewer)
    book = await source(c, h, eid, [transaction(id="BOOK")], "SYNTHETIC history books")
    statement = await source(c, h, eid, [transaction(id="BANK")], "SYNTHETIC history statement")
    approved = []
    for item in (book, statement):
        value = await decision(c, reviewer[0], eid, item)
        assert value.status_code == 201, value.text
        approved.append(value.json())
    for index in range(12):
        result = await execute(
            c,
            h,
            eid,
            "country-workflow",
            {**bank_payload(*approved), "title": f"SYNTHETIC shared history {index}"},
        )
        value = await decision(c, reviewer[0], eid, result)
        assert value.status_code == 201, value.text
    path = f"/api/v1/intelligence/engagements/{eid}/events?limit=100&newest=true"

    async def counted():
        count = 0

        def query(*args):
            nonlocal count
            count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", query)
        try:
            response = await c.get(path, headers=h)
            assert response.status_code == 200, response.text
            return response.json(), count
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", query)

    optimized, reused_queries = await counted()
    with monkeypatch.context() as disabled:
        disabled.setattr(views, "read_projection", lambda *args: nullcontext())
        reference, reference_queries = await counted()
    assert optimized == reference
    assert {row["freshness"] for row in optimized["items"]} == {"CURRENT", "STALE"}
    assert reused_queries < reference_queries / 2, (reused_queries, reference_queries)

    limited = await actor(h, "Audit Manager", "history-limited-reader")
    permissions_url = "/api/v1/admin/roles/" + limited[2] + "/permissions"
    assigned = await c.post(
        permissions_url,
        headers=h,
        json={"permissions": ["audit.read", "accounting.read", "engagements.read"]},
    )
    assert assigned.status_code == 200, assigned.text
    await grant(c, h, base, limited)
    assert (await c.get(path, headers=limited[0])).json()["items"]
    revoked = await c.post(
        permissions_url, headers=h, json={"permissions": ["audit.read", "engagements.read"]}
    )
    assert revoked.status_code == 200, revoked.text
    hidden = await c.get(path, headers=limited[0])
    assert hidden.status_code == 200 and hidden.json()["items"] == []
    assert (await c.get(path, headers=h)).json()["items"]
    # A new evidence version invalidates every dependent review on the next
    # request even though the process and access token are unchanged.
    receipt = next(item for item in book["dependencies"] if item["type"] == "evidence")
    replaced = await c.post(
        base + "/evidence-files/" + receipt["record_id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC changed history books.csv",
                csv_bytes([transaction(id="BOOK", amount="101")]),
                "text/csv",
            )
        },
    )
    assert replaced.status_code == 201, replaced.text
    changed = await c.get(path, headers=h)
    assert changed.status_code == 200, changed.text
    dependent = [row for row in changed.json()["items"] if row["kind"] == "country-workflow"]
    assert dependent and all(row["freshness"] == "STALE" for row in dependent)
    fresh_book = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": replaced.json()["id"],
            "table_type": "transactions",
            "label": "SYNTHETIC updated history books",
            "expected_rows": 1,
            "control_totals": {"AED": "101"},
        },
    )
    fresh_approval = await decision(c, reviewer[0], eid, fresh_book)
    assert fresh_approval.status_code == 201, fresh_approval.text
    new_result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(fresh_approval.json(), approved[1], book_closing="101"),
    )
    before_head_change = (await c.get(path, headers=h)).json()["items"]
    assert (
        next(row for row in before_head_change if row["id"] == new_result["id"])["freshness"]
        == "CURRENT"
    )
    rereviewed = await decision(c, reviewer[0], eid, fresh_approval.json())
    assert rereviewed.status_code == 201, rereviewed.text
    after_head_change = (await c.get(path, headers=h)).json()["items"]
    assert (
        next(row for row in after_head_change if row["id"] == new_result["id"])["freshness"]
        == "STALE"
    )
