"""Streaming file readers and exact normalization. Source values are never evaluated."""

import csv
import io
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

import pycountry
from openpyxl import load_workbook

from app.modules.accounting.schemas import ImportOptions


class ImportProblem(ValueError):
    pass


ALIASES = {
    "account_code": ["account code", "ledger code", "gl account", "account_code", "ledgername"],
    "account_name": ["account name", "ledger name", "account_name"],
    "journal_ref": ["voucher number", "journal number", "journal_ref", "reference"],
    "posting_date": ["posting date", "transaction date", "posting_date", "date"],
    "document_date": ["document date", "document_date"],
    "description": ["description", "narration"],
    "debit": ["debit", "dr"],
    "credit": ["credit", "cr"],
    "amount": ["amount", "balance"],
    "currency": ["currency"],
    "source_id": ["source id", "source_id", "line id"],
    "opening_balance": ["opening balance", "opening_balance"],
    "closing_balance": ["closing balance", "closing_balance"],
    "exchange_rate": ["exchange rate", "exchange_rate"],
    "base_debit": ["base debit", "base_debit"],
    "base_credit": ["base credit", "base_credit"],
    "opening": ["opening"],
    "counterparty": ["counterparty"],
    "cost_center": ["cost center", "cost_center"],
    "department": ["department"],
    "project": ["project"],
    "tax_code": ["tax code", "tax_code"],
    "related_party": ["related party", "related_party"],
    "reversal_ref": ["reversal reference", "reversal_ref"],
    "manual": ["manual"],
    "posting_timestamp": ["posting timestamp", "posting_timestamp"],
    "user": ["user"],
    "source_group": ["source group", "source_group"],
    "category": ["category"],
    "parent_code": ["parent code", "parent_code"],
}


def map_headers(headers: list[str], custom: dict[str, str]) -> dict[str, str]:
    if len(set(headers)) != len(headers):
        raise ImportProblem("Duplicate column headings")
    mapping = {}
    for canonical, aliases in ALIASES.items():
        matches = [h for h in headers if h.strip().lower() in aliases]
        if len(matches) > 1 and canonical not in custom:
            raise ImportProblem("Ambiguous columns for " + canonical)
        if matches:
            mapping[canonical] = matches[0]
    for key, value in custom.items():
        if key not in ALIASES or value not in headers:
            raise ImportProblem("Invalid mapping column: " + key)
        mapping[key] = value
    if "account_code" not in mapping:
        raise ImportProblem("Missing required column: account_code")
    return mapping


