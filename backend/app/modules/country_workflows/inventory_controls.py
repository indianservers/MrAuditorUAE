"""Independent row and directional quantity controls; incompatible units never net."""

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Annotated, TypedDict

from pydantic import Field, field_validator

from app.modules.jurisdictions.profiles import Strict

Quantity = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=120)]


class InventoryQuantityControl(Strict):
    site: Identifier
    sku: Identifier
    lot: str = Field(default="", max_length=120)
    uom: Identifier
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    expected_rows: int = Field(ge=1, le=5000, strict=True)
    positive_quantity: Quantity = Field(ge=0)
    negative_quantity: Quantity = Field(le=0)

    @field_validator("site", "sku", "lot", "uom")
    @classmethod
    def exact_identifiers(cls, value):
        if value != value.strip():
            raise ValueError(
                "Inventory controls require exact identifiers without surrounding whitespace"
            )
        return value


def stock_key(row):
    return row["site"], row["sku"], row["uom"], row["currency"], row.get("lot", "")


class ActualControl(TypedDict):
    expected_rows: int
    positive_quantity: Decimal
    negative_quantity: Decimal


def verify_quantity_controls(rows, declared):
    controls = [InventoryQuantityControl.model_validate(item) for item in declared]
    keyed = {stock_key(item.model_dump()): item for item in controls}
    if len(keyed) != len(controls):
        raise ValueError("Duplicate inventory quantity-control partition")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        actual: defaultdict[tuple[str, str, str, str, str], ActualControl] = defaultdict(
            lambda: {
                "expected_rows": 0,
                "positive_quantity": Decimal(0),
                "negative_quantity": Decimal(0),
            }
        )
        for row in rows:
            group = actual[stock_key(row)]
            value = Decimal(str(row["quantity"]))
            group["expected_rows"] += 1
            group["positive_quantity" if value >= 0 else "negative_quantity"] += value
        if actual.keys() != keyed.keys() or any(
            any(getattr(keyed[key], field) != value for field, value in totals.items())
            for key, totals in actual.items()
        ):
            raise ValueError(
                "Independent inventory row, positive and negative quantity controls do not agree for every site/SKU/lot/UOM/currency partition"
            )
