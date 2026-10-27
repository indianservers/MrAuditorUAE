"""Retained value-only workbook sources with real DB/storage and scanner/broker doubles."""

import hashlib
import io
import os
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_generic_candidates import context
from tests.unit.test_workflow_workbook import SAMPLES, workbook

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned database")


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("kind", ["transactions", "tax-documents", "stock", "obligations"])
async def test_retained_workbook_source_review_export_and_consumption(
    environment, monkeypatch, country, kind
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await context(c, country)
    row = dict(SAMPLES[kind][0], currency="AED" if country == "AE" else "INR")
    if kind == "tax-documents" and country == "IN":
        row["component"] = "CGST"
    original = workbook(list(row), [list(row.values())], extra_sheet=True)
    record = await create(
        c, h, audit, "evidence", dict(category="Other", retain_until="2036-12-31")
    )
    uploaded = await c.post(
        audit + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-population.xlsx",
                original,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    field = "amount" if "amount" in row else "tax" if "tax" in row else None
    totals = {row["currency"]: str(Decimal(row[field]))} if field else {}
    result = await execute(
        c,
        h,
        eid,
        "workflow-source",
        dict(
            evidence_version_id=uploaded.json()["id"],
            table_type=kind,
            label=f"SYNTHETIC {country} {kind} workbook",
            expected_rows=1,
            control_totals=totals,
            workbook_sheet="Population",
            workbook_assessment="Assessed selected worksheet and excluded supporting sheet",
        ),
    )
    body = result["body"]
    assert body["parser_version"] == "country-workbook-1"
    assert body["workbook_metadata"]["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert body["workbook_metadata"]["unselected_worksheets"] == ["Excluded"]
    assert body["rows"][0]["source_row"] == 2
    assert body["rows"][0]["source_worksheet"] == "Population"
    assert (await decision(c, h, eid, result)).status_code == 403
    reviewer = await actor(h, "Firm Administrator", f"workbook-reviewer-{country}-{kind}")
    await grant(c, h, audit, reviewer)
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    result = approved.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    book = load_workbook(io.BytesIO(exported.content), read_only=True)
    try:
        rows = list(book["Rows"].values)
        assert len(rows) == 2
        assert "source_worksheet" in rows[0] and "source_row" in rows[0]
    finally:
        book.close()
    downloaded = await c.get(
        audit + f"/evidence-files/{record['id']}/{uploaded.json()['id']}/download", headers=h
    )
    assert downloaded.status_code == 200 and downloaded.content == original
    if kind == "transactions":
        refused = await c.post(
            f"/api/v1/intelligence/engagements/{eid}/jobs",
            headers=h,
            json={
                "operation": "country-workflow",
                "payload": bank_payload(result, result, currency=row["currency"]),
            },
        )
        assert refused.status_code == 422
        statement = await source(
            c, h, eid, [dict(row, id="S1")], "SYNTHETIC independent bank CSV", totals=totals
        )
        approved_statement = await decision(c, reviewer[0], eid, statement)
        assert approved_statement.status_code == 201, approved_statement.text
        reconciled = await execute(
            c,
            h,
            eid,
            "country-workflow",
            bank_payload(result, approved_statement.json(), currency=row["currency"]),
        )
        assert reconciled["collection_totals"]["matches"] == 1
        assert reconciled["body"]["exception_count"] == 0
