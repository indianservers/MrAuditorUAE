"""Compare separately assessed UAE pension contributions with reported amounts."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

SCOPE = (
    "authority",
    "scheme",
    "membership_cohort",
    "pension_country",
    "nationality",
    "employment_sector",
    "jurisdiction",
)
IDENTITY = ("registration", "subject", "period", "component", "currency", *SCOPE)


def identity(row):
    return tuple(row[field] for field in IDENTITY)


def pension(data, tables):
    if data.currency != "AED":
        raise ValueError("UAE pension review requires explicitly assessed AED amounts")
    bases: dict[tuple, dict[str, Any]] = {}
    reported: dict[tuple, dict[str, Any]] = {}
    for role, target in (("bases", bases), ("reported", reported)):
        for row in tables[role]:
            key = identity(row)
            if key in target:
                raise ValueError(
                    "Duplicate pension identity; restate corrections before comparison"
                )
            year, month = map(int, row["period"].split("-"))
            end = date(year, month, calendar.monthrange(year, month)[1])
            if end > data.as_of or row["currency"] != "AED":
                raise ValueError("Pension wage month must be closed and use AED")
            target[key] = row
    selected, expected, problems = {}, {}, {}
    details: dict[tuple, dict[str, Any]] = {}
    grouped = defaultdict(list)
    for rule in tables["rules"]:
        grouped[tuple(rule[field] for field in (*SCOPE, "component"))].append(rule)
    for key, basis in bases.items():
        year, month = map(int, basis["period"].split("-"))
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        overlapping = [
            rule
            for rule in grouped[tuple(basis[field] for field in (*SCOPE, "component"))]
            if (
                "selected_wage_months" not in rule
                or basis["period"] in rule["selected_wage_months"]
            )
            and date.fromisoformat(rule["effective_from"]) <= last
            and date.fromisoformat(rule["effective_to"]) >= first
        ]
        rules = [
            rule
            for rule in overlapping
            if date.fromisoformat(rule["effective_from"]) <= first
            and date.fromisoformat(rule["effective_to"]) >= last
        ]
        if len(rules) != len(overlapping):
            problems[key] = "RULE_MISSING_OR_SPLIT_PERIOD"
            continue
        if len(rules) != 1:
            problems[key] = "AMBIGUOUS_RULE" if rules else "RULE_MISSING_OR_SPLIT_PERIOD"
            continue
        rule = selected[key] = rules[0]
        amount = Decimal(basis["amount"])
        if not basis["eligible"]:
            expected[key] = Decimal(0)
            continue
        if amount < Decimal(rule["minimum_basis"]):
            problems[key] = "ASSESSED_SALARY_BELOW_REVIEWED_MINIMUM"
            continue
        ceiling = rule.get("exclusive_eligibility_ceiling")
        if ceiling is not None and amount >= Decimal(ceiling):
            expected[key] = Decimal(0)
            details[key] = {
                "eligibility_outcome": "AT_OR_ABOVE_REVIEWED_EXCLUSIVE_SALARY_CEILING",
                "eligibility_basis": str(amount),
                "exclusive_eligibility_ceiling": str(ceiling),
            }
            continue
        capped = min(amount, Decimal(rule["salary_cap"])) if rule["salary_cap"] else amount
        unrounded = (
            Decimal(rule["fixed_amount"])
            if rule["formula"] == "fixed"
            else capped * Decimal(rule["rate"])
        )
        rounded = unrounded.quantize(
            Decimal("0.01"),
            rounding={
                "nearest-fils": ROUND_HALF_UP,
                "next-fils": ROUND_CEILING,
                "floor-fils": ROUND_FLOOR,
            }[rule["rounding"]],
        )
        details[key] = {
            "capped_base": str(capped),
            "unrounded_amount": str(unrounded),
            "rounded_gross_contribution": str(rounded),
        }
        if rule["formula"] != "employer-minus-government":
            expected[key] = rounded
    for key, basis in bases.items():
        rule = selected.get(key)
        if (
            not rule
            or rule["formula"] != "employer-minus-government"
            or key in expected
            or key in problems
        ):
            continue
        support_key = identity({**basis, "component": "PENSION:GOVERNMENT"})
        if support_key not in expected:
            problems[key] = "GOVERNMENT_SUPPORT_UNRESOLVED"
            continue
        support_basis = bases[support_key]
        support_rule = selected[support_key]
        salary_dependent = (
            support_rule["formula"] != "fixed"
            or Decimal(support_rule["minimum_basis"]) > 0
            or support_rule.get("exclusive_eligibility_ceiling") is not None
        )
        details[key].update(
            {
                "government_basis_source_id": support_basis["id"],
                "government_assessed_base": support_basis["amount"],
                "government_salary_basis_reference": support_basis["salary_basis_reference"],
                "government_salary_basis_required": salary_dependent,
            }
        )
        if salary_dependent and Decimal(support_basis["amount"]) != Decimal(basis["amount"]):
            problems[key] = "GOVERNMENT_SUPPORT_SALARY_BASIS_MISMATCH"
            continue
        support = expected[support_key]
        gross = Decimal(details[key]["rounded_gross_contribution"])
        details[key].update(
            {
                "government_support": str(support),
                "government_basis_source_id": bases[support_key]["id"],
            }
        )
        if support > gross:
            problems[key] = "GOVERNMENT_SUPPORT_EXCEEDS_EMPLOYER_CONTRIBUTION"
        else:
            expected[key] = gross - support
    rows: list[dict[str, Any]] = []
    for key in sorted(bases.keys() | reported.keys()):
        basis_row, actual, rule = bases.get(key), reported.get(key), selected.get(key)
        wanted = expected.get(key)
        difference = Decimal(actual["amount"]) - wanted if actual and wanted is not None else None
        state = problems.get(key) or (
            "REPORTED_ONLY"
            if not basis_row
            else "REPORTED_COMPONENT_MISSING"
            if not actual
            else "MATCHED"
            if difference is not None and abs(difference) <= data.tolerance
            else "CONTRIBUTION_DIFFERENCE"
        )
        record = basis_row or actual
        assert record is not None
        rows.append(
            {
                "id": "pension:" + str(len(rows) + 1),
                **{field: record[field] for field in IDENTITY},
                "basis_source_id": basis_row["id"] if basis_row else None,
                "reported_source_id": actual["id"] if actual else None,
                "assessed_base": basis_row["amount"] if basis_row else None,
                "eligible_as_declared": basis_row["eligible"] if basis_row else None,
                "membership_reference": basis_row["membership_reference"] if basis_row else None,
                "salary_basis_reference": basis_row["salary_basis_reference"]
                if basis_row
                else None,
                "rule_source_id": rule["id"] if rule else None,
                "rule_version": rule["source_version"] if rule else None,
                "rule_document_sha256": rule["source_sha256"] if rule else None,
                "rule_url": rule["source_url"] if rule else None,
                **(
                    {
                        field: rule[field]
                        for field in (
                            "source_document_id",
                            "published_rule_version_id",
                            "published_rule_sha256",
                            "source_copies",
                        )
                    }
                    if rule and rule.get("published_rule_version_id")
                    else {}
                ),
                "formula": rule["formula"] if rule else None,
                "rate": rule["rate"] if rule else None,
                "rounding": rule["rounding"] if rule else None,
                "exclusive_eligibility_ceiling": rule.get("exclusive_eligibility_ceiling")
                if rule
                else None,
                **details.get(key, {}),
                "expected_amount": str(wanted) if wanted is not None else None,
                "reported_amount": actual["amount"] if actual else None,
                "difference": str(difference) if difference is not None else None,
                "state": state,
                "payment_verification": "NOT_PERFORMED_BY_CONTRIBUTION_REVIEW",
            }
        )
    complete = not problems and not (reported.keys() - bases.keys())
    return {
        "rows": rows,
        "blocked": not complete,
        "exception_count": sum(row["state"] != "MATCHED" for row in rows),
        "expected_total": str(sum(expected.values(), Decimal(0))),
        "expected_total_complete": complete,
        "expected_total_basis": "RESOLVED_ASSESSED_COMPONENTS_ONLY_NOT_GROSS_PAYROLL",
        "reported_total": str(
            sum((Decimal(row["amount"]) for row in reported.values()), Decimal(0))
        ),
        "currency": "AED",
        "limitations": [
            "Authority, scheme, nationality, membership continuity, employment jurisdiction and sector are assessed inputs; no statutory coverage is inferred",
            "Salary bases must already reflect the applicable salary definition, reference month and any assessed partial-month treatment; this workflow does not derive them from gross payroll",
            "No statutory rates, ceilings, government support eligibility or rounding methods are supplied by default",
            "Rules must cover the whole wage month; missing or overlapping rules block approval",
            "Employer-minus-government deducts only separately resolved support for the exact employee, registration, month and pension scope; no missing support is treated as zero",
            "Salary-dependent government support and net employer contributions must use the same assessed contribution-account salary before caps; contradictory salary bases block netting, including threshold-driven zero-support claims",
            "Totals add employee, net employer and separately assessed government components; they are not solely the employer bank payment",
            "Filing, payment, arrears, penalties, gratuity and pension entitlements are not established by contribution comparison",
        ],
    }


PENSION_CALCULATORS = {"uae-pension-review": pension}
