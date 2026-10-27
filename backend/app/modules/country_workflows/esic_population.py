"""Assessed ESIC member/wage populations, separate from contribution liabilities."""

import calendar
import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.jurisdictions.profiles import Strict

REFERENCE = "https://portal.esic.gov.in/InsuranceGlobalWebV4/ESICInsurancePortal/Documents/MC_Presentation.pdf"


class ESICMember(Strict):
    id: str = Field(min_length=1, max_length=120)
    registration: str = Field(pattern=r"^[0-9]{17}$")
    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    subject: str = Field(pattern=r"^[0-9]{10}$")
    member_name: str = Field(min_length=1, max_length=200)
    paid_days: int = Field(ge=0, le=31)
    amount: Decimal = Field(ge=0, max_digits=28, decimal_places=2, allow_inf_nan=False)
    currency: Literal["INR"] = "INR"
    zero_wage_reason: str = Field(default="", max_length=120)
    zero_day_reason: str = Field(default="", max_length=120)
    last_working_day: date | None = None
    evidence_reference: str = Field(min_length=1, max_length=120)
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("paid_days", mode="before")
    @classmethod
    def whole_days(cls, value):
        if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,2}", str(value)):
            raise ValueError("Retain whole paid days without rounding source values")
        return value

    @model_validator(mode="after")
    def assessed(self):
        _, end = month_bounds(self.period)
        if self.paid_days > end.day:
            raise ValueError("Paid days exceed the calendar month")
        if self.last_working_day and self.last_working_day > end:
            raise ValueError("Last working day is after the wage month")
        if self.amount == 0 and not self.zero_wage_reason:
            raise ValueError("Retain the assessed reason for zero wages")
        if self.amount > 0 and self.zero_wage_reason:
            raise ValueError("Zero-wage reason cannot accompany positive wages")
        for value in (self.id, self.member_name, self.evidence_reference, self.assessment):
            if not value.strip() or value != value.strip():
                raise ValueError("Retain exact nonblank ESIC identifiers and assessments")
        if (
            self.zero_wage_reason != self.zero_wage_reason.strip()
            or self.zero_day_reason != self.zero_day_reason.strip()
        ):
            raise ValueError("Retain the exact assessed zero-wage reason")
        return self


def month_bounds(period):
    year, month = map(int, period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def verify_controls(rows, paid_days, zero_members):
    actual = {
        "paid_days": sum(row["paid_days"] for row in rows),
        "zero_wage_members": sum(Decimal(row["amount"]) == 0 for row in rows),
    }
    if actual != {"paid_days": paid_days, "zero_wage_members": zero_members}:
        raise ValueError("Independent ESIC paid-day or zero-wage member controls do not agree")
    return actual


def compare(data, tables):
    if data.currency != "INR":
        raise ValueError("ESIC population reconciliation requires INR")
    populations: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {}
    scopes = set()
    for role, records in tables.items():
        population = populations[role] = {}
        for row in records:
            key = row["registration"], row["period"], row["subject"]
            if key in population:
                raise ValueError("Duplicate ESIC member within employer and wage month")
            population[key] = row
            scopes.add(key[:2])
            if month_bounds(row["period"])[1] > data.as_of:
                raise ValueError("ESIC wage month closes after reconciliation date")
    if len(scopes) != 1:
        raise ValueError("Select one explicit ESIC employer and wage month across both populations")
    rows: list[dict[str, Any]] = []
    for index, key in enumerate(
        sorted(populations["payroll"].keys() | populations["reported"].keys()), 1
    ):
        payroll, reported = (populations[role].get(key) for role in ("payroll", "reported"))
        issues = (["MISSING_PAYROLL_MEMBER"] if payroll is None else []) + (
            ["MISSING_REPORTED_MEMBER"] if reported is None else []
        )
        difference = (
            Decimal(reported["amount"]) - Decimal(payroll["amount"])
            if payroll and reported
            else None
        )
        day_difference = (
            reported["paid_days"] - payroll["paid_days"] if payroll and reported else None
        )
        if payroll and reported:
            if difference is not None and abs(difference) > data.tolerance:
                issues.append("WAGE_VARIANCE")
            if day_difference:
                issues.append("PAID_DAY_VARIANCE")
            for field in ("member_name", "zero_wage_reason", "zero_day_reason", "last_working_day"):
                if payroll[field] != reported[field]:
                    issues.append(field.upper() + "_DIFFERENCE")
        rows.append(
            {
                "id": f"esic-member:{index}",
                "registration": key[0],
                "period": key[1],
                "subject": key[2],
                **{
                    f"{role}_{field}": row[field] if row else None
                    for role, row in (("payroll", payroll), ("reported", reported))
                    for field in (
                        "id",
                        "member_name",
                        "amount",
                        "paid_days",
                        "zero_wage_reason",
                        "zero_day_reason",
                        "last_working_day",
                        "evidence_reference",
                    )
                },
                "currency": "INR",
                "wage_difference": str(difference) if difference is not None else None,
                "paid_day_difference": day_difference,
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            blocked=any(
                any(issue.startswith("MISSING_") for issue in row["exceptions"]) for row in rows
            ),
            limitations=[
                "Controlled member/wage populations; native file structure checks do not establish current portal compatibility, retrieval, filing or payment evidence",
                "Employer/IP identifiers and zero-wage reasons are assessed inputs; registry membership, reason-code applicability and employment status require independent verification",
                "Wages are not contributions: eligibility, contribution bases, rates, rounding and challan/bank settlement remain separate reviewed procedures",
                "Monetary tolerance never excuses member identity, paid-day, name, reason or leaving-date differences; supplementary returns are not automatically merged",
            ],
        ),
        "esic_population_scope": dict(
            zip(("registration", "period"), next(iter(scopes)), strict=True)
        ),
        "esic_population_contract": "india-esic-population/1",
        "esic_profile_reference": REFERENCE,
        "esic_population_totals": {
            role: {
                "members": len(records),
                "wages": str(sum((Decimal(row["amount"]) for row in records.values()), Decimal(0))),
                "paid_days": sum(row["paid_days"] for row in records.values()),
                "zero_wage_members": sum(Decimal(row["amount"]) == 0 for row in records.values()),
            }
            for role, records in populations.items()
        },
    }
