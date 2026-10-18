import csv
import io

import pytest
from openpyxl import Workbook

from app.modules.tp.imports import parse


def source():
    return {
        "company_key": "SYN-A",
        "name": "SYNTHETIC independent fixture",
        "country": "AE",
        "industry": "Synthetic",
        "fiscal_year": 2026,
        "currency": "AED",
        "revenue": "100",
        "cost_sales": "80",
        "opex": "5",
        "assets": "100",
        "value": ".05",
        "activity": "Synthetic distribution",
        "independence": "Reviewed synthetic",
        "related_party_exposure": "None in fixture",
        "extraordinary_events": "None in fixture",
        "observation_date": "2026-10-18",
    }


def csv_bytes(body):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=body)
    writer.writeheader()
    writer.writerow(body)
    return stream.getvalue().encode()


def test_csv_and_xlsx_preserve_the_same_observations_and_hash():
    body = source()
    wb = Workbook()
    ws = wb.active
    ws.append(list(body))
    ws.append(list(body.values()))
    stream = io.BytesIO()
    wb.save(stream)
    csv_rows = parse(csv_bytes(body), "source.csv")
    xlsx_rows = parse(stream.getvalue(), "source.xlsx")
    assert csv_rows[0][0] == xlsx_rows[0][0]
    assert csv_rows[0][1] == xlsx_rows[0][1]


@pytest.mark.parametrize(
    "field,value", [("revenue", "NaN"), ("value", "Infinity"), ("name", "=HYPERLINK(1)")]
)
def test_nonfinite_and_formula_observations_are_rejected(field, value):
    body = source()
    body[field] = value
    with pytest.raises(ValueError):
        parse(csv_bytes(body), "source.csv")


def test_duplicate_columns_and_duplicate_company_year_are_rejected():
    with pytest.raises(ValueError, match="column"):
        parse(b"company_key,company_key\nA,B\n", "source.csv")
    data = csv_bytes(source())
    with pytest.raises(ValueError, match="Duplicate company/year"):
        parse(data + data.splitlines(keepends=True)[1], "source.csv")
