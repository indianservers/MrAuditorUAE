import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.modules.audit_execution.schemas import Strict


class ToolInput(Strict):
    query: str = Field(default="", max_length=200)
    source_id: uuid.UUID | None = None
    limit: int = Field(default=20, ge=1, le=50)


class Command(Strict):
    engagement_id: uuid.UUID
    task: str | None = Field(default=None, max_length=60)
    prompt: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    inputs: ToolInput = Field(default_factory=ToolInput)
    template_id: uuid.UUID | None = None


class ToolResult(Strict):
    status: Literal["COMPLETED", "MISSING", "LIMITED", "DENIED", "FAILED"]
    agent: str
    tool: str
    sources: list[dict] = Field(default_factory=list, max_length=50)
    data: dict = Field(default_factory=dict)
    uncertainty: list[str] = Field(default_factory=list, max_length=20)


class Control(Strict):
    version: int = Field(ge=1)
    action: Literal["pause", "resume", "cancel"]


class ExtractInput(Strict):
    record_id: uuid.UUID
    classification: Literal[
        "invoice",
        "loan",
        "lease",
        "bank-statement",
        "financial-statement",
        "contract",
        "policy",
        "other",
    ]
    confidentiality: Literal["confidential", "restricted"] = "confidential"


class Correction(Strict):
    fields: dict[str, str] = Field(max_length=30)
    reason: str = Field(min_length=10, max_length=1000)


class ProposalInput(Strict):
    run_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    narrative: str = Field(min_length=10, max_length=4000)
    record_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class Decision(Strict):
    version: int = Field(ge=1)
    payload_hash: str = Field(min_length=64, max_length=64)
    decision: Literal["approve", "reject"]
    comments: str = Field(min_length=10, max_length=2000)


class ScheduleInput(Strict):
    task: str = Field(max_length=60)
    frequency: Literal["daily", "weekly", "monthly"]
    next_due: datetime
    active: bool = False
    inputs: ToolInput = Field(default_factory=ToolInput)


class Graph(Strict):
    nodes: list[str] = Field(min_length=1, max_length=12)
    edges: list[tuple[int, int]] = Field(max_length=20)


class TemplateInput(Graph):
    title: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=100)


class MatchInput(Strict):
    journal_id: uuid.UUID
    signals_hash: str = Field(min_length=64, max_length=64)
    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=10, max_length=1000)


class CitationInput(Strict):
    kind: Literal["record", "journal", "snapshot", "chunk", "ml", "ifrs", "tax", "vat", "tp"]
    id: uuid.UUID
    version: int | None = Field(default=None, ge=1)


def validate_graph(data: Graph):
    from app.modules.enterprise_ai.catalogue import TOOLS

    if len(set(data.nodes)) != len(data.nodes) or not set(data.nodes) <= set(TOOLS):
        raise ValueError("Distinct approved tool nodes required")
    if any(a < 0 or b >= len(data.nodes) or a >= b for a, b in data.edges):
        raise ValueError("Only forward edges in an ordered acyclic graph are supported")
    if len(data.nodes) > 1 and {b for _, b in data.edges} != set(range(1, len(data.nodes))):
        raise ValueError("Every node must be reachable from the trigger")
    return True
