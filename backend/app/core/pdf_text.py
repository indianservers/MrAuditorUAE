"""Portable shaped review text; never silently omit unsupported source characters."""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast


class PDFTextError(ValueError):
    """The requested text cannot be faithfully represented in this PDF font set."""


@dataclass(frozen=True)
class PDFTable:
    """A bounded paper view; callers retain the complete source in XLSX."""

    headers: list[str]
    rows: list[list[str]]


def render_text_schedule(
    sections: Iterable[tuple[str, bool] | PDFTable], *, draft: bool = False
) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import MethodReturnValue, XPos, YPos
    from fpdf.fonts import TTFFont

    root = Path(__file__).resolve().parents[1] / "assets/fonts"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    class SchedulePDF(FPDF):
        def header(self):
            if not draft:
                return
            self.set_font("NotoSans", size=46)
            self.set_text_color(235, 235, 235)
            with self.rotation(30, self.w / 2, self.h / 2):
                self.text(self.w / 2 - 30, self.h / 2, "DRAFT")
            self.set_text_color(0, 0, 0)

        def footer(self):
            if not draft:
                return
            self.set_font("NotoSans", size=8)
            self.set_text_color(70, 70, 70)
            self.set_xy(self.l_margin, self.h - 12)
            self.cell(w=0, text=f"Page {self.page_no()} - Not signed or filed", align="R")
            self.set_text_color(0, 0, 0)

    pdf = SchedulePDF(orientation="L" if draft else "P")
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

    def validate(text):
        missing = {ord(c) for c in text if ord(c) not in coverage and c not in "\n\r\u200c\u200d"}
        if missing:
            codes = ", ".join(f"U+{c:04X}" for c in sorted(missing)[:5])
            raise PDFTextError(
                f"PDF font coverage is unavailable for {codes}; use the complete XLSX export"
            )

    def marked_cell(line, width, height):
        # Hex-encoded ISO ActualText cannot inject PDF operators. Every span
        # closes before a page break, including rows continued across pages.
        actual = (b"\xfe\xff" + line.encode("utf-16-be")).hex().upper()
        pdf._out(f"/Span << /ActualText <{actual}> >> BDC")
        pdf.cell(w=width, h=height, text=line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf._out("EMC")

    def wrap(text, width, height):
        validate(text)
        return cast(
            list[str],
            pdf.multi_cell(
                w=width,
                h=height,
                text=text,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
                dry_run=True,
                output=MethodReturnValue.LINES,
            ),
        ) or [""]

    def grid(table):
        if not table.headers or any(len(row) != len(table.headers) for row in table.rows):
            raise PDFTextError("Invalid PDF table dimensions; use the complete XLSX export")
        pdf.set_font("NotoSans", size=8)
        width = pdf.w - pdf.l_margin - pdf.r_margin
        widths = (
            [width]
            if len(table.headers) == 1
            else [12, *[(width - 12) / (len(table.headers) - 1)] * (len(table.headers) - 1)]
        )
        height, padding = 4, 1

        def lines(row):
            return [wrap(cell, size - 2 * padding, height) for cell, size in zip(row, widths)]

        header = lines(table.headers)
        header_height = max(map(len, header)) * height + 2 * padding
        page_bottom = pdf.h - pdf.b_margin
        full_body = page_bottom - pdf.t_margin - header_height
        if full_body < height + 2 * padding:
            raise PDFTextError("PDF table header exceeds a page; use the complete XLSX export")

        def draw(cells, count, heading=False):
            start_y = pdf.y
            x = pdf.l_margin
            row_height = count * height + 2 * padding
            for cell, size in zip(cells, widths):
                if heading:
                    pdf.set_fill_color(240, 243, 247)
                pdf.set_draw_color(180, 185, 190)
                pdf.rect(x, start_y, size, row_height, style="DF" if heading else "D")
                for index, line in enumerate(cell):
                    pdf.set_xy(x + padding, start_y + padding + index * height)
                    marked_cell(line, size - 2 * padding, height)
                x += size
            pdf.set_xy(pdf.l_margin, start_y + row_height)

        def heading(new_page=False):
            if new_page or pdf.will_page_break(header_height + height + 2 * padding):
                pdf.add_page()
            draw(header, max(map(len, header)), heading=True)

        heading()
        for row in table.rows:
            cells = lines(row)
            count = max(map(len, cells))
            if count * height + 2 * padding <= full_body and pdf.will_page_break(
                count * height + 2 * padding
            ):
                heading(new_page=True)
            offset = 0
            while offset < count:
                capacity = int((page_bottom - pdf.y - 2 * padding) / height)
                if capacity < 1:
                    heading(new_page=True)
                    continue
                length = min(count - offset, capacity)
                draw([cell[offset : offset + length] for cell in cells], length)
                offset += length
                if offset < count:
                    heading(new_page=True)
        pdf.ln(2)

    for section in sections:
        if isinstance(section, PDFTable):
            grid(section)
            continue
        text, heading = section
        pdf.set_font("NotoSans", size=15 if heading else 9)
        height = 7 if heading else 4.8
        for line in wrap(text, 0, height):
            if pdf.will_page_break(height):
                pdf.add_page()
            marked_cell(line, 0, height)
        pdf.ln(2 if heading else 1)
    return bytes(pdf.output())
