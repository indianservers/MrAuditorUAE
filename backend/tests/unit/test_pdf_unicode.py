"""Source text must survive shaping and PDF page boundaries."""

from io import BytesIO

import pypdfium2
import pytest
from pypdf import PdfReader
from pypdf.generic import ContentStream

from app.core.pdf_text import PDFTextError, render_text_schedule
from tests.unit.indic_pdf_samples import SAMPLES


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


def test_table_row_taller_than_page_continues_without_losing_cells():
    from app.core.pdf_text import PDFTable

    content = render_text_schedule(
        [PDFTable(["Row", "Detail"], [["1", "\n".join(f"LINE-{i:03}" for i in range(200))]])],
        draft=True,
    )
    reader = PdfReader(BytesIO(content))
    assert len(reader.pages) > 2
    lines = []
    for page in reader.pages:
        page_lines = [
            str(args[1]["/ActualText"])
            for args, operator in ContentStream(page.get_contents(), reader).operations
            if operator == b"BDC"
        ]
        assert "Detail" in page_lines
        lines.extend(line for line in page_lines if line.startswith("LINE-"))
    assert lines == [f"LINE-{i:03}" for i in range(200)]


@pytest.mark.parametrize("script,party", SAMPLES.items())
def test_indian_scripts_survive_workflow_and_statutory_pdf_exports(script, party):
    from app.modules.intelligence.exports import render
    from tests.unit.test_statutory_report_exports import report_event

    event = report_event()
    event["firm_name"] = party
    block = event["body"]["blocks"][0]
    block.update(title=party, text=party)
    block["source_receipt"]["party"] = party
    block["data"]["rows"][0]["counterparty"] = party
    for kind in ["workflow-source", "statutory-report"]:
        event["kind"] = kind
        event["body"]["rows"] = [{"counterparty": party, "amount": "105.00"}]
        content, _ = render(event, "pdf")
        reader = PdfReader(BytesIO(content))
        actual = [
            str(args[1]["/ActualText"])
            for page in reader.pages
            for args, operator in ContentStream(page.get_contents(), reader).operations
            if operator == b"BDC"
        ]
        assert party in "\n".join(actual), (script, kind)
        embedded_names = []
        for page in reader.pages:
            for font in page["/Resources"]["/Font"].values():
                font = font.get_object()
                if font["/Subtype"] == "/Type0":
                    embedded_names.append(str(font["/BaseFont"]))
                    desc = font["/DescendantFonts"][0].get_object()["/FontDescriptor"]
                    assert "/FontFile2" in desc.get_object()
        family = "NotoSans" + ("Oriya" if script == "Odia" else script.replace(" ", ""))
        assert any(family in name for name in embedded_names), (script, kind)
