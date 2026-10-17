import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.accounting.calculations import movements, reconcile, trial_balance
from app.modules.accounting.schemas import ImportOptions
from app.modules.audit_analytics.sampling import select_items
from app.modules.ingestion.parser import (
    ImportProblem,
    map_headers,
    money,
    normalize,
    rows,
    safe_cell,
)


@pytest.fixture
def options():
    return ImportOptions(client_id=uuid.uuid4(), entity_id=uuid.uuid4(), period_id=uuid.uuid4())


@pytest.mark.parametrize(
    "text,separator,expected",
    [
        ("1,234.56", ".", "1234.56"),
        ("1.234,56", ",", "1234.56"),
        ("(0.01)", ".", "-0.01"),
        ("0.10000001", ".", "0.10000001"),
        ("", ".", "0"),
    ],
)
def test_money(text, separator, expected):
    assert money(text, separator) == Decimal(expected)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "12,34", "1.000000001", "1e40", "=SUM(A1)"])
def test_bad_money(text):
    with pytest.raises(ImportProblem):
        money(text)


def raw(**kwargs):
    return {
        "Account Code": "100",
        "Journal Number": "J1",
        "Posting Date": "2026-01-01",
        "Debit": "0.10",
        "Credit": "0",
        "Source ID": "line1",
        **kwargs,
    }


def test_normalize_sign_and_currency(options):
    normalized, warnings = normalize(raw(), options, date(2026, 1, 1), date(2026, 12, 31), "AED", 2)
    assert normalized["base_debit"] == "0.10" and not warnings
    with pytest.raises(ImportProblem):
        normalize(raw(Currency="USD"), options, date(2026, 1, 1), date(2026, 12, 31), "AED", 2)
    normalized, _ = normalize(
        raw(Currency="USD", **{"Exchange Rate": "3.6725"}),
        options,
        date(2026, 1, 1),
        date(2026, 12, 31),
        "AED",
        2,
    )
    assert Decimal(normalized["base_debit"]) == Decimal("0.36725")


@pytest.mark.parametrize(
    "change",
    [
        {"Account Code": ""},
        {"Posting Date": "bad"},
        {"Posting Date": "2025-12-31"},
        {"Credit": "1"},
        {"Debit": "-1"},
        {"Currency": "ZZZ"},
        {"Posting Timestamp": "2026-01-01T11:00:00"},
    ],
)
def test_bad_normalization(options, change):
    with pytest.raises(ImportProblem):
        normalize(raw(**change), options, date(2026, 1, 1), date(2026, 12, 31), "AED", 2)


def test_signed_and_tb_only(options):
    options = options.model_copy(update={"signed_convention": "credit_positive"})
    row = {"Account Code": "1", "Amount": "-5", "Journal Number": "J", "Posting Date": "2026-01-01"}
    result, warnings = normalize(row, options, date(2026, 1, 1), date(2026, 12, 31), "AED", 2)
    assert result["debit"] == "5" and warnings
    options = options.model_copy(update={"kind": "tb"})
    result, _ = normalize(
        {
            "Account Code": "1",
            "Debit": "10",
            "Credit": "5",
            "Opening Balance": "2",
            "Closing Balance": "7",
        },
        options,
        date(2026, 1, 1),
        date(2026, 12, 31),
        "AED",
        2,
    )
    assert result["closing_balance"] == "7"


def test_tb_exact_and_opening():
    data = [
        {
            "account_code": "100",
            "functional_currency": "AED",
            "base_debit": "0.10",
            "base_credit": "0",
            "opening": True,
        },
        {
            "account_code": "100",
            "functional_currency": "AED",
            "base_debit": "0.20",
            "base_credit": "0",
        },
        {
            "account_code": "100",
            "functional_currency": "AED",
            "base_debit": "0",
            "base_credit": "0.05",
        },
    ]
    result = trial_balance(data, "AED")[0]
    assert result["closing"] == Decimal("0.25") and result["opening"] == Decimal("0.10")
    with pytest.raises(ValueError):
        trial_balance(data, "USD")
    assert reconcile({"100": Decimal("0.25")}, {"100": result["closing"]})["status"] == "passed"
    assert reconcile({"100": Decimal("0.30")}, {"100": result["closing"]})["status"] == "failed"
    assert movements({"a": Decimal(20)}, {"a": Decimal(10)})[0]["percentage"] == "100"


