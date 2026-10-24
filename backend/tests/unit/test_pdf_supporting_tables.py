import hashlib
import io
import subprocess
from copy import deepcopy

import pytest
from pypdf import PdfReader, PdfWriter

from app.modules.intelligence.pdf_tables import PDFGrid, read_pdf_grid
from tests.unit.pdf_bank_example import layout, statement


def extract(tmp_path, content=None, profile=None, *, sha256=None):
    content = statement() if content is None else content
    target = tmp_path / "SYNTHETIC-statement.pdf"
    target.write_bytes(content)
    return read_pdf_grid(
        target, profile or layout(), ".", "iso", sha256 or hashlib.sha256(content).hexdigest()
    )


@pytest.mark.parametrize("currency", ["AED", "INR"])
def test_pdf_header_scope_exact_debit_credit_and_page_provenance(tmp_path, currency):
    result = extract(tmp_path, statement(currency), layout(currency))
    assert [row["amount"] for row in result["rows"]] == ["100.25", "-5"]
    assert [row["reference"] for row in result["rows"]] == ["REF-1", "REF-2"]
    assert all(
        row["currency"] == currency and row["account_code"] == "BANK-1" for row in result["rows"]
    )
    assert result["rows"][0]["source_page"] == 1
    assert result["rows"][0]["source_page_row"] == 1
    assert result["rows"][0]["source_pdf_cells"]["credit"] == "100.25"
    assert result["metadata"]["selected_pages"] == [1]
    assert result["metadata"]["population_basis"] == "ASSESSED_ROW_BANDS_NOT_DOCUMENT_COMPLETENESS"


def test_debit_positive_convention_is_explicit_not_guessed(tmp_path):
    profile = layout()
    profile["amount_basis"] = "debit-positive"
    assert [row["amount"] for row in extract(tmp_path, profile=profile)["rows"]] == ["-100.25", "5"]


@pytest.mark.parametrize(
    "case", ["account", "currency", "clipped-amount", "unmapped-text", "multiline"]
)
def test_pdf_scope_and_geometry_fail_closed(tmp_path, case):
    profile, data = layout(), statement()
    if case == "account":
        data = statement(account="BANK-2")
    elif case == "currency":
        data = statement("INR")
    elif case == "clipped-amount":
        profile["columns"]["credit"]["right"] = 58
    elif case == "unmapped-text":
        data = statement(extra=True)
    else:
        data = statement(multiline=True)
    with pytest.raises(ValueError):
        extract(tmp_path, data, profile)


def test_explicit_ignored_column_retains_the_exclusion_receipt(tmp_path):
    profile = layout()
    profile["ignored_columns"] = [{"left": 0, "right": 5}]
    result = extract(tmp_path, statement(extra=True), profile)
    assert len(result["rows"]) == 2
    assert result["metadata"]["excluded_columns"] == [{"left": 0, "right": 5}]


def test_repeated_page_headers_are_checked_and_rows_remain_distinct(tmp_path):
    profile = layout()
    second = deepcopy(profile["pages"][0])
    second["page"] = 2
    profile["pages"].append(second)
    result = extract(tmp_path, statement(pages=2), profile)
    assert [row["source_page"] for row in result["rows"]] == [1, 1, 2, 2]
    assert len({row["id"] for row in result["rows"]}) == 4


@pytest.mark.parametrize("case", ["overlap", "duplicate-page", "beyond-page", "amount-basis"])
def test_pdf_profile_validation_rejects_ambiguous_layouts(case):
    profile = layout()
    if case == "overlap":
        profile["ignored_columns"] = [{"left": 0, "right": 10}]
    elif case == "duplicate-page":
        profile["pages"] *= 2
    elif case == "beyond-page":
        profile["pages"][0]["row_count"] = 5000
    else:
        profile["amount_basis"] = "signed"
    with pytest.raises(ValueError):
        PDFGrid.model_validate(profile)


def test_pdf_original_bytes_are_verified_again_inside_the_isolated_worker(tmp_path):
    with pytest.raises(ValueError, match="hash verification"):
        extract(tmp_path, sha256="0" * 64)


@pytest.mark.parametrize("variant", ["encrypted", "active", "rotated"])
def test_unsupported_pdf_features_are_not_silently_accepted(tmp_path, variant):
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(statement())).pages:
        writer.add_page(page)
    if variant == "encrypted":
        writer.encrypt("synthetic-secret")
    elif variant == "active":
        writer.add_js("app.alert('synthetic test only')")
    else:
        writer.pages[0].rotate(90)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError):
        extract(tmp_path, output.getvalue())


def test_worker_timeout_fails_closed_without_a_table_result(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 45
        assert args[0][1:3] == ["-m", "app.modules.intelligence.pdf_tables"]
        raise subprocess.TimeoutExpired(args[0], 45)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ValueError, match="45-second"):
        extract(tmp_path)


def test_image_only_pdf_requires_a_separately_qualified_ocr_profile(tmp_path):
    from PIL import Image
    from reportlab.pdfgen import canvas

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(600, 800))
    pdf.drawInlineImage(Image.new("RGB", (100, 100), "white"), 0, 0, 600, 800)
    pdf.save()
    with pytest.raises(ValueError, match="no usable text layer"):
        extract(tmp_path, output.getvalue())


def test_selected_page_must_exist_and_unselected_pages_are_recorded(tmp_path):
    profile = layout()
    profile["pages"][0]["page"] = 2
    with pytest.raises(ValueError, match="does not exist"):
        extract(tmp_path, statement(), profile)
    result = extract(tmp_path, statement(pages=2))
    assert result["metadata"]["unselected_pages"] == [2]


def test_cropped_pdf_uses_visible_page_origin_for_percentage_coordinates(tmp_path):
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(statement())).pages[0])
    writer.pages[0].cropbox.lower_left = (10, 20)
    writer.pages[0].cropbox.upper_right = (590, 790)
    content = io.BytesIO()
    writer.write(content)
    profile = layout()
    for column in profile["columns"].values():
        column["left"] = (column["left"] * 6 - 10) / 580 * 100
        column["right"] = (column["right"] * 6 - 10) / 580 * 100
    grid = profile["pages"][0]
    grid["top"] = (grid["top"] * 8 - 10) / 770 * 100
    grid["row_height"] = grid["row_height"] * 8 / 770 * 100
    for header in (grid["account_header"], grid["currency_header"]):
        for key in ("left", "right"):
            header[key] = (header[key] * 6 - 10) / 580 * 100
        for key in ("top", "bottom"):
            header[key] = (header[key] * 8 - 10) / 770 * 100
    result = extract(tmp_path, content.getvalue(), profile)
    assert [row["amount"] for row in result["rows"]] == ["100.25", "-5"]
    assert result["metadata"]["page_geometry"][0]["origin_left"] == 10
