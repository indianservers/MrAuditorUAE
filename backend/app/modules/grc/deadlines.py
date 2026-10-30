"""Explicit, bounded calendar rules; no jurisdictional default deadlines."""

import calendar
import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BeforeValidator, Field, model_validator

from app.modules.audit_execution.schemas import Strict


def explicit_calendar_date(value):
    if type(value) is date or isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    raise ValueError(
        "Business calendars require explicit ISO dates, not timestamps or numeric dates"
    )


CalendarDate = Annotated[date, BeforeValidator(explicit_calendar_date)]


class BusinessDayCalendar(Strict):
    coverage_start: CalendarDate
    coverage_end: CalendarDate
    weekend_days: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(
        min_length=1, max_length=6
    )
    holidays: list[CalendarDate] = Field(max_length=1000)
    independent_holiday_count: int = Field(ge=0, le=1000, strict=True)
    assessment: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def complete(self):
        if not 0 <= (self.coverage_end - self.coverage_start).days <= 3660:
            raise ValueError("Business-day calendar needs an ordered bounded coverage window")
        if len(set(self.weekend_days)) != len(self.weekend_days) or any(
            type(day) is not int or day not in range(7) for day in self.weekend_days
        ):
            raise ValueError("Declare distinct integer weekend days from 0 through 6")
        if (
            len(set(self.holidays)) != len(self.holidays)
            or len(self.holidays) != self.independent_holiday_count
        ):
            raise ValueError(
                "Business-day holidays must be distinct and agree with the independent count"
            )
        if any(not self.coverage_start <= day <= self.coverage_end for day in self.holidays):
            raise ValueError("Every retained holiday must lie within calendar coverage")
        if len(self.assessment.strip()) < 10:
            raise ValueError(
                "Assess calendar completeness for the selected jurisdiction and interval"
            )
        return self


class DeadlineRule(Strict):
    identifier: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    effective_from: date
    effective_to: date | None = None
    trigger: date
    date_basis: Literal["period_end", "registration", "licence_expiry", "specified_event"]
    months_after: int = Field(default=0, ge=0, le=120)
    days_after: int = Field(default=0, ge=0, le=3660)
    timezone: str = Field(min_length=1, max_length=100)
    convention: Literal["calendar", "following", "preceding"] = "calendar"
    weekend_days: list[int] = Field(default_factory=list, max_length=7)
    holidays: list[date] = Field(default_factory=list, max_length=1000)
    day_count_basis: Literal["calendar", "business"] = Field(
        default="calendar", exclude_if=lambda value: value == "calendar"
    )
    business_trigger_policy: Literal["exclude", "include_if_working"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    business_calendar: BusinessDayCalendar | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="before")
    @classmethod
    def explicit_business_inputs(cls, value):
        if isinstance(value, dict) and value.get("day_count_basis") == "business":
            explicit_calendar_date(value.get("trigger"))
            if type(value.get("days_after")) is not int:
                raise ValueError("Business-day offsets require an explicit integer")
        return value

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("Recognized IANA timezone required") from exc
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Invalid rule validity window")
        if (
            self.trigger < self.effective_from
            or self.effective_to
            and self.trigger > self.effective_to
        ):
            raise ValueError("Rule not effective at triggering event")
        if any(d not in range(7) for d in self.weekend_days) or len(set(self.weekend_days)) != len(
            self.weekend_days
        ):
            raise ValueError("Distinct weekday numbers 0 through 6 required")
        if self.convention != "calendar" and (not self.weekend_days or len(self.weekend_days) == 7):
            raise ValueError("Explicit usable working-week convention required")
        if self.day_count_basis == "business":
            if (
                self.business_calendar is None
                or self.business_trigger_policy is None
                or self.months_after
                or not self.days_after
                or self.convention != "calendar"
                or self.weekend_days
                or self.holidays
            ):
                raise ValueError(
                    "Business-day counting requires its complete calendar, positive day offset and no mixed month/rolling convention"
                )
            if (
                not self.business_calendar.coverage_start
                <= self.trigger
                <= self.business_calendar.coverage_end
            ):
                raise ValueError("Business calendar must cover the explicit triggering event")
        elif self.business_calendar is not None or self.business_trigger_policy is not None:
            raise ValueError("A business calendar applies only to explicit business-day counting")
        return self


def calculate(rule: DeadlineRule):
    if rule.day_count_basis == "business":
        assert rule.business_calendar is not None
        selected = rule.business_calendar
        remaining = rule.days_after
        cursor = rule.trigger
        weekends, holidays = set(selected.weekend_days), set(selected.holidays)
        if (
            rule.business_trigger_policy == "include_if_working"
            and cursor.weekday() not in weekends
            and cursor not in holidays
        ):
            remaining -= 1
            if remaining == 0:
                return cursor
        # Trigger treatment is explicit. Coverage, rather than an assumed
        # national weekend or an empty/missing holiday feed, bounds the search.
        for _ in range((selected.coverage_end - cursor).days):
            cursor += timedelta(days=1)
            if cursor.weekday() not in weekends and cursor not in holidays:
                remaining -= 1
                if remaining == 0:
                    return cursor
        raise ValueError("Business calendar coverage cannot establish the complete deadline")
    month = rule.trigger.year * 12 + rule.trigger.month - 1 + rule.months_after
    year, index = divmod(month, 12)
    month = index + 1
    day = min(rule.trigger.day, calendar.monthrange(year, month)[1])
    result = date(year, month, day) + timedelta(days=rule.days_after)
    for _ in range(370):
        if (
            rule.convention == "calendar"
            or result.weekday() not in rule.weekend_days
            and result not in rule.holidays
        ):
            return result
        result += timedelta(days=1 if rule.convention == "following" else -1)
    raise ValueError("Calendar has no working day in bounded search")


def missing_obligation_period(body):
    rule = body.get("deadline_rule")
    return (
        isinstance(body.get("jurisdiction_scope"), dict)
        and isinstance(rule, dict)
        and rule.get("date_basis") == "period_end"
        and (not body.get("obligation_period_start") or not body.get("obligation_period_end"))
    )


def state(body, today):
    scope = body.get("jurisdiction_scope")
    if isinstance(scope, dict):
        if scope.get("applicability") == "assessed_not_applicable":
            return "ASSESSED_NOT_APPLICABLE"
        if scope.get("applicability") != "assessed_applicable":
            return "APPLICABILITY_PENDING"
        if missing_obligation_period(body):
            return "PERIOD_SCOPE_PENDING"
    deadline = body.get("extension_deadline") or body.get("deadline")
    if not deadline:
        return "UNRESOLVED"
    if body.get("filing_stage") == "acknowledged":
        return "ACKNOWLEDGED"
    if body.get("filing_stage") == "submitted":
        return "SUBMITTED_AWAITING_ACKNOWLEDGMENT"
    return "OVERDUE" if date.fromisoformat(str(deadline)) < today else "OPEN"


def local_today(body, now=None):
    timezone = (body.get("deadline_rule") or {}).get("timezone")
    return (
        (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()
        if timezone
        else date.today()
    )
