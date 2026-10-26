"""Source setup for existing arithmetic tests; independent control failures have literal fixtures."""

from decimal import Decimal


def quantity_controls(rows):
    grouped = {}
    fields = ("order_id", "line_reference", "vendor", "currency", "uom", "document_type")
    for row in rows:
        if row["document_type"] == "payment":
            continue
        identity = tuple(row[field] for field in fields)
        value = grouped.setdefault(identity, {**dict(zip(fields, identity, strict=True)), "expected_rows": 0, "quantity": Decimal(0)})
        value["expected_rows"] += 1
        value["quantity"] += Decimal(row["quantity"])
    return [{**value, "quantity": str(value["quantity"])} for value in grouped.values()]
