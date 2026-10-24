import io
import zipfile

from openpyxl import load_workbook

from app.modules.intelligence.exports import render


def test_exact_decimal_and_formula_injection_stay_text_in_exports():
    event = dict(
        id="SYNTHETIC-RESULT",
        kind="lead",
        version=1,
        sha256="a" * 64,
        created_at="2026-10-24T00:00:00Z",
        dependencies=[],
        body={
            "review_status": "UNVERIFIED",
            "rows": [{"name": "=HYPERLINK(unsafe)", "amount": "99999999999999999999.12345678"}],
        },
    )
    xlsx, media = render(event, "xlsx")
    assert "spreadsheet" in media
    workbook = load_workbook(io.BytesIO(xlsx))
    cells = [cell for sheet in workbook for row in sheet for cell in row]
    assert any(c.value == "99999999999999999999.12345678" and c.data_type == "s" for c in cells)
    assert any(c.value == "=HYPERLINK(unsafe)" and c.data_type == "s" for c in cells)
    pdf, _ = render(event, "pdf")
    assert pdf.startswith(b"%PDF-")
    docx, _ = render(event, "docx")
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        assert b"UNVERIFIED" in archive.read("word/document.xml")
