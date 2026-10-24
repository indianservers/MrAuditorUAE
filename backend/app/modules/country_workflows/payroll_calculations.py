"""Calculate from reviewed rule inputs; never infer coverage, rates or membership."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any


def key(row):
    return (
        row["registration"].upper(),
        row["subject"].upper(),
        row["period"],
        row["component"],
        row["currency"],
    )


def rounding(amount, method):
    return amount.quantize(
        Decimal("0.01") if method == "paise" else Decimal(1),
        rounding={
            "nearest-rupee": ROUND_HALF_UP,
            "next-rupee": ROUND_CEILING,
            "floor-rupee": ROUND_FLOOR,
            "paise": ROUND_HALF_UP,
        }[method],
    )


def payroll_rules(data, tables):
    if data.currency != "INR":
        raise ValueError("India payroll rule calculations require INR")
    bases, selected, expected, problems = {}, {}, {}, {}
    rule_groups = defaultdict(list)
    for rule in tables["rules"]:
        rule_groups[(rule["rule_group"], rule["component"], rule["jurisdiction"])].append(rule)
    for row in tables["bases"]:
        identity = key(row)
        if identity in bases:
            raise ValueError(
                "Duplicate payroll subject/month/component; resolve allocations before calculating"
            )
        bases[identity] = row
        year, month = map(int, row["period"].split("-"))
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        if last > data.as_of:
            raise ValueError("Payroll wage month closes after the reconciliation date")
        base = Decimal(row["amount"])
        rules = [
            rule
            for rule in rule_groups[(row["rule_group"], row["component"], row["jurisdiction"])]
            if date.fromisoformat(rule["effective_from"]) <= first
            and date.fromisoformat(rule["effective_to"]) >= last
            and Decimal(rule["threshold_from"]) <= base
            and (rule["threshold_to"] is None or base < Decimal(rule["threshold_to"]))
        ]
        if len(rules) != 1:
            problems[identity] = "RULE_MISSING_OR_SPLIT_PERIOD" if not rules else "AMBIGUOUS_RULE"
            continue
        rule = selected[identity] = rules[0]
        if not row["eligible"]:
            expected[identity] = Decimal(0)
        elif rule["formula"] == "fixed":
            expected[identity] = rounding(Decimal(rule["fixed_amount"]), rule["rounding"])
        elif rule["formula"] != "employer-minus-eps":
            assessed = (
                min(base, Decimal(rule["salary_cap"])) if rule["salary_cap"] is not None else base
            )
            expected[identity] = rounding(assessed * Decimal(rule["rate"]), rule["rounding"])
    # EPS must itself be resolved under a reviewed rule for this exact employee,
    # establishment and month. An absent/ambiguous pension row is never zero.
    for identity, row in bases.items():
        rule = selected.get(identity)
        if not rule or rule["formula"] != "employer-minus-eps" or identity in expected:
            continue
        pension_key = identity[:3] + ("PF:EPS", identity[4])
        if pension_key not in expected:
            problems[identity] = "PENSION_COMPONENT_UNRESOLVED"
            continue
        if bases[pension_key]["jurisdiction"] != row["jurisdiction"]:
            problems[identity] = "PENSION_JURISDICTION_DIFFERENCE"
            continue
        base = Decimal(row["amount"])
        assessed = (
            min(base, Decimal(rule["salary_cap"])) if rule["salary_cap"] is not None else base
        )
        total_employer = rounding(assessed * Decimal(rule["rate"]), rule["rounding"])
        contribution = total_employer - expected[pension_key]
        if contribution < 0:
            problems[identity] = "PENSION_EXCEEDS_EMPLOYER_CONTRIBUTION"
        else:
            expected[identity] = contribution
    reported: dict[tuple, dict[str, Any]] = defaultdict(lambda: {"amount": Decimal(0), "ids": []})
    for row in tables["reported"]:
        if row["period"] > data.as_of.strftime("%Y-%m") or row["currency"] != "INR":
            raise ValueError("Reported payroll period or currency is outside this calculation")
        value = Decimal(row["amount"])
        if value < 0:
            raise ValueError(
                "Negative reported payroll contributions require a corrected allocation source"
            )
        reported[key(row)]["amount"] += value
        reported[key(row)]["ids"].append(row["id"])
    rows: list[dict[str, Any]] = []
    blocked = bool(problems)
    for identity in sorted(bases.keys() | reported.keys()):
        basis, actual, rule = bases.get(identity), reported.get(identity), selected.get(identity)
        wanted = expected.get(identity)
        delta = actual["amount"] - wanted if actual and wanted is not None else None
        state = problems.get(identity) or (
            "REPORTED_ONLY"
            if not basis
            else "REPORTED_COMPONENT_MISSING"
            if not actual
            else "MATCHED"
            if delta is not None and abs(delta) <= data.tolerance
            else "CONTRIBUTION_DIFFERENCE"
        )
        rows.append(
            {
                "id": "payroll:" + str(len(rows) + 1),
                "registration": identity[0],
                "subject": identity[1],
                "period": identity[2],
                "component": identity[3],
                "currency": identity[4],
                "basis_source_id": basis["id"] if basis else None,
                "rule_source_id": rule["id"] if rule else None,
                "rule_version": rule["source_version"] if rule else None,
                "rule_document_sha256": rule["source_sha256"] if rule else None,
                "rule_url": rule["source_url"] if rule else None,
                "formula": rule["formula"] if rule else None,
                "rate": rule["rate"] if rule else None,
                "fixed_amount": rule["fixed_amount"] if rule else None,
                "salary_cap": rule["salary_cap"] if rule else None,
                "rounding": rule["rounding"] if rule else None,
                "jurisdiction": basis["jurisdiction"] if basis else None,
                "eligibility_reference": basis["eligibility_reference"] if basis else None,
                "eligible_as_declared": basis["eligible"] if basis else None,
                "assessed_base": basis["amount"] if basis else None,
                "expected_amount": str(wanted) if wanted is not None else None,
                "reported_amount": str(actual["amount"]) if actual else None,
                "reported_source_ids": actual["ids"] if actual else [],
                "difference": str(delta) if delta is not None else None,
                "state": state,
                "payment_verification": "NOT_PERFORMED_BY_CONTRIBUTION_REVIEW",
            }
        )
    return {
        "rows": rows,
        "blocked": blocked,
        "exception_count": sum(row["state"] != "MATCHED" for row in rows),
        "expected_total": str(sum(expected.values(), Decimal(0))),
        "expected_total_complete": not problems,
        "expected_total_basis": "RESOLVED_ASSESSED_COMPONENTS_ONLY_NOT_GROSS_PAYROLL",
        "reported_total": str(sum((row["amount"] for row in reported.values()), Decimal(0))),
        "currency": "INR",
        "limitations": [
            "Rates, wage bases, membership, continuity, exemptions and jurisdiction/cohort choices are explicit reviewed inputs; no legal entitlement is inferred",
            "Each selected rule must cover the whole wage month; mid-month changes require a separate supported assessment",
            "Half-open source-defined slabs select one rule; overlapping or missing rules block approval",
            "Employer PF is rounded total employer contribution less separately resolved EPS; no pension component is silently treated as zero",
            "This compares expected and reported contributions only; use statutory-dues for independent payment evidence",
            "EDLI/administration fees, interest, damages and filing are not calculated by this workflow",
        ],
    }


PAYROLL_CALCULATORS = {"india-payroll-rules": payroll_rules}