def safe_cell(value: object) -> str:
    text = str(value) if value is not None else ""
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def rows(path: Path, filename: str, options: ImportOptions) -> Iterator[tuple[int, dict[str, str]]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".json" and options.source_system == "quickbooks":
        import json
        from app.modules.connectors.quickbooks_desktop import package_rows as desktop_rows

        if path.stat().st_size > 64 * 1024 * 1024:
            raise ImportProblem("Desktop SDK package exceeds import limit; narrow the selected period")
        for index, row in enumerate(desktop_rows(json.loads(path.read_bytes()), options), 2):
            yield index, row
    elif suffix == ".ndjson" and options.source_system == "tally":
        from app.modules.connectors.tally_windows import package_rows

        if not options.tally_company:
            raise ImportProblem("Tally company must be explicitly selected")
        for index, row in enumerate(package_rows(path, options), 2):
            yield index, row
    elif suffix in {".xml", ".json"} and options.source_system == "tally":
        from app.modules.connectors.tally import parse_export

        if not options.tally_company:
            raise ImportProblem("Tally company must be explicitly selected")
        if suffix == ".json":
            import base64
            import json
            from xml.etree.ElementTree import Element, tostring

            from defusedxml.ElementTree import fromstring

            package = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(package, dict)
                or not isinstance(package.get("exports"), dict)
                or not package["exports"]
            ):
                raise ImportProblem("Invalid Tally package: native exports are required")
            if package.get("company", options.tally_company) != options.tally_company:
                raise ImportProblem("Tally package company does not match selected company")
            root = Element("ENVELOPE")
            for encoded in package["exports"].values():
                if not isinstance(encoded, str):
                    raise ImportProblem("Invalid Tally package export encoding")
                root.append(fromstring(base64.b64decode(encoded, validate=True)))
            content = tostring(root)
        else:
            content = path.read_bytes()
        # Period checks are repeated during canonical normalization.
        result = parse_export(content, options.tally_company, date.min, date.max, expected_fingerprint=options.tally_company_fingerprint)
        selected = result["lines"]
        if options.kind == "coa":
            selected = [
                {
                    "account_code": name,
                    "account_name": name,
                    "source_group": master.get("group") or "",
                    "source_id": "ledger:" + name,
                }
                for name, master in result["masters"].items()
            ]
        elif options.kind == "tb":
            from app.modules.connectors.tally import trial_balance_rows

            selected = trial_balance_rows(result)
        for index, row in enumerate(selected, 2):
            yield index, row
    elif suffix == ".csv":
        try:
            with path.open(encoding=options.encoding, newline="") as file:
                reader = csv.DictReader(file, delimiter=options.delimiter)
                if not reader.fieldnames:
                    raise ImportProblem("Empty CSV")
                if len(reader.fieldnames) > 100:
                    raise ImportProblem("Too many columns")
                headers = list(reader.fieldnames)
                map_headers(headers, options.mapping)
                for index, row in enumerate(reader, 2):
                    if None in row or any(v is None for v in row.values()):
                        raise ImportProblem(f"Row {index}: inconsistent CSV columns")
                    if any(len(v) > 32000 for v in row.values()):
                        raise ImportProblem(f"Row {index}: cell too long")
                    yield index, row
        except UnicodeError as exc:
            raise ImportProblem("Invalid CSV encoding; select the source encoding") from exc
    elif suffix == ".xlsx":
        try:
            with zipfile.ZipFile(path) as archive:
                items = archive.infolist()
                if len(items) > 5000 or sum(i.file_size for i in items) > 512 * 1024 * 1024:
                    raise ImportProblem("Excel archive exceeds decompression limit")
                if any(
                    i.file_size > 1000000 and i.file_size / max(i.compress_size, 1) > 200
                    for i in items
                ):
                    raise ImportProblem("Suspicious Excel compression ratio")
                if any(
                    "vbaproject" in i.filename.lower() or "externallinks/" in i.filename.lower()
                    for i in items
                ):
                    raise ImportProblem("Macros and external links are prohibited")
            # Object-store keys deliberately have no file extension.
            with path.open("rb") as workbook_source:
                book = load_workbook(
                    workbook_source, read_only=True, data_only=False, keep_links=False
                )
                try:
                    if options.sheet is None and len(book.sheetnames) > 1:
                        raise ImportProblem("Multiple worksheets: explicitly select a sheet")
                    if options.sheet and options.sheet not in book.sheetnames:
                        raise ImportProblem("Worksheet not found")
                    sheet = book[options.sheet or book.sheetnames[0]]
                    iterator = sheet.iter_rows()
                    first = next(iterator, None)
                    if first is None:
                        raise ImportProblem("Empty worksheet")
                    if any(c.data_type == "f" for c in first):
                        raise ImportProblem("Formula headings are prohibited")
                    headers = [str(c.value or "").strip() for c in first]
                    if len(headers) > 100:
                        raise ImportProblem("Too many columns")
                    map_headers(headers, options.mapping)
                    for index, cells in enumerate(iterator, 2):
                        if any(c.data_type == "f" for c in cells):
                            raise ImportProblem(
                                f"Row {index}: formulas are prohibited; export values"
                            )
                        values = [c.value for c in cells]
                        if all(v is None for v in values):
                            continue
                        row = {
                            h: (
                                v.isoformat()
                                if isinstance(v, (date, datetime))
                                else str(v)
                                if v is not None
                                else ""
                            )
                            for h, v in zip(headers, values, strict=True)
                        }
                        if any(len(v) > 32000 for v in row.values()):
                            raise ImportProblem(f"Row {index}: cell too long")
                        yield index, row
                finally:
                    book.close()
        except (zipfile.BadZipFile, KeyError, ValueError, io.UnsupportedOperation) as exc:
            raise ImportProblem("Corrupted or unsupported Excel file") from exc
    else:
        raise ImportProblem("Only CSV and macro-free XLSX are accepted")


def money(value: str, separator: str = ".") -> Decimal:
    text = value.strip().replace(" ", "").replace(" ", "")
    if not text:
        return Decimal(0)
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    grouping = "," if separator == "." else "."
    if grouping in text:
        whole = text.lstrip("-+").split(separator)[0]
        groups = whole.split(grouping)
        if not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:]):
            raise ImportProblem("Invalid thousands grouping")
    text = text.replace(grouping, "").replace(separator, ".")
    try:
        value_d = Decimal(text)
    except InvalidOperation as exc:
        raise ImportProblem("Invalid monetary amount") from exc
    if (
        not value_d.is_finite()
        or abs(value_d) >= Decimal("1e20")
        or int(value_d.as_tuple().exponent) < -8
    ):
        raise ImportProblem("Amount exceeds NUMERIC(28,8) precision")
    return value_d


def date_value(value: str, fmt: str) -> date:
    try:
        if len(value) >= 10 and value[4] == "-":
            return date.fromisoformat(value[:10])
        return datetime.strptime(value, fmt).date()
    except ValueError as exc:
        raise ImportProblem("Invalid date") from exc


