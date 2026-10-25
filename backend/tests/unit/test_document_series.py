"""Synthetic Table 13 ranges and independently authored count expectations."""

import csv
import io
import json
import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.document_series import DocumentSeries, SeriesCounts
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv

GSTIN = "27ABCDE5678G1Z8"


def row(**changes):
    return {
        "id": "SYN-SERIES-1",
        "registration": GSTIN,
        "period": "2026-06",
        "doc_num": 1,
        "serial_from": "SYN/0001",
        "serial_to": "SYN/0010",
        "issued": 10,
        "cancelled": 2,
        "net_issued": 8,
        **changes,
    }


def payload():
    return {
        "gstin": GSTIN,
        "fp": "062026",
        "doc_issue": {
            "doc_det": [
                {
                    "doc_num": 1,
                    "docs": [
                        {
                            "num": 1,
                            "from": "SYN/0001",
                            "to": "SYN/0010",
                            "totnum": 10,
                            "cancel": 2,
                            "net_issue": 8,
                        },
                    ],
                }
            ]
        },
    }


def parameters(**changes):
    return SourceInput.model_validate(
        {
            "evidence_version_id": str(uuid.uuid4()),
            "file_format": "india-gstr1-document-series-json",
            "table_type": "gst-document-series",
            "label": "SYNTHETIC Table 13 response",
            "expected_rows": 1,
            "control_totals": {},
            "document_series_controls": {"issued": 10, "cancelled": 2, "net_issued": 8},
            "gst_registration": GSTIN,
            "gst_period": "2026-06",
            "gstr1_context_evidence_version_id": str(uuid.uuid4()),
            "gstr1_retrieval_assessment": "Independent synthetic GSTIN and reporting period request context",
            **changes,
        }
    )


def native(body=None, **changes):
    return parse_native(
        json.dumps(body or payload()).encode(), parameters(**changes), "IN", "SYNTHETIC-series.json"
    )


def comparison(left=None, right=None, country="IN", **changes):
    sources = {
        role: {"table_type": "gst-document-series", "rows": rows, "control_totals": {}}
        for role, rows in [
            ("books", left if left is not None else [row()]),
            ("reported", right if right is not None else [row(id="SYN-R1")]),
        ]
    }
    data = WorkflowInput.model_validate(
        {
            "workflow": "india-document-series",
            "source_ids": {role: str(uuid.uuid4()) for role in sources},
            "as_of": "2026-06-30",
            "title": "SYNTHETIC document series",
            "rationale": "Independently specified retained series count comparison",
            "currency": "INR",
            **changes,
        }
    )
    return calculate(data, country, sources)


def test_native_and_canonical_preserve_ranges_and_independent_counts():
    output = native()
    assert output["rows"][0]["serial_from"] == "SYN/0001"
    assert output["document_series_controls"] == {"issued": 10, "cancelled": 2, "net_issued": 8}
    assert output["allowed_source_roles"] == ["reported"]
    assert output["native_metadata"]["filing_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_SERIES"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(row()))
    writer.writeheader()
    writer.writerow(row())
    canonical = parse_csv(
        buffer.getvalue().encode(),
        parameters(
            file_format="canonical-csv",
            gstr1_context_evidence_version_id=None,
            gstr1_retrieval_assessment="",
        ),
    )
    assert canonical["rows"][0] == row()
    assert comparison()["exception_count"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("issued", True),
        ("cancelled", "2.0"),
        ("net_issued", -1),
        ("doc_num", False),
        ("serial_from", " SYN/0001"),
        ("serial_to", ""),
        ("period", "2026-13"),
    ],
)
def test_invalid_canonical_fields_fail(field, value):
    with pytest.raises(ValueError):
        DocumentSeries.model_validate(row(**{field: value}))


def test_native_does_not_infer_total_from_serial_endpoints_or_expand_a_range():
    body = payload()
    body["doc_issue"]["doc_det"][0]["docs"][0].update(totnum=9, cancel=1, net_issue=8)
    output = native(body, document_series_controls={"issued": 9, "cancelled": 1, "net_issued": 8})
    assert len(output["rows"]) == 1 and output["rows"][0]["issued"] == 9


def test_explicit_zero_row_is_not_inferred_from_an_absent_category():
    body = payload()
    body["doc_issue"]["doc_det"][0]["docs"][0].update(
        {"from": "", "to": "", "totnum": 0, "cancel": 0, "net_issue": 0}
    )
    assert (
        native(body, document_series_controls={"issued": 0, "cancelled": 0, "net_issued": 0})[
            "row_count"
        ]
        == 1
    )
    body["doc_issue"]["doc_det"] = []
    with pytest.raises(ValueError, match="absence is not zero"):
        native(body)


