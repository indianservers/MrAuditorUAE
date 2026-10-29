"""Source-assessed event accrual mechanics; no country rates or legal defaults.

Intervals are inclusive calendar days. Beginning-of-day events precede accrual;
end-of-day events follow it. A monthly rest follows that day's events. Unposted
interest does not earn interest until a rest. All monetary arithmetic uses a
private decimal context, and complete segment/event/rest traces are returned.
"""

import calendar
import re
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
    localcontext,
)
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.payroll_profiles import Identifier, Money

CONTRACT = "assessed-event-interest/1"
MAX_BALANCE = Decimal("9" * 36)


def calendar_day(value):
    if (
        type(value) is date
        or isinstance(value, str)
        and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    ):
        return value
    raise ValueError("Interest events require explicit ISO calendar dates, not inferred timestamps")


Day = Annotated[date, BeforeValidator(calendar_day)]


class AccrualTerms(Strict):
    start: Day
    cutoff: Day
    rest_basis: Literal["CALENDAR_MONTH_END", "MONTHLY_ANNIVERSARY"]
    day_basis: Literal["ACT_365_FIXED", "ACT_ACT_YEAR"]
    event_timing: Literal["BEGINNING_OF_DAY", "END_OF_DAY"]
    rest_rounding: Literal["ROUND_EACH_REST", "CARRY_PRECISION"]
    rounding: Literal["HALF_UP", "CEILING", "FLOOR"]
    currency_scale: int = Field(strict=True, ge=0, le=6)
    multiplier: Decimal = Field(ge=0, le=10, max_digits=18, decimal_places=12)

    @model_validator(mode="after")
    def ordered(self):
        if self.cutoff < self.start or (self.cutoff - self.start).days > 36600:
            raise ValueError("Accrual needs an ordered window bounded to 36,600 days")
        return self


