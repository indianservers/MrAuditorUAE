"""Strict canonical CSV contract over clean, hash-verified evidence."""

import csv
import io
from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from pydantic import ValidationError

from app.modules.country_workflows.schemas import ROW_TYPES

MAX_BYTES = 10 * 1024 * 1024


def parse_csv(content, data):
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return _parse_csv(content, data)


def _parse_csv(content, data):
    if len(content) > MAX_BYTES:
        raise ValueError("Workflow CSV exceeds 10 MiB")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    fields = reader.fieldnames or []
    model = ROW_TYPES[data.table_type]
    if (
        len(fields) != len(set(fields))
        or not fields
        or any(f not in model.model_fields for f in fields)
    ):
        raise ValueError("Duplicate, empty or unsupported CSV columns")
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
        values = {k: v.strip() for k, v in raw.items() if v.strip() != ""}
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
        rows.append(item.model_dump(mode="json"))
        amount = getattr(item, "amount", getattr(item, "tax", None))
        if data.table_type == "confirmations":
            amount = getattr(item, "requested_amount")
        if amount is not None:
            totals[getattr(item, "currency")] += amount
    if len(rows) != data.expected_rows:
        raise ValueError("Source row-count control does not agree")
    if not rows:
        if any(v != 0 for v in data.control_totals.values()):
            raise ValueError("A nil population cannot carry nonzero control totals")
        totals.update(data.control_totals)
    if data.table_type in {
        "transactions", "tax-documents", "obligations", "return-boxes",
        "audit-open-items", "settlements", "balance-controls", "confirmations", "cutoff-documents",
        "purchase-lines", "expense-claims", "benefit-employees",
        "trade-lines", "excise-movements", "excise-returns", "escrow-entries", "billing-lines", "accounting-controls",
    }:
        if dict(totals) != data.control_totals:
            raise ValueError(
                "Source currency control totals do not agree; every currency must be controlled"
            )
    elif data.control_totals:
        raise ValueError(
            "Money control totals apply only to transaction, tax and obligation tables"
        )
    return {
        "table_type": data.table_type,
        "rows": rows,
        "row_count": len(rows),
        "control_totals": {k: str(v) for k, v in sorted(totals.items())},
        "population_completeness": "UPLOADED_FILE_CONTROLS_ONLY",
        "review_status": "UNVERIFIED",
        "nil_reason": data.nil_reason,
        "title": data.label,
        "parser_version": "country-csv-1",
    }
