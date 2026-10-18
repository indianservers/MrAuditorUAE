import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=6000)
    observations: list[str] = Field(max_length=20)
    proposed_procedures: list[str] = Field(max_length=20)
    missing_information: list[str] = Field(max_length=20)
    citations: list[uuid.UUID] = Field(min_length=1, max_length=100)
    requires_human_review: Literal[True]
    evidence_sufficiency_determined: Literal[False]
    opinion_issued: Literal[False]
