"""Synthetic plumbing vectors for non-arithmetic integration tests.

These are not legal golden data. Dedicated validation tests use literal expected
amounts. Production never manufactures expected results from these helpers.
"""

from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext


def cases(body):
    kind = body["method"]
    end = date.fromisoformat(body["effective_from"])
    base = {
        "id": "SYNTHETIC-STANDARD",
        "kind": kind,
        "expected_reference": "SYNTHETIC integration plumbing oracle; not legally qualified data",
    }
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        if kind in {"checklist", "flat_rate"}:
            facts = {key: "SYNTHETIC" for key in body["input_requirements"]}
            facts.update(
                entity_type="company",
                tax_base="100",
                tax_base_currency=body.get("calculation_currency")
                or ("AED" if body["country"] == "AE" else "INR"),
            )
            for predicate in body.get("applicability", []):
                value = predicate["values"][0]
                operator = predicate["operator"]
                if operator in {"gt", "lt"}:
                    value = str(Decimal(value) + (1 if operator == "gt" else -1))
                facts[predicate["field"]] = value
            return [
                {
                    **base,
                    "facts": facts,
                    "period_start": str(end),
                    "period_end": str(end),
                    "transaction_date": str(end),
                    "expected_applicability": "APPLICABLE",
                    **(
                        {"expected_amount": str(Decimal(facts["tax_base"]) * Decimal(body["rate"]))}
                        if kind == "flat_rate"
                        else {}
                    ),
                }
            ]
        if kind == "benefit_profile":
            params = body["benefit_parameters"]
            years = Decimal(2)
            days = int(
                (years * Decimal(params["year_days"])).to_integral_value(rounding=ROUND_CEILING)
            )
            start = end - timedelta(days=days - 1)
            years = Decimal(days) / Decimal(params["year_days"])
            tier = min(years, Decimal(params["first_tier_years"])) * Decimal(
                params["first_tier_days"]
            )
            tier += max(Decimal(0), years - Decimal(params["first_tier_years"])) * Decimal(
                params["later_tier_days"]
            )
            expected = min(
                Decimal(3000) / Decimal(params["salary_divisor"]) * tier,
                Decimal(3000) * Decimal(params["maximum_salary_months"]),
            )
            if years < Decimal(params["minimum_service_years"]):
                expected = Decimal(0)
            part_time = params["work_model"] == "part-time"
            if part_time:
                expected /= 2
            expected = expected.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            employee = {
                "id": "SYNTHETIC-EMPLOYEE",
                "regime": params["regime"],
                "cohort": params["cohort"],
                "work_model": params["work_model"],
                "work_model_assessment": "Synthetic fixture work-model comparator",
                "work_model_constant_for_service": True,
                "currency": "AED",
                "service_start": str(start),
                "service_end": str(end),
                "excluded_service_days": 0,
                "monthly_basic_salary": "1500" if part_time else "3000",
                "amount": str(expected),
                "scheme": "gratuity",
                "contract_evidence": "SYNTHETIC-FIXTURE",
            }
            if part_time:
                employee.update(
                    annual_contract_hours="1000",
                    annual_full_time_hours="2000",
                    full_time_monthly_basic_salary="3000",
                )
            return [
                {
                    **base,
                    "employee": employee,
                    "as_of": str(end),
                    "expected_state": "MATCHED",
                    "expected_amount": str(expected),
                }
            ]
        params = body["payroll_parameters"]
        start_amount = Decimal(params.get("threshold_from", "0"))
        upper = params.get("threshold_to")
        amount = (
            (start_amount + Decimal(upper)) / 2
            if upper is not None
            else max(Decimal(1000), start_amount)
        )
        assessed = (
            min(amount, Decimal(params["salary_cap"])) if params.get("salary_cap") else amount
        )
        expected = (
            Decimal(params["fixed_amount"])
            if params["formula"] == "fixed"
            else assessed * Decimal(params["rate"])
        )
        expected = expected.quantize(
            Decimal(".01") if params["rounding"] == "paise" else Decimal(1),
            rounding={
                "paise": ROUND_HALF_UP,
                "nearest-rupee": ROUND_HALF_UP,
                "next-rupee": ROUND_CEILING,
                "floor-rupee": ROUND_FLOOR,
            }[params["rounding"]],
        )
        extra = {}
        if params["formula"] == "employer-minus-eps":
            pension = min(expected, Decimal(1))
            extra["pension_amount"] = str(pension)
            expected -= pension
        first = end.replace(day=1)
        import calendar

        if first < end:
            candidate = (
                date(first.year + 1, 1, 1)
                if first.month == 12
                else date(first.year, first.month + 1, 1)
            )
            candidate_last = candidate.replace(
                day=calendar.monthrange(candidate.year, candidate.month)[1]
            )
            if body.get("effective_to") is None or candidate_last <= date.fromisoformat(
                body["effective_to"]
            ):
                first = candidate

        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        basis = {
            "id": "SYNTHETIC-BASIS",
            "registration": "SYNTHETIC-REG",
            "subject": "SYNTHETIC-EMPLOYEE",
            "period": first.strftime("%Y-%m"),
            "component": params["component"],
            "currency": "INR",
            "amount": str(amount),
            "rule_group": params["rule_group"],
            "jurisdiction": params["jurisdiction"],
            "eligible": True,
            "eligibility_reference": "SYNTHETIC-FIXTURE",
            "assessment": "Synthetic eligibility; not legal qualification",
        }
        supported_month = first >= end and (
            body.get("effective_to") is None or last <= date.fromisoformat(body["effective_to"])
        )
        return [
            {
                **base,
                "basis": basis,
                "as_of": str(last),
                "reported_amount": str(expected),
                "expected_state": "MATCHED" if supported_month else "RULE_MISSING_OR_SPLIT_PERIOD",
                "expected_amount": str(expected) if supported_month else None,
                **extra,
            }
        ]
