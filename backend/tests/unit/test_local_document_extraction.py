"""Genuine local extraction on explicitly generated fixtures; no scanner qualification claim."""

import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen.canvas import Canvas

from app.modules.intelligence.documents import extract_document, preview_page


def test_digital_pdf_and_scanned_image_are_real_and_traceable(tmp_path):
    pdf = tmp_path / "synthetic.pdf"
    canvas = Canvas(str(pdf))
    canvas.drawString(40, 780, "Invoice No: SYNTHETIC-104")
    canvas.drawString(40, 750, "Grand Total: 105.00")
    canvas.save()
    digital = extract_document(pdf, "application/pdf", "AE")
    assert digital["fields"]["invoice_number"] == "SYNTHETIC-104"
    assert digital["pages"][0]["provider"] == "pdfium-text"
    assert digital["pages"][0]["blocks"][0]["bbox"] is None
    assert preview_page(pdf, "application/pdf", 1).startswith(b"\x89PNG")
    image = Image.new("RGB", (1000, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(
        str(Path(__file__).resolve().parents[2] / "app/assets/fonts/NotoSans-Regular.ttf"), 32
    )
    for i, text in enumerate(
        [
            "Supplier: Example Trading LLC",
            "Invoice No: TEST-104",
            "Invoice Date: 2026-10-01",
            "Grand Total: 105.00",
            "Currency: AED",
        ]
    ):
        draw.text((30, 30 + i * 70), text, font=font, fill="black")
    path = tmp_path / "synthetic.png"
    image.save(path)
    result = extract_document(path, "image/png", "AE")
    assert result["fields"]["invoice_number"] == "TEST-104"
    assert result["fields"]["gross_amount"] == "105.00"
    assert result["pages"][0]["blocks"][0]["bbox"]
    assert result["model_artifacts"] and all(
        len(h) == 64 for h in result["model_artifacts"].values()
    )
    assert not result["network_document_transfer"]
    assert result["review_status"] == "UNVERIFIED"
    assert preview_page(path, "image/png", 1).startswith(b"\x89PNG")


def test_zip_keeps_documents_separate_and_can_select_member(tmp_path):
    def pdf(number):
        buffer = io.BytesIO()
        canvas = Canvas(buffer)
        canvas.drawString(40, 780, "Invoice No: " + number)
        canvas.save()
        return buffer.getvalue()

    path = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("one.pdf", pdf("ONE"))
        archive.writestr("two.pdf", pdf("TWO"))
    batch = extract_document(path, "application/zip", "AE")
    assert len(batch["documents"]) == 2
    assert batch["fields"]["invoice_number"] is None
    selected = extract_document(path, "application/zip", "AE", {"zip_member": "two.pdf"})
    assert selected["fields"]["invoice_number"] == "TWO"