@pytest.mark.parametrize("method", ["random", "systematic", "mus", "high_value", "risk", "full"])
def test_sampling_reproducibility(method):
    pop = [{"id": str(i), "amount": str(i - 2), "risk": i} for i in range(30)]
    first = select_items(iter(pop), method, 5, 42, Decimal(20))
    second = select_items(iter(pop), method, 5, 42, Decimal(20))
    assert first == second and first["selected"]
    if method == "mus":
        assert (
            first["excluded_negative"] == 2
            and first["excluded_zero"] == 1
            and sum(i["hits"] for i in first["selected"]) == 5
        )


def test_invalid_sampling():
    with pytest.raises(ValueError):
        select_items([{"id": "0", "amount": "0"}], "mus", 5, 0)
    with pytest.raises(ValueError):
        select_items([], "unknown", 5, 0)
    with pytest.raises(ValueError):
        select_items([], "random", 0, 0)


def test_csv_mapping_and_security(tmp_path, options):
    path = tmp_path / "data.csv"
    path.write_text("Ledger Code;Balance\nA;1.234,56\n")
    options = options.model_copy(update={"delimiter": ";", "decimal_separator": ","})
    assert list(rows(path, path.name, options))[0][1]["Balance"] == "1.234,56"
    assert safe_cell("=SUM(A1)").startswith("'")
    with pytest.raises(ImportProblem):
        map_headers(["Account Code", "Account Code"], {})
    with pytest.raises(ImportProblem):
        map_headers(["unknown"], {})
    with pytest.raises(ImportProblem):
        map_headers(["Account Code"], {"bad": "Account Code"})


def test_xlsx_multisheet_and_corruption(tmp_path, options):
    from openpyxl import Workbook

    path = tmp_path / "test.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.append(["Account Code", "Debit"])
    sheet.append(["100", 10])
    book.create_sheet("Other")
    book.save(path)
    with pytest.raises(ImportProblem):
        list(rows(path, path.name, options))
    assert len(list(rows(path, path.name, options.model_copy(update={"sheet": sheet.title})))) == 1
    sheet["B2"] = "=1+2"
    book.save(path)
    with pytest.raises(ImportProblem):
        list(rows(path, path.name, options.model_copy(update={"sheet": sheet.title})))
    path.write_bytes(b"corrupt")
    with pytest.raises(ImportProblem):
        list(rows(path, path.name, options))


@pytest.mark.parametrize("entry", ["xl/vbaProject.bin", "xl/externalLinks/link.xml", "large.xml"])
def test_excel_malicious_archive(tmp_path, options, entry):
    import zipfile

    path = tmp_path / "malicious.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry, b"0" * (1100000 if entry == "large.xml" else 10))
    with pytest.raises(ImportProblem):
        list(rows(path, path.name, options))


def test_alternate_csv_encoding_and_dates(tmp_path, options):
    path = tmp_path / "source.csv"
    path.write_bytes(
        "Account Code,Account Name,Posting Date,Journal Number,Debit,Credit\nA,Café,31/12/2026,J,1,0\n".encode(
            "cp1252"
        )
    )
    configured = options.model_copy(update={"encoding": "cp1252", "date_format": "%d/%m/%Y"})
    index, source = list(rows(path, path.name, configured))[0]
    canonical, _ = normalize(source, configured, date(2026, 1, 1), date(2026, 12, 31), "AED", index)
    assert canonical["account_name"] == "Café" and canonical["posting_date"] == "2026-12-31"
    with pytest.raises(ImportProblem):
        list(rows(path, "source.exe", options))


def test_fx_conflicting_base_and_contra_precision(options):
    with pytest.raises(ImportProblem):
        normalize(
            raw(
                Currency="USD", **{"Exchange Rate": "3.67", "Base Debit": "100", "Base Credit": "0"}
            ),
            options,
            date(2026, 1, 1),
            date(2026, 12, 31),
            "AED",
            2,
        )
    result = trial_balance(
        [
            {
                "account_code": "C",
                "functional_currency": "AED",
                "base_debit": "0",
                "base_credit": "0.015",
                "opening": False,
            }
        ],
        "AED",
        precision=2,
        rounding="ROUND_HALF_UP",
    )
    assert result[0]["closing"] == Decimal("-0.02")
