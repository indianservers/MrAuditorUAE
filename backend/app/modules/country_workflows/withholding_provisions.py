"""Narrow retained boundary for positive, expressly identified 206C(1H) expectations."""

import re
from decimal import Decimal, InvalidOperation

CUTOFF = "2025-04-01"
REFERENCE = "https://www.incometaxindia.gov.in/w/section-72-94"
ISSUE = "WITHDRAWN_206C_1H_POSITIVE_EXPECTATION"


def withdrawn_expectation(record):
    reference = re.sub(r"\s+", "", str(record.get("rule_reference", ""))).upper()
    if (
        record.get("legal_role") != "collector"
        or record.get("tax_kind") != "TCS"
        or reference.removeprefix("TCS:") != "206C(1H)"
    ):
        return False
    try:
        amount = Decimal(str(record.get("amount")))
    except (InvalidOperation, ValueError):
        return False
    return (
        amount.is_finite()
        and amount > 0
        and (
            str(record.get("transaction_date", "")) >= CUTOFF
            or str(record.get("period", "")) >= CUTOFF[:7]
        )
    )


def saved_withdrawn_expectation(body):
    if body.get("workflow") != "india-withholding-liability":
        return False
    return any(
        withdrawn_expectation({**row, "amount": row.get("amounts", {}).get("expected")})
        for row in body.get("rows", [])
    )
