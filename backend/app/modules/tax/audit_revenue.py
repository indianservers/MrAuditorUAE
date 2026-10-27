"""Retained, reviewed UAE PE/nexus revenue; not inferred from worldwide turnover."""

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Strict
from app.modules.ifrs.schemas import Nonnegative


class NonresidentAuditRevenue(Strict):
    amount: Nonnegative
    currency: Literal["AED"]
    period_start: date
    period_end: date
    scope: Literal["uae_pe_and_nexus"]
    population_complete: bool = Field(strict=True)
    assessment: str = Field(min_length=10, max_length=2000)
    evidence_id: uuid.UUID
    source_path: list[
        Annotated[str, Field(strict=True, min_length=1, max_length=100)]
        | Annotated[int, Field(strict=True, ge=0, le=10000)]
    ] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def explicit_scope(self):
        if self.period_end < self.period_start or len(self.assessment.strip()) < 10:
            raise ValueError(
                "Retained revenue scope requires an ordered period and meaningful assessment"
            )
        return self

    def facts(self):
        return self.model_dump(mode="json", exclude={"evidence_id", "source_path"})

    def verify_body(self, body):
        value = body
        try:
            for key in self.source_path:
                value = value[key]
            if not isinstance(value, dict):
                raise ValueError("Retained revenue scope must be an object")
            for key, expected in self.facts().items():
                actual = value[key]
                if key == "amount":
                    if (
                        not isinstance(actual, (str, int))
                        or isinstance(actual, bool)
                        or not Decimal(str(actual)).is_finite()
                        or Decimal(str(actual)) != self.amount
                    ):
                        raise ValueError("Retained revenue differs")
                elif type(actual) is not type(expected) or actual != expected:
                    raise ValueError("Retained scope differs")
        except (KeyError, IndexError, TypeError, InvalidOperation, ValueError):
            raise ValueError(
                "Nonresident audit revenue and scope do not agree to the retained source object"
            ) from None
