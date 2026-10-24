from copy import deepcopy
from types import SimpleNamespace

from app.modules.ifrs.exports import rows_for
from app.modules.ifrs.review import presentation_lines, review_statements


def statement():
    return {
        "precision": 2,
        "comparative": {"snapshot_id": "prior"},
        "presentation_settings": {"suppress_zero": True},
        "lines": [
            {
                "line_code": "cash",
                "label": "Cash",
                "section": "assets",
                "current": "130",
                "comparative": "100",
                "note": "1",
            },
            {
                "line_code": "capital",
                "label": "Capital",
                "section": "equity",
                "current": "-100",
                "comparative": "-100",
                "note": "1",
            },
            {
                "line_code": "sales",
                "label": "Sales",
                "section": "income",
                "current": "-30",
                "comparative": "0",
                "note": "1",
            },
            {
                "line_code": "zero",
                "label": "Zero",
                "section": "assets",
                "current": "0",
                "comparative": "0",
                "note": "1",
            },
        ],
        "totals": {
            "assets": "130",
            "liabilities": "0",
            "equity": "130",
            "profit": "30",
            "oci": "0",
            "total_comprehensive_income": "30",
        },
        "notes": [
            {
                "reference": "1",
                "text": "SYNTHETIC note",
                "lines": [
                    {"code": "cash", "current": "130", "comparative": "100"},
                    {"code": "capital", "current": "-100", "comparative": "-100"},
                    {"code": "sales", "current": "-30", "comparative": "0"},
                ],
            }
        ],
        "validation": {"checks": []},
    }


def test_review_ties_balanced_statements_without_mutating_source():
    data = statement()
    original = deepcopy(data)
    review = review_statements(data)
    assert review["ready"] and not review["issues"]
    assert len(review["presentation_lines"]) == 4
    assert review["presentation_lines"][1]["display_current"] == "100.00"
    assert data == original


def test_note_ties_duplicates_dangling_links_and_totals_are_detected():
    data = statement()
    data["notes"][0]["lines"][0]["current"] = "129"
    data["notes"][0]["lines"].pop()
    data["notes"][0]["lines"].append({"code": "unknown", "current": "1"})
    data["notes"].append(deepcopy(data["notes"][0]))
    data["totals"]["assets"] = "129"
    review = review_statements(data)
    assert not review["ready"]
    assert {
        "note_tie",
        "missing_note_link",
        "unknown_note_line",
        "duplicate_note_reference",
        "statement_total",
    } <= {i["code"] for i in review["issues"]}


def test_rounding_difference_is_explicit_and_prior_only_line_is_visible():
    data = statement()
    data["lines"][0]["current"] = "130.005"
    data["lines"].append(
        {
            "line_code": "tiny",
            "label": "Tiny",
            "section": "assets",
            "current": ".005",
            "comparative": "0",
            "note": "1",
        }
    )
    data["lines"][-2]["comparative"] = "1"
    review = review_statements(data)
    warning = next(i for i in review["issues"] if i["code"] == "rounding_difference")
    assert warning["severity"] == "warning" and warning["evidence"]["difference"] == "0.01"
    assert any(r["line_code"] == "zero" for r in presentation_lines(data))


def test_draft_comparison_tracks_changes_carried_and_resolved_issues():
    old = statement()
    old["notes"][0]["lines"][0]["current"] = "129"
    old["notes"][0]["lines"][1]["current"] = "-99"
    new = deepcopy(old)
    new["notes"][0]["lines"][0]["current"] = "130"
    new["notes"][0]["text"] = "SYNTHETIC revised disclosure"
    review = review_statements(new, old)
    assert "note_tie:1/cash" in review["resolved_issue_keys"]
    assert next(i for i in review["issues"] if i["key"] == "note_tie:1/capital")["carry_forward"]
    assert review["changes"][0]["change"] == "note_changed"


def test_exports_share_precision_signs_and_suppression_with_preview():
    data = statement()
    run = SimpleNamespace(
        results=data,
        id="synthetic",
        sha256="test",
        methodology_version="test",
        created_by="test",
        created_at="test",
    )
    rows = rows_for(run, False)
    assert ["Capital", "100.00", "100.00", "1"] in rows
    assert ["capital", "100.00", "100.00", "Presentation signs"] in rows
    assert not any(row[0] == "Zero" for row in rows)
    assert ["Total assets", "130.00", "100.00", "Sum of displayed lines"] in rows
    assert ["Total equity", "130.00", "100.00", "Sum of displayed lines"] in rows
    assert ["Current period profit / loss", "30.00", "0.00", ""] in rows
