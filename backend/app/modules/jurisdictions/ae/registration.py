"""Registration exposure arithmetic against an independently reviewed effective policy.

This engine does not decide residence, exceptions, taxable classification or filing dates.
"""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Strict


class RegistrationPolicy(Strict):
    threshold_aed: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    historical_months: int = Field(ge=1, le=24)
    forecast_days: int = Field(ge=1, le=366)


class Observation(Strict):
    id: str = Field(min_length=1, max_length=100)
    date: date
    amount_aed: Decimal = Field(ge=0, max_digits=28, decimal_places=8)
    taxable_classification_confirmed: bool = False


class Exposure(Strict):
    as_of: date
    historical: list[Observation] = Field(min_length=1, max_length=20000)
    forecast: list[Observation] = Field(default_factory=list, max_length=20000)
    nonresident_or_exception_requires_review: bool = True

    @model_validator(mode="after")
    def distinct(self):
        ids = [row.id for row in self.historical + self.forecast]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicated registration observation")
        return self


def subtract_months(day: date, months: int) -> date:
    ordinal = day.year * 12 + day.month - 1 - months
    year, month = divmod(ordinal, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def calculate(data: Exposure, policy: RegistrationPolicy):
    start = subtract_months(data.as_of, policy.historical_months) + timedelta(days=1)
    horizon = data.as_of + timedelta(days=policy.forecast_days)
    if any(not start <= r.date <= data.as_of for r in data.historical):
        raise ValueError("Historical observations are outside the reviewed lookback window")
    if any(not data.as_of < r.date <= horizon for r in data.forecast):
        raise ValueError("Forecast observations are outside the reviewed forward window")
    historic = sum(
        (r.amount_aed for r in data.historical if r.taxable_classification_confirmed), Decimal(0)
    )
    forecast = sum(
        (r.amount_aed for r in data.forecast if r.taxable_classification_confirmed), Decimal(0)
    )
    unknown = [
        r.id for r in data.historical + data.forecast if not r.taxable_classification_confirmed
    ]
    return {
        "historical_confirmed_aed": str(historic),
        "forecast_confirmed_aed": str(forecast),
        "threshold_aed": str(policy.threshold_aed),
        "historical_exposure_signal": historic > policy.threshold_aed,
        "forecast_exposure_signal": forecast > policy.threshold_aed,
        "unresolved_observation_ids": unknown,
        "window": [start.isoformat(), data.as_of.isoformat()],
        "forecast_through": horizon.isoformat(),
        "scope": "Supplied validated population only; no completeness assertion",
        "registration_required": None,
        "filing_due_date": None,
        "review_required": True,
        "residence_exceptions_review": data.nonresident_or_exception_requires_review,
        "execution_mode": "deterministic_engine",
    }
