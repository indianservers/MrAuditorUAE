import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopeInput(Input):
    client_id: uuid.UUID
    entity_id: uuid.UUID
    period_id: uuid.UUID


SourceSystem = Literal[
    "file",
    "tally",
    "zoho",
    "busy",
    "marg",
    "sap-b1",
    "sap-s4",
    "netsuite",
    "quickbooks",
    "dynamics",
    "xero",
]


class ImportOptions(ScopeInput):
    kind: Literal["gl", "journals", "tb", "coa"] = "gl"
    source_system: SourceSystem = "file"
    mapping: dict[str, str] = Field(default_factory=dict, max_length=60)
    profile_id: uuid.UUID | None = None
    sheet: str | None = None
    encoding: Literal["utf-8-sig", "cp1252", "utf-16"] = "utf-8-sig"
    delimiter: Literal[",", ";", "\t"] = ","
    decimal_separator: Literal[".", ","] = "."
    date_format: str = "%Y-%m-%d"
    signed_convention: Literal["debit_positive", "credit_positive"] = "debit_positive"
    currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")
    expected_rows: int | None = Field(default=None, ge=0)
    expected_debit: Decimal | None = None
    expected_credit: Decimal | None = None
    source_complete: bool = False
    supersedes_id: uuid.UUID | None = None
    tax_codes: list[str] | None = None
    tally_company: str | None = None
    tally_company_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_sync_run_id: uuid.UUID | None = None
    report_package: dict = Field(default_factory=dict, max_length=12)


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    client_id: uuid.UUID
    entity_id: uuid.UUID
    period_id: uuid.UUID
    kind: str
    status: str
    progress: int
    row_count: int
    valid_count: int


class AccountAssignment(Input):
    classification: Literal["Assets", "Liabilities", "Equity", "Income", "Expenses"]
    statement_group: str | None = Field(default=None, max_length=100)
    source_group: str | None = Field(default=None, max_length=300)
    contra: bool = Field(default=False, strict=True)
    parent_code: str | None = Field(default=None, max_length=100)


class MappingCreate(ScopeInput):
    name: str = Field(min_length=1, max_length=100)
    mapping: dict = Field(max_length=1000)
    approved: bool = False


class RecordOut(BaseModel):
    id: uuid.UUID
    data: dict


class ResourcePage(BaseModel):
    items: list[dict]
    total: int
    offset: int
    limit: int


class SnapshotRequest(Input):
    snapshot_id: uuid.UUID


class ReconcileRequest(SnapshotRequest):
    comparison_snapshot_id: uuid.UUID | None = None
    tolerance: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class SampleExclusion(Input):
    line_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=2000)


class SamplingRequest(SnapshotRequest):
    method: Literal["random", "systematic", "mus", "high_value", "risk", "full", "judgmental"]
    size: int = Field(default=10, ge=1, le=1000000)
    seed: int = Field(default=0, ge=0, le=2147483647)
    threshold: Decimal = Field(default=Decimal("0"), ge=0)
    analytics_run_id: uuid.UUID | None = None
    selected_line_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    selection_rationale: str = Field(default="", max_length=4000)
    objective: str = Field(default="", max_length=4000)
    population_definition: str = Field(default="", max_length=4000)
    exclusions: list[SampleExclusion] = Field(default_factory=list, max_length=1000)
    certainty_threshold: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=8)


class RunOut(BaseModel):
    id: uuid.UUID
    status: str
    result: dict = Field(default_factory=dict)