class RateWindow(Strict):
    id: Identifier
    effective_from: Day
    effective_to: Day
    annual_rate: Decimal = Field(ge=0, le=1, max_digits=18, decimal_places=12)

    @model_validator(mode="after")
    def ordered(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Rate dates must be ordered")
        return self


class BalanceEvent(Strict):
    id: Identifier
    day: Day
    category: Literal["PRINCIPAL", "UNCAPITALIZED_INTEREST", "CAPITALIZED_INTEREST"]
    origin: Literal["BANK", "DOCUMENT_ADJUSTMENT"]
    amount: Money = Field(ge=0)


class MissingRate(ValueError):
    def __init__(self, day):
        self.day = day
        super().__init__("No reviewed rate covers " + day.isoformat())


def rest_days(terms):
    if terms.rest_basis == "CALENDAR_MONTH_END":
        year, month = terms.start.year, terms.start.month
        while year <= terms.cutoff.year:
            value = date(year, month, calendar.monthrange(year, month)[1])
            if value > terms.cutoff:
                break
            yield value.toordinal()
            month += 1
            if month == 13:
                month, year = 1, year + 1
    else:
        index = 1
        while True:
            month_index = terms.start.year * 12 + terms.start.month - 1 + index
            year, zero_month = divmod(month_index, 12)
            if year > 9999:
                break
            month = zero_month + 1
            anniversary = date(
                year, month, min(terms.start.day, calendar.monthrange(year, month)[1])
            )
            ordinal = anniversary.toordinal() - 1
            if ordinal > terms.cutoff.toordinal():
                break
            yield ordinal
            index += 1


def accrue(principal, terms, rates, events):
    """Accrue assessed balances from inception, never infer an opening interest balance."""
    terms = AccrualTerms.model_validate(terms)
    rates = [RateWindow.model_validate(row) for row in rates]
    events = [BalanceEvent.model_validate(row) for row in events]
    try:
        opening = Decimal(principal)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("An explicit finite non-negative principal is required") from None
    if (
        isinstance(principal, (bool, float))
        or not opening.is_finite()
        or not Decimal(0) <= opening <= MAX_BALANCE
    ):
        raise ValueError("An explicit finite non-negative principal is required")
    if len(rates) > 5000 or len(events) > 10000:
        raise ValueError("Interest rate and event populations exceed their supported bounds")
    if len({row.id for row in rates}) != len(rates) or len({row.id for row in events}) != len(
        events
    ):
        raise ValueError("Duplicate rate or balance-event identity")
    rates.sort(key=lambda row: row.effective_from)
    if any(a.effective_to >= b.effective_from for a, b in zip(rates, rates[1:])):
        raise ValueError("Competing rate windows must be resolved; no latest-rate selection")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return _accrue(opening, terms, rates, events)


def _accrue(principal, terms, rates, events):
    quantum = Decimal(1).scaleb(-terms.currency_scale)
    rounding = {"HALF_UP": ROUND_HALF_UP, "CEILING": ROUND_CEILING, "FLOOR": ROUND_FLOOR}[
        terms.rounding
    ]

    def rounded(value):
        return value.quantize(quantum, rounding=rounding)

    first, stop = terms.start.toordinal(), terms.cutoff.toordinal() + 1
    rests = set(rest_days(terms))
    boundaries = {first, stop, *(value + 1 for value in rests)}
    rate_starts = [row.effective_from.toordinal() for row in rates]
    for row in rates:
        for value in (row.effective_from.toordinal(), row.effective_to.toordinal() + 1):
            if first < value < stop:
                boundaries.add(value)
    if terms.day_basis == "ACT_ACT_YEAR":
        boundaries.update(
            date(year, 1, 1).toordinal()
            for year in range(terms.start.year + 1, terms.cutoff.year + 1)
        )
    by_day = defaultdict(list)
    for row in events:
        if row.day > terms.cutoff:
            raise ValueError("Balance events cannot follow the cutoff")
        if row.day < terms.start and row.category != "PRINCIPAL":
            raise ValueError("Interest reductions cannot predate the assessed first interest day")
        by_day[row.day.toordinal()].append(row)
        for value in (row.day.toordinal(), row.day.toordinal() + 1):
            if first < value < stop:
                boundaries.add(value)
    capitalized = unposted = interest_reduced = cash_interest_paid = accrued = adjustments = (
        Decimal(0)
    )
    event_trace, segments, rest_trace = [], [], []

    def apply(day, phase):
        nonlocal principal, capitalized, unposted, interest_reduced, cash_interest_paid
        for event in sorted(by_day.get(day, []), key=lambda row: row.id):
            before = {
                "principal": principal,
                "capitalized_interest": capitalized,
                "unposted_interest": unposted,
            }
            available = {
                "PRINCIPAL": principal,
                "CAPITALIZED_INTEREST": capitalized,
                "UNCAPITALIZED_INTEREST": unposted,
            }[event.category]
            if event.amount > available:
                raise ValueError(
                    "Balance reduction exceeds the assessed unpaid " + event.category.lower()
                )
            if event.category == "PRINCIPAL":
                principal -= event.amount
            else:
                interest_reduced += event.amount
                if event.origin == "BANK":
                    cash_interest_paid += event.amount
                if event.category == "CAPITALIZED_INTEREST":
                    capitalized -= event.amount
                else:
                    unposted -= event.amount
            event_trace.append(
                {
                    "id": event.id,
                    "day": event.day.isoformat(),
                    "category": event.category,
                    "origin": event.origin,
                    "phase": phase,
                    "amount": str(event.amount),
                    **{"opening_" + key: str(value) for key, value in before.items()},
                    "closing_principal": str(principal),
                    "closing_capitalized_interest": str(capitalized),
                    "closing_unposted_interest": str(unposted),
                }
            )

    for day in sorted(value for value in by_day if value < first):
        apply(day, "BEFORE_FIRST_INTEREST_DAY")
    ordered = sorted(boundaries)
    for start, end in zip(ordered, ordered[1:]):
        if terms.event_timing == "BEGINNING_OF_DAY":
            apply(start, "BEGINNING_OF_DAY")
        index = bisect_right(rate_starts, start) - 1
        if index < 0 or rates[index].effective_to.toordinal() < end - 1:
            raise MissingRate(date.fromordinal(start))
        rate = rates[index]
        year = date.fromordinal(start).year
        denominator = 366 if terms.day_basis == "ACT_ACT_YEAR" and calendar.isleap(year) else 365
        opening_principal, opening_capitalized, opening_unposted = principal, capitalized, unposted
        addition = (
            (principal + capitalized)
            * rate.annual_rate
            * terms.multiplier
            * Decimal(end - start)
            / Decimal(denominator)
        )
        unposted += addition
        accrued += addition
        if max(principal, capitalized + unposted, accrued) > MAX_BALANCE:
            raise ValueError("Accrued balances exceed the supported 36-digit monetary range")
        if terms.event_timing == "END_OF_DAY":
            apply(end - 1, "END_OF_DAY")
        segments.append(
            {
                "start": date.fromordinal(start).isoformat(),
                "end": date.fromordinal(end - 1).isoformat(),
                "days": end - start,
                "year_denominator": denominator,
                "principal_basis": str(opening_principal),
                "capitalized_interest_basis": str(opening_capitalized),
                "opening_unposted_interest": str(opening_unposted),
                "rate_source_id": rate.id,
                "annual_base_rate": str(rate.annual_rate),
                "multiplier": str(terms.multiplier),
                "accrued_interest": str(addition),
                "closing_unposted_before_rest": str(unposted),
            }
        )
        if end - 1 in rests:
            raw = unposted
            posted = rounded(raw) if terms.rest_rounding == "ROUND_EACH_REST" else raw
            rest_trace.append(
                {
                    "day": date.fromordinal(end - 1).isoformat(),
                    "unrounded_interest": str(raw),
                    "capitalized_amount": str(posted),
                    "rounding_adjustment": str(posted - raw),
                    "opening_capitalized_interest": str(capitalized),
                    "closing_capitalized_interest": str(capitalized + posted),
                }
            )
            adjustments += posted - raw
            capitalized += posted
            unposted = Decimal(0)
    raw_outstanding = capitalized + unposted
    outstanding = rounded(raw_outstanding)
    closing_adjustment = outstanding - raw_outstanding
    return {
        "interest_accrual_contract": CONTRACT,
        "expected_amount": str(outstanding),
        "principal_remaining": str(principal),
        "unrounded_interest_outstanding": str(raw_outstanding),
        "interest_accrued_unrounded": str(accrued),
        "interest_charged_rounded": str(outstanding + interest_reduced),
        "interest_reductions": str(interest_reduced),
        "interest_cash_paid": str(cash_interest_paid),
        "rest_rounding_adjustment": str(adjustments),
        "closing_rounding_adjustment": str(closing_adjustment),
        "capitalized_interest_outstanding": str(capitalized),
        "unposted_interest_outstanding": str(unposted),
        "segments": segments,
        "balance_events": event_trace,
        "monthly_rests": rest_trace,
    }
