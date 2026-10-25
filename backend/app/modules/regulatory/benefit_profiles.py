"""Reviewed gratuity parameters shared by the rule library and employee engine.

No statutory defaults are inferred here. Regime, cohort and rates require an
effective-dated source and professional assessment in the consuming workflow.
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.modules.jurisdictions.profiles import Strict

Parameter = Annotated[Decimal, Field(max_digits=28, decimal_places=8)]
Scope = Annotated[str, Field(min_length=1, max_length=120)]


class BenefitParameters(Strict):
    regime: Scope
    cohort: Scope
    work_model: Literal["full-time", "part-time", "other"]
    minimum_service_years: Parameter = Field(ge=0)
    year_days: Parameter = Field(gt=0, le=366)
    salary_divisor: Parameter = Field(gt=0, le=31)
    first_tier_years: Parameter = Field(ge=0)
    first_tier_days: Parameter = Field(ge=0)
    later_tier_days: Parameter = Field(ge=0)
    maximum_salary_months: Parameter = Field(gt=0)
