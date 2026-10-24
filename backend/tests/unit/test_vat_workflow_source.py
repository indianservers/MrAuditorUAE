from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.country_workflows.vat_source import source_rows
from app.modules.vat.catalogue import BOXES


def calculation():
    return {
        "currency": "AED",
        "validation": {"ready": True},
        "exceptions": [],
        "mapping_version": "synthetic-mapping",
        "boxes": [{"box": box, "net": "200", "vat": "15"} for box in BOXES],
    }


def convert(result, adjustments=()):
    return source_rows(
        result, "999999999999999", date(2026, 10, 1), date(2026, 10, 31), adjustments
    )


def test_bridge_preserves_final_boxes_and_separates_reviewed_tax_adjustments():
    adjustments = [
        SimpleNamespace(box="1", tax_amount=Decimal("5"), statutory_conditions_confirmed=True),
        SimpleNamespace(box="9", tax_amount=Decimal("2"), statutory_conditions_confirmed=True),
    ]
    rows, totals = convert(calculation(), adjustments)
    boxes = {row["box"]: row for row in rows}
    expected = {"1": "5", "8": "5", "12": "5", "9": "2", "11": "2", "13": "2", "14": "3"}
    for key, row in boxes.items():
        assert Decimal(row["tax"]) + Decimal(row["adjustment"]) == 15
        assert Decimal(row["adjustment"]) == Decimal(expected.get(key, "0"))
        assert Decimal(row["taxable_amount"]) == 200
    assert Decimal(totals["AED"]) == sum(Decimal(row["tax"]) for row in rows)


@pytest.mark.parametrize(
    "defect", ["currency", "not-ready", "exception", "missing", "duplicate", "mapping", "nan"]
)
def test_incomplete_calculations_are_not_accepted(defect):
    result = calculation()
    if defect == "currency":
        result["currency"] = "INR"
    elif defect == "not-ready":
        result["validation"]["ready"] = False
    elif defect == "exception":
        result["exceptions"] = ["unresolved"]
    elif defect == "missing":
        result["boxes"].pop()
    elif defect == "duplicate":
        result["boxes"][-1] = result["boxes"][0]
    elif defect == "mapping":
        result.pop("mapping_version")
    elif defect == "nan":
        result["boxes"][0]["vat"] = "NaN"
    with pytest.raises(ValueError):
        convert(result)
