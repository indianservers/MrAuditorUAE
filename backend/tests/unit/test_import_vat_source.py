from copy import deepcopy

import pytest

from app.modules.country_workflows.import_vat_source import ImportVATSourceInput, source_rows
from tests.unit.test_import_vat import line, populations
from tests.unit.test_shared_audit_workflows import run


def controls(**changes):
    return ImportVATSourceInput.model_validate(
        {
            "source_role": "books",
            "label": "SYNTHETIC assessed import boxes",
            "assessment": "Independent selected book totals assessed for import boxes only",
            "boxes": {
                "6": {"expected_rows": 1, "taxable_amount": "1000", "tax": "50"},
                "7": {"expected_rows": 1, "taxable_amount": "-100", "tax": "-5"},
            },
            **changes,
        }
    )


def comparison(adjustments=True):
    rows = [line()]
    if adjustments:
        rows.append(
            line(
                id="ADJ-1",
                entry_kind="adjustment",
                adjustment_reference="ADJ-1",
                net="-100",
                tax="-5",
            )
        )
    return run("uae-import-vat", populations(rows))


def test_selected_import_boxes_preserve_signs_counts_and_source_links():
    rows, totals = source_rows(comparison(), controls())
    assert totals == {"AED": "45"}
    assert [(row["box"], row["taxable_amount"], row["tax"], row["adjustment"]) for row in rows] == [
        ("6", "1000", "50", "0"),
        ("7", "-100", "-5", "0"),
    ]
    assert all(
        len(row["source_import_row_ids"]) == 1 and len(row["source_import_detail_ids"]) == 1
        for row in rows
    )


@pytest.mark.parametrize(
    "field,value", [("expected_rows", 2), ("taxable_amount", "999.99"), ("tax", "49.99")]
)
def test_each_independent_box_control_must_agree_exactly(field, value):
    params = controls().model_dump(mode="json")
    params["boxes"]["6"][field] = value
    with pytest.raises(ValueError, match="controls do not agree"):
        source_rows(comparison(), ImportVATSourceInput.model_validate(params))


def test_absent_adjustment_population_is_not_converted_into_zero_box7():
    with pytest.raises(ValueError, match="absence is not a verified nil"):
        source_rows(comparison(False), controls())
    selected = controls().model_copy(update={"boxes": {"6": controls().boxes["6"]}})
    rows, totals = source_rows(comparison(False), selected)
    assert len(rows) == 1 and rows[0]["box"] == "6" and totals == {"AED": "50"}


@pytest.mark.parametrize(
    "change",
    [
        "missing-amount",
        "incomplete",
        "mismatched-summary",
        "wrong-currency",
        "cross-period",
        "legacy",
    ],
)
def test_unresolved_or_inconsistent_selected_details_are_rejected(change):
    body = deepcopy(comparison())
    if change == "missing-amount":
        body["rows"][0]["amounts"]["books"] = None
    elif change == "incomplete":
        body["role_totals"]["books"]["declaration"]["complete_for_selected_population"] = False
    elif change == "mismatched-summary":
        body["role_totals"]["books"]["declaration"]["tax"] = "49"
    elif change == "wrong-currency":
        body["rows"][0]["currency"] = "INR"
    elif change == "cross-period":
        body["rows"][0]["period_start"] = "2026-06-01"
    else:
        body.pop("import_comparison_contract")
    with pytest.raises(ValueError):
        source_rows(body, controls())


def test_no_summary_boxes_or_whitespace_assessment_can_be_invented():
    with pytest.raises(ValueError):
        controls(boxes={"8": {"expected_rows": 1, "taxable_amount": "0", "tax": "0"}})
    with pytest.raises(ValueError):
        controls(assessment=" " * 20)
