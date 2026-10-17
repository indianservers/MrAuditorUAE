from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.modules.financial_ai.schemas import (
    AnomalyExplanation,
    AuditProcedures,
    Classification,
    Commentary,
)


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=4000)


class TextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=12000)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_type: Literal["summarize_text"]
    input: TextInput
    model: str = "mock-diagnostic"


class AIRequest(BaseModel):
    task_type: str = "summarize_text"
    text: str
    model: str
    system_prompt: str
    max_tokens: int = Field(ge=1, le=4096)
    request_id: str


class AIResponse(BaseModel):
    output: Summary | Classification | AnomalyExplanation | AuditProcedures | Commentary
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    usage_source: Literal["provider_reported", "mock_word_estimate", "unavailable"] = (
        "provider_reported"
    )


class AIProvider(Protocol):
    async def generate(self, request: AIRequest) -> AIResponse: ...
