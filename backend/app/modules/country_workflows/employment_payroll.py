"""Assessed employment/month payroll evidence; no salary entitlement inferred."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.country_workflows.audit_calculations import result
from app.modules.jurisdictions.profiles import Strict

ID = Annotated[str, Field(min_length=1, max_length=120)]
Token = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Month = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Component = Literal["BASIC", "ALLOWANCE", "GROSS", "DEDUCTION", "BONUS", "OTHER_ASSESSED"]
Kind = Literal["regular", "arrears", "settlement", "assessed_adjustment"]
CONTRACT = "employment-payroll-period-controls/1"
ROLES = {
    "employment": "employment-payroll-episodes",
    "controls": "employment-payroll-controls",
    "register": "employment-payroll-register",
}


def month_span(value):
    year, month = map(int, value.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


class EmploymentKey(Strict):
    id: ID
    registration: ID
    employee_token: Token
    episode_reference: ID
    component: Component
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    evidence_reference: ID

    @field_validator("id", "registration", "episode_reference", "evidence_reference")
    @classmethod
    def exact_identifiers(cls, value):
        if value != value.strip() or not value.strip():
            raise ValueError("Use exact nonblank identifiers and pseudonymous employee tokens")
        return value


class EmploymentEpisode(EmploymentKey):
    started_on: date
    ended_on: date | None = None
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def dates(self):
        if (self.ended_on is not None and self.ended_on < self.started_on) or len(
            self.assessment.strip()
        ) < 10:
            raise ValueError("Employment episode dates must be ordered")
        return self


class PayrollObservation(EmploymentKey):
    payroll_month: Month
    earning_month: Month
    category: Kind
    entry_reference: ID
    amount: Money

    @field_validator("amount", mode="before")
    @classmethod
    def exact_amount(cls, value):
        if isinstance(value, (bool, float)):
            raise ValueError("Use exact decimal strings or integers for payroll amounts")
        return value

    @model_validator(mode="after")
    def months(self):
        month_span(self.payroll_month)
        month_span(self.earning_month)
        if (
            self.earning_month > self.payroll_month
            or (self.category == "regular" and self.earning_month != self.payroll_month)
            or (self.category == "arrears" and self.earning_month >= self.payroll_month)
        ):
            raise ValueError(
                "Regular earnings use the payroll month; arrears use an earlier earning month"
            )
        if not self.entry_reference.strip() or self.entry_reference != self.entry_reference.strip():
            raise ValueError("Retain an exact independently assessed payroll entry reference")
        return self


class EmploymentPayrollControl(PayrollObservation):
    service_from: date
    service_through: date
    contract_reference: ID
    attendance_reference: ID
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def service_dates(self):
        first, last = month_span(self.earning_month)
        if not first <= self.service_from <= self.service_through <= last:
            raise ValueError("Assessed service dates must be inside the earning month")
        if not self.contract_reference.strip() or not self.attendance_reference.strip():
            raise ValueError("Retain contract/master-change and attendance assessment references")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Retain a meaningful independent payroll expectation assessment")
        return self


class EmploymentPayrollRegister(PayrollObservation):
    revision: int = Field(ge=1, strict=False)
    record_status: Literal["current", "superseded", "cancelled"]
    run_reference: ID

    @field_validator("revision", mode="before")
    @classmethod
    def exact_revision(cls, value):
        if isinstance(value, (bool, float)):
            raise ValueError("Use a whole-number revision identifier")
        return value

    @field_validator("run_reference")
    @classmethod
    def run_identity(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Retain an exact payroll run reference")
        return value


ROW_TYPES: dict[str, type[BaseModel]] = {
    "employment-payroll-episodes": EmploymentEpisode,
    "employment-payroll-controls": EmploymentPayrollControl,
    "employment-payroll-register": EmploymentPayrollRegister,
}


def employee_key(row):
    return tuple(
        row[field]
        for field in (
            "registration",
            "employee_token",
            "episode_reference",
            "component",
            "currency",
        )
    )


def observation_key(row):
    return employee_key(row) + tuple(
        row[field] for field in ("payroll_month", "earning_month", "category", "entry_reference")
    )


def reconcile(data, tables):
    start, end = data.period_start, data.as_of
    if (
        start is None
        or start.day != 1
        or start > end
        or end != month_span(end.strftime("%Y-%m"))[1]
    ):
        raise ValueError("Employment payroll review requires complete ordered calendar months")
    episodes, controls, registered = {}, {}, {}
    episode_dates: dict[tuple[str, ...], tuple[str, str | None]] = {}
    for item in tables["employment"]:
        key = employee_key(item)
        if key in episodes:
            raise ValueError("Resolve duplicate employment episode/component/currency facts")
        episodes[key] = item
        dates = item["started_on"], item["ended_on"]
        if key[:3] in episode_dates and episode_dates[key[:3]] != dates:
            raise ValueError("Employment dates conflict across components of the same episode")
        episode_dates[key[:3]] = dates
    for item in tables["controls"]:
        key = observation_key(item)
        if key in controls:
            raise ValueError("Resolve duplicate independently assessed payroll entry controls")
        controls[key] = item
    groups = defaultdict(list)
    for item in tables["register"]:
        groups[observation_key(item)].append(item)
    history = []
    for key, versions in groups.items():
        first, last = month_span(key[5])
        if not start <= first <= last <= end:
            raise ValueError("All payroll revisions must lie within the declared review months")
        revisions = [item["revision"] for item in versions]
        latest = max(versions, key=lambda item: item["revision"])
        current = [item for item in versions if item["record_status"] == "current"]
        if (
            len(set(revisions)) != len(revisions)
            or len(current) > 1
            or latest["record_status"] == "superseded"
            or (current and current[0] is not latest)
        ):
            raise ValueError("Resolve duplicate, ambiguous or superseded current payroll revisions")
        if latest["record_status"] == "current":
            registered[key] = latest
        for item in versions:
            history.append(
                {
                    "id": "revision:" + item["id"],
                    "kind": "revision-history",
                    "employee_token": item["employee_token"],
                    **{
                        field: item[field]
                        for field in (
                            "registration",
                            "episode_reference",
                            "component",
                            "currency",
                            "payroll_month",
                            "earning_month",
                            "category",
                            "entry_reference",
                        )
                    },
                    "source_row_id": item["id"],
                    "revision": item["revision"],
                    "record_status": item["record_status"],
                    "run_reference": item["run_reference"],
                    "retained_amount": item["amount"],
                    "counted_in_current_payroll": item is latest
                    and item["record_status"] == "current",
                    "state": "MATCHED",
                }
            )
    rows, coverage = [], set()
    for index, key in enumerate(sorted(controls.keys() | registered.keys()), 1):
        expected, actual, episode = controls.get(key), registered.get(key), episodes.get(key[:5])
        payroll_start, payroll_end = month_span(key[5])
        if not start <= payroll_start <= payroll_end <= end:
            raise ValueError("Payroll observations must lie within the declared review months")
        state = "MATCHED"
        if episode is None:
            state = "MISSING_EMPLOYMENT_EPISODE"
        elif expected is None:
            state = "MISSING_INDEPENDENT_CONTROL"
        else:
            service_start, service_end = map(
                date.fromisoformat, (expected["service_from"], expected["service_through"])
            )
            if service_start < date.fromisoformat(episode["started_on"]) or (
                episode["ended_on"] is not None
                and service_end > date.fromisoformat(episode["ended_on"])
            ):
                state = "SERVICE_OUTSIDE_EMPLOYMENT"
            elif actual is None:
                state = "MISSING_CURRENT_PAYROLL"
            elif abs(Decimal(actual["amount"]) - Decimal(expected["amount"])) > data.tolerance:
                state = "PAYROLL_AMOUNT_VARIANCE"
        if expected and expected["category"] == "regular":
            coverage.add(key[:5] + (key[5],))
        rows.append(
            {
                "id": f"employment-payroll:{index}",
                "kind": "entry-comparison",
                **dict(
                    zip(
                        (
                            "registration",
                            "employee_token",
                            "episode_reference",
                            "component",
                            "currency",
                            "payroll_month",
                            "earning_month",
                            "category",
                            "entry_reference",
                        ),
                        key,
                    )
                ),
                "control_source_row_id": expected["id"] if expected else None,
                "register_source_row_id": actual["id"] if actual else None,
                "employment_source_row_id": episode["id"] if episode else None,
                "expected_amount": expected["amount"] if expected else None,
                "reported_amount": actual["amount"] if actual else None,
                "difference": str(Decimal(actual["amount"]) - Decimal(expected["amount"]))
                if actual and expected
                else None,
                "contract_reference": expected["contract_reference"] if expected else None,
                "attendance_reference": expected["attendance_reference"] if expected else None,
                "state": state,
            }
        )
    for key, episode in episodes.items():
        cursor = max(start, date.fromisoformat(episode["started_on"])).replace(day=1)
        last = min(end, date.fromisoformat(episode["ended_on"]) if episode["ended_on"] else end)
        while cursor <= last:
            if len(rows) + len(history) >= 20000:
                raise ValueError("Employment/month expansion exceeds the 20,000-observation bound")
            month = cursor.strftime("%Y-%m")
            if key + (month,) not in coverage:
                rows.append(
                    {
                        "id": "monthly-coverage:" + episode["id"] + ":" + month,
                        "kind": "population-coverage",
                        "employee_token": episode["employee_token"],
                        "registration": key[0],
                        "episode_reference": key[2],
                        "component": key[3],
                        "currency": key[4],
                        "payroll_month": month,
                        "expected_amount": None,
                        "state": "MISSING_EMPLOYEE_MONTH_CONTROL",
                    }
                )
            cursor = (
                date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
                if cursor.year < 9999 or cursor.month < 12
                else date.max
            )
            if cursor == date.max:
                break
    if len(rows) + len(history) > 20000:
        raise ValueError("Employment/month expansion exceeds the 20,000-observation bound")
    return {
        **result(
            [*rows, *history],
            any(row["state"] != "MATCHED" for row in rows),
            [
                "Employment episodes, expected pay, contract/master-change and attendance facts are independently assessed source inputs; document authenticity and legal entitlement are not inferred",
                "Regular payroll requires explicit employee/month controls, including assessed zero; missing controls never establish zero payroll",
                "Arrears use their original earning month and assessed service dates; payment after termination is not automatically invalid",
                "Only the latest explicit current revision contributes to pay; all supplied revision observations are retained",
                "Employee tokens must be pseudonymous SHA256-form identifiers; no names, bank details or national identifiers are canonical fields",
                "No salary proration, payroll tax, pension membership, payment execution or overall payroll-population completeness is inferred",
            ],
        ),
        "employment_payroll_contract": CONTRACT,
        "population_completeness": "DECLARED_EPISODES_COMPONENTS_AND_REVIEW_MONTHS_ONLY",
    }
