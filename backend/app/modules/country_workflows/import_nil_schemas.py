"""Explicit scope for an evidenced absence; an empty file alone proves nothing."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.modules.jurisdictions.profiles import Strict


class ImportNilScope(Strict):
    registration: str = Field(pattern=r"^[0-9]{15}$")
    period_start: date
    period_end: date
    kinds: list[Literal["declaration", "adjustment"]] = Field(min_length=1, max_length=2)
    context_evidence_version_id: UUID
    context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("assessment")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Assess the nil import population explicitly")
        return value.strip()

    @model_validator(mode="after")
    def ordered(self):
        if self.period_start > self.period_end or len(set(self.kinds)) != len(self.kinds):
            raise ValueError("Nil import scope requires ordered dates and distinct population kinds")
        return self
