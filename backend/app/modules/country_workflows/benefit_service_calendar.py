"""Dated, source-assessed gratuity exclusions; never infer leave eligibility."""

from collections import defaultdict
from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from app.modules.country_workflows.benefit_settlement_scope import (
    BenefitSettlementScope,
    Identifier,
)
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "benefit-service-calendar/1"
TABLE = "benefit-service-exclusions"
SCOPE = tuple(BenefitSettlementScope.model_fields)


class ServiceDayControls(Strict):
    employee_count: int = Field(strict=True, ge=1, le=5000)
    excluded_days: int = Field(strict=True, ge=0, le=182500000)


class ServiceExclusion(BenefitSettlementScope):
    id: Identifier
    employee_id: Identifier
    kind: Literal["EXCLUDED_CALENDAR_DAYS", "NO_EXCLUDED_DAYS_ASSESSED"]
    exclusion_start: date | None = None
    exclusion_end: date | None = None
    days: int = Field(ge=0, le=36500)
    evidence_reference: Identifier
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def explicit_days(self):
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the original absence records and applicable service-day basis")
        if self.kind == "NO_EXCLUDED_DAYS_ASSESSED":
            if self.exclusion_start is not None or self.exclusion_end is not None or self.days != 0:
                raise ValueError("An assessed zero exclusion has no interval and exactly zero days")
        elif (
            self.exclusion_start is None
            or self.exclusion_end is None
            or not self.service_start
            <= self.exclusion_start
            <= self.exclusion_end
            <= self.service_end
            or (self.exclusion_end - self.exclusion_start).days + 1 != self.days
        ):
            raise ValueError(
                "Exclusion days must equal the inclusive dated interval inside service"
            )
        return self


def verify(rows, controls):
    controls = ServiceDayControls.model_validate(controls)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ids = set()
    for raw in rows:
        row = ServiceExclusion.model_validate(raw).model_dump(mode="json")
        if row["id"] in ids:
            raise ValueError("Duplicate service-calendar source row")
        ids.add(row["id"])
        grouped[row["employee_id"]].append(row)
    if (
        len(grouped) != controls.employee_count
        or sum(r["days"] for rs in grouped.values() for r in rs) != controls.excluded_days
    ):
        raise ValueError("Independent service employee/day controls do not agree")
    for records in grouped.values():
        scope = tuple(records[0][field] for field in SCOPE)
        if any(tuple(row[field] for field in SCOPE) != scope for row in records):
            raise ValueError("One employee service calendar must use one exact employment scope")
        if any(row["kind"] == "NO_EXCLUDED_DAYS_ASSESSED" for row in records):
            if len(records) != 1:
                raise ValueError("An explicit zero cannot coexist with other exclusion records")
            continue
        ordered = sorted(records, key=lambda row: (row["exclusion_start"], row["exclusion_end"]))
        if any(
            current["exclusion_start"] <= prior["exclusion_end"]
            for prior, current in zip(ordered, ordered[1:])
        ):
            raise ValueError(
                "Overlapping service exclusions require a corrected original population"
            )
    return grouped


def bind(employees, source):
    if source.get("benefit_service_calendar_contract") != CONTRACT:
        raise ValueError(
            "Regenerate dated service exclusions with independent employee/day controls"
        )
    grouped = verify(source["rows"], source.get("benefit_service_controls"))
    expected = {row["id"]: row for row in employees}
    if len(expected) != len(employees) or set(grouped) - set(expected):
        raise ValueError(
            "Service calendars require unique employees in the selected benefit population"
        )
    checks = {}
    for identifier, employee in expected.items():
        records = grouped.get(identifier, [])
        if records and any(records[0][field] != employee[field] for field in SCOPE):
            raise ValueError("Service calendar and employee employment scopes differ")
        actual = sum(row["days"] for row in records) if records else None
        state = (
            "SERVICE_CALENDAR_MISSING"
            if actual is None
            else "EXCLUDED_SERVICE_DAYS_DIFFER"
            if actual != employee["excluded_service_days"]
            else "MATCHED"
        )
        checks[identifier] = {
            "service_calendar_state": state,
            "declared_excluded_service_days": employee["excluded_service_days"],
            "calendar_excluded_service_days": actual,
            "service_calendar_records": sorted(
                records, key=lambda row: (row["exclusion_start"] or "", row["id"])
            ),
            "service_calendar_source_row_ids": [row["id"] for row in records],
        }
    return checks
