import io
import struct
import uuid

import olefile
import pytest
import xlrd
import xlwt

from app.modules.audit_execution.evidence import validate_file
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from app.modules.ingestion.legacy_xls import text_table, validate_xls_container

HEADERS = ["IP Number (10 Digits)", "IP Name (Only alphabets and space)",
    "No of Days for which wages paid/payable during the month", "Total Monthly Wages",
    "Reason Code for Zero working days (numeric only; provide 0 for all other reasons)",
    "Last Working Day (Format DD-MM-YYYY)"]


def member_rows():
    return [["0012345678", "SYNTHETIC MEMBER ONE", "25", "10000", "0", ""],
            ["0012345679", "SYNTHETIC MEMBER TWO", "0", "0", "6", "02/06/2026"]]


def workbook(rows=None, headers=None, configure=None):
    book = xlwt.Workbook()
    sheet = book.add_sheet("SYNTHETIC ESIC")
    style = xlwt.easyxf("alignment: wrap on, vert centre;", num_format_str="@")
    for col, value in enumerate(HEADERS if headers is None else headers):
        sheet.write(0, col, value, style)
        sheet.col(col).width = (24 if col != 1 else 30) * 256
    sheet.row(0).height = 1000
    for row_index, values in enumerate(member_rows() if rows is None else rows, 1):
        for col, value in enumerate(values):
            sheet.write(row_index, col, value, style)
    if configure:
        configure(book, sheet)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def parameters(**changes):
    return SourceInput.model_validate({"file_format": "india-esic-members-xls", "table_type": "esic-members",
        "evidence_version_id": uuid.uuid4(), "esic_context_evidence_version_id": uuid.uuid4(),
        "employer_registration": "00123456789012345", "obligation_period": "2026-06", "esic_return_kind": "monthly",
        "esic_scope_assessment": "Independent fictional employer/month and original member wage workbook assessment",
        "label": "SYNTHETIC original ESIC XLS", "expected_rows": 2, "control_totals": {"INR": "10000"},
        "esic_paid_days_control": 25, "esic_zero_wage_members_control": 1, **changes})


def parse(content=None, **changes):
    return parse_native(workbook() if content is None else content, parameters(**changes), "IN", "SYNTHETIC-esic.xls")


def mutate_record(content, opcode, mutate):
    output = io.BytesIO(content)
    with olefile.OleFileIO(output, write_mode=True) as container:
        stream = bytearray(container.openstream("Workbook").read())
        offset = 0
        while offset + 4 <= len(stream):
            record, size = struct.unpack_from("<HH", stream, offset)
            if record == opcode:
                mutate(stream, offset + 4, size)
                container.write_stream("Workbook", bytes(stream))
                break
            offset += 4 + size
        else:
            raise AssertionError("Synthetic test record was not present")
    return output.getvalue()


def test_native_xls_preserves_text_id_cells_and_both_reason_meanings():
    data = parse()
    assert data["row_count"] == 2 and data["control_totals"] == {"INR": "10000"}
    assert data["allowed_source_roles"] == ["reported"] and data["allowed_workflows"] == ["india-esic-population"]
    first, zero = data["rows"]
    assert first["subject"] == "0012345678" and first["source_text_cells"]["A2"] == "0012345678"
    assert first["zero_day_reason"] == first["zero_wage_reason"] == "" and first["source_zero_day_reason"] == "0"
    assert zero["zero_day_reason"] == zero["zero_wage_reason"] == "6"
    assert zero["last_working_day"] == "2026-06-02" and zero["source_text_cells"]["F3"] == "02/06/2026"
    assert data["native_metadata"]["population_controls"] == {"paid_days": 25, "zero_wage_members": 1}
    assert validate_file(io.BytesIO(workbook()), "SYNTHETIC.xls") == "application/vnd.ms-excel"
    assert data["statutory_calculation_qualified"] is False


def test_zero_days_with_positive_wages_preserves_day_reason_without_inventing_zero_wages():
    rows = member_rows()[:1]
    rows[0][2], rows[0][4] = "0", "6"
    data = parse(workbook(rows), expected_rows=1, esic_paid_days_control=0, esic_zero_wage_members_control=0)
    assert data["rows"][0]["zero_day_reason"] == "6" and data["rows"][0]["zero_wage_reason"] == ""


def test_cached_numeric_formula_is_rejected_before_reader_can_accept_its_result():
    rows = member_rows()
    rows[0][3] = xlwt.Formula("1+1")
    content = mutate_record(workbook(rows), 0x0006, lambda stream, offset, size: struct.pack_into("<d", stream, offset + 6, 999.0))
    book = xlrd.open_workbook(file_contents=content)
    assert book.sheet_by_index(0).cell_value(1, 3) == 999.0
    with pytest.raises(ValueError, match="formulas"):
        parse(content)
    with pytest.raises(ValueError, match="formulas"):
        validate_file(io.BytesIO(content), "cached.xls")


