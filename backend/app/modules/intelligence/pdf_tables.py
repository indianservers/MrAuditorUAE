"""Explicit PDF text grids. No OCR, inferred columns, account ownership or bank qualification."""

import hashlib
import io
import json
import math
import os
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

PDF_FIELDS = Literal[
    "date", "reference", "amount", "debit", "credit", "counterparty", "account_code", "currency"
]


class PDFColumn(Strict):
    left: float = Field(ge=0, lt=100, allow_inf_nan=False)
    right: float = Field(gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.left >= self.right:
            raise ValueError("PDF column left must precede right")
        return self


class PDFPageGrid(Strict):
    page: int = Field(ge=1, le=20)
    top: float = Field(ge=0, lt=100, allow_inf_nan=False)
    row_height: float = Field(gt=0, le=100, allow_inf_nan=False)
    row_count: int = Field(ge=1, le=5000)
    account_header: "PDFBox"
    currency_header: "PDFBox"

    @model_validator(mode="after")
    def within_page(self):
        if self.top + self.row_height * self.row_count > 100:
            raise ValueError("PDF row grid exceeds the selected page")
        return self


class PDFBox(PDFColumn):
    top: float = Field(ge=0, lt=100, allow_inf_nan=False)
    bottom: float = Field(gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def vertical_order(self):
        if self.top >= self.bottom:
            raise ValueError("PDF header top must precede bottom")
        return self


class PDFGrid(Strict):
    pages: list[PDFPageGrid] = Field(min_length=1, max_length=20)
    columns: dict[PDF_FIELDS, PDFColumn] = Field(min_length=3, max_length=8)
    ignored_columns: list[PDFColumn] = Field(default_factory=list, max_length=12)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    account: str = Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")
    amount_basis: Literal["signed", "debit-positive", "credit-positive"] = "signed"
    scope_assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def unambiguous(self):
        if len(self.scope_assessment.strip()) < 10:
            raise ValueError("Assess the selected PDF population and excluded columns explicitly")
        if len({page.page for page in self.pages}) != len(self.pages):
            raise ValueError("Select one non-overlapping row grid per PDF page")
        if sum(page.row_count for page in self.pages) > 5000:
            raise ValueError("PDF table exceeds 5,000 selected row bands")
        required = {"date", "reference"} | (
            {"amount"} if self.amount_basis == "signed" else {"debit", "credit"}
        )
        conflicting = {"debit", "credit"} if self.amount_basis == "signed" else {"amount"}
        if not required <= self.columns.keys() or conflicting.intersection(self.columns):
            raise ValueError("PDF columns must agree with the explicit signed/debit-credit basis")
        columns = sorted(
            [*self.columns.values(), *self.ignored_columns], key=lambda column: column.left
        )
        if any(left.right > right.left for left, right in zip(columns, columns[1:])):
            raise ValueError("PDF mapped and ignored columns must not overlap")
        return self


def _extract(path, profile, separator, date_format, expected_sha256):
    import logging

    logging.disable(logging.CRITICAL)
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    from app.modules.intelligence.documents import NUMERALS, money
    from app.modules.intelligence.supporting_tables import normalize

    profile = PDFGrid.model_validate(profile)
    path = Path(path)
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("PDF supporting table exceeds 10 MiB")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("PDF original evidence hash verification failed")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
        raise ValueError("Encrypted PDF or 20-page limit exceeded")
    root: Any = reader.trailer["/Root"]
    names = root.get("/Names", {})
    if hasattr(names, "get_object"):
        names = names.get_object()
    names = str(names)
    if any(key in root for key in ("/OpenAction", "/AA", "/AcroForm")) or any(
        key in names for key in ("/JavaScript", "/EmbeddedFiles")
    ):
        raise ValueError("Active, attached-file or interactive PDF content is unsupported")
    metadata: dict[str, Any] = {
        "source_format": "PDF_TEXT_GRID",
        "reader_version": "pdf-text-grid/1",
        "coordinate_system": "PERCENT_OF_PAGE_FROM_TOP_LEFT",
        "pdf_layout": profile.model_dump(mode="json"),
        "selected_pages": sorted(page.page for page in profile.pages),
        "unselected_pages": sorted(
            set(range(1, len(reader.pages) + 1)) - {page.page for page in profile.pages}
        ),
        "population_basis": "ASSESSED_ROW_BANDS_NOT_DOCUMENT_COMPLETENESS",
        "currency_basis": "MATCHED_SELECTED_CURRENCY_HEADER_AND_MAPPED_ROWS_IF_PRESENT",
        "account_scope_basis": "MATCHED_SELECTED_HEADER_TEXT_NOT_OWNERSHIP_VERIFICATION",
        "original_headers": list(profile.columns),
        "excluded_columns": [column.model_dump() for column in profile.ignored_columns],
        "page_geometry": [],
    }
    raw_rows, provenance = [], []
    chars_total = 0
    with pdfium.PdfDocument(data) as document:
        for grid in sorted(profile.pages, key=lambda page: page.page):
            if grid.page > len(document):
                raise ValueError("Selected PDF page does not exist")
            page = document[grid.page - 1]
            try:
                width, height = page.get_width(), page.get_height()
                origin_left, origin_bottom, box_right, box_top = page.get_bbox()
                if page.get_rotation() or not all(
                    math.isfinite(value) and 0 < value <= 20000 for value in (width, height)
                ):
                    raise ValueError("Rotated or unsupported PDF page dimensions")
                if (
                    not all(
                        math.isfinite(value) and abs(value) <= 40000
                        for value in (origin_left, origin_bottom, box_right, box_top)
                    )
                    or abs(box_right - origin_left - width) > 0.05
                    or abs(box_top - origin_bottom - height) > 0.05
                ):
                    raise ValueError("Unsupported PDF crop/media-box geometry")
                geometry = {
                    "page": grid.page,
                    "width": width,
                    "height": height,
                    "origin_left": origin_left,
                    "origin_bottom": origin_bottom,
                }
                metadata["page_geometry"].append(geometry)
                if "/AA" in reader.pages[grid.page - 1]:
                    raise ValueError("Active PDF page content is unsupported")
                textpage = page.get_textpage()
                try:
                    count = textpage.count_chars()
                    chars_total += count
                    if count > 100000 or chars_total > 1000000:
                        raise ValueError("PDF character limit exceeded")
                    if count == 0:
                        raise ValueError(
                            "PDF page has no usable text layer; qualified OCR is required"
                        )
                    for name, box, expected in (
                        ("account", grid.account_header, profile.account),
                        ("currency", grid.currency_header, profile.currency),
                    ):
                        header_left, header_right = (
                            origin_left + box.left * width / 100,
                            origin_left + box.right * width / 100,
                        )
                        header_top, header_bottom = (
                            origin_bottom + height * (1 - box.top / 100),
                            origin_bottom + height * (1 - box.bottom / 100),
                        )
                        for index in range(count):
                            code = pdfium.raw.FPDFText_GetUnicode(textpage, index)
                            if code and chr(code).isspace():
                                continue
                            left, lower, right, upper = textpage.get_charbox(index)
                            if not all(
                                math.isfinite(value) for value in (left, lower, right, upper)
                            ):
                                raise ValueError("Invalid PDF header character coordinates")
                            if (
                                right <= header_left
                                or left >= header_right
                                or upper <= header_bottom
                                or lower >= header_top
                            ):
                                continue
                            if (
                                not code
                                or left < header_left - 0.05
                                or right > header_right + 0.05
                                or lower < header_bottom - 0.05
                                or upper > header_top + 0.05
                            ):
                                raise ValueError("Text crosses a selected PDF header boundary")
                        observed = textpage.get_text_bounded(
                            header_left, header_bottom, header_right, header_top, errors="strict"
                        ).strip()
                        if observed != expected:
                            raise ValueError(
                                f"PDF {name} header differs from the explicit statement scope"
                            )
                        geometry[name + "_header_text"] = observed
                        geometry[name + "_header_bbox"] = [
                            header_left,
                            header_bottom,
                            header_right,
                            header_top,
                        ]
                    # Coordinates are explicit: no text is discarded inside a row band unless
                    # it belongs to a declared ignored column. Reject clipping instead of
                    # accepting a shortened date, reference or amount.
                    top = origin_bottom + height * (1 - grid.top / 100)
                    row_height = height * grid.row_height / 100
                    bottom = top - grid.row_count * row_height
                    intervals = [
                        (
                            origin_left + column.left * width / 100,
                            origin_left + column.right * width / 100,
                        )
                        for column in [*profile.columns.values(), *profile.ignored_columns]
                    ]
                    for index in range(count):
                        code = pdfium.raw.FPDFText_GetUnicode(textpage, index)
                        if code and chr(code).isspace():
                            continue
                        left, lower, right, upper = textpage.get_charbox(index)
                        if upper <= bottom or lower >= top:
                            continue
                        if not code or not all(
                            math.isfinite(value) for value in (left, lower, right, upper)
                        ):
                            raise ValueError(
                                "Unmapped PDF character encoding or invalid coordinates"
                            )
                        center = (lower + upper) / 2
                        band = int((top - center) // row_height)
                        if not 0 <= band < grid.row_count:
                            raise ValueError("Text crosses the PDF row-grid boundary")
                        row_top, row_bottom = top - band * row_height, top - (band + 1) * row_height
                        if lower < row_bottom - 0.05 or upper > row_top + 0.05:
                            raise ValueError("Text crosses a PDF row boundary; adjust the profile")
                        if (
                            sum(
                                left >= start - 0.05 and right <= end + 0.05
                                for start, end in intervals
                            )
                            != 1
                        ):
                            raise ValueError(
                                "Text crosses a PDF column boundary or undeclared column"
                            )
                    for band in range(grid.row_count):
                        row_top, row_bottom = top - band * row_height, top - (band + 1) * row_height
                        cells = {
                            field: textpage.get_text_bounded(
                                origin_left + column.left * width / 100,
                                row_bottom,
                                origin_left + column.right * width / 100,
                                row_top,
                                errors="strict",
                            ).strip()
                            for field, column in profile.columns.items()
                        }
                        if any(
                            len(value) > 4000 or "\n" in value or "\r" in value
                            for value in cells.values()
                        ):
                            raise ValueError(
                                "Multiline or oversized PDF cell; a qualified layout is required"
                            )
                        if not cells["date"]:
                            raise ValueError(
                                "PDF row has no usable date text; image-only/unsupported layouts require qualified OCR"
                            )
                        if "currency" in cells and cells["currency"] != profile.currency:
                            raise ValueError(
                                "Mapped PDF currency differs from the declared statement scope"
                            )
                        if "account_code" in cells and cells["account_code"] != profile.account:
                            raise ValueError("Mapped PDF account differs from the statement header")
                        row = {
                            key: value
                            for key, value in cells.items()
                            if key not in {"amount", "debit", "credit"}
                        }
                        row["currency"] = profile.currency
                        row["account_code"] = profile.account

                        def number(value, unsigned=False):
                            if any(character.isspace() for character in value):
                                raise ValueError(
                                    "Spaces within a PDF amount require a separately qualified profile"
                                )
                            normalized = value.translate(NUMERALS)
                            if unsigned and (
                                normalized.startswith("-") or normalized.startswith("(")
                            ):
                                raise ValueError(
                                    "PDF debit/credit columns require unsigned amounts"
                                )
                            return Decimal(money(value, separator))

                        with localcontext() as arithmetic:
                            arithmetic.prec = 80
                            if profile.amount_basis == "signed":
                                row["amount"] = str(number(cells["amount"]))
                            else:
                                debit, credit = cells["debit"], cells["credit"]
                                if not debit and not credit:
                                    raise ValueError("PDF debit and credit are both blank")
                                d, c = (
                                    number(debit, True) if debit else Decimal(0),
                                    number(credit, True) if credit else Decimal(0),
                                )
                                if d and c:
                                    raise ValueError("PDF debit and credit are both nonzero")
                                row["amount"] = str(
                                    d - c if profile.amount_basis == "debit-positive" else c - d
                                )
                        raw_rows.append(row)
                        provenance.append(
                            {
                                "source_page": grid.page,
                                "source_page_row": band + 1,
                                "source_pdf_bbox": [
                                    origin_left,
                                    row_bottom,
                                    origin_left + width,
                                    row_top,
                                ],
                                "source_pdf_cells": cells,
                                "source_pdf_amount_basis": profile.amount_basis,
                            }
                        )
                finally:
                    textpage.close()
            finally:
                page.close()
    rows = normalize(enumerate(raw_rows, 1), "bank", ".", date_format, metadata)
    for row, origin in zip(rows, provenance, strict=True):
        row.update(origin)
    return {"rows": rows, "metadata": metadata}


def read_pdf_grid(path, profile, separator, date_format, sha256):
    """Use an OS subprocess, including under Celery's daemonic prefork workers."""
    profile = PDFGrid.model_validate(profile)
    payload = {
        "path": str(Path(path).resolve()),
        "profile": profile.model_dump(mode="json"),
        "separator": separator,
        "date_format": date_format,
        "expected_sha256": sha256,
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.modules.intelligence.pdf_tables", "--worker"],
            input=json.dumps(payload),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
            cwd=Path(__file__).resolve().parents[3],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("PDF table extraction exceeded its 45-second bound") from None
    if result.returncode or len(result.stdout) > 20 * 1024 * 1024:
        raise ValueError("PDF table extraction worker failed or exceeded output limits")
    try:
        output = json.loads(result.stdout)
    except ValueError:
        raise ValueError("PDF table extraction returned an invalid receipt") from None
    if "error" in output:
        raise ValueError(output["error"])
    return output


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        response = _extract(**request)
    except ValueError as exc:
        response = {"error": str(exc)[:250]}
    except Exception:
        response = {"error": "PDF text-grid extraction failed; select a qualified supported layout"}
    print(json.dumps(response, ensure_ascii=True))
