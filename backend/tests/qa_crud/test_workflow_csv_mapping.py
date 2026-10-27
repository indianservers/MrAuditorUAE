import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.unit.test_workflow_csv_mapping import CONTENT, SPLIT, options, split_options

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database required"
)


async def test_original_mapped_csv_retention_review_and_export(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("SYNTHETIC-original-export.csv", CONTENT, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    payload = options(evidence_version_id=upload.json()["id"]).model_dump(mode="json")
    prepared = await execute(c, h, eid, "workflow-source", payload)
    body = prepared["body"]
    assert body["csv_mapping"]["original_headers"][0] == "رقم"
    assert body["csv_mapping"]["ignored_columns"] == ["Description"]
    assert body["rows"][0]["amount"] == "100.25"
    original = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + upload.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == CONTENT
    reviewer = await actor(h, "Firm Administrator", "csv-mapping-reviewer")
    await grant(c, h, base, reviewer)
    reviewed = await decision(c, reviewer[0], eid, prepared)
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()["body"]["csv_mapping"] == body["csv_mapping"]
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content), read_only=True)
    try:
        values = [
            str(value)
            for sheet in workbook
            for row in sheet.values
            for value in row
            if value is not None
        ]
        assert any("csv_mapping" in value for value in values)
        assert any("Description" in value for value in values)
    finally:
        workbook.close()
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {**payload, "ignored_columns": [], "label": "Synthetic rejected unmapped export"},
        failed="map or explicitly exclude",
    )


async def test_explicit_debit_credit_csv_reconciles_with_independent_books(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("SYNTHETIC-split-columns.csv", SPLIT, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    request = split_options().model_dump(mode="json")
    request["evidence_version_id"] = upload.json()["id"]
    statement = await execute(c, h, eid, "workflow-source", request)
    assert statement["body"]["csv_mapping"]["amount_derivation"] == "debit-positive"
    assert [row["amount"] for row in statement["body"]["rows"]] == ["100.25", "-5"]
    books = await source(
        c,
        h,
        eid,
        [
            {
                "id": "BOOK-1",
                "account": "BANK-1",
                "date": "2026-06-30",
                "currency": "AED",
                "amount": "100.25",
                "reference": "REF-1",
            },
            {
                "id": "BOOK-2",
                "account": "BANK-1",
                "date": "2026-06-30",
                "currency": "AED",
                "amount": "-5",
                "reference": "REF-2",
            },
        ],
        "Synthetic independently prepared cashbook",
        "transactions",
        {"AED": "95.25"},
    )
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(books, statement, book_closing="95.25", statement_closing="95.25"),
    )
    assert result["body"]["exception_count"] == 0 and not result["body"]["blocked"]
