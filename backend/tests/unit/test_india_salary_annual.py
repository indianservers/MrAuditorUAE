"""Entirely synthetic Q4 completion; the unchanged issuer sample remains separate."""

import hashlib
from uuid import uuid4

import pytest

from app.modules.country_workflows.india_salary_annual import PROFILE, SPEC_SHA256, annual_layout
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_24q_native import controls24, original24
from tests.unit.test_india_withholding_native import ROOT, edit


def q4_fixture(year=2024, restricted=False, pension=True):
    pension = pension and year >= 2021
    restricted = restricted and year >= 2020
    flag = ("N" if restricted else "Y") if year >= 2023 else ("Y" if restricted else "N")
    standard = 0 if restricted and year < 2023 else 5000 if year >= 2018 else 500
    other = 0 if restricted else -1000
    other_sources = 2000 if year >= 2018 else 0
    gross = 100000 - standard + other + other_sources
    section = (
        []
        if not standard
        else [
            ["", "S16", "1", "1", "1", "16(ia)" if year >= 2018 else "16(ii)", f"{standard}.00", ""]
        ]
    )
    chapter_code = "80CCD(2)" if restricted else "80C" if year >= 2018 else "80CCE"
    chapter = [
        "",
        "C6A",
        "1",
        "1",
        "1",
        chapter_code,
        "1000.00",
        "2000.00" if year >= 2018 else "",
        "",
        "",
    ]
    sd = [""] * 88
    values = {
        2: "SD",
        3: "1",
        4: "1",
        5: "A",
        7: "AAAPA1234A",
        9: "SYNTHETIC employee",
        10: "G",
        11: f"0104{year}",
        12: f"3103{year + 1}",
        13: "100000.00",
        15: str(len(section)),
        16: f"{standard}.00",
        17: f"{100000 - standard}.00",
        18: f"{other}.00",
        19: f"{gross}.00",
        21: "1",
        22: "1000.00",
        23: f"{gross - 1000}.00",
        24: "10000.00",
        25: "0.00",
        26: "400.00",
        27: "0.00",
        28: "10400.00",
        29: "12000.00",
        30: "-1600.00",
    }
    if year >= 2013:
        values.update({34: "100000.00", 35: "0.00", 36: "12000.00", 37: "0.00", 38: "N", 59: "N"})
    if year >= 2015:
        values.update({39: "N", 40: "0", 49: "N", 50: "0"})
    if year >= 2018:
        values.update(
            {
                31: "0.00" if restricted else "1000.00",
                67: "100000.00",
                68: "0.00",
                69: "0.00",
                71: "0.00",
                72: "0.00",
                73: "0.00",
                75: "0.00",
                76: "0.00",
                77: "2000.00",
                78: "0.00",
            }
        )
        if not restricted:
            values.update({70: "0.00", 74: "0.00"})
    if year >= 2020:
        values[79] = flag
    if year >= 2023:
        values[80] = "0.00"
    if year >= 2024:
        values[81] = "0.00"
    for number, value in values.items():
        sd[number - 1] = value
    annual = [sd, *section, chapter]
    pension_gross = pension_taxable = pension_net = 0
    psection = []
    pchapter = []
    if pension:
        pension_deduction = 0 if restricted and year < 2023 else 2000
        pension_chapter = 0 if restricted else 500
        pension_gross = 51000 - pension_deduction
        pension_taxable = pension_gross - pension_chapter
        pension_net = 1030
        parent = [""] * 28
        for number, value in {
            2: "94P",
            3: "1",
            4: "1",
            5: "A",
            6: "BBBPB1234B",
            7: "SYNTHETIC senior",
            8: "S",
            9: flag,
            10: "50000.00",
            11: "1" if pension_deduction else "0",
            12: f"{pension_deduction}.00",
            13: f"{50000 - pension_deduction}.00",
            14: "1000.00",
            15: f"{pension_gross}.00",
            17: f"{pension_chapter}.00",
            18: "1" if pension_chapter else "0",
            19: f"{pension_chapter}.00",
            20: f"{pension_taxable}.00",
            21: "1000.00",
            22: "0.00",
            23: "0.00",
            24: "40.00",
            25: "1040.00",
            26: "10.00",
            27: "1030.00",
        }.items():
            parent[number - 1] = value
        if pension_deduction:
            psection = [["", "P16", "1", "1", "1", "16(ia)", f"{pension_deduction}.00", ""]]
        if pension_chapter:
            pchapter = [["", "P6A", "1", "1", "1", "80C", "700.00", "", "500.00", ""]]
        annual += [parent, *psection, *pchapter]
    raw = original24()
    for line, field, value in [
        (1, 5, f"0104{year + 1}"),
        (2, 16, f"{year + 1}{(year + 2) % 100:02}"),
        (2, 17, f"{year}{(year + 1) % 100:02}"),
        (2, 18, "Q4"),
        (2, 49, "1"),
        (2, 50, f"{gross}.00"),
        (2, 70, "1" if pension else "0"),
        (2, 71, f"{pension_gross}.00"),
        (3, 18, f"1402{year + 1}"),
        (4, 23, f"1602{year + 1}"),
        (4, 24, f"1602{year + 1}"),
        (4, 25, f"1402{year + 1}"),
    ]:
        raw = edit(raw, line, field, value)
    for i, f in enumerate(annual, 5):
        f[0] = str(i)
    raw += ("\r\n".join("^".join(f) for f in annual) + "\r\n").encode()
    native = controls24()
    native.update(financial_year=f"{year}{(year + 1) % 100:02}", quarter="Q4")
    native["groups"][0].update(period=f"{year + 1}-02", transaction_date=f"{year + 1}-02-16")
    controls = {
        "record_counts": {
            "SD": 1,
            "S16": len(section),
            "C6A": 1,
            "94P": int(pension),
            "P16": len(psection),
            "P6A": len(pchapter),
        },
        "salary_gross_income": str(gross),
        "salary_taxable_income": str(gross - 1000),
        "salary_net_tax_payable": "10400",
        "salary_tax_deducted": "12000",
        "salary_shortfall": "-1600",
        "pension_gross_income": str(pension_gross),
        "pension_taxable_income": str(pension_taxable),
        "pension_net_tax_payable": str(pension_net),
        "assessment": "SYNTHETIC independently specified annual salary and specified-senior population and arithmetic, not issuer/client or tax qualification",
    }
    return raw, native, controls


