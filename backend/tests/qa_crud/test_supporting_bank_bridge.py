import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    csv_bytes,
    decision,
    double_boundaries,
    execute,
    source,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_reviewed_bank_table_bridge_retains_evidence_reviewers_controls_and_staleness(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    original = csv_bytes(
        [
            {
                "reference": "REF-1",
                "currency": "AED",
                "amount": "100,25",
                "date": "30/06/2026",
                "account_code": "BANK-1",
            }
        ]
    )
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-reviewed-bank.csv", original, "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    table = await execute(
        c,
        h,
        eid,
        "source-table",
        {
            "evidence_version_id": uploaded.json()["id"],
            "table_kind": "bank",
            "date_format": "dmy",
            "decimal_separator": ",",
        },
    )
    payload = {
        "evidence_version_id": uploaded.json()["id"],
        "supporting_table_id": table["id"],
        "supporting_scope_assessment": "Reviewed original statement and all rows as the BANK-1 population",
        "account_identifier": "BANK-1",
        "table_type": "transactions",
        "label": "Synthetic supporting bank bridge",
        "expected_rows": 1,
        "control_totals": {"AED": "100.25"},
    }
    await execute(c, h, eid, "workflow-source", payload, failed="independently reviewed")
    reviewer = await actor(h, "Firm Administrator", "supporting-table-reviewer")
    await grant(c, h, base, reviewer)
    approved = await decision(c, reviewer[0], eid, table)
    assert approved.status_code == 201, approved.text
    payload["supporting_table_id"] = approved.json()["id"]
    prepared = await execute(c, h, eid, "workflow-source", payload)
    row = prepared["body"]["rows"][0]
    assert row["amount"] == "100.25" and row["date"] == "2026-06-30"
    assert row["supporting_source_row"] == 2
    assert any(
        dep["type"] == "event" and dep["id"] == approved.json()["id"]
        for dep in prepared["dependencies"]
    )
    assert (await decision(c, reviewer[0], eid, prepared)).status_code == 403
    downloaded = await c.get(
        base + "/evidence-files/" + record["id"] + "/" + uploaded.json()["id"] + "/download",
        headers=h,
    )
    assert downloaded.status_code == 200 and downloaded.content == original
    books = await source(
        c,
        h,
        eid,
        [
            {
                "id": "BOOK-1",
                "account": "BANK-1",
                "reference": "REF-1",
                "currency": "AED",
                "amount": "100.25",
                "date": "2026-06-30",
            }
        ],
        "Synthetic independent bridge cashbook",
        "transactions",
        {"AED": "100.25"},
    )
    reconciled = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(books, prepared, book_closing="100.25", statement_closing="100.25"),
    )
    assert reconciled["body"]["exception_count"] == 0 and not reconciled["body"]["blocked"]
    listed = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events?limit=100&newest=true", headers=h
    )
    choice = next(item for item in listed.json()["items"] if item["id"] == approved.json()["id"])
    assert choice["table_kind"] == "bank" and choice["evidence_version_id"] == uploaded.json()["id"]
    for changes, error in [
        ({"expected_rows": 2}, "row-count"),
        ({"account_identifier": "ANOTHER"}, "selected scope"),
    ]:
        await execute(c, h, eid, "workflow-source", {**payload, **changes}, failed=error)
    replaced = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-bank-v2.csv", original + b"\n", "text/csv")},
    )
    assert replaced.status_code == 201, replaced.text
    for identifier in (approved.json()["id"], prepared["id"], reconciled["id"]):
        detail = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{identifier}", headers=h
        )
        assert detail.status_code == 200 and detail.json()["freshness"] == "STALE"