def normalize(
    raw: dict[str, str], options: ImportOptions, start: date, end: date, functional: str, index: int
) -> tuple[dict, list[str]]:
    mapping = map_headers(list(raw), options.mapping)
    data = {key: raw[column].strip() for key, column in mapping.items()}
    code = data.get("account_code", "")
    if not code or len(code) > 100:
        raise ImportProblem("Blank or oversized account identifier")
    if (
        len(data.get("account_name", "")) > 300
        or len(data.get("journal_ref", "")) > 200
        or len(data.get("source_id", "")) > 300
    ):
        raise ImportProblem("Account name, journal reference or source ID exceeds field limit")
    warnings = []
    if not data.get("source_id"):
        warnings.append("missing_source_reference")
    normalized: dict = {
        **data,
        "account_code": code,
        "account_name": data.get("account_name") or code,
        "source_id": data.get("source_id") or f"row:{index}",
        "kind": options.kind,
    }
    if options.kind == "coa":
        return normalized, warnings
    if not any(key in data for key in ["debit", "credit", "amount", "closing_balance"]):
        raise ImportProblem("Missing monetary columns")
    debit, credit = (
        money(data.get("debit", ""), options.decimal_separator),
        money(data.get("credit", ""), options.decimal_separator),
    )
    if "debit" not in data and "credit" not in data:
        signed = money(
            data.get("amount", data.get("closing_balance", "")), options.decimal_separator
        )
        if options.signed_convention == "credit_positive":
            signed = -signed
        debit, credit = max(signed, Decimal(0)), max(-signed, Decimal(0))
    if debit < 0 or credit < 0 or (options.kind != "tb" and debit > 0 and credit > 0):
        raise ImportProblem("Debit/credit must be nonnegative and mutually exclusive")
    currency = data.get("currency") or options.currency
    if pycountry.currencies.get(alpha_3=currency) is None:
        raise ImportProblem("Invalid ISO currency")
    rate = money(
        data.get("exchange_rate") or ("1" if currency == functional else ""),
        options.decimal_separator,
    )
    if rate <= 0:
        raise ImportProblem("Missing supported source exchange rate")
    with localcontext() as ctx:
        ctx.prec = 48
        base_debit = (
            money(data["base_debit"], options.decimal_separator)
            if data.get("base_debit")
            else debit * rate
        )
        base_credit = (
            money(data["base_credit"], options.decimal_separator)
            if data.get("base_credit")
            else credit * rate
        )
    if currency != functional:
        from babel.numbers import get_currency_precision

        tolerance = Decimal(1).scaleb(-get_currency_precision(functional))
        if (
            abs(base_debit - debit * rate) > tolerance
            or abs(base_credit - credit * rate) > tolerance
        ):
            raise ImportProblem(
                "Source functional amounts conflict with the supplied exchange rate"
            )
    # Reject unsupported precision; no silent rounding during ingestion.
    base_debit, base_credit = money(format(base_debit, "f")), money(format(base_credit, "f"))
    if (
        base_debit < 0
        or base_credit < 0
        or (options.kind != "tb" and base_debit > 0 and base_credit > 0)
    ):
        raise ImportProblem("Invalid functional-currency debit/credit")
    if currency == functional and (base_debit != debit or base_credit != credit or rate != 1):
        raise ImportProblem("Inconsistent functional-currency amounts")
    opening = money(data.get("opening_balance", ""), options.decimal_separator)
    if options.kind == "tb":
        closing = (
            money(data["closing_balance"], options.decimal_separator)
            if data.get("closing_balance")
            else opening + base_debit - base_credit
        )
        if closing != opening + base_debit - base_credit:
            raise ImportProblem("TB closing does not roll forward")
        normalized.update(opening_balance=str(opening), closing_balance=str(closing))
    else:
        posting = date_value(data.get("posting_date", ""), options.date_format)
        if not start <= posting <= end:
            raise ImportProblem("Posting date outside selected financial period")
        if not data.get("journal_ref"):
            raise ImportProblem("Missing journal/voucher reference")
        normalized["posting_date"] = posting.isoformat()
        normalized["document_date"] = (
            date_value(data["document_date"], options.date_format).isoformat()
            if data.get("document_date")
            else None
        )
        stamp = data.get("posting_timestamp")
        if stamp:
            try:
                parsed = datetime.fromisoformat(stamp)
                if parsed.tzinfo is None:
                    raise ValueError("offset missing")
            except ValueError as exc:
                raise ImportProblem("Posting timestamp must have a reliable UTC offset") from exc
        normalized["opening"] = data.get("opening", "").lower() in {"true", "1", "yes"}
    if data.get("tax_code") and (
        options.tax_codes is None or data["tax_code"] not in options.tax_codes
    ):
        warnings.append("unsupported_tax_code")
    normalized.update(
        debit=str(debit),
        credit=str(credit),
        base_debit=str(base_debit),
        base_credit=str(base_credit),
        exchange_rate=str(rate),
        currency=currency,
        functional_currency=functional,
    )
    return normalized, warnings
