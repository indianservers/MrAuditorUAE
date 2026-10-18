import uuid
from datetime import date, datetime
from typing import Annotated, Literal

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Name = Annotated[str, Field(min_length=1, max_length=200)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Status = Literal["active", "inactive", "archived"]
EngagementType = Literal[
    "External Audit",
    "Internal Audit",
    "IFRS Review",
    "Corporate Tax",
    "VAT",
    "Transfer Pricing",
    "Pillar Two",
    "General Compliance",
]
EngagementStatus = Literal["draft", "active", "completed", "cancelled"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientCreate(Input):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: Name
    kind: Literal["individual", "company", "group"] = "company"
    status: Status = "active"


class ClientPatch(Input):
    name: Name | None = None
    status: Status | None = None
    version: int = Field(ge=1)
    lifecycle_reason: str | None = Field(default=None, min_length=10, max_length=1000)


class EntityCreate(Input):
    client_id: uuid.UUID
    name: Name
    country: str = Field(pattern=r"^[A-Z]{2}$")
    jurisdiction: str = Field(min_length=1, max_length=100)
    functional_currency: Currency
    presentation_currency: Currency
    status: Status = "active"

    @field_validator("functional_currency", "presentation_currency")
    @classmethod
    def currency(cls, value: str) -> str:
        if pycountry.currencies.get(alpha_3=value) is None:
            raise ValueError("Unknown ISO 4217 currency")
        return value

    @field_validator("country")
    @classmethod
    def country_code(cls, value: str) -> str:
        if pycountry.countries.get(alpha_2=value) is None:
            raise ValueError("Unknown ISO 3166 country")
        return value


class EntityPatch(Input):
    name: Name | None = None
    jurisdiction: str | None = Field(default=None, min_length=1, max_length=100)
    status: Status | None = None
    version: int = Field(ge=1)
    lifecycle_reason: str | None = Field(default=None, min_length=10, max_length=1000)


class EngagementCreate(Input):
    entity_id: uuid.UUID
    period_id: uuid.UUID | None = None
    name: Name
    engagement_type: EngagementType
    status: EngagementStatus = "draft"


class EngagementPatch(Input):
    name: Name | None = None
    status: EngagementStatus | None = None
    version: int = Field(ge=1)


class PeriodCreate(Input):
    entity_id: uuid.UUID
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        return self


class OwnedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ClientOut(OwnedOut, ClientCreate):
    version: int


class EntityOut(OwnedOut, EntityCreate):
    version: int


class EngagementOut(OwnedOut, EngagementCreate):
    status: str  # type: ignore[assignment]
    version: int


class PeriodOut(OwnedOut):
    entity_id: uuid.UUID
    start_date: date
    end_date: date


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int
