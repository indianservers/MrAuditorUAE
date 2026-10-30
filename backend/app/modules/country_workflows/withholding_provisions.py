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
    if body.get("workflow") in {"statutory-dues", "payroll-settlement"}:
        return any(
            withdrawn_obligation({**row, "amount": row.get("amounts", {}).get("expected")})
            for row in body.get("rows", [])
        )
    if body.get("workflow") == "obligation-bank-allocations":
        return any(
            row.get("kind") == "obligation"
            and withdrawn_obligation({**row, "amount": row.get("expected_amount")})
            for row in body.get("rows", [])
        )
    if body.get("workflow") != "india-withholding-liability":
        return False
    return any(
        withdrawn_expectation({**row, "amount": row.get("amounts", {}).get("expected")})
        for row in body.get("rows", [])
    )


def withdrawn_obligation(record):
    scope = record.get("withholding_scope")
    if (
        not isinstance(scope, dict)
        and re.sub(r"\s+", "", str(record.get("component", ""))).upper() != "TCS:206C(1H)"
    ):
        return False
    return withdrawn_expectation(
        {
            **(
                scope
                if isinstance(scope, dict)
                else {
                    "legal_role": "collector",
                    "tax_kind": "TCS",
                    "rule_reference": str(record.get("component", "")),
                }
            ),
            "period": record.get("period", ""),
            "amount": record.get("amount"),
        }
    )
