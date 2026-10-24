import io, hashlib
from openpyxl import Workbook
from app.modules.audit_analytics.workbooks import inspect


def workbook():
    b = Workbook()
    s = b.active
    s.title = "SYNTHETIC"
    s["A1"] = 10
    s["B1"] = "=A1*2"
    s["B2"] = "=A2*3"
    s["D1"] = "=E1"
    s["E1"] = "=D1"
    s["F1"] = "=#REF!"
    s["A3"] = 5
    s.row_dimensions[3].hidden = True
    s["A4"] = "=1+1"
    s["B4"] = 123
    s["C4"] = "=1+1"
    s["G1"] = "='Missing'!A1"
    s["H1"] = "='[remote.xlsx]Sheet1'!A1"
    o = io.BytesIO()
    b.save(o)
    b.close()
    return o.getvalue()


def test_static_scan_finds_specific_errors_without_mutating_or_executing():
    data = workbook()
    result = inspect(data)
    codes = {r["code"] for r in result["findings"]}
    assert {
        "circular_formula_reference",
        "broken_reference",
        "hidden_numeric_input",
        "possible_hardcoded_override",
        "missing_sheet_reference",
        "adjacent_formula_difference_review",
        "external_or_structured_reference_review",
    } <= codes
    assert result["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert result["original_preserved"] and result["professional_conclusion"] is None
    assert data == workbook() or data[:2] == b"PK"
