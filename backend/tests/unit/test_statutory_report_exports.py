import io
import zipfile

from openpyxl import load_workbook
from pypdf import PdfReader

from app.modules.intelligence.exports import render


def test_report_exports_keep_source_figures_provenance_and_draft_status():
    event = {
        "id": "SYNTHETIC-REPORT",
        "engagement_id": "SYNTHETIC-ENGAGEMENT",
        "kind": "statutory-report",
        "version": 1,
        "sha256": "a" * 64,
        "created_at": "2026-10-24T00:00:00Z",
        "dependencies": [],
        "body": {
            "title": "SYNTHETIC source report",
            "country": "IN",
            "reporting_framework": "Ind AS",
            "template_version": 1,
            "review_status": "UNVERIFIED",
            "blocks": [
                {
                    "number": 1,
                    "title": "Actual source fixture",
                    "kind": "financial_table",
                    "text": "Synthetic draft only",
                    "source_receipt": {"id": "actual-source-fixture", "version": 2},
                    "data": {
                        "rows": [
                            {"account": "=FORMULA()", "amount": "12345678901234567890.12345678"}
                        ]
                    },
                }
            ],
        },
    }
    xlsx, _ = render(event, "xlsx")
    cells = [c for s in load_workbook(io.BytesIO(xlsx)) for row in s for c in row]
    assert any(c.value == "12345678901234567890.12345678" and c.data_type == "s" for c in cells)
    assert any(c.value == "=FORMULA()" and c.data_type == "s" for c in cells)
    word, _ = render(event, "docx")
    with zipfile.ZipFile(io.BytesIO(word)) as archive:
        assert b"12345678901234567890.12345678" in archive.read("word/document.xml")
        assert b"DRAFT" in archive.read("word/header1.xml")
    pdf, _ = render(event, "pdf")
    extracted = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "DRAFT" in extracted and "NOT SIGNED OR FILED" in extracted
    assert "actual-source-fixture" in extracted
