"""Strict canonical CSV contract over clean, hash-verified evidence."""

import csv
import io
import re
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from pydantic import ValidationError

from app.modules.country_workflows.schemas import ROW_TYPES

MAX_BYTES = 10 * 1024 * 1024


def parse_csv(content, data, defaults=None):
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return _parse_csv(content, data, defaults)


def _parse_csv(content, data, defaults=None):
    if len(content) > MAX_BYTES:
        raise ValueError("Workflow CSV exceeds 10 MiB")
    if (data.column_mapping or data.ignored_columns) and len(data.mapping_rationale.strip()) < 10:
        raise ValueError("CSV column mapping/exclusions require an explicit assessment")
    reader = csv.DictReader(
        io.StringIO(content.decode("utf-8-sig"), newline=""), delimiter=data.delimiter
    )
    fields = reader.fieldnames or []
    model = ROW_TYPES[data.table_type]
    if len(fields) != len(set(fields)) or not fields or any(not f or len(f) > 120 for f in fields):
        raise ValueError("Duplicate, empty or unsupported CSV columns")
    mapping = data.column_mapping
    ignored = set(data.ignored_columns)
    if len(ignored) != len(data.ignored_columns) or not ignored <= set(fields):
        raise ValueError("Ignored CSV columns must be distinct actual source headers")
    if (
        any(
            target not in model.model_fields or source not in fields
            for target, source in mapping.items()
        )
        or len(set(mapping.values())) != len(mapping)
        or ignored.intersection(mapping.values())
    ):
        raise ValueError("CSV mapping must select distinct actual columns for supported fields")
    explicit = {source: target for target, source in mapping.items()}
    deriving = data.amount_derivation != "none"
    amount_columns = {data.debit_column, data.credit_column} if deriving else set()
    if deriving and (
        not amount_columns <= set(fields)
        or amount_columns.intersection(ignored)
        or amount_columns.intersection(mapping.values())
        or "amount" in mapping
    ):
        raise ValueError(
            "Debit/credit columns must be present, independent and not mapped or excluded"
        )
    applied = {}
    for source in fields:
        if source in ignored or source in amount_columns:
            continue
        target = explicit.get(source, source)
        if target not in model.model_fields or target in applied:
            raise ValueError(
                "Unsupported or competing CSV columns; map or explicitly exclude each source column"
            )
        applied[target] = source
    if deriving and "amount" in applied:
        raise ValueError("A signed amount column competes with debit/credit derivation")
    rows: list[dict[str, Any]] = []
    ids = set()
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for index, raw in enumerate(reader, 2):
        if (
            len(rows) >= 5000
            or None in raw
            or any(v is None or len(v) > 4000 for v in raw.values())
        ):
            raise ValueError(f"Invalid CSV row {index} or 5,000-row bound exceeded")
        values = {
            target: raw[source].strip()
            for target, source in applied.items()
            if raw[source].strip() != ""
        }
        sides = None
        if deriving:
            debit, credit = raw[data.debit_column].strip(), raw[data.credit_column].strip()
            if not debit and not credit:
                raise ValueError(f"Debit and credit are both blank at CSV row {index}")
            if any(
                value and not re.fullmatch(r"\d{1,20}(?:\.\d{1,8})?", value)
                for value in (debit, credit)
            ):
                raise ValueError(
                    f"Debit/credit values must be unsigned plain decimals at CSV row {index}"
                )
            sides = (Decimal(debit or "0"), Decimal(credit or "0"))
            if sides[0] and sides[1]:
                raise ValueError(f"Both debit and credit are nonzero at CSV row {index}")
            derived = sides[0] - sides[1]
            if data.amount_derivation == "credit-positive":
                derived = -derived
            values["amount"] = str(derived)
        for key, selected_value in (defaults or {}).items():
            if key in values and values[key] != selected_value:
                raise ValueError(
                    "CSV rule document differs from the explicitly selected retained evidence"
                )
            values[key] = selected_value
        # Empty references are permitted for bank statements, not tax documents.
        if data.table_type == "transactions":
            values.setdefault("reference", "")
        try:
            item = model.model_validate(values)
        except ValidationError as exc:
            fields = sorted({str(e["loc"][0]) if e["loc"] else "record" for e in exc.errors()})
            raise ValueError(f"Invalid CSV row {index}, fields: {', '.join(fields)}") from None
        if getattr(item, "id") in ids:
            raise ValueError(f"Duplicate source identifier at row {index}")
        ids.add(getattr(item, "id"))
        row = item.model_dump(mode="json")
        if sides is not None:
            row.update(
                source_debit=str(sides[0]),
                source_credit=str(sides[1]),
                source_amount_derivation=data.amount_derivation,
            )
        rows.append(row)
        amount = getattr(item, "amount", getattr(item, "tax", None))
        if data.table_type == "confirmations":
            amount = getattr(item, "requested_amount")
        if amount is not None:
            totals[getattr(item, "currency")] += amount
    metric_controls = None
    if data.table_type == "gst-summary-metrics":
        from app.modules.country_workflows.gst_summary import verify_controls

        metric_controls = verify_controls(rows, data.gst_summary_metric_controls)
    if len(rows) != data.expected_rows:
        raise ValueError("Source row-count control does not agree")
    if data.inventory_quantity_controls is not None:
        from app.modules.country_workflows.inventory_controls import verify_quantity_controls

        verify_quantity_controls(rows, [item.model_dump(mode="json") for item in data.inventory_quantity_controls])
    if not rows:
        if any(v != 0 for v in data.control_totals.values()):
            raise ValueError("A nil population cannot carry nonzero control totals")
        totals.update(data.control_totals)
    if data.table_type in {
        "obligation-allocations",
        "bank-outstanding",
        "bank-clearances",
        "withholding-records",
        "credit-applications",
        "cash-payments",
        "item-allocations",
        "transactions",
        "payroll-account-balances",
        "payroll-ledger-lines",
        "tax-documents",
        "import-vat-lines",
        "obligations",
        "return-boxes",
        "audit-open-items",
        "settlements",
        "balance-controls",
        "confirmations",
        "cutoff-documents",
        "purchase-lines",
        "expense-claims",
        "benefit-employees",
        "payroll-bases",
        "pension-bases",
        "pension-reported",
        "trade-lines",
        "excise-movements",
        "excise-returns",
        "escrow-entries",
        "billing-lines",
        "accounting-controls",
    }:
        if dict(totals) != data.control_totals:
            raise ValueError(
                "Source currency control totals do not agree; every currency must be controlled"
            )
    elif data.control_totals:
        raise ValueError(
            "Money control totals apply only to transaction, tax and obligation tables"
        )
    if (
        data.table_type == "import-vat-lines"
        and sum((Decimal(row["net"]) for row in rows), Decimal(0))
        != data.import_taxable_base_control
    ):
        raise ValueError("Import taxable-base control does not agree to all retained source rows")
    return {
        "table_type": data.table_type,
        **({"metric_controls": metric_controls} if metric_controls is not None else {}),
        "rows": rows,
        "row_count": len(rows),
        "control_totals": {k: str(v) for k, v in sorted(totals.items())},
        **({"inventory_controls_verified": True, "inventory_quantity_controls": [item.model_dump(mode="json") for item in data.inventory_quantity_controls]} if data.inventory_quantity_controls is not None else {}),
        **(
            {"import_taxable_base_control": str(data.import_taxable_base_control)}
            if data.table_type == "import-vat-lines"
            else {}
        ),
        "population_completeness": "UPLOADED_FILE_CONTROLS_ONLY",
        "review_status": "UNVERIFIED",
        "nil_reason": data.nil_reason,
        "title": data.label,
        "parser_version": "country-csv-2",
        "csv_mapping": {
            "original_headers": fields,
            "applied_columns": applied,
            "ignored_columns": data.ignored_columns,
            "rationale": data.mapping_rationale.strip(),
            "delimiter": data.delimiter,
            "value_transformations": "EXPLICIT_DEBIT_CREDIT_DIFFERENCE"
            if deriving
            else "NONE_TYPED_VALIDATION_ONLY",
            "amount_derivation": data.amount_derivation,
            "debit_column": data.debit_column,
            "credit_column": data.credit_column,
            "blank_side_basis": "ZERO_ONLY_WHEN_OTHER_SIDE_IS_PRESENT" if deriving else None,
        },
    }
