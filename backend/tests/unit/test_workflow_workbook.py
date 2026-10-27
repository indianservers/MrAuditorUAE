import csv
import hashlib
import io
import json
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.modules.country_workflows.catalogue import WORKFLOWS
from app.modules.country_workflows.schemas import SourceInput
from app.modules.country_workflows.sources import parse_csv
from app.modules.country_workflows.workbook_source import parse_workbook
from tests.unit.country_workflow_cases import CASES

SAMPLES = {}
for case in CASES:
    for role, rows in case["sources"].items():
        if rows:
            SAMPLES.setdefault(WORKFLOWS[case["workflow"]][2][role], rows)


def workbook(headers, rows, extra_sheet=False):
    book = Workbook()
    book.active.title = "Population"
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    if extra_sheet:
        book.create_sheet("Excluded")
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def parse(content, data):
    return parse_workbook(content, data, expected_sha256=hashlib.sha256(content).hexdigest())


@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_existing_canonical_populations_survive_workbook_reader(kind):
    rows = SAMPLES[kind]
    fields = list(rows[0])
    values = [
        [json.dumps(row.get(k)) if isinstance(row.get(k), dict) else row.get(k) for k in fields]
        for row in rows
    ]
    totals = {}
    for row in rows:
        field = "amount" if "amount" in row else "tax" if "tax" in row else None
        if field:
            totals[row["currency"]] = totals.get(row["currency"], Decimal(0)) + Decimal(row[field])
    data = SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type=kind,
        label="SYNTHETIC workbook population",
        expected_rows=len(rows),
        control_totals=totals,
        workbook_sheet="Population",
        workbook_assessment="Independently selected synthetic worksheet scope",
        **(
            {
                "document_series_controls": {
                    k: sum(r[k] for r in rows) for k in ("issued", "cancelled", "net_issued")
                }
            }
            if kind == "gst-document-series"
            else {}
        ),
    )
    original = workbook(fields, values, extra_sheet=True)
    actual = parse(original, data)
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(fields)
    writer.writerows(values)
    expected = parse_csv(text.getvalue().encode(), data)
    assert [
        {
            k: v
            for k, v in r.items()
            if k not in {"source_worksheet", "source_row", "source_cell_storage"}
        }
        for r in actual["rows"]
    ] == expected["rows"]
    assert actual["control_totals"] == expected["control_totals"]
    assert actual["workbook_metadata"]["unselected_worksheets"] == ["Excluded"]
    assert actual["review_status"] == "UNVERIFIED"
    assert [r["source_row"] for r in actual["rows"]] == list(range(2, len(rows) + 2))


def data(**changes):
    return SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type="transactions",
        label="SYNTHETIC workbook",
        expected_rows=1,
        control_totals={"AED": "100"},
        workbook_sheet="Population",
        workbook_assessment="Assessed original worksheet population",
        **changes,
    )


HEADERS = ["id", "account", "reference", "date", "currency", "amount", "counterparty"]
ROW = ["L1", "BANK-1", "SYNTHETIC-1", datetime(2026, 6, 1), "AED", 100, "شركة ألف"]


def test_actual_date_numeric_cells_and_physical_row_provenance():
    content = workbook(HEADERS, [[None] * len(HEADERS), ROW])
    result = parse(content, data())
    row = result["rows"][0]
    assert row["date"] == "2026-06-01" and row["amount"] == "100"
    assert row["source_row"] == 3
    assert row["source_cell_storage"] == {"numeric_columns": ["amount"], "date_columns": ["date"]}


def test_physical_row_bound_is_not_bypassed_by_blank_rows():
    content = workbook(HEADERS, [[None] * len(HEADERS)] * 5000 + [ROW])
    with pytest.raises(ValueError, match="physical row bound"):
        parse(content, data())


@pytest.mark.parametrize("changes", [
    {"workbook_assessment": ""}, {"workbook_sheet": None},
    {"file_format": "camt053"}, {"delimiter": ";"},
])
def test_workbook_scope_cannot_be_mixed_or_unassessed(changes):
    values = data().model_dump(mode="json")
    with pytest.raises(ValueError):
        SourceInput.model_validate({**values, **changes})


@pytest.mark.parametrize(
    "bad", ["formula", "time", "extra", "duplicate", "wrong-sheet", "hash", "control"]
)
def test_workbook_refuses_unsafe_or_uncontrolled_population(bad):
    row, fields = list(ROW), list(HEADERS)
    if bad == "formula":
        row[5] = "=50+50"
    if bad == "time":
        row[3] = datetime(2026, 6, 1, 12)
    if bad == "extra":
        fields += ["unassessed"]
        row += ["not ignored"]
    if bad == "duplicate":
        fields[-1] = "id"
    if bad == "wrong-sheet":
        fields = HEADERS
    if bad == "control":
        row[5] = 99
    content = workbook(fields, [row])
    options = (
        data().model_copy(update={"workbook_sheet": "Missing"}) if bad == "wrong-sheet" else data()
    )
    with pytest.raises(ValueError):
        parse_workbook(content, options, expected_sha256="0" * 64) if bad == "hash" else parse(
            content, options
        )
