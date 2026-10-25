"""Explicit reconciliation layouts, without deriving legal allocation or eligibility."""

from decimal import Decimal
from typing import Literal

VAT201Layout = Literal["aggregate-14", "emirate-20"]
EMIRATES = {
    "1a": "Abu Dhabi", "1b": "Dubai", "1c": "Sharjah", "1d": "Ajman",
    "1e": "Umm Al Quwain", "1f": "Ras Al Khaimah", "1g": "Fujairah",
}
LAYOUTS = {
    "aggregate-14": {"label": "Aggregate Box 1 - fourteen rows", "boxes": [str(i) for i in range(1, 15)]},
    "emirate-20": {"label": "Box 1a-1g by emirate - twenty rows", "boxes": [*EMIRATES, *[str(i) for i in range(2, 15)]]},
}


def validate_comparison(data, tables):
    if data.vat201_layout == "custom":
        return
    required = set(LAYOUTS[data.vat201_layout]["boxes"])
    scopes = set()
    if data.currency != "AED":
        raise ValueError("The selected VAT201 layout requires AED without inferred currency conversion")
    for population in tables.values():
        seen = set()
        for row in population:
            if row["box"] not in required or row["box"] in seen:
                raise ValueError("VAT201 layout rows must be distinct and cannot mix aggregate Box 1 with emirate sub-boxes")
            seen.add(row["box"])
            trn = row["registration"]
            if row["currency"] != "AED" or len(trn) != 15 or not trn.isascii() or not trn.isdigit():
                raise ValueError("The selected VAT201 layout requires one 15-digit TRN and AED")
            for field in ("taxable_amount", "tax", "adjustment"):
                amount = Decimal(row[field])
                if amount != amount.quantize(Decimal("0.01")):
                    raise ValueError("The selected VAT201 row layout requires amounts stated to the nearest fils")
            scopes.add((trn, row["period_start"], row["period_end"]))
    if len(scopes) != 1:
        raise ValueError("The selected VAT201 layout requires one TRN and one reporting period")
