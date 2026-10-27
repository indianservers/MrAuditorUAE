"""Portable shaped review text; never silently omit unsupported source characters."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast


class PDFTextError(ValueError):
    """The requested text cannot be faithfully represented in this PDF font set."""


def render_text_schedule(sections: Iterable[tuple[str, bool]]) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import MethodReturnValue, XPos, YPos
    from fpdf.fonts import TTFFont

    root = Path(__file__).resolve().parents[1] / "assets/fonts"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    pdf = FPDF()
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    coverage: set[int] = set()
    families = ["NotoSans", "NotoSansArabic", "NotoSansDevanagari"]
    for family in families:
        name = family + "-Regular.ttf"
        path = root / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError("PDF font integrity verification failed")
        pdf.add_font(family, fname=str(path))
        coverage.update(cast(TTFFont, pdf.fonts[family.lower()]).cmap)
    pdf.set_font("NotoSans", size=10)
    pdf.set_fallback_fonts(families[1:], exact_match=False)
    pdf.set_text_shaping(True)
    pdf.set_title("Mr Auditor - reviewable audit schedule")
    pdf.set_producer("Mr Auditor multilingual text schedule/1")
    pdf.add_page()
    for text, heading in sections:
        missing = {ord(c) for c in text if ord(c) not in coverage and c not in "\n\r\u200c\u200d"}
        if missing:
            codes = ", ".join(f"U+{c:04X}" for c in sorted(missing)[:5])
            raise PDFTextError(
                f"PDF font coverage is unavailable for {codes}; use the complete XLSX export"
            )
        pdf.set_font("NotoSans", size=15 if heading else 9)
        height = 7 if heading else 4.8
        lines = cast(
            list[str],
            pdf.multi_cell(
                w=0,
                h=height,
                text=text,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
                dry_run=True,
                output=MethodReturnValue.LINES,
            ),
        )
        for line in lines:
            if pdf.will_page_break(height):
                pdf.add_page()
            # ISO 32000 ActualText preserves logical Unicode independently of
            # shaped glyph codes. Hex encoding cannot inject PDF operators.
            # Close each line's marked content before any automatic page break.
            actual = (b"\xfe\xff" + line.encode("utf-16-be")).hex().upper()
            pdf._out(f"/Span << /ActualText <{actual}> >> BDC")
            pdf.cell(w=0, h=height, text=line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf._out("EMC")
        pdf.ln(2 if heading else 1)
    return bytes(pdf.output())