def options_q4(native=None, annual=None, **changes):
    _, n, a = q4_fixture()
    return SourceInput.model_validate(
        {
            "file_format": PROFILE,
            "evidence_version_id": str(uuid4()),
            "table_type": "withholding-records",
            "label": "SYNTHETIC complete annual Q4 observations",
            "expected_rows": 1,
            "control_totals": {"INR": "1000"},
            "native_withholding_controls": native or n,
            "salary_annual_controls": annual if annual is not None else a,
            **changes,
        }
    )


def parse(raw=None, native=None, annual=None):
    return parse_native(
        raw if raw is not None else q4_fixture()[0],
        options_q4(native, annual),
        "IN",
        "SYNTHETIC-q4.txt",
    )


def test_complete_annual_population_and_signed_excess_preserve_all_numbered_fields():
    result = parse()
    m = result["native_metadata"]["salary_annual"]
    assert len(m["records"]) == 6
    assert m["totals"]["salary_gross_income"] == "96000.00"
    assert m["totals"]["salary_shortfall"] == "-1600.00"
    assert m["totals"]["pension_gross_income"] == "49000.00"
    assert m["totals"]["pension_net_tax_payable"] == "1030.00"
    assert [len(r["fields"]) for r in m["records"]] == [88, 8, 10, 28, 8, 10]
    assert m["records"][0]["fields"][17] == "-1000.00"
    assert m["records"][-1]["fields"][6] == "700.00"
    assert m["records"][-1]["fields"][8] == "500.00"
    assert result["native_metadata"]["fvu_validation"] == "NOT_PERFORMED"
    assert (
        result["row_count"] == 1
    )  # Annual observations are not double-counted as quarterly TDS rows.


@pytest.mark.parametrize("year", [2011, 2013, 2018, 2019, 2020, 2022, 2023, 2024, 2025])
@pytest.mark.parametrize("restricted", [False, True])
def test_period_and_recorded_regime_change_the_supported_components(year, restricted):
    raw, native, annual = q4_fixture(year, restricted)
    assert (
        parse(raw, native, annual)["native_metadata"]["salary_annual"]["record_counts"]
        == annual["record_counts"]
    )