@pytest.mark.parametrize("column,value", [(0, 12345678), (2, 25), (3, 10000.0), (4, True)])
def test_native_numeric_boolean_and_date_coercion_are_not_permitted(column, value):
    rows = member_rows()
    rows[0][column] = value
    with pytest.raises(ValueError, match="Every XLS source cell must be text"):
        parse(workbook(rows))


@pytest.mark.parametrize("change,error", [
    ({"esic_paid_days_control": 24}, "paid-day"), ({"esic_zero_wage_members_control": 0}, "zero-wage"),
    ({"control_totals": {"INR": "9999"}}, "currency control"), ({"expected_rows": 1}, "row-count"),
])
def test_native_independent_controls_are_all_enforced(change, error):
    with pytest.raises(ValueError, match=error):
        parse(**change)


@pytest.mark.parametrize("configure,error", [
    (lambda book, sheet: setattr(sheet, "visibility", 1), "Hidden"),
    (lambda book, sheet: setattr(sheet.row(1), "hidden", 1), "Hidden XLS table rows"),
    (lambda book, sheet: setattr(sheet.col(0), "hidden", 1), "Hidden XLS table rows"),
    (lambda book, sheet: book.add_sheet("Other"), "one worksheet"),
])
def test_hidden_or_additional_populations_are_not_silently_discarded(configure, error):
    with pytest.raises(ValueError, match=error):
        parse(workbook(configure=configure))


def test_header_order_blank_gaps_duplicates_and_dates_are_checked():
    with pytest.raises(ValueError, match="header order"):
        parse(workbook(headers=[HEADERS[1], HEADERS[0], *HEADERS[2:]]))
    with pytest.raises(ValueError, match="Blank gaps"):
        parse(workbook([member_rows()[0], [""] * 6, member_rows()[1]]))
    with pytest.raises(ValueError, match="Duplicate ESIC"):
        parse(workbook([member_rows()[0], member_rows()[0]]))
    rows = member_rows()
    rows[1][5] = "2/6/2026"
    with pytest.raises(ValueError, match="padded"):
        parse(workbook(rows))
    assert parse(workbook([*member_rows(), [""] * 6]))["native_metadata"]["trailing_blank_rows"] == 1


@pytest.mark.parametrize("opcode,mutator,error", [
    (0x0085, lambda stream, offset, size: stream.__setitem__(offset + 5, 6), "module"),
    (0x0085, lambda stream, offset, size: struct.pack_into("<I", stream, offset, 1), "BOF link"),
    (0x0081, lambda stream, offset, size: struct.pack_into("<H", stream, offset, 0x0010), "dialog"),
    (0x0200, lambda stream, offset, size: struct.pack_into("<I", stream, offset + 4, 65536), "dimensions"),
    (0x00FC, lambda stream, offset, size: struct.pack_into("<I", stream, offset, 0xFFFFFFFF), "shared-string"),
    (0x0809, lambda stream, offset, size: struct.pack_into("<H", stream, offset, 0x0500), "BIFF8"),
])
def test_biff_structure_is_checked_before_materializing_cells(opcode, mutator, error):
    with pytest.raises(ValueError, match=error):
        parse(mutate_record(workbook(), opcode, mutator))


def test_native_scope_and_original_container_cannot_be_guessed():
    for change in ({"esic_context_evidence_version_id": None}, {"employer_registration": "123"},
                   {"obligation_period": "0000-06"}, {"esic_return_kind": None}):
        with pytest.raises(ValueError):
            parameters(**change)
    with pytest.raises(ValueError, match="unavailable"):
        parse_native(workbook(), parameters(), "AE", "SYNTHETIC.xls")
    with pytest.raises(ValueError, match="filename"):
        parse_native(workbook(), parameters(), "IN", "SYNTHETIC.xlsx")
    with pytest.raises(ValueError, match="original bounded"):
        text_table(b"not an XLS workbook", width=6, max_rows=5001)


def test_maximum_population_and_explicit_nil_source_are_controlled():
    rows = [[f"{index:010d}", "SYNTHETIC MEMBER", "25", "1", "0", ""] for index in range(5000)]
    data = parse(workbook(rows), expected_rows=5000, control_totals={"INR": "5000"}, esic_paid_days_control=125000, esic_zero_wage_members_control=0)
    assert len(data["rows"]) == 5000 and data["rows"][-1]["subject"] == "0000004999"
    nil = parse(workbook([]), expected_rows=0, control_totals={"INR": "0"}, esic_paid_days_control=0, esic_zero_wage_members_control=0,
        nil_reason="SYNTHETIC independently assessed nil member workbook")
    assert nil["rows"] == [] and nil["control_totals"] == {"INR": "0"}
    with pytest.raises(ValueError, match="bounded"):
        validate_xls_container(b"x" * (10 * 1024 * 1024 + 1))
