import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.country_workflows.vat201_layouts import EMIRATES, LAYOUTS
from app.modules.country_workflows.vat_composition import VATCompositionInput, source_rows
from tests.unit.test_country_workflows import parsed
from tests.unit.test_vat_box_scope import full_filed_boxes


def detailed_rows(prefix="FILED"):
    base = full_filed_boxes()
    main = base[0]
    emirates = [
        {
            **main,
            "id": prefix + "-" + box,
            "box": box,
            "taxable_amount": "100" if box in {"1a", "1b"} else "0",
            "tax": "5" if box in {"1a", "1b"} else "0",
        }
        for box in EMIRATES
    ]
    return emirates + [
        {**row, "id": prefix + "-" + row["box"]} for row in base if row["box"] != "1"
    ]


def composition():
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    rows = detailed_rows("BOOK")
    sources = {
        ids[0]: {
            "table_type": "return-boxes",
            "source_identity": "emirate-books",
            "rows": rows[:7],
        },
        ids[1]: {"table_type": "return-boxes", "source_identity": "other-books", "rows": rows[7:]},
    }
    data = VATCompositionInput(
        source_ids=ids,
        layout="emirate-20",
        taxable_amount="2400",
        tax="230",
        adjustment="0",
        label="SYNTHETIC emirate books",
        assessment="Seven independently assessed emirate totals and thirteen other explicit book boxes",
    )
    return sources, data


def compare(books=None, filed=None, **changes):
    sources = {
        "books": parsed("return-boxes", detailed_rows("BOOK") if books is None else books),
        "return": parsed("return-boxes", detailed_rows() if filed is None else filed),
    }
    data = WorkflowInput.model_validate(
        {
            "workflow": "uae-vat-return",
            "source_ids": {role: uuid.uuid4() for role in sources},
            "vat201_layout": "emirate-20",
            "required_boxes": LAYOUTS["emirate-20"]["boxes"],
            "as_of": "2026-06-30",
            "currency": "AED",
            "title": "SYNTHETIC emirate comparison",
            "rationale": "Retained emirate allocation and period applicability independently assessed",
            **changes,
        }
    )
    return calculate(data, "AE", sources)


def test_twenty_explicit_rows_keep_every_emirate_zero_and_source_identity():
    sources, data = composition()
    rows, totals = source_rows(sources, data)
    assert [row["box"] for row in rows] == LAYOUTS["emirate-20"]["boxes"]
    assert totals == {"AED": "230"}
    assert rows[0]["emirate"] == "Abu Dhabi" and rows[6]["emirate"] == "Fujairah"
    assert rows[6]["tax"] == "0" and rows[6]["taxable_amount"] == "0"
    assert rows[6]["source_component_row_id"] == "BOOK-1g"
    assert rows[6]["source_component_event_id"] == str(data.source_ids[0])
    result = compare()
    assert len(result["rows"]) == 20 and result["exception_count"] == 0
    assert result["vat201_layout"] == "emirate-20"
    assert [row["box"] for row in result["rows"]] == LAYOUTS["emirate-20"]["boxes"]


def test_opposing_emirate_errors_do_not_disappear_into_unchanged_aggregate_box1():
    filed = detailed_rows()
    filed[0].update(taxable_amount="120", tax="6")
    filed[1].update(taxable_amount="80", tax="4")
    result = compare(filed=filed)
    assert result["exception_count"] == 2 and not result["blocked"]
    assert result["rows"][0]["state"] == result["rows"][1]["state"] == "VARIANCE"
    assert result["rows"][0]["differences"]["tax"] == "-1"
    assert result["rows"][1]["differences"]["tax"] == "1"


@pytest.mark.parametrize("missing", ["books", "return", "both"])
def test_missing_emirate_blocks_approval_instead_of_becoming_nil(missing):
    books, filed = detailed_rows("BOOK"), detailed_rows()
    if missing in {"books", "both"}:
        books = [row for row in books if row["box"] != "1g"]
    if missing in {"return", "both"}:
        filed = [row for row in filed if row["box"] != "1g"]
    result = compare(books, filed)
    assert result["blocked"]
    row = next(row for row in result["rows"] if row["box"] == "1g")
    assert row["state"] != "MATCHED" and row["differences"]["tax"] is None


@pytest.mark.parametrize(
    "change,message",
    [
        ("aggregate", "disjoint boxes"),
        ("missing", "twenty"),
        ("overlap", "overlap"),
        ("fraction", "nearest fils"),
        ("tax", "controls"),
        ("adjustment", "controls"),
    ],
)
def test_composition_requires_complete_disjoint_assessed_layout(change, message):
    sources, data = composition()
    first, second = list(sources.values())
    if change == "aggregate":
        second["rows"].append(deepcopy(full_filed_boxes()[0]))
    elif change == "missing":
        first["rows"].pop()
    elif change == "overlap":
        second["rows"].append(deepcopy(first["rows"][0]))
    elif change == "fraction":
        first["rows"][0]["tax"] = "5.001"
    elif change == "tax":
        data.tax += 1
    else:
        data.adjustment += 1
    with pytest.raises(ValueError, match=message):
        source_rows(sources, data)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("currency", "USD", "AED"),
        ("registration", "OTHER", "TRN"),
        ("period_start", "2026-05-01", "one reporting period"),
        ("tax", "5.001", "nearest fils"),
        ("box", "1", "aggregate Box 1"),
    ],
)
def test_profile_never_mixes_scopes_or_aggregate_and_detail(field, value, message):
    rows = detailed_rows("BOOK")
    rows[0][field] = value
    with pytest.raises(ValueError, match=message):
        compare(books=rows)


def test_layout_cannot_be_truncated_or_used_for_an_indian_workflow():
    for changes in (
        {
            "restrict_to_required_boxes": True,
            "box_scope_assessment": "Independent selected scope assessment",
        },
        {"required_boxes": ["1a"]},
        {"workflow": "india-gst"},
    ):
        with pytest.raises(ValueError, match="all its explicit boxes"):
            compare(**changes)
    with pytest.raises(ValueError, match="distinct"):
        rows = detailed_rows("BOOK")
        rows.append({**rows[0], "id": "DUPLICATED"})
        compare(books=rows)


def test_legacy_aggregate_layout_remains_separate_and_accepts_all_fourteen_rows():
    result = compare(
        full_filed_boxes(),
        [{**row, "id": "SEPARATE-" + row["box"]} for row in full_filed_boxes()],
        vat201_layout="aggregate-14",
        required_boxes=LAYOUTS["aggregate-14"]["boxes"],
    )
    assert len(result["rows"]) == 14 and result["exception_count"] == 0
    with pytest.raises(ValueError, match="aggregate Box 1"):
        compare(books=full_filed_boxes())
