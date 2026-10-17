"""Pure Decimal accounting functions. Debit-positive, credit-negative, no model dependencies."""

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, localcontext

ZERO = Decimal(0)


def trial_balance(
    lines: Iterable[dict], currency: str, precision: int = 2, rounding: str = "ROUND_HALF_EVEN"
) -> list[dict]:
    if rounding not in {"ROUND_HALF_EVEN", "ROUND_HALF_UP"} or not 0 <= precision <= 8:
        raise ValueError("Unsupported rounding policy")
    accounts: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"opening": ZERO, "debit": ZERO, "credit": ZERO}
    )
    with localcontext() as context:
        context.prec = 48
        for line in lines:
            if line["functional_currency"] != currency:
                raise ValueError("Mixed functional currencies")
            debit, credit = Decimal(str(line["base_debit"])), Decimal(str(line["base_credit"]))
            if not debit.is_finite() or not credit.is_finite():
                raise ValueError("Non-finite amount")
            if debit < 0 or credit < 0 or (debit and credit):
                raise ValueError("Invalid debit/credit")
            account = accounts[line["account_code"]]
            if line.get("opening") in {True, "true", "True", "1"}:
                account["opening"] += debit - credit
            else:
                account["debit"] += debit
                account["credit"] += credit
        quantum = Decimal(1).scaleb(-precision)
        result = []
        for code, values in sorted(accounts.items()):
            rounded = {
                key: value.quantize(quantum, rounding=rounding) for key, value in values.items()
            }
            rounded["closing"] = rounded["opening"] + rounded["debit"] - rounded["credit"]
            result.append({"account_code": code, **rounded, "currency": currency})
        return result


def reconcile(
    source: dict[str, Decimal], computed: dict[str, Decimal], tolerance: Decimal = ZERO
) -> dict:
    if tolerance < 0:
        raise ValueError("Negative tolerance")
    differences = []
    for code in sorted(source.keys() | computed.keys()):
        expected, actual = source.get(code, ZERO), computed.get(code, ZERO)
        delta = actual - expected
        if abs(delta) > tolerance:
            differences.append(
                {
                    "account_code": code,
                    "source": str(expected),
                    "calculated": str(actual),
                    "difference": str(delta),
                }
            )
    return {
        "status": "failed" if differences else "passed",
        "tolerance": str(tolerance),
        "source_total": str(sum(source.values(), ZERO)),
        "calculated_total": str(sum(computed.values(), ZERO)),
        "differences": differences,
    }


def movements(current: dict[str, Decimal], previous: dict[str, Decimal]) -> list[dict]:
    return [
        {
            "account_code": code,
            "current": str(current.get(code, ZERO)),
            "previous": str(previous.get(code, ZERO)),
            "variance": str(current.get(code, ZERO) - previous.get(code, ZERO)),
            "percentage": str(
                (current.get(code, ZERO) - previous[code]) / abs(previous[code]) * 100
            )
            if previous.get(code)
            else None,
        }
        for code in sorted(current.keys() | previous.keys())
    ]
