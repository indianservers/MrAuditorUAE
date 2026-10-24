"""Shared bounded supporting-table normalization for CSV and value-only XLSX."""

from datetime import datetime
from typing import Any

import pycountry

from app.modules.intelligence.documents import money

FIELDS = {
    "reference",
    "currency",
    "amount",
    "open_amount",
    "counterparty",
    "account_code",
    "document_type",
    "segment",
    "date",
    "document_date",
    "due_date",
    "balance_date",
}


def headers(fields, kind, metadata):
    required = (
        {"reference", "currency", "amount", "date"}
        if kind == "bank"
        else {"reference", "currency", "open_amount"}
    )
    if (
        not fields
        or len(fields) > 100
        or len(set(fields)) != len(fields)
        or any(not field or len(field) > 120 for field in fields)
    ):
        raise ValueError(
            "Supporting-table headers must be distinct non-empty names within column bounds"
        )
    if not required <= set(fields):
        raise ValueError("Required supporting-table columns: " + ", ".join(sorted(required)))
    metadata.update(
        original_headers=fields, excluded_columns=[field for field in fields if field not in FIELDS]
    )


def normalize(records, kind, separator, date_format, metadata, spreadsheet_receipt=None):
    output: list[dict[str, Any]] = []
    for number, row in records:
        if number > 20001 or len(output) >= 20000:
            raise ValueError(
                "Supporting table exceeds 20,000 physical/data rows; partition the source"
            )
        if any(value is None or len(str(value)) > 4000 for value in row.values()) or None in row:
            raise ValueError(f"Invalid row {number}: size/column count")
        numeric = (
            spreadsheet_receipt["numeric_columns_by_row"].pop(number, [])
            if spreadsheet_receipt is not None
            else []
        )
        dates = (
            spreadsheet_receipt["date_columns_by_row"].pop(number, [])
            if spreadsheet_receipt is not None
            else []
        )
        item = {
            "id": f"row-{number}",
            "source_row": number,
            "reference": row["reference"],
            "currency": row["currency"].upper(),
            "counterparty": row.get("counterparty") or None,
            "account_code": row.get("account_code") or None,
            "document_type": row.get("document_type") or None,
            "segment": row.get("segment") or "",
        }
        if pycountry.currencies.get(alpha_3=item["currency"]) is None:
            raise ValueError(f"Invalid currency at row {number}")
        for key in ("date", "due_date", "document_date", "balance_date"):
            value = row.get(key)
            if value and key in dates:
                typed = datetime.fromisoformat(value)
                if typed.time() != datetime.min.time() or typed.tzinfo is not None:
                    raise ValueError(
                        "Spreadsheet date cells must contain dates without time or timezone"
                    )
                item[key] = typed.date().isoformat()
            else:
                item[key] = (
                    datetime.strptime(
                        value,
                        {"iso": "%Y-%m-%d", "dmy": "%d/%m/%Y", "mdy": "%m/%d/%Y"}[date_format],
                    )
                    .date()
                    .isoformat()
                    if value
                    else None
                )
        field = "amount" if kind == "bank" else "open_amount"
        item[field] = money(row[field], "." if field in numeric else separator)
        if spreadsheet_receipt is not None:
            item.update(
                source_worksheet=spreadsheet_receipt["sheet"],
                source_amount_storage="ORIGINAL_XLSX_NUMERIC_XML"
                if field in numeric
                else "TEXT_CELL",
            )
        output.append(item)
    if not output:
        raise ValueError("Supporting source is empty")
    if spreadsheet_receipt is not None:
        metadata["normalized_headers"] = metadata["original_headers"]
        metadata["original_headers"] = spreadsheet_receipt["raw_headers"]
        metadata.update(
            excel_epoch=spreadsheet_receipt["excel_epoch"],
            unselected_worksheets=[
                name
                for name in spreadsheet_receipt["available_worksheets"]
                if name != spreadsheet_receipt["sheet"]
            ],
            worksheet=spreadsheet_receipt["sheet"],
            numeric_basis="ORIGINAL_XML_DECIMALS_NOT_FLOAT_ROUNDTRIP",
        )
    return output
