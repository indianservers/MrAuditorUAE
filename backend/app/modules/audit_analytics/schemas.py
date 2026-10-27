from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from app.modules.accounting.schemas import SnapshotRequest


class AnalyticsRequest(SnapshotRequest):
    materiality: Decimal = Field(default=Decimal("100000"), gt=0)
    high_value: Decimal = Field(default=Decimal("50000"), gt=0)
    round_unit: Decimal = Field(default=Decimal("10000"), gt=0)
    rare_count: int = Field(default=2, ge=1)
    near_duplicate_days: int = Field(default=3, ge=0, le=365)
    near_duplicate_ratio: Decimal = Field(default=Decimal("0.01"), ge=0, le=1)
    dormant_days: int = Field(default=90, ge=1)
    activity_multiple: Decimal = Field(default=Decimal("3"), gt=0)
    frequency_min_count: int = Field(default=2, ge=1)
    frequency_ratio: Decimal = Field(default=Decimal("0.5"), gt=0, le=1)
    benford_min_count: int = Field(default=1000, ge=100)
    benford_min_distinct: int = Field(default=100, ge=10)
    benford_min_span: Decimal = Field(default=Decimal("100"), ge=10)
    outlier_multiple: Decimal = Field(default=Decimal("3"), gt=0)
    concentration: Decimal = Field(default=Decimal("0.5"), gt=0, le=1)
    velocity_limit: int = Field(default=50, ge=1)
    date_gap_days: int = Field(default=30, ge=0)
    year_end: date | None = None
    year_end_window: int = Field(default=7, ge=1, le=90)
    holidays: list[date] | None = None
    weekend_days: list[int] = Field(default_factory=list)
    calendar_rationale: str = Field(default="", max_length=4000)
    timezone: str | None = None
    business_hours: tuple[int, int] | None = None
    timestamps_reliable: bool = False
    voucher_sequential: bool = False
    expected_pairs: list[list[str]] | None = None
    prior_activity: dict[str, Decimal] | None = None
    last_activity: dict[str, date] | None = None
    unusual_words: list[str] = Field(default_factory=lambda: ["adjust", "misc", "override", "plug"])
    benford_eligible: bool = False
    benford_chi_limit: Decimal = Field(default=Decimal("20.09"), gt=0)
    weights: dict[str, Decimal] = Field(default_factory=dict, max_length=25)

    @field_validator("weekend_days")
    @classmethod
    def days(cls, value):
        if any(i < 0 or i > 6 for i in value):
            raise ValueError("Invalid weekday")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate non-working weekday")
        return sorted(value)

    @model_validator(mode="after")
    def assessed_calendar(self):
        if self.weekend_days and len(self.calendar_rationale.strip()) < 10:
            raise ValueError(
                "Selected non-working weekdays require an operating-calendar assessment"
            )
        return self

    @field_validator("timezone")
    @classmethod
    def tz(cls, value):
        if value:
            ZoneInfo(value)
        return value

    @field_validator("business_hours")
    @classmethod
    def hours(cls, value):
        if value and not 0 <= value[0] < value[1] <= 24:
            raise ValueError("Invalid business hours")
        return value

    @field_validator("weights")
    @classmethod
    def valid_weights(cls, value):
        if any(v < 0 or v > 100 for v in value.values()):
            raise ValueError("Weights must lie between zero and 100")
        return value
