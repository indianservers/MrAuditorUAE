"""Source text must survive shaping and PDF page boundaries."""

from io import BytesIO

import pypdfium2
import pytest
from pypdf import PdfReader
from pypdf.generic import ContentStream

from app.core.pdf_text import PDFTextError, render_text_schedule


@pytest.mark.parametrize("party", ["شركة النور للتجارة", "भारत आपूर्तिकर्ता"])
def test_shaped_source_text_survives_page_boundaries(party):
    rows = [f"SYN-{i}: {party} | 105.00" for i in range(100)]
    data = render_text_schedule([(row, False) for row in rows])
    reader = PdfReader(BytesIO(data))
    assert len(reader.pages) > 1
    logical = []
    for page in reader.pages:
        depth = 0
        for args, operator in ContentStream(page.get_contents(), reader).operations:
            if operator == b"BDC":
                depth += 1
                logical.append(str(args[1]["/ActualText"]))
            elif operator == b"EMC":
                depth -= 1
                assert depth >= 0
        assert depth == 0
    assert logical == rows
    document = pypdfium2.PdfDocument(data)
    extracted = "".join(page.get_textpage().get_text_range() for page in document)
    # PDFium can reorder mixed RTL runs even with correct ActualText. The
    # exact logical source is asserted above; every word must still survive.
    assert all(word in extracted for word in party.split())
    assert "105.00" in extracted
    document.close()


def test_pdf_operators_and_markup_are_literal_source_text():
    text = "<script> /Span << /ActualText (altered) >> BDC EMC 105.00"
    data = render_text_schedule([(text, False)])
    reader = PdfReader(BytesIO(data))
    logical = [
        str(args[1]["/ActualText"])
        for args, operator in ContentStream(reader.pages[0].get_contents(), reader).operations
        if operator == b"BDC"
    ]
    assert " ".join(logical) == text


def test_unsupported_script_fails_instead_of_omitting_source_text():
    with pytest.raises(PDFTextError, match="U\\+4E2D"):
        render_text_schedule([("中", False)])


def test_font_integrity_is_verified(monkeypatch):
    from pathlib import Path

    original = Path.read_bytes

    def altered(path):
        data = original(path)
        return data + b"tampered" if path.name == "NotoSans-Regular.ttf" else data

    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(ValueError, match="integrity"):
        render_text_schedule([("105.00", False)])
