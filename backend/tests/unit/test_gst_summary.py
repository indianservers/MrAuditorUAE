import copy
import csv
import io
import json
import uuid
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.gst_summary import COUNTS, METRICS, GSTSummaryMetric
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv

GSTIN = "27ABCDE5678G1Z8"


def summary():
    return {
        "gstin": GSTIN,
        "ret_period": "062026",
        "newSumFlag": True,
        "sec_sum": [
            {
                "sec_nm": "B2B",
                "ttl_igst": 18,
                "ttl_tax": 100,
                "ttl_rec": 1,
                "cpty_sum": [
                    {"ctin": "29ABCDE1234F1Z5", "ttl_igst": 18, "ttl_tax": 100, "ttl_rec": 1}
                ],
            },
            {"sec_nm": "B2B_4A", "ttl_igst": 18, "ttl_tax": 100, "ttl_rec": 1},
            {
                "sec_nm": "CDNR",
                "ttl_igst": -9,
                "ttl_tax": -50,
                "ttl_rec": 1,
                "sub_sections": [
                    {"sec_nm": "CDNR_4A", "typ": "C", "ttl_igst": -9, "ttl_tax": -50, "ttl_rec": 1}
                ],
            },
            {
                "sec_nm": "NIL",
                "ttl_expt_amt": 25,
                "ttl_nilsup_amt": 0,
                "ttl_ngsup_amt": 0,
                "ttl_rec": 1,
            },
            {
                "sec_nm": "DOC_ISSUE",
                "ttl_doc_issued": 3,
                "ttl_doc_cancelled": 1,
                "net_doc_issued": 2,
                "ttl_rec": 1,
            },
        ],
    }


CONTROLS = {
    "ttl_igst": "36",
    "ttl_tax": "200",
    "ttl_rec": "7",
    "ttl_expt_amt": "25",
    "ttl_nilsup_amt": "0",
    "ttl_ngsup_amt": "0",
    "ttl_doc_issued": "3",
    "ttl_doc_cancelled": "1",
    "net_doc_issued": "2",
}


def canonical_rows():
    """Separately authored flat book schedule; two offsetting section errors."""
    scopes = [
        ("B2B", "", "", "", {"ttl_igst": 19, "ttl_tax": 100, "ttl_rec": 1}),
        ("B2B", "", "", "29ABCDE1234F1Z5", {"ttl_igst": 18, "ttl_tax": 100, "ttl_rec": 1}),
        ("B2B_4A", "", "", "", {"ttl_igst": 17, "ttl_tax": 100, "ttl_rec": 1}),
        ("CDNR", "", "", "", {"ttl_igst": -9, "ttl_tax": -50, "ttl_rec": 1}),
        ("CDNR", "CDNR_4A", "C", "", {"ttl_igst": -9, "ttl_tax": -50, "ttl_rec": 1}),
        (
            "NIL",
            "",
            "",
            "",
            {"ttl_expt_amt": 25, "ttl_nilsup_amt": 0, "ttl_ngsup_amt": 0, "ttl_rec": 1},
        ),
        (
            "DOC_ISSUE",
            "",
            "",
            "",
            {"ttl_doc_issued": 3, "ttl_doc_cancelled": 1, "net_doc_issued": 2, "ttl_rec": 1},
        ),
    ]
    return [
        {
            "id": f"BOOK-{index}-{metric}",
            "registration": GSTIN,
            "period": "2026-06",
            "section": section,
            "sub_section": sub,
            "nature": nature,
            "counterparty": party,
            "state_code": "",
            "metric": metric,
            "unit": "COUNT" if metric in COUNTS else "INR",
            "value": str(value),
        }
        for index, (section, sub, nature, party, values) in enumerate(scopes, 1)
        for metric, value in values.items()
    ]


def options(**changes):
    args = dict(
        evidence_version_id=uuid.uuid4(),
        file_format="india-gstr1-summary-json",
        table_type="gst-summary-metrics",
        label="SYNTHETIC summary metrics",
        expected_rows=23,
        control_totals={},
        gst_registration=GSTIN,
        gst_period="2026-06",
        gst_summary_metric_controls=CONTROLS,
    )
    args.update(changes)
    return SourceInput(**args)


def parsed(payload=None, **changes):
    return parse_native(
        json.dumps(summary() if payload is None else payload).encode(),
        options(**changes),
        "IN",
        "summary.json",
    )


def workflow(**changes):
    args = dict(
        workflow="india-gstr1-summary",
        source_ids={"books": uuid.uuid4(), "return": uuid.uuid4()},
        as_of="2026-06-30",
        currency="INR",
        title="SYNTHETIC summary reconciliation",
        rationale="Independent section metric controls and original hierarchy assessed",
    )
    args.update(changes)
    return WorkflowInput(**args)


def test_native_summary_preserves_hierarchy_counts_signed_values_and_original_metrics():
    body = parsed()
    assert body["row_count"] == 23
    assert body["control_totals"] == {}
    assert body["metric_controls"] == CONTROLS
    assert body["allowed_source_roles"] == ["return"]
    assert body["native_metadata"]["filing_status"] == "NOT_ESTABLISHED_BY_SUMMARY"
    assert len([r for r in body["rows"] if r["metric"] == "ttl_igst"]) == 5
    assert all(r["unit"] == ("COUNT" if r["metric"] in COUNTS else "INR") for r in body["rows"])
    wrapped = {"code": 200, "data": {"status_cd": "1", "data": summary()}}
    assert parsed(wrapped)["native_metadata"]["transparent_wrapper_depth"] == 2