@pytest.mark.parametrize(
    "change",
    [
        "cancelled",
        "control",
        "duplicate",
        "duplicate-category",
        "scope",
        "flag",
        "unknown",
        "fraction",
        "missing",
        "extra-section",
    ],
)
def test_native_rejects_inconsistent_or_unsupported_evidence(change):
    body = payload()
    series = body["doc_issue"]["doc_det"][0]["docs"]
    if change == "cancelled":
        series[0]["cancel"] = 11
    elif change == "control":
        series[0].update(totnum=11, net_issue=9)
    elif change == "duplicate":
        series.append(deepcopy(series[0]))
    elif change == "duplicate-category":
        body["doc_issue"]["doc_det"].append(deepcopy(body["doc_issue"]["doc_det"][0]))
    elif change == "scope":
        body["gstin"] = "29ABCDE1234F1Z5"
    elif change == "flag":
        body["doc_issue"]["flag"] = "D"
    elif change == "unknown":
        series[0]["canc"] = 2
    elif change == "fraction":
        series[0]["totnum"] = 10.0
    elif change == "missing":
        del series[0]["net_issue"]
    else:
        body["b2b"] = []
    with pytest.raises(ValueError):
        native(body)


def test_numeric_string_counts_accepted_but_not_fractions_booleans_or_unicode_digits():
    assert SeriesCounts(issued="10", cancelled="2", net_issued="8").issued == 10
    with pytest.raises(ValueError):
        SeriesCounts(issued="١٠", cancelled=2, net_issued=8)


def test_cancellation_difference_is_exact_even_when_money_tolerance_is_high():
    output = comparison(right=[row(id="R1", cancelled=1, net_issued=9)], tolerance="1000")
    assert output["exception_count"] == 1
    assert output["rows"][0]["differences"] == {"issued": 0, "cancelled": -1, "net_issued": 1}


def test_cancelled_counts_cannot_offset_differences_between_ranges():
    left = [row(), row(id="L2", serial_from="B001", serial_to="B010")]
    right = [
        row(id="R1", cancelled=1, net_issued=9),
        row(id="R2", serial_from="B001", serial_to="B010", cancelled=3, net_issued=7),
    ]
    assert comparison(left, right)["exception_count"] == 2


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "cross-period", "future", "country", "currency"]
)
def test_compare_rejects_wrong_scope_or_keeps_missing_as_unknown(change):
    if change == "missing":
        output = comparison(right=[row(id="OTHER", serial_from="OTHER-001")])
        assert output["exception_count"] == 2 and all(
            None in item["differences"].values() for item in output["rows"]
        )
        return
    with pytest.raises(ValueError):
        if change == "duplicate":
            comparison(right=[row(), row(id="DUP")])
        elif change == "cross-period":
            comparison(right=[row(period="2026-05")])
        elif change == "future":
            comparison(as_of="2026-06-29")
        elif change == "country":
            comparison(country="AE")
        else:
            comparison(currency="AED")


@pytest.mark.parametrize("field", ["issued", "cancelled", "net_issued"])
def test_count_bounds_are_explicit_and_exact_in_browser_safe_range(field):
    with pytest.raises(ValueError):
        SeriesCounts.model_validate(
            {"issued": 10, "cancelled": 2, "net_issued": 8, field: 10**12 + 1}
        )


def test_distinct_row_numbers_cannot_duplicate_the_same_retained_range():
    body = payload()
    duplicate = deepcopy(body["doc_issue"]["doc_det"][0]["docs"][0])
    duplicate["num"] = 2
    body["doc_issue"]["doc_det"][0]["docs"].append(duplicate)
    with pytest.raises(ValueError, match="Duplicate document-series scope"):
        native(
            body,
            expected_rows=2,
            document_series_controls={"issued": 20, "cancelled": 4, "net_issued": 16},
        )


def test_assessed_context_is_required_and_must_be_separate():
    for changes in (
        {"gstr1_context_evidence_version_id": None},
        {"gstr1_retrieval_assessment": "   "},
    ):
        with pytest.raises(ValueError, match="distinct retained request context"):
            parameters(**changes)
    identifier = str(uuid.uuid4())
    with pytest.raises(ValueError, match="distinct retained request context"):
        parameters(evidence_version_id=identifier, gstr1_context_evidence_version_id=identifier)


def test_success_wrapper_keeps_scope_and_unsuccessful_wrapper_is_rejected():
    assert (
        native({"code": 200, "data": payload()})["native_metadata"]["transparent_wrapper_depth"]
        == 1
    )
    with pytest.raises(ValueError, match="unsuccessful"):
        native({"code": 401, "data": payload()})


def test_native_reported_file_cannot_be_reused_as_books_or_in_a_uae_engagement():
    reported = native()
    data = WorkflowInput.model_validate(
        {
            "workflow": "india-document-series",
            "source_ids": {role: str(uuid.uuid4()) for role in ("books", "reported")},
            "as_of": "2026-06-30",
            "title": "SYNTHETIC role guard",
            "rationale": "Original reported source is not independent book evidence",
            "currency": "INR",
        }
    )
    with pytest.raises(ValueError, match="only the reported role"):
        calculate(data, "IN", {"books": reported, "reported": reported})
    with pytest.raises(ValueError, match="unavailable"):
        parse_native(json.dumps(payload()).encode(), parameters(), "AE", "SYNTHETIC-series.json")
