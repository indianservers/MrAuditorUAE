"""Arithmetic on explicitly mapped VAT201 rows, not tax eligibility or filing approval."""

from decimal import Decimal, localcontext

from app.modules.country_workflows.vat201_layouts import EMIRATES

CONTRACT = "uae-vat201-arithmetic/2"
ECOMMERCE_SOURCE = "https://tax.gov.ae/DownloadOpenTextFile?fileUrl=en%2FVAT_VAT_Guides%2FProcess_Final_VAT_return%2FFinal_VAT_return_for_e-commerce_reporting.pdf"
SOURCE = "https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf"


def checks(layout, tables):
    if layout == "custom":
        return []
    output = (
        [*EMIRATES, *map(str, range(2, 8))]
        if layout in {"emirate-20", "ecommerce-20"}
        else list(map(str, range(1, 8)))
    )
    checks = []
    with localcontext() as context:
        context.prec = 80
        for role, population in tables.items():
            rows = {row["box"]: row for row in population}

            def check(box, field, terms, formula):
                needed = {box, *(key for key, name, sign in terms)}
                missing = sorted(needed - rows.keys())
                expected = (
                    None
                    if missing
                    else sum(
                        (Decimal(rows[key][name]) * sign for key, name, sign in terms), Decimal(0)
                    )
                )
                observed = Decimal(rows[box][field]) if box in rows else None
                difference = (
                    observed - expected if expected is not None and observed is not None else None
                )
                checks.append(
                    {
                        "id": f"{role}-{box}-{field}",
                        "source_role": role,
                        "box": box,
                        "field": field,
                        "formula": formula,
                        "expected": str(expected) if expected is not None else None,
                        "observed": str(observed) if observed is not None else None,
                        "difference": str(difference) if difference is not None else None,
                        "status": "MISSING_INPUT"
                        if missing
                        else "MATCHED"
                        if difference == 0
                        else "ARITHMETIC_ERROR",
                        "missing_boxes": missing,
                        "source_row_ids": [
                            rows[key]["id"] for key in sorted(needed) if key in rows
                        ],
                    }
                )

            if layout == "ecommerce-20":
                for box in EMIRATES:
                    for field in ("taxable_amount", "tax", "adjustment"):
                        check(
                            box,
                            field,
                            [(box, "ecommerce_" + field, 1), (box, "other_standard_" + field, 1)],
                            "e-commerce + other standard-rated supplies",
                        )
            for field in ("taxable_amount", "tax", "adjustment"):
                check("8", field, [(box, field, 1) for box in output], "SUM(output detail rows)")
                check("11", field, [("9", field, 1), ("10", field, 1)], "Box 9 + Box 10")
            check(
                "12",
                "tax",
                [("8", "tax", 1), ("8", "adjustment", 1)],
                "Box 8 tax + Box 8 adjustment",
            )
            check(
                "13",
                "tax",
                [("11", "tax", 1), ("11", "adjustment", 1)],
                "Box 11 tax + Box 11 adjustment",
            )
            check("14", "tax", [("12", "tax", 1), ("13", "tax", -1)], "Box 12 tax - Box 13 tax")
            # Scalar payable/recoverable boxes are represented only in the tax column.
            for box in ("12", "13", "14"):
                for field in ("taxable_amount", "adjustment"):
                    check(box, field, [], "0 (scalar box carried in tax column only)")
    return checks
