"""UAE VAT reporting currency controls; no FX valuation is inferred."""

CONTRACT = "uae-vat-aed-comparison/1"


def validate(data, tables):
    if data.currency != "AED" or any(
        row["currency"] != "AED" for population in tables.values() for row in population
    ):
        raise ValueError(
            "UAE VAT return comparison requires AED reporting amounts; retain separately assessed FX conversion before comparison"
        )


def current(body):
    parameters = body.get("parameters")
    rows = body.get("rows")
    if not isinstance(parameters, dict) or not isinstance(rows, list):
        return False
    return (
        body.get("vat_reporting_currency_contract") == CONTRACT
        and body.get("vat_reporting_currency") == "AED"
        and parameters.get("currency") == "AED"
        and all(isinstance(row, dict) and row.get("currency") == "AED" for row in rows)
    )
