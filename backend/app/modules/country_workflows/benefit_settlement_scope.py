"""A gratuity settlement belongs to one reviewed employment service span."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.jurisdictions.profiles import Strict

Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")]


class BenefitSettlementScope(Strict):
    service_start: date
    service_end: date
    regime: Identifier
    cohort: Identifier
    work_model: Literal["full-time", "part-time"]
    scheme: Literal["gratuity"]

    @model_validator(mode="after")
    def ordered(self):
        if self.service_end < self.service_start:
            raise ValueError("Gratuity service dates must be ordered")
        return self