def test_independent_csv_comparison_never_nets_metrics_or_treats_absent_zero_as_match():
    right = parsed()
    rows = canonical_rows()
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(GSTSummaryMetric.model_fields))
    writer.writeheader()
    writer.writerows(rows)
    books = parse_csv(output.getvalue().encode(), options(file_format="canonical-csv"))
    result = calculate(workflow(tolerance="100"), "IN", {"books": books, "return": right})
    assert result["exception_count"] == 2
    assert result["totals"] == {}
    assert {r["difference"] for r in result["rows"] if r["state"] == "VARIANCE"} == {"1", "-1"}
    rows = copy.deepcopy(right["rows"])
    rows.pop(next(i for i, r in enumerate(rows) if r["metric"] == "ttl_nilsup_amt"))
    # Independent canonical books, not a native return with its format marker removed.
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(GSTSummaryMetric.model_fields))
    writer.writeheader()
    writer.writerows(rows)
    books = parse_csv(
        output.getvalue().encode(),
        options(
            file_format="canonical-csv",
            expected_rows=len(rows),
            gst_summary_metric_controls={
                key: value for key, value in CONTROLS.items() if key != "ttl_nilsup_amt"
            },
        ),
    )
    missing = calculate(workflow(), "IN", {"books": books, "return": right})
    assert missing["blocked"]
    assert (
        next(r for r in missing["rows"] if r["metric"] == "ttl_nilsup_amt")["state"]
        == "RETURN_ONLY"
    )


@pytest.mark.parametrize(
    "defect",
    [
        "unknown_root",
        "unknown_metric",
        "duplicate_section",
        "duplicate_counterparty",
        "fractional_count",
        "negative_count",
        "string_number",
        "boolean_number",
        "wrong_gstin",
        "wrong_period",
        "incomplete_control",
        "wrong_control",
        "row_count",
        "unknown_depth",
        "wrong_wrapper",
        "empty",
        "invalid_section",
    ],
)
def test_native_summary_rejects_ambiguous_or_uncontrolled_populations(defect):
    payload = summary()
    changes = {}
    if defect == "unknown_root":
        payload["b2b"] = []
    elif defect == "unknown_metric":
        payload["sec_sum"][0]["ttl_future"] = 0
    elif defect == "duplicate_section":
        payload["sec_sum"].append(copy.deepcopy(payload["sec_sum"][0]))
    elif defect == "duplicate_counterparty":
        payload["sec_sum"][0]["cpty_sum"] *= 2
    elif defect == "fractional_count":
        payload["sec_sum"][0]["ttl_rec"] = 1.5
    elif defect == "negative_count":
        payload["sec_sum"][0]["ttl_rec"] = -1
    elif defect == "string_number":
        payload["sec_sum"][0]["ttl_tax"] = "100"
    elif defect == "boolean_number":
        payload["sec_sum"][0]["ttl_tax"] = True
    elif defect == "wrong_gstin":
        payload["gstin"] = "29ABCDE1234F1Z5"
    elif defect == "wrong_period":
        payload["ret_period"] = "072026"
    elif defect == "incomplete_control":
        changes["gst_summary_metric_controls"] = {
            k: v for k, v in CONTROLS.items() if k != "ttl_nilsup_amt"
        }
    elif defect == "wrong_control":
        changes["gst_summary_metric_controls"] = {**CONTROLS, "ttl_igst": "18"}
    elif defect == "row_count":
        changes["expected_rows"] = 22
    elif defect == "unknown_depth":
        payload["sec_sum"][2]["sub_sections"][0]["sub_sections"] = []
    elif defect == "wrong_wrapper":
        payload = {"code": 400, "data": payload}
    elif defect == "empty":
        payload["sec_sum"] = []
    elif defect == "invalid_section":
        payload["sec_sum"][0]["sec_nm"] = []
    with pytest.raises(ValueError):
        parsed(payload, **changes)


def test_summary_country_role_period_and_duplicate_boundaries():
    right = parsed()
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(GSTSummaryMetric.model_fields))
    writer.writeheader()
    writer.writerows(right["rows"])
    books = parse_csv(output.getvalue().encode(), options(file_format="canonical-csv"))
    with pytest.raises(ValueError, match="unavailable"):
        calculate(workflow(), "AE", {"books": books, "return": right})
    with pytest.raises(ValueError, match="requires INR"):
        calculate(workflow(currency="AED"), "IN", {"books": books, "return": right})
    with pytest.raises(ValueError, match="only the return role"):
        calculate(workflow(), "IN", {"books": right, "return": books})
    with pytest.raises(ValueError, match="extends beyond"):
        calculate(workflow(as_of="2026-06-15"), "IN", {"books": books, "return": right})
    books["rows"] = [*books["rows"], books["rows"][0]]
    with pytest.raises(ValueError, match="unique"):
        calculate(workflow(), "IN", {"books": books, "return": right})
    with pytest.raises(ValueError):
        options(control_totals={"INR": "36"})


def test_all_documented_metrics_remain_exact_and_separate():
    payload = {
        "gstin": GSTIN,
        "ret_period": "062026",
        "sec_sum": [{"sec_nm": "SYNTHETIC", **{k: 0 if k in COUNTS else -1 for k in METRICS}}],
    }
    controls = {k: Decimal(0 if k in COUNTS else -1) for k in METRICS}
    body = parsed(payload, expected_rows=19, gst_summary_metric_controls=controls)
    assert len(body["rows"]) == 19
    assert body["metric_controls"] == {k: str(v) for k, v in controls.items()}


def test_native_summary_row_bound_rejects_oversized_hierarchy():
    payload = {
        "gstin": GSTIN,
        "ret_period": "062026",
        "sec_sum": [{"sec_nm": f"S{i}", **{metric: 0 for metric in METRICS}} for i in range(264)],
    }
    with pytest.raises(ValueError, match="5,000"):
        parsed(payload, expected_rows=5000, gst_summary_metric_controls={k: "0" for k in METRICS})
