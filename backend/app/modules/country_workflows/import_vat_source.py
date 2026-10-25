"""Explicit, controlled import-detail bridge; no filing or recovery inference."""

from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field, field_validator

from app.modules.country_workflows.schemas import Money, ReturnBox
from app.modules.jurisdictions.profiles import Strict


class ImportBoxControl(Strict):
    expected_rows: int = Field(ge=0, le=5000)
    taxable_amount: Money
    tax: Money


class ImportVATSourceInput(Strict):
    source_role: Literal["customs", "portal", "books"]
    boxes: dict[Literal["6", "7"], ImportBoxControl] = Field(min_length=1, max_length=2)
    label: str = Field(min_length=1, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("assessment")
    @classmethod
    def meaningful_assessment(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Assess the selected role and box populations explicitly")
        return value.strip()


def source_rows(body, data):
    if body.get("import_comparison_contract") != "uae-import-vat/1":
        raise ValueError("Select a current import VAT detail comparison")
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        tax_total = Decimal(0)
        for box, control in sorted(data.boxes.items()):
            kind = "declaration" if box == "6" else "adjustment"
            total = body.get("role_totals", {}).get(data.source_role, {}).get(kind, {})
            selected = [row for row in body["rows"] if row["entry_kind"] == kind]
            nil = body.get("import_nil_scope") or {}
            evidenced_nil = (
                not selected
                and kind in nil.get("kinds", [])
                and nil.get("binding_status") == "VERIFIED_RETAINED_CONTEXT"
                and bool(nil.get("context_receipt"))
                and nil.get("basis") == "EXPLICIT_EVIDENCED_NIL"
                and nil.get("currency") == "AED"
            )
            if (
                (not selected and not evidenced_nil)
                or not total.get("complete_for_selected_population")
                or total.get("selected_rows") != len(selected)
                or any(
                    not row["selected_source_ids"].get(data.source_role)
                    or row["amounts"].get(data.source_role) is None
                    for row in selected
                )
            ):
                raise ValueError(
                    f"Box {box} has no complete selected population; absence is not a verified nil box"
                )
            scopes = {
                (row["registration"], row["period_start"], row["period_end"], row["currency"])
                for row in selected
            }
            if evidenced_nil:
                scopes.add((nil["registration"], nil["period_start"], nil["period_end"], "AED"))
            if len(scopes) != 1 or next(iter(scopes))[3] != "AED":
                raise ValueError("Import bridge requires one AED registration and period")
            registration, start, end, currency = next(iter(scopes))
            net = sum(
                (Decimal(row["amounts"][data.source_role]["net"]) for row in selected), Decimal(0)
            )
            tax = sum(
                (Decimal(row["amounts"][data.source_role]["tax"]) for row in selected), Decimal(0)
            )
            if (
                control.expected_rows != len(selected)
                or control.taxable_amount != net
                or control.tax != tax
                or total.get("net") is None
                or total.get("tax") is None
                or Decimal(total["net"]) != net
                or Decimal(total["tax"]) != tax
            ):
                raise ValueError(
                    f"Independent Box {box} row, taxable-base and tax controls do not agree"
                )
            canonical = ReturnBox(
                id=f"import-box-{box}",
                registration=registration,
                period_start=start,
                period_end=end,
                box=box,
                currency=currency,
                taxable_amount=net,
                tax=tax,
                adjustment=Decimal(0),
            ).model_dump(mode="json")
            rows.append(
                {
                    **canonical,
                    "population_basis": "EXPLICIT_EVIDENCED_NIL" if evidenced_nil else "SELECTED_IMPORT_DETAIL",
                    "nil_context_receipt": nil["context_receipt"] if evidenced_nil else None,
                    "source_import_row_ids": [row["id"] for row in selected],
                    "source_import_detail_ids": [
                        row["selected_source_ids"][data.source_role] for row in selected
                    ],
                }
            )
            tax_total += tax
    if len({(row["registration"], row["period_start"], row["period_end"]) for row in rows}) != 1:
        raise ValueError("Selected import boxes must share one registration and period")
    return rows, {"AED": str(tax_total)}
