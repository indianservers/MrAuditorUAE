"""Dated assessed PF wage bases; no membership, ceiling or rate is inferred."""

import calendar
import uuid
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.country_workflows.payroll_calculations import key
from app.modules.country_workflows.payroll_schemas import Identifier, Money, PayrollBasis
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "india-payroll-basis-proration/1"
COMPONENTS = {"PF:EMPLOYEE", "PF:EPS", "PF:EMPLOYER"}
PFComponent = Literal["PF:EMPLOYEE", "PF:EPS", "PF:EMPLOYER"]
ROLES = {
    "segments": "payroll-basis-segments",
    "rules": "payroll-cap-rules",
    "controls": "payroll-bases",
}


def month_span(period):
    year, month = map(int, period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def prorate(monthly, days, denominator):
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return (Decimal(monthly) * days / denominator).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class PayrollBasisSegment(PayrollBasis):
    component: PFComponent
    segment_start: date
    segment_end: date
    monthly_reference_basis: Money = Field(ge=0)
    proration_method: Literal["ACTUAL_CALENDAR_MONTH_PAISE"]

    @model_validator(mode="after")
    def dated_basis(self):
        first, last = month_span(self.period)
        if not first <= self.segment_start <= self.segment_end <= last:
            raise ValueError("Wage segment must be an ordered interval within its wage month")
        expected = prorate(
            self.monthly_reference_basis,
            (self.segment_end - self.segment_start).days + 1,
            last.day,
        )
        if self.amount != expected:
            raise ValueError("Uncapped segment amount must equal its explicit calendar-paise basis")
        if len(self.assessment.strip()) < 10 or len(self.eligibility_reference.strip()) < 3:
            raise ValueError("Assess segment eligibility and retain its supporting reference")
        return self


class PayrollCapRule(Strict):
    id: Identifier
    rule_group: Identifier
    component: PFComponent
    jurisdiction: Identifier
    effective_from: date
    effective_to: date
    cap_mode: Literal["CAPPED", "ASSESSED_ACTUAL_BASIS"]
    monthly_ceiling: Money | None = Field(default=None, gt=0)
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_evidence_version_id: uuid.UUID
    source_version: Identifier
    evidence_reference: Identifier
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def explicit_policy(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Ceiling policy dates must be ordered")
        if (self.cap_mode == "CAPPED") != (self.monthly_ceiling is not None):
            raise ValueError("Supply a ceiling only for an explicitly capped policy")
        if len(self.applicability_review.strip()) < 10:
            raise ValueError("Assess the membership cohort and applicable ceiling option")
        return self


ROW_TYPES: dict[str, type[BaseModel]] = {
    "payroll-basis-segments": PayrollBasisSegment,
    "payroll-cap-rules": PayrollCapRule,
}


def rate_profile_error(basis, rule):
    if basis.get("post_cap_basis_contract") != CONTRACT:
        return None
    if (
        rule.get("salary_cap") is not None
        or Decimal(rule["threshold_from"]) != 0
        or rule.get("threshold_to") is not None
        or rule["formula"] not in {"rate", "employer-minus-eps"}
    ):
        return "POST_CAP_BASIS_REQUIRES_UNCAPPED_RATE_WITHOUT_WAGE_SLABS"
    return None


def calculate(data, tables):
    if data.currency != "INR" or data.tolerance != 0 or data.date_tolerance != 0:
        raise ValueError("Dated PF wage bases require INR and exact amount/calendar controls")
    segments: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    controls = {}
    ids = set()
    for raw in tables["segments"]:
        row = PayrollBasisSegment.model_validate(raw).model_dump(mode="json")
        if row["id"] in ids:
            raise ValueError("Duplicate wage-segment source identifier")
        ids.add(row["id"])
        segments[key(row)].append(row)
    for raw in tables["controls"]:
        row = PayrollBasis.model_validate(raw).model_dump(mode="json")
        if row["component"] not in COMPONENTS or key(row) in controls:
            raise ValueError("Monthly PF controls must be unique employee/month/components")
        controls[key(row)] = row
    if not segments or not controls:
        raise ValueError("Explicit wage segments and independent monthly controls are required")
    rules = [PayrollCapRule.model_validate(r).model_dump(mode="json") for r in tables["rules"]]
    if not rules or len({r["id"] for r in rules}) != len(rules):
        raise ValueError("Distinct retained ceiling policies are required")
    identities = segments.keys() | controls.keys()
    population: dict[tuple, set[str]] = defaultdict(set)
    for identity in identities:
        population[identity[:3] + identity[4:]].add(identity[3])
    if any(components != COMPONENTS for components in population.values()):
        raise ValueError("Retain all three PF component bases, including assessed excluded zeros")
    rows: list[dict[str, Any]] = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for identity in sorted(identities):
            first, last = month_span(identity[2])
            if last > data.as_of:
                raise ValueError("Wage month must close before the calculation date")
            records = sorted(segments.get(identity, []), key=lambda r: r["segment_start"])
            control = controls.get(identity)
            trace = []
            expected = Decimal(0)
            next_day = first.toordinal()
            problem = None if records and control else "MONTH_CONTROL_OR_SEGMENTS_MISSING"
            for record in records:
                start, end = map(
                    date.fromisoformat, (record["segment_start"], record["segment_end"])
                )
                if start.toordinal() != next_day:
                    problem = problem or "SEGMENT_GAP_OR_OVERLAP"
                next_day = end.toordinal() + 1
                if control and any(
                    record[field] != control[field] for field in ("rule_group", "jurisdiction")
                ):
                    problem = problem or "MONTH_CONTROL_SCOPE_DIFFERENCE"
                matching = [
                    rule
                    for rule in rules
                    if all(
                        rule[field] == record[field]
                        for field in ("component", "rule_group", "jurisdiction")
                    )
                    and date.fromisoformat(rule["effective_from"]) <= start
                    and date.fromisoformat(rule["effective_to"]) >= end
                ]
                intersecting = [
                    rule
                    for rule in rules
                    if all(
                        rule[field] == record[field]
                        for field in ("component", "rule_group", "jurisdiction")
                    )
                    and date.fromisoformat(rule["effective_from"]) <= end
                    and date.fromisoformat(rule["effective_to"]) >= start
                ]
                policy = matching[0] if len(matching) == len(intersecting) == 1 else None
                if policy is None:
                    problem = problem or "CEILING_POLICY_MISSING_SPLIT_OR_AMBIGUOUS"
                    value = None
                else:
                    monthly = Decimal(record["monthly_reference_basis"])
                    if policy["cap_mode"] == "CAPPED":
                        monthly = min(monthly, Decimal(policy["monthly_ceiling"]))
                    value = (
                        prorate(monthly, (end - start).days + 1, last.day)
                        if record["eligible"]
                        else Decimal(0)
                    )
                    expected += value
                trace.append(
                    {
                        **record,
                        "calendar_days": (end - start).days + 1,
                        "month_days": last.day,
                        "cap_rule_id": policy["id"] if policy else None,
                        "cap_rule": policy,
                        "post_cap_segment_basis": str(value) if value is not None else None,
                    }
                )
            if next_day != last.toordinal() + 1:
                problem = problem or "SEGMENT_GAP_OR_OVERLAP"
            eligible = any(r["eligible"] for r in records)
            if control and control["eligible"] != eligible:
                problem = problem or "MONTH_ELIGIBILITY_CONTROL_DIFFERENCE"
            wanted = None if problem else expected
            difference = (
                Decimal(control["amount"]) - wanted if control and wanted is not None else None
            )
            state = problem or ("MATCHED" if difference == 0 else "MONTH_BASIS_CONTROL_DIFFERENCE")
            rows.append(
                {
                    "id": "prorated:" + str(len(rows) + 1),
                    "registration": identity[0],
                    "subject": identity[1],
                    "period": identity[2],
                    "component": identity[3],
                    "currency": identity[4],
                    "rule_group": control["rule_group"] if control else None,
                    "jurisdiction": control["jurisdiction"] if control else None,
                    "eligible": eligible,
                    "basis_source_id": control["id"] if control else None,
                    "computed_monthly_basis": str(wanted) if wanted is not None else None,
                    "controlled_monthly_basis": control["amount"] if control else None,
                    "difference": str(difference) if difference is not None else None,
                    "state": state,
                    "segment_trace": trace,
                }
            )
    blocked = any(r["state"] != "MATCHED" for r in rows)
    return {
        "rows": rows,
        "blocked": blocked,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "monthly_basis_complete": not blocked,
        "payroll_proration_contract": CONTRACT,
        "currency": "INR",
        "limitations": [
            "Calendar-paise proration of explicit assessed PF wage bases only; membership, higher-wage options and ceiling amounts require retained independent assessment",
            "All calendar days and all three component bases must be explicit, including ineligible periods; missing coverage is not zero",
            "This produces wage bases, not contributions or payment proof; apply separately reviewed contribution rates without applying a ceiling again",
            "ESI/PT, EDLI/establishment administration minima, changing contribution rates, interest, damages and native ECR filing are outside this calculation",
        ],
    }
