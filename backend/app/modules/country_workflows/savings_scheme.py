"""Assessed UAE alternative-scheme basic contributions, distinct from gratuity."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.pension_profiles import Identifier, Money

CONTRACT = "uae-savings-basic-contributions/1"
COMPONENT: Literal["SAVINGS:EMPLOYER_BASIC"] = "SAVINGS:EMPLOYER_BASIC"
WorkModel = Literal["full-time", "part-time", "job-share"]


class SavingsScope(Strict):
    authority: Literal["MOHRE"] = "MOHRE"
    scheme: Literal["MOHRE_SAVINGS"] = "MOHRE_SAVINGS"
    fund_id: Identifier
    membership_reference: Identifier
    enrolled_on: date
    coverage_start: date
    coverage_end: date
    regime: Identifier
    cohort: Identifier
    work_model: WorkModel

    @model_validator(mode="after")
    def dated(self):
        if not self.enrolled_on <= self.coverage_start <= self.coverage_end:
            raise ValueError("Savings contribution coverage must be ordered and follow enrolment")
        if self.coverage_start.strftime("%Y-%m") != self.coverage_end.strftime("%Y-%m"):
            raise ValueError("Savings coverage belongs to one explicit contribution month")
        return self


class SavingsObservation(SavingsScope):
    id: Identifier
    registration: Identifier
    subject: Identifier
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: Literal["SAVINGS:EMPLOYER_BASIC"] = COMPONENT
    currency: Literal["AED"] = "AED"
    amount: Money = Field(ge=0)
    evidence_reference: Identifier

    @model_validator(mode="after")
    def month(self):
        if self.period != self.coverage_start.strftime("%Y-%m"):
            raise ValueError("Savings contribution period must equal its covered wage month")
        return self


class SavingsBasis(SavingsObservation):
    employment_start: date
    employment_end: date | None = None
    eligible: bool
    rate_band: Identifier
    rate_band_assessment: str = Field(min_length=10, max_length=2000)
    salary_basis_kind: Literal["CONTRACT_BASIC", "ASSESSED_FULL_TIME_COMPARATOR"]
    annual_contract_hours: Money | None = Field(default=None, gt=0)
    annual_full_time_hours: Money | None = Field(default=None, gt=0)
    basis_method: Literal["FULL_MONTH_BASIC", "ASSESSED_COVERED_PERIOD_BASIC"]
    period_basis_assessment: str = Field(min_length=10, max_length=2000)
    enrolment_evidence_version_id: UUID
    enrolment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def assessed(self):
        if not self.employment_start <= self.enrolled_on:
            raise ValueError("Savings enrolment cannot predate assessed employment")
        if self.employment_end is not None and self.coverage_end > self.employment_end:
            raise ValueError("Savings wage coverage cannot extend beyond assessed employment")
        first = self.coverage_start.replace(day=1)
        last = self.coverage_end.replace(day=calendar.monthrange(first.year, first.month)[1])
        if self.basis_method == "FULL_MONTH_BASIC" and (self.coverage_start, self.coverage_end) != (
            first,
            last,
        ):
            raise ValueError("A full-month basic wage requires full calendar-month coverage")
        if self.work_model == "full-time":
            if (
                self.salary_basis_kind != "CONTRACT_BASIC"
                or self.annual_contract_hours is not None
                or self.annual_full_time_hours is not None
            ):
                raise ValueError(
                    "Full-time savings bases use contract basic wages without an hours ratio"
                )
        elif (
            self.salary_basis_kind != "ASSESSED_FULL_TIME_COMPARATOR"
            or self.annual_contract_hours is None
            or self.annual_full_time_hours is None
            or self.annual_contract_hours > self.annual_full_time_hours
        ):
            raise ValueError(
                "Other supported work models need an assessed full-time salary comparator and positive comparable annual hours"
            )
        if any(
            len(value.strip()) < 10
            for value in (self.rate_band_assessment, self.period_basis_assessment)
        ):
            raise ValueError(
                "Assess service-rate band and the covered-period basic wage explicitly"
            )
        return self


class SavingsRule(Strict):
    id: Identifier
    authority: Literal["MOHRE"] = "MOHRE"
    scheme: Literal["MOHRE_SAVINGS"] = "MOHRE_SAVINGS"
    fund_id: Identifier
    regime: Identifier
    cohort: Identifier
    work_model: WorkModel
    rate_band: Identifier
    rate: Decimal = Field(ge=0, le=1, max_digits=18, decimal_places=12)
    rounding: Literal["nearest-fils", "next-fils", "floor-fils"]
    effective_from: date
    effective_to: date
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_evidence_version_id: UUID
    source_version: Identifier
    evidence_reference: Identifier
    applicability_review: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to < self.effective_from or len(self.applicability_review.strip()) < 10:
            raise ValueError(
                "Savings rules need ordered dates and a meaningful cohort/rate assessment"
            )
        return self


ROW_TYPES: dict[str, type[BaseModel]] = {
    "savings-bases": SavingsBasis,
    "savings-rules": SavingsRule,
    "savings-reported": SavingsObservation,
}
ROLES = {"bases": "savings-bases", "rules": "savings-rules", "reported": "savings-reported"}
SCOPE = tuple(SavingsScope.model_fields)
RULE_SCOPE = ("authority", "scheme", "fund_id", "regime", "cohort", "work_model", "rate_band")


def enrolment_documents(rows):
    return [
        {
            "source_evidence_version_id": row["enrolment_evidence_version_id"],
            "source_sha256": row["enrolment_sha256"],
        }
        for row in rows
    ]


def identity(row):
    return tuple(
        row[field]
        for field in ("registration", "subject", "period", "component", "currency", *SCOPE)
    )


def calculate(data, tables):
    if data.currency != "AED" or data.tolerance != 0 or data.date_tolerance != 0:
        raise ValueError("Savings contribution review requires AED and exact source controls")
    indexed: dict[str, dict[tuple, dict[str, Any]]] = {}
    for role, model in (("bases", SavingsBasis), ("reported", SavingsObservation)):
        records = {}
        for raw in tables[role]:
            row = model.model_validate(raw).model_dump(mode="json")
            key = identity(row)
            if key in records:
                raise ValueError(
                    "Duplicate savings participant/coverage identity; restate corrections"
                )
            year, month = map(int, row["period"].split("-"))
            if date(year, month, calendar.monthrange(year, month)[1]) > data.as_of:
                raise ValueError("Savings wage month must be closed at the review date")
            records[key] = row
        indexed[role] = records
    bases, reported = indexed["bases"], indexed["reported"]
    if not bases:
        raise ValueError(
            "Supply an explicit enrolled savings basis population, including assessed zeros"
        )
    coverage = defaultdict(list)
    for member in bases.values():
        coverage[(member["registration"], member["subject"], member["period"])].append(member)
    for intervals in coverage.values():
        ordered = sorted(intervals, key=lambda row: row["coverage_start"])
        if any(
            current["coverage_start"] <= prior["coverage_end"]
            for prior, current in zip(ordered, ordered[1:])
        ):
            raise ValueError(
                "Overlapping basic-contribution coverage would double count the employee across fund or work-model records"
            )
    policies = defaultdict(list)
    for raw in tables["rules"]:
        policy = SavingsRule.model_validate(raw).model_dump(mode="json")
        policies[tuple(policy[field] for field in RULE_SCOPE)].append(policy)
    rows: list[dict[str, Any]] = []
    expected_total = Decimal(0)
    problems = False
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for key in sorted(bases.keys() | reported.keys()):
            basis, observed = bases.get(key), reported.get(key)
            rule = None
            state = "BASIS_MISSING" if basis is None else None
            amount = ratio = unrounded = None
            if basis:
                overlapping = [
                    r
                    for r in policies[tuple(basis[f] for f in RULE_SCOPE)]
                    if r["effective_from"] <= basis["coverage_end"]
                    and r["effective_to"] >= basis["coverage_start"]
                ]
                if (
                    len(overlapping) != 1
                    or overlapping[0]["effective_from"] > basis["coverage_start"]
                    or overlapping[0]["effective_to"] < basis["coverage_end"]
                ):
                    state = "RULE_MISSING_SPLIT_OR_AMBIGUOUS"
                else:
                    rule = overlapping[0]
                    ratio = (
                        Decimal(1)
                        if basis["work_model"] == "full-time"
                        else Decimal(basis["annual_contract_hours"])
                        / Decimal(basis["annual_full_time_hours"])
                    )
                    unrounded = (
                        Decimal(basis["amount"]) * Decimal(rule["rate"]) * ratio
                        if basis["eligible"]
                        else Decimal(0)
                    )
                    amount = unrounded.quantize(
                        Decimal("0.01"),
                        rounding={
                            "nearest-fils": ROUND_HALF_UP,
                            "next-fils": ROUND_CEILING,
                            "floor-fils": ROUND_FLOOR,
                        }[rule["rounding"]],
                    )
                    expected_total += amount
            problems = problems or state is not None
            difference = (
                Decimal(observed["amount"]) - amount if observed and amount is not None else None
            )
            state = state or (
                "FUND_OBSERVATION_MISSING"
                if observed is None
                else "MATCHED"
                if difference == 0
                else "FUND_CONTRIBUTION_DIFFERENCE"
            )
            item = basis or observed
            assert item is not None
            scope = {field: item[field] for field in SCOPE}
            rows.append(
                {
                    "id": "savings:" + str(len(rows) + 1),
                    **{
                        field: item[field]
                        for field in ("registration", "subject", "period", "component", "currency")
                    },
                    **scope,
                    "savings_scope": scope,
                    "basis_source_id": basis["id"] if basis else None,
                    "reported_source_id": observed["id"] if observed else None,
                    "rule_source_id": rule["id"] if rule else None,
                    "rate_band": basis["rate_band"] if basis else None,
                    "rule_version": rule["source_version"] if rule else None,
                    "rule_document_sha256": rule["source_sha256"] if rule else None,
                    "assessed_basic_wage": basis["amount"] if basis else None,
                    "hours_ratio": str(ratio) if ratio is not None else None,
                    "rate": rule["rate"] if rule else None,
                    "unrounded_amount": str(unrounded) if unrounded is not None else None,
                    "expected_amount": str(amount) if amount is not None else None,
                    "reported_amount": observed["amount"] if observed else None,
                    "difference": str(difference) if difference is not None else None,
                    "eligible_as_assessed": basis["eligible"] if basis else None,
                    "state": state,
                }
            )
    return {
        "rows": rows,
        "blocked": problems,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "expected_total": str(expected_total),
        "expected_total_complete": not problems,
        "currency": "AED",
        "savings_contribution_contract": CONTRACT,
        "limitations": [
            "Assessed MOHRE savings basic contributions only; fund approval, enrolment, service band, salary comparator and rate applicability are not inferred",
            "Partial-period wage bases and supported work-model salary/hour comparators require explicit retained assessment; no automatic day proration or five-year threshold classification",
            "Pre-enrolment gratuity, pension, voluntary employee savings, fund returns/NAV, redemptions and benefit payout are separate; none are netted against basic contributions",
            "Fund-reported contributions are not bank payment evidence; use controlled remittance expectations and independent bank allocations",
        ],
    }
