import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LegalReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_record_id: uuid.UUID
    source_id: str = Field(max_length=100)
    article: str = Field(max_length=100)
    rule_version: int = Field(ge=1)


class TaxAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue: str = Field(min_length=1, max_length=2000)
    relevant_facts: list[str] = Field(max_length=20)
    applicable_legislation: list[LegalReference] = Field(min_length=1, max_length=20)
    tax_period: str = Field(min_length=1, max_length=100)
    analysis: str = Field(min_length=1, max_length=6000)
    potential_treatment: str = Field(min_length=1, max_length=4000)
    missing_facts: list[str] = Field(max_length=30)
    uncertainties: list[str] = Field(min_length=1, max_length=30)
    supporting_references: list[uuid.UUID] = Field(min_length=1, max_length=50)
    required_human_action: str = Field(min_length=1, max_length=4000)
    requires_human_review: Literal[True]
    tax_position_approved: Literal[False]
