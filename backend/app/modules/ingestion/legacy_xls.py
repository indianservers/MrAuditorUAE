"""Bounded BIFF8 text tables. Never accept formula caches as source values."""

import io
import struct

import olefile
import xlrd

MAX_BYTES = 10 * 1024 * 1024
# BIFF formula/cache families, encrypted workbooks, defined names and supporting
# links. This value-only profile does not need any of these records.
PROHIBITED = {0x0006, 0x0206, 0x0406, 0x0221, 0x04BC, 0x0236, 0x002F,
              0x0017, 0x0023, 0x0018, 0x01AE, 0x00D3, 0x005D, 0x00EC, 0x00EB, 0x007F}
CELL_RECORDS = {0x00FD, 0x0204, 0x0203, 0x027E, 0x0201, 0x0205, 0x00D6}


def inspect_biff(stream, width, max_rows):
    offset = 0
    active: int | None = None
    starts: list[int] = []
    bounds: list[int] = []
    record_count = 0
    worksheet_flags = 0
    while offset < len(stream):
        if active is None and not any(stream[offset:]):
            break  # OLE stream padding, not an extra data population.
        if len(stream) - offset < 4:
            raise ValueError("Truncated XLS record header")
        position = offset
        opcode, size = struct.unpack_from("<HH", stream, offset)
        offset += 4
        record_count += 1
        if size > 8224 or offset + size > len(stream) or record_count > 200000:
            raise ValueError("XLS record size or count exceeds the supported bounds")
        record = stream[offset:offset + size]
        offset += size
        if opcode in PROHIBITED:
            raise ValueError("XLS formulas, cached formulas, encryption and supporting links are prohibited")
        if opcode == 0x0809:  # BOF: only BIFF8 globals and one ordinary worksheet.
            if active is not None or size < 8:
                raise ValueError("Invalid XLS substream boundary")
            version, kind = struct.unpack_from("<HH", record)
            if version != 0x0600 or kind != (0x0005 if not starts else 0x0010) or len(starts) >= 2:
                raise ValueError("Only BIFF8 globals and one worksheet are supported")
            active = kind
            starts.append(position)
        elif opcode == 0x000A:
            if size or active is None:
                raise ValueError("Invalid XLS end-of-substream record")
            active = None
        elif active is None:
            raise ValueError("XLS records occur outside a declared substream")
        elif opcode == 0x0085:  # BoundSheet8: flags, sheet type and BOF pointer.
            if active != 0x0005 or size < 8 or record[4] & 3 or record[5] != 0:
                raise ValueError("Hidden, macro, chart and module XLS sheets are unsupported")
            bounds.append(struct.unpack_from("<I", record)[0])
        elif opcode in CELL_RECORDS | {0x00BD, 0x00BE, 0x0208}:
            if active != 0x0010 or size < 4:
                raise ValueError("Invalid XLS cell/row record")
            row, col = struct.unpack_from("<HH", record)
            end_col = struct.unpack_from("<H", record, size - 2)[0] + 1 if opcode in {0x00BD, 0x00BE} else col + 1
            if opcode == 0x0208:
                if size < 6:
                    raise ValueError("Invalid XLS row record")
                end_col = struct.unpack_from("<H", record, 4)[0]
            if row >= max_rows or col >= width or end_col > width:
                raise ValueError("XLS cells exceed the declared table dimensions")
        elif opcode == 0x0200:
            if active != 0x0010 or size < 14:
                raise ValueError("Invalid BIFF8 worksheet dimensions")
            if struct.unpack_from("<I", record, 4)[0] > max_rows or struct.unpack_from("<H", record, 10)[0] > width:
                raise ValueError("XLS dimensions exceed the supported table bounds")
        elif opcode == 0x00FC:
            if size < 8 or max(struct.unpack_from("<II", record)) > width * max_rows:
                raise ValueError("XLS shared-string population exceeds table bounds")
        elif opcode == 0x00E5:
            raise ValueError("Merged XLS cells are unsupported in a controlled text table")
        elif opcode == 0x0081:
            if active != 0x0010 or size != 2 or struct.unpack_from("<H", record)[0] & 0x0010:
                raise ValueError("XLS dialog sheets are unsupported")
            worksheet_flags += 1
    if active is not None or len(starts) != 2 or bounds != [starts[1]] or worksheet_flags != 1:
        raise ValueError("XLS must retain one complete visible worksheet with an exact BOF link")
    return record_count


