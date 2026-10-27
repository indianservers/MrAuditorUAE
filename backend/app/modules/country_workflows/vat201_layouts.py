"""Explicit reconciliation layouts, without deriving legal allocation or eligibility."""

from decimal import Decimal
from typing import Literal

VAT201Layout = Literal["aggregate-14", "emirate-20", "ecommerce-20"]
EMIRATES = {
    "1a": "Abu Dhabi",
    "1b": "Dubai",
    "1c": "Sharjah",
    "1d": "Ajman",
    "1e": "Umm Al Quwain",
    "1f": "Ras Al Khaimah",
    "1g": "Fujairah",
}
SPLIT_FIELDS = [
    f"{prefix}_{field}"
    for prefix in ("ecommerce", "other_standard")
    for field in ("taxable_amount", "tax", "adjustment")
]
LAYOUTS = {
    "aggregate-14": {
        "label": "Aggregate Box 1 - fourteen rows",
        "boxes": [str(i) for i in range(1, 15)],
    },
    "ecommerce-20": {
        "label": "Box 1a-1g e-commerce and other standard-rated supplies - twenty rows",
        "boxes": [*EMIRATES, *[str(i) for i in range(2, 15)]],
    },
    "emirate-20": {
        "label": "Box 1a-1g by emirate - twenty rows",
        "boxes": [*EMIRATES, *[str(i) for i in range(2, 15)]],
    },
}


def validate_comparison(data, tables):
    if data.vat201_layout == "custom":
        if any(
            row.get(field) is not None
            for rows in tables.values()
            for row in rows
            for field in SPLIT_FIELDS
        ):
            raise ValueError(
                "E-commerce split fields require the explicit e-commerce VAT201 layout"
            )
        return
    required = set(LAYOUTS[data.vat201_layout]["boxes"])
    scopes = set()
    if data.currency != "AED":
        raise ValueError(
            "The selected VAT201 layout requires AED without inferred currency conversion"
        )
    for population in tables.values():
        seen = set()
        for row in population:
            if row["box"] not in required or row["box"] in seen:
                raise ValueError(
                    "VAT201 layout rows must be distinct and cannot mix aggregate Box 1 with emirate sub-boxes"
                )
            seen.add(row["box"])
            trn = row["registration"]
            if row["currency"] != "AED" or len(trn) != 15 or not trn.isascii() or not trn.isdigit():
                raise ValueError("The selected VAT201 layout requires one 15-digit TRN and AED")
            split = [field for field in SPLIT_FIELDS if row.get(field) is not None]
            if data.vat201_layout == "ecommerce-20" and row["box"] in EMIRATES:
                if len(split) != len(SPLIT_FIELDS):
                    raise ValueError(
                        "E-commerce VAT201 requires both explicit supply breakdowns, including nil, for every emirate"
                    )
            elif split:
                raise ValueError(
                    "Select the e-commerce VAT201 layout for split supply fields; only Box 1a-1g permits breakdowns"
                )
            for field in ("taxable_amount", "tax", "adjustment", *split):
                amount = Decimal(row[field])
                if amount != amount.quantize(Decimal("0.01")):
                    raise ValueError(
                        "The selected VAT201 row layout requires amounts stated to the nearest fils"
                    )
            scopes.add((trn, row["period_start"], row["period_end"]))
    if len(scopes) != 1:
        raise ValueError("The selected VAT201 layout requires one TRN and one reporting period")
