"""India GST reporting currency controls; no FX valuation is inferred."""

CONTRACT = "india-gst-inr-comparison/1"


def validate(data, tables):
    if data.currency != "INR" or any(
        row["currency"] != "INR" for population in tables.values() for row in population
    ):
        raise ValueError(
            "India GST return comparison requires INR reporting amounts; retain separately assessed FX conversion before comparison"
        )


def current(body):
    parameters = body.get("parameters")
    rows = body.get("rows")
    if not isinstance(parameters, dict) or not isinstance(rows, list):
        return False
    return (
        body.get("gst_reporting_currency_contract") == CONTRACT
        and body.get("gst_reporting_currency") == "INR"
        and parameters.get("currency") == "INR"
        and all(isinstance(row, dict) and row.get("currency") == "INR" for row in rows)
    )
