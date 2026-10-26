"""Independent, exact purchase quantity controls; no unit conversions are inferred."""

from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]


class PurchaseQuantityControl(Strict):
    order_id: ID
    line_reference: ID
    vendor: ID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    uom: ID
    document_type: Literal["order", "receipt", "invoice"]
    expected_rows: int = Field(ge=1, le=5000, strict=True)
    quantity: Decimal = Field(ge=0, max_digits=64, decimal_places=8, allow_inf_nan=False)

    @field_validator("order_id", "line_reference", "vendor", "uom")
    @classmethod
    def exact(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Purchase quantity controls require exact nonblank identifiers and units")
        return value


FIELDS = ("order_id", "line_reference", "vendor", "currency", "uom", "document_type")


def key(row):
    return tuple(row.get(field) for field in FIELDS)


def verify(rows, controls):
    declared = {}
    for value in controls:
        control = PurchaseQuantityControl.model_validate(value).model_dump(mode="json")
        identity = key(control)
        if identity in declared:
            raise ValueError("Duplicate purchase quantity control partition")
        declared[identity] = control
    actual: dict[tuple, tuple[int, Decimal]] = {}
    with localcontext() as context:
        context.prec = 80
        for row in rows:
            if row["document_type"] == "payment":
                continue
            if not row.get("uom"):
                raise ValueError("Controlled purchase quantities require an explicit unit on every non-payment row")
            identity = key(row)
            count, quantity = actual.get(identity, (0, Decimal(0)))
            actual[identity] = count + 1, quantity + Decimal(row["quantity"])
    if actual.keys() != declared.keys() or any(
        values[0] != declared[identity]["expected_rows"]
        or values[1] != Decimal(declared[identity]["quantity"])
        for identity, values in actual.items()
    ):
        raise ValueError("Independent purchase row and quantity controls do not agree for every order/line/vendor/currency/unit/document partition")