def validate_xls_container(content, *, width=256, max_rows=65536):
    if len(content) > MAX_BYTES or not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValueError("Retain an original bounded Excel 97-2003 OLE XLS file")
    try:
        with olefile.OleFileIO(io.BytesIO(content), raise_defects=olefile.DEFECT_INCORRECT) as container:
            entries = container.listdir(streams=True, storages=True)
            allowed = {"workbook", "book", "\x05summaryinformation", "\x05documentsummaryinformation"}
            if len(entries) > 4 or any(len(entry) != 1 or entry[0].casefold() not in allowed for entry in entries):
                raise ValueError("XLS extra streams, embedded objects and macro storage are prohibited")
            workbook = [entry for entry in entries if entry[0].casefold() in {"workbook", "book"}]
            if len(workbook) != 1 or not 1 <= container.get_size(workbook[0]) <= MAX_BYTES:
                raise ValueError("Retain exactly one bounded XLS Workbook stream")
            stream = container.openstream(workbook[0]).read(MAX_BYTES + 1)
            if container.parsing_issues:
                raise ValueError("Malformed XLS OLE directory or stream")
        return inspect_biff(stream, width, max_rows)
    except (OSError, EOFError, IndexError, struct.error, UnicodeError) as exc:
        raise ValueError("Invalid or unsupported original XLS container") from exc


def text_table(content, *, width, max_rows):
    records = validate_xls_container(content, width=width, max_rows=max_rows)
    try:
        book = xlrd.open_workbook(file_contents=content, formatting_info=True, on_demand=True, logfile=io.StringIO())
        try:
            if book.biff_version != 80 or book.nsheets != 1:
                raise ValueError("Retain one BIFF8 worksheet for this explicit XLS profile")
            sheet = book.sheet_by_index(0)
            if sheet.visibility or sheet.ncols != width or not 1 <= sheet.nrows <= max_rows or sheet.merged_cells:
                raise ValueError("XLS table visibility or dimensions are unsupported")
            if any(info.hidden for row, info in sheet.rowinfo_map.items() if row < sheet.nrows) or any(info.hidden for col, info in sheet.colinfo_map.items() if col < width):
                raise ValueError("Hidden XLS table rows or columns require an explicit visible source")
            rows = []
            for row in range(sheet.nrows):
                values = []
                for col in range(width):
                    cell = sheet.cell(row, col)
                    if cell.ctype not in {xlrd.XL_CELL_TEXT, xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                        raise ValueError("Every XLS source cell must be text; numeric/date/error/boolean cells are not converted")
                    value = cell.value if cell.ctype == xlrd.XL_CELL_TEXT else ""
                    if len(value) > 4000 or "\x00" in value:
                        raise ValueError("XLS text cell exceeds the source field bound")
                    values.append(value)
                rows.append(values)
            return rows, {"sheet": sheet.name, "physical_rows": sheet.nrows, "columns": width,
                          "biff_version": book.biff_version, "biff_records_checked": records,
                          "cell_policy": "TEXT_ONLY_NO_FORMULA_CACHES_OR_NUMERIC_COERCION"}
        finally:
            book.release_resources()
    except (OSError, EOFError, IndexError, struct.error, UnicodeError, xlrd.XLRDError) as exc:
        raise ValueError("Invalid or unsupported original XLS workbook") from exc
