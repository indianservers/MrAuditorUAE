"""One-page synthetic script checks; these names are not verified client data."""

from pdf_unicode_preview import ROOT

from app.core.pdf_text import PDFTable, render_text_schedule
from tests.unit.indic_pdf_samples import SAMPLES

if __name__ == "__main__":
    samples = {
        "Arabic": "شركة النور للتجارة",
        "Devanagari": "भारत आपूर्तिकर्ता",
        **SAMPLES,
    }
    target = ROOT / "output/pdf/indic-script-review.pdf"
    sections = [
        ("SYNTHETIC UAE / India source-name script checks", True),
        (
            "Original Unicode source names; not translated legal content or verified client identities.",
            False,
        ),
        PDFTable(
            ["Row", "Script", "Source name", "Currency", "Amount"],
            [
                [
                    str(i),
                    script,
                    party,
                    "AED" if script == "Arabic" else "INR",
                    "105.00",
                ]
                for i, (script, party) in enumerate(samples.items(), 1)
            ],
        ),
        (
            "Source values and exact decimal strings are retained. Unsupported characters fail PDF export; XLSX remains available.",
            False,
        ),
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render_text_schedule(sections, draft=True))
    print("Saved synthetic Indic-script PDF for visual inspection")
