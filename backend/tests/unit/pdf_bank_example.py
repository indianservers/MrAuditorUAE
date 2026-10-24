"""Fictional PDF input for deterministic grid-reader and bank-reconciliation tests."""

import io

from reportlab.pdfgen import canvas


def layout(currency="AED"):
    return {
        "account": "BANK-1",
        "currency": currency,
        "amount_basis": "credit-positive",
        "scope_assessment": "Synthetic header identity, all selected row bands and declared columns checked against the original",
        "pages": [
            {
                "page": 1,
                "top": 11.25,
                "row_height": 2.5,
                "row_count": 2,
                "account_header": {"left": 16, "right": 28, "top": 6.25, "bottom": 8.75},
                "currency_header": {"left": 45, "right": 52, "top": 6.25, "bottom": 8.75},
            }
        ],
        "columns": {
            "date": {"left": 5, "right": 19},
            "reference": {"left": 19, "right": 39},
            "debit": {"left": 39, "right": 54},
            "credit": {"left": 54, "right": 69},
            "counterparty": {"left": 69, "right": 96},
        },
    }


def statement(currency="AED", *, pages=1, account="BANK-1", extra=False, multiline=False):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(600, 800), invariant=1)
    pdf.setTitle("Synthetic bank statement - not bank issued")
    for page in range(pages):
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(40, 765, "SYNTHETIC TEST STATEMENT - NOT BANK ISSUED")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, 740, "Account:")
        pdf.drawString(100, 740, account)
        pdf.drawString(220, 740, "Currency:")
        pdf.drawString(275, 740, currency)
        for x, heading in [
            (40, "Date"),
            (120, "Reference"),
            (240, "Debit"),
            (330, "Credit"),
            (440, "Party"),
        ]:
            pdf.drawString(x, 720, heading)
        for y, reference, debit, credit in [(700, "REF-1", "", "100.25"), (680, "REF-2", "5", "")]:
            for x, value in [
                (40, "2026-06-30"),
                (120, reference),
                (240, debit),
                (330, credit),
                (440, "SYN-CLIENT"),
            ]:
                if value:
                    pdf.drawString(x, y, value)
        if extra:
            pdf.drawString(4, 700, "X")
        if multiline:
            pdf.drawString(330, 695, "20")
        pdf.drawString(40, 645, "Opening balance: 0.00    Closing balance: 95.25")
        pdf.drawString(
            40,
            625,
            "All parties and values are fictional. No payment instruction or financial assertion.",
        )
        pdf.drawString(40, 40, f"Synthetic page {page + 1}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
