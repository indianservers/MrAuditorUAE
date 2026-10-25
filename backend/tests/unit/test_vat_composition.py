"""Disjoint explicit VAT201 schedules retain controls and original row identities."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.vat_composition import VATCompositionInput, source_rows
from tests.unit.test_vat_box_scope import full_filed_boxes


def composition():
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    rows = full_filed_boxes()
    sources = {
        identifier: {
            "table_type": "return-boxes",
            "source_identity": "schedule-" + str(index),
            "rows": [row for row in rows if (row["box"] in {"6", "7"}) == (index == 0)],
        }
        for index, identifier in enumerate(ids)
    }
    data = VATCompositionInput(
        source_ids=ids,
        taxable_amount="2400",
        tax="230",
        adjustment="0",
        label="Synthetic composed books",
        assessment="Independent disjoint explicit fourteen-box schedule controls",
    )
    return sources, data


def test_composition_preserves_signed_corrections_and_original_provenance():
    sources, data = composition()
    rows, totals = source_rows(sources, data)
    assert len(rows) == 14 and totals == {"AED": "230"}
    assert rows[6]["box"] == "7" and rows[6]["tax"] == "-5"
    assert rows[5]["source_component_event_id"] == str(data.source_ids[0])
    assert rows[5]["source_component_row_id"] == "FILED-6"
    assert len({row["id"] for row in rows}) == 14


@pytest.mark.parametrize(
    "change, message",
    [
        ("missing", "fourteen"),
        ("overlap", "overlap"),
        ("same-original", "same underlying"),
        ("registration", "one TRN"),
        ("period", "one TRN"),
        ("currency", "AED"),
        ("unknown", "disjoint boxes"),
        ("tax", "controls"),
        ("base", "controls"),
        ("adjustment", "controls"),
        ("empty", "explicit return-box"),
    ],
)
def test_composition_refuses_unsafe_population_or_controls(change, message):
    sources, data = composition()
    first, second = list(sources.values())
    if change == "missing":
        first["rows"].pop()
    elif change == "overlap":
        second["rows"].append(deepcopy(first["rows"][0]))
    elif change == "same-original":
        second["source_identity"] = first["source_identity"]
    elif change == "registration":
        second["rows"][0]["registration"] = "100000000000002"
    elif change == "period":
        second["rows"][0]["period_start"] = "2026-05-01"
    elif change == "currency":
        first["rows"][0]["currency"] = "USD"
    elif change == "unknown":
        first["rows"][0]["box"] = "15"
    elif change == "tax":
        data.tax += 1
    elif change == "base":
        data.taxable_amount += 1
    elif change == "adjustment":
        data.adjustment += 1
    elif change == "empty":
        first["rows"] = []
    with pytest.raises(ValueError, match=message):
        source_rows(sources, data)


def test_duplicate_source_versions_and_blank_assessment_are_invalid():
    _, data = composition()
    for changes in (
        {"source_ids": [data.source_ids[0]] * 2},
        {"assessment": " " * 20},
        {"tax": "NaN"},
    ):
        with pytest.raises(ValidationError):
            VATCompositionInput.model_validate({**data.model_dump(), **changes})
