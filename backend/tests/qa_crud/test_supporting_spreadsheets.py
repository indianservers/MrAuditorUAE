import io
import os
from datetime import datetime

import pytest
from openpyxl import Workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


@pytest.mark.parametrize("kind", ["bank", "open-items"])
async def test_reviewed_xlsx_table_reuses_original_evidence_and_selected_sheet(
    environment, monkeypatch, kind
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    book = Workbook()
    sheet = book.active
    sheet.title = "Selected"
    if kind == "bank":
        sheet.append(["reference", "currency", "amount", "date", "account_code"])
        sheet.append(["REF-1", "AED", 10.5, datetime(2026, 6, 30), "ACCOUNT-1"])
    else:
        sheet.append(
            [
                "reference",
                "currency",
                "open_amount",
                "counterparty",
                "document_type",
                "document_date",
                "due_date",
                "account_code",
            ]
        )
        sheet.append(
            [
                "INV-1",
                "AED",
                10.5,
                "SYNTHETIC-PARTY",
                "invoice",
                datetime(2026, 6, 1),
                datetime(2026, 6, 30),
                "ACCOUNT-1",
            ]
        )
    sheet.row_dimensions[2].hidden = True  # Hidden rows remain part of the population.
    book.create_sheet("Other")
    buffer = io.BytesIO()
    book.save(buffer)
    book.close()
    content = buffer.getvalue()
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-supporting.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    request = {
        "evidence_version_id": uploaded.json()["id"],
        "table_kind": kind,
        "decimal_separator": ",",
        "date_format": "dmy",
    }
    await execute(c, h, eid, "source-table", request, failed="explicitly select")
    table = await execute(c, h, eid, "source-table", {**request, "worksheet": "Selected"})
    assert table["body"]["row_count"] == 1
    assert table["body"]["table_metadata"]["worksheet"] == "Selected"
    assert table["body"]["table_metadata"]["unselected_worksheets"] == ["Other"]
    assert (
        table["body"]["table_metadata"]["numeric_basis"]
        == "ORIGINAL_XML_DECIMALS_NOT_FLOAT_ROUNDTRIP"
    )
    reviewer = await actor(h, "Firm Administrator", "spreadsheet-reviewer")
    await grant(c, h, base, reviewer)
    reviewed = await decision(c, reviewer[0], eid, table)
    assert reviewed.status_code == 201, reviewed.text
    payload = {
        "evidence_version_id": uploaded.json()["id"],
        "supporting_table_id": reviewed.json()["id"],
        "supporting_scope_assessment": "Reviewed all rows of Selected worksheet including hidden rows and account evidence",
        "account_identifier": "ACCOUNT-1",
        "table_type": "transactions" if kind == "bank" else "audit-open-items",
        "expected_rows": 1,
        "control_totals": {"AED": "10.5"},
        "label": "Synthetic spreadsheet bridge",
    }
    if kind == "open-items":
        payload.update(supporting_side="receivable", supporting_balance_date="2026-06-30")
    result = await execute(c, h, eid, "workflow-source", payload)
    assert result["body"]["rows"][0]["amount"] == "10.5"
    assert result["body"]["rows"][0]["supporting_source_worksheet"] == "Selected"
    assert result["body"]["supporting_table_metadata"]["source_format"] == "XLSX"
    original = await c.get(
        base + "/evidence-files/" + record["id"] + "/" + uploaded.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == content
