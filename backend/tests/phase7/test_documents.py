from app.modules.vat.documents import extract_text_pdf


def test_actual_text_pdf_extracts_fields_without_visual_verification(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "synthetic-invoice.pdf"
    doc = canvas.Canvas(str(path))
    for index, line in enumerate(
        [
            "SYNTHETIC Tax Invoice",
            "Invoice Number: SYN-001",
            "Supplier TRN: 999999999999999",
            "VAT Amount: 50.00",
            "Gross Amount: 1,050.00",
        ]
    ):
        doc.drawString(40, 750 - index * 22, line)
    doc.save()
    result = extract_text_pdf(path)
    assert result["fields"] == {
        "invoice_number": "SYN-001",
        "supplier_trn": "999999999999999",
        "declared_tax": "50.00",
        "declared_gross": "1,050.00",
    }
    assert result["state"] == "TEXT_PDF_EXTRACTED_UNVERIFIED"
    assert result["human_review_required"] and not result["visual_verification"]