@pytest.mark.parametrize(
    "line,field,value,reason",
    [
        (2, 49, "0", "batch salary count"),
        (2, 50, "0.00", "batch salary gross"),
        (2, 70, "0", "specified-senior count"),
        (2, 71, "0.00", "specified-senior gross"),
        (5, 3, "2", "batch"),
        (5, 4, "2", "parent serial"),
        (5, 5, "C", "mode"),
        (5, 7, "badpan", "PAN"),
        (5, 10, "X", "category"),
        (5, 12, "01012024", "employment"),
        (5, 14, "0", "reserved"),
        (5, 15, "0", "section-16 count"),
        (5, 16, "0.00", "section-16 total"),
        (5, 17, "1.00", "chargeable"),
        (5, 19, "1.00", "gross income"),
        (5, 21, "0", "chapter-VIA count"),
        (5, 22, "0.00", "chapter-VIA total"),
        (5, 23, "1.00", "taxable"),
        (5, 28, "1.00", "net tax"),
        (5, 29, "1.00", "annual deducted"),
        (5, 30, "1600.00", "signed"),
        (5, 31, "0.00", "aggregate"),
        (5, 38, "", "flags"),
        (5, 39, "", "rent"),
        (5, 40, "1", "flag"),
        (5, 41, "AAAPA1234A", "flag"),
        (5, 59, "NONSENSE", "width"),
        (5, 60, "name", "superannuation"),
        (5, 67, "1.00", "gross salary"),
        (5, 76, "1.00", "exemption"),
        (5, 79, "", "regime"),
        (5, 82, "0", "width"),
        (6, 4, "2", "parent identity"),
        (6, 5, "2", "sequence"),
        (6, 6, "unknown", "identifier"),
        (7, 7, "2001.00", "gross"),
        (8, 6, "PANINVALIDX", "width"),
        (8, 9, "", "regime"),
        (8, 11, "0", "section-16 count"),
        (8, 12, "1.00", "section-16 total"),
        (8, 13, "1.00", "chargeable"),
        (8, 15, "1.00", "gross income"),
        (8, 18, "0", "chapter-VIA count"),
        (8, 19, "1.00", "chapter-VIA total"),
        (8, 20, "1.00", "taxable"),
        (8, 25, "1.00", "tax payable"),
        (10, 4, "2", "parent identity"),
    ],
)
def test_invalid_annual_records_are_not_silently_ignored(line, field, value, reason):
    with pytest.raises(ValueError, match=reason):
        parse(edit(q4_fixture()[0], line, field, value))


@pytest.mark.parametrize(
    "key",
    [
        "salary_gross_income",
        "salary_taxable_income",
        "salary_net_tax_payable",
        "salary_tax_deducted",
        "salary_shortfall",
        "pension_gross_income",
        "pension_taxable_income",
        "pension_net_tax_payable",
    ],
)
def test_each_independent_annual_amount_control_is_enforced(key):
    raw, n, a = q4_fixture()
    a[key] = "1"
    with pytest.raises(ValueError, match="independent"):
        parse(raw, n, a)


def test_public_q4_sample_is_preserved_and_rejected_instead_of_widened():
    with pytest.raises(ValueError, match="field count"):
        parse((ROOT / "protean-24Q-Q4-original-sample.txt").read_bytes())


def test_all_six_record_counts_and_explicit_q4_scope_are_required():
    raw, n, a = q4_fixture()
    a["record_counts"].pop("P6A")
    with pytest.raises(ValueError, match="all six"):
        options_q4(n, a)
    _, n, a = q4_fixture()
    n["quarter"] = "Q3"
    with pytest.raises(ValueError, match="Q4"):
        options_q4(n, a)
    with pytest.raises(ValueError):
        options_q4(salary_annual_controls=None)


def test_all_ten_record_widths_are_bound_to_the_unchanged_issuer_workbook():
    assert hashlib.sha256((ROOT / "protean-24Q-Q4-7.5.xls").read_bytes()).hexdigest() == SPEC_SHA256
    layout, _ = annual_layout()
    assert {tag: len(values) for tag, values in layout["field_lengths"].items()} == {
        "FH": 18,
        "BH": 72,
        "CD": 41,
        "DD": 54,
        "SD": 88,
        "S16": 8,
        "C6A": 10,
        "94P": 28,
        "P16": 8,
        "P6A": 10,
    }


def test_recorded_superannuation_remains_separate_and_enters_the_explicit_annual_total():
    raw, n, a = q4_fixture()
    for field, value in [
        (59, "Y"),
        (60, "SYNTHETIC fund"),
        (61, "01042022"),
        (62, "31032025"),
        (63, "10000.00"),
        (64, "2.0000"),
        (65, "500.00"),
        (66, "106000.00"),
        (29, "12500.00"),
        (30, "-2100.00"),
    ]:
        raw = edit(raw, 5, field, value)
    a.update(salary_tax_deducted="12500", salary_shortfall="-2100")
    annual = parse(raw, n, a)["native_metadata"]["salary_annual"]
    assert annual["totals"]["salary_shortfall"] == "-2100.00"
    assert annual["records"][0]["fields"][63] == "2.0000"


def test_declared_landlord_and_lender_populations_preserve_exact_source_identities():
    raw, n, a = q4_fixture()
    for field, value in [
        (39, "Y"),
        (40, "2"),
        (41, "AAAPA1234A"),
        (42, "SYNTHETIC landlord"),
        (43, "GOVERNMENT"),
        (44, "SYNTHETIC public landlord"),
        (49, "Y"),
        (50, "1"),
        (51, "BBBPB1234B"),
        (52, "SYNTHETIC lender"),
    ]:
        raw = edit(raw, 5, field, value)
    record = parse(raw, n, a)["native_metadata"]["salary_annual"]["records"][0]
    assert record["fields"][42] == "GOVERNMENT" and record["fields"][50] == "BBBPB1234B"
    with pytest.raises(ValueError, match="population"):
        parse(edit(raw, 5, 40, "3"), n, a)
