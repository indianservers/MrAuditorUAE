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
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import transaction
from tests.unit.pdf_bank_example import layout, statement

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_retained_pdf_grid_review_bridge_controls_export_and_staleness(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    uploader = await actor(h, "Firm Administrator", "pdf-statement-uploader")
    reviewer = await actor(h, "Firm Administrator", "pdf-table-reviewer")
    final = await actor(h, "Firm Administrator", "pdf-bridge-reviewer")
    for person in (uploader, reviewer, final):
        await grant(c, h, base, person)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    original = statement(currency)
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=uploader[0],
        files={"file": ("SYNTHETIC-bank-grid.pdf", original, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "table_type": "transactions",
            "label": "Synthetic unreviewed PDF cannot be canonical CSV",
            "expected_rows": 2,
            "control_totals": {currency: "95.25"},
        },
        failed="media type",
    )
    table = await execute(
        c,
        h,
        eid,
        "source-table",
        {
            "evidence_version_id": uploaded.json()["id"],
            "table_kind": "bank",
            "pdf_layout": layout(currency),
        },
    )
    assert table["body"]["table_metadata"]["source_format"] == "PDF_TEXT_GRID"
    assert [r["amount"] for r in table["body"]["rows"]] == ["100.25", "-5"]
    assert (await decision(c, uploader[0], eid, table)).status_code == 403
    approved = await decision(c, reviewer[0], eid, table)
    assert approved.status_code == 201, approved.text
    prepared = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "supporting_table_id": approved.json()["id"],
            "evidence_version_id": uploaded.json()["id"],
            "supporting_scope_assessment": "Reviewed every selected row and PDF page header against account scope and independent totals",
            "account_identifier": "BANK-1",
            "table_type": "transactions",
            "expected_rows": 2,
            "control_totals": {currency: "95.25"},
            "label": "Synthetic reviewed PDF bank population",
        },
    )
    assert prepared["body"]["rows"][0]["supporting_source_page"] == 1
    assert prepared["body"]["rows"][0]["supporting_source_pdf_cells"]["credit"] == "100.25"
    assert (await decision(c, reviewer[0], eid, prepared)).status_code == 403
    reviewed = await decision(c, final[0], eid, prepared)
    assert reviewed.status_code == 201, reviewed.text
    books = await source(
        c,
        h,
        eid,
        [
            transaction(
                id="B1",
                reference="REF-1",
                date="2026-06-30",
                amount="100.25",
                currency=currency,
                counterparty="SYN-CLIENT",
            ),
            transaction(
                id="B2",
                reference="REF-2",
                date="2026-06-30",
                amount="-5",
                currency=currency,
                counterparty="SYN-CLIENT",
            ),
        ],
        "Synthetic independent PDF cashbook",
        totals={currency: "95.25"},
    )
    book_review = await decision(c, final[0], eid, books)
    assert book_review.status_code == 201, book_review.text
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(
            book_review.json(),
            reviewed.json(),
            book_closing="95.25",
            statement_closing="95.25",
            currency=currency,
        ),
    )
    assert result["body"]["exception_count"] == 0 and not result["body"]["blocked"]
    assert (await decision(c, uploader[0], eid, result)).status_code == 403
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    preview = await c.get(f"{prefix}/evidence/{uploaded.json()['id']}/preview?page=1", headers=h)
    assert preview.status_code == 200 and preview.content.startswith(b"\x89PNG")
    export = await c.get(f"{prefix}/events/{reviewed.json()['id']}/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    workbook = load_workbook(io.BytesIO(export.content))
    headings = [cell.value for cell in workbook["Rows"][1]]
    assert "supporting_source_pdf_cells" in headings and "supporting_source_page" in headings
    downloaded = await c.get(
        base + f"/evidence-files/{record['id']}/{uploaded.json()['id']}/download", headers=h
    )
    assert downloaded.status_code == 200 and downloaded.content == original
    replacement = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-bank-grid-v2.pdf", original + b"\n", "application/pdf")},
    )
    assert replacement.status_code == 201, replacement.text
    for identifier in (approved.json()["id"], reviewed.json()["id"], result["id"]):
        detail = await c.get(f"{prefix}/events/{identifier}", headers=h)
        assert detail.status_code == 200 and detail.json()["freshness"] == "STALE"
