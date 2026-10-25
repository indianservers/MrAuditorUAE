"""Fail-closed, bounded declarative evaluation; no executable expressions."""

from decimal import Decimal, InvalidOperation, localcontext


def evaluate(rule, facts, period_start, period_end, transaction_date=None):
    if rule.method in {"benefit_profile", "payroll_profile", "pension_profile"}:
        return {
            "applicability": "PENDING",
            "required_workflow": "uae-benefit-review"
            if rule.method == "benefit_profile"
            else "uae-pension-review"
            if rule.method == "pension_profile"
            else "india-payroll-rules",
            "professional_conclusion": "NOT_DETERMINED",
            "reason": "Employee profiles require the dedicated employee-level workflow and retained-source review",
        }
    selected = {
        "period_start": period_start,
        "period_end": period_end,
        "transaction_date": transaction_date,
    }[rule.period_basis]
    if selected is None:
        return {"applicability": "PENDING", "missing_inputs": [rule.period_basis]}
    if selected < rule.effective_from or (rule.effective_to and selected > rule.effective_to):
        return {"applicability": "OUTSIDE_EFFECTIVE_PERIOD", "selected_date": selected.isoformat()}
    missing = [
        key for key in rule.input_requirements if facts.get(key) is None or facts.get(key) == ""
    ]
    checks = []
    for predicate in rule.applicability:
        value = facts.get(predicate.field)
        if value is None:
            missing.append(predicate.field)
            continue
        value = str(value).lower() if isinstance(value, bool) else str(value)
        if predicate.operator in {"equals", "in"}:
            matched = value in predicate.values
        else:
            try:
                left, right = Decimal(value), Decimal(predicate.values[0])
                if not left.is_finite() or not right.is_finite():
                    raise ValueError("Non-finite applicability input")
                matched = {
                    "gte": left >= right,
                    "gt": left > right,
                    "lte": left <= right,
                    "lt": left < right,
                }[predicate.operator]
            except (InvalidOperation, ValueError):
                return {"applicability": "PENDING", "invalid_inputs": [predicate.field]}
        checks.append(
            {
                "field": predicate.field,
                "operator": predicate.operator,
                "actual": value,
                "expected": predicate.values,
                "matched": matched,
            }
        )
    result = {
        "applicability": "PENDING"
        if missing
        else "NOT_APPLICABLE"
        if any(not c["matched"] for c in checks)
        else "APPLICABLE",
        "selected_date": selected.isoformat(),
        "checks": checks,
        "missing_inputs": sorted(set(missing)),
        "professional_conclusion": "NOT_DETERMINED",
        "exceptions_and_elections": rule.exceptions_and_elections,
    }
    if result["applicability"] == "APPLICABLE" and rule.method == "flat_rate":
        if (
            rule.calculation_currency
            and facts.get("tax_base_currency", facts.get("functional_currency"))
            != rule.calculation_currency
        ):
            return {
                **result,
                "applicability": "PENDING",
                "invalid_inputs": ["tax_base_currency"],
                "expected_currency": rule.calculation_currency,
            }
        try:
            base = Decimal(str(facts["tax_base"]))
            exponent = base.as_tuple().exponent
            if (
                not base.is_finite()
                or base.copy_abs() >= Decimal("1e20")
                or base < 0
                or not isinstance(exponent, int)
                or exponent < -18
            ):
                raise ValueError("Invalid tax base")
            with localcontext() as arithmetic:
                arithmetic.prec = 80
                amount = base * rule.rate
            result["calculation"] = {
                "tax_base": str(base),
                "rate": str(rule.rate),
                "unrounded_amount": str(amount),
                "method": "flat_rate",
                "rounding": "Not applied; rule-specific rounding must be reviewed",
                **({"currency": rule.calculation_currency} if rule.calculation_currency else {}),
            }
        except (InvalidOperation, ValueError):
            result.update(applicability="PENDING", invalid_inputs=["tax_base"])
    return result
