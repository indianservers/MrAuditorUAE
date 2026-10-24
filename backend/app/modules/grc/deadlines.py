"""Explicit, bounded calendar rules; no jurisdictional default deadlines."""

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Strict


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
        return self


def calculate(rule: DeadlineRule):
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


def state(body, today):
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
