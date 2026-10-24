import hashlib
import io
import zipfile
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from app.modules.intelligence import service

MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook(*, second=False, formula=False, epoch1904=False):
    book = Workbook()
    if epoch1904:
        from openpyxl.utils.datetime import CALENDAR_MAC_1904

        book.epoch = CALENDAR_MAC_1904
    sheet = book.active
    sheet.title = "Bank"
    sheet.append(["reference", "currency", "amount", "date", "Memo"])
    sheet.append(
        ["REF-1", "AED", 100.25, datetime(2026, 6, 30), "=1+1" if formula else "original note"]
    )
    sheet.append([])
    sheet.append(["REF-2", "AED", "100,25", datetime(2026, 6, 30), "text amount"])
    if second:
        book.create_sheet("Other")
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def prepare(tmp_path, monkeypatch, content):
    path = tmp_path / "private-object-without-extension"
    path.write_bytes(content)

    @contextmanager
    def local(*args):
        yield path

    monkeypatch.setattr(service, "ObjectStore", lambda: SimpleNamespace(local=local))
    return SimpleNamespace(
        media_type=MEDIA,
        object_key="synthetic",
        object_version="1",
        sha256=hashlib.sha256(content).hexdigest(),
    )


def rewrite(content, edit, extra=None):
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as original,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in original.infolist():
            target.writestr(item.filename, edit(item.filename, original.read(item)))
        if extra:
            target.writestr(extra, b"synthetic prohibited member")
    return out.getvalue()


def test_numeric_cells_ignore_text_locale_and_dates_keep_physical_rows(tmp_path, monkeypatch):
    version = prepare(tmp_path, monkeypatch, workbook())
    metadata = {}
    rows = service.read_table(version, "bank", ",", "dmy", metadata=metadata)
    assert [row["amount"] for row in rows] == ["100.25", "100.25"]
    assert [row["source_row"] for row in rows] == [2, 4]
    assert all(row["date"] == "2026-06-30" and row["source_worksheet"] == "Bank" for row in rows)
    assert rows[0]["source_amount_storage"] == "ORIGINAL_XLSX_NUMERIC_XML"
    assert rows[1]["source_amount_storage"] == "TEXT_CELL"
    assert metadata["excluded_columns"] == ["Memo"]
    assert metadata["worksheet"] == "Bank"


def test_original_numeric_xml_is_not_rounded_through_float(tmp_path, monkeypatch):
    data = rewrite(
        workbook(),
        lambda name, value: (
            value.replace(b"<v>100.25</v>", b"<v>123456789012345.12</v>")
            if name == "xl/worksheets/sheet1.xml"
            else value
        ),
    )
    version = prepare(tmp_path, monkeypatch, data)
    assert service.read_table(version, "bank", ",", "iso")[0]["amount"] == "123456789012345.12"


def test_workbook_date_epoch_is_used_and_retained(tmp_path, monkeypatch):
    version = prepare(tmp_path, monkeypatch, workbook(epoch1904=True))
    metadata = {}
    assert (
        service.read_table(version, "bank", ",", "iso", metadata=metadata)[0]["date"]
        == "2026-06-30"
    )
    assert metadata["excel_epoch"].startswith("1904-01-01")


def test_original_and_normalized_heading_receipts_remain_distinct(tmp_path, monkeypatch):
    data = rewrite(
        workbook(),
        lambda name, value: (
            value.replace(b">currency<", b"> currency <")
            if name == "xl/worksheets/sheet1.xml"
            else value
        ),
    )
    version = prepare(tmp_path, monkeypatch, data)
    metadata = {}
    assert len(service.read_table(version, "bank", ",", "iso", metadata=metadata)) == 2
    assert " currency " in metadata["original_headers"]
    assert "currency" in metadata["normalized_headers"]


def test_multiple_sheets_require_explicit_selection(tmp_path, monkeypatch):
    version = prepare(tmp_path, monkeypatch, workbook(second=True))
    with pytest.raises(ValueError, match="explicitly select"):
        service.read_table(version, "bank", ",", "iso")
    assert len(service.read_table(version, "bank", ",", "iso", "Bank")) == 2
    with pytest.raises(ValueError, match="not found"):
        service.read_table(version, "bank", ",", "iso", "Missing")


def test_formulas_in_excluded_columns_are_not_accepted_as_cached_values(tmp_path, monkeypatch):
    version = prepare(tmp_path, monkeypatch, workbook(formula=True))
    with pytest.raises(ValueError, match="formulas"):
        service.read_table(version, "bank", ",", "iso")


@pytest.mark.parametrize("extra", ["xl/vbaProject.bin", "xl/externalLinks/link.xml"])
def test_macros_and_external_links_fail_before_reading(tmp_path, monkeypatch, extra):
    version = prepare(tmp_path, monkeypatch, rewrite(workbook(), lambda _, value: value, extra))
    with pytest.raises(ValueError, match="Macros and external"):
        service.read_table(version, "bank", ",", "iso")


@pytest.mark.parametrize("value", [b"1e9999", b"NaN", b"100.123456789"])
def test_unsupported_original_numeric_precision_is_rejected(tmp_path, monkeypatch, value):
    data = rewrite(
        workbook(),
        lambda name, data: (
            data.replace(b"<v>100.25</v>", b"<v>" + value + b"</v>")
            if name == "xl/worksheets/sheet1.xml"
            else data
        ),
    )
    version = prepare(tmp_path, monkeypatch, data)
    with pytest.raises(ValueError):
        service.read_table(version, "bank", ",", "iso")
