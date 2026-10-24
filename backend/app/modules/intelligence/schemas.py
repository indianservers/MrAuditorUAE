import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.country_workflows.schemas import (
    LedgerSourceInput,
    SourceInput,
    VATSourceInput,
    WorkflowInput,
)
from app.modules.intelligence.foundations import ValidationInput
from app.modules.jurisdictions.profiles import Strict

SECTIONS = [
    "Cash & Bank",
    "Trade Receivables",
    "Trade Payables",
    "Inventories",
    "Property, Plant & Equipment",
    "Intangible Assets",
    "Investments",
    "Loans & Advances",
    "Borrowings",
    "Share Capital",
    "Reserves",
    "Revenue",
    "Cost of Sales",
    "Employee Benefits",
    "Administrative Expenses",
    "Finance Costs",
    "Other Income",
    "Provisions",
    "Accruals",
    "Related-Party Balances",
]


class OCRInput(Strict):
    evidence_version_id: uuid.UUID
    decimal_separator: Literal[".", ","] = "."
    date_format: Literal["iso", "dmy", "mdy"] = "iso"
    force_image: bool = False
    zip_member: str | None = Field(default=None, max_length=500)


class LeadInput(Strict):
    snapshot_id: uuid.UUID
    comparative_snapshot_id: uuid.UUID | None = None
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    section: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=10, max_length=4000)
    materiality_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def known_section(self):
        if self.section not in SECTIONS:
            raise ValueError("Unknown lead-schedule section")
        if len(set(self.account_ids)) != len(self.account_ids):
            raise ValueError("Duplicate account selection")
        return self


class TableInput(OCRInput):
    table_kind: Literal["bank", "open-items"]
    worksheet: str | None = Field(default=None, min_length=1, max_length=128)


class AgeingInput(Strict):
    source_id: uuid.UUID
    as_of: date
    buckets: list[int] = Field(
        default_factory=lambda: [30, 60, 90, 180], min_length=1, max_length=10
    )
    use_document_date_when_due_missing: bool = False
    control_snapshot_id: uuid.UUID | None = None
    control_account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def ordered(self):
        if (
            sorted(set(self.buckets)) != self.buckets
            or self.buckets[0] < 1
            or self.buckets[-1] > 3650
        ):
            raise ValueError("Buckets must be unique increasing positive days")
        return self


class ReconcileInput(Strict):
    snapshot_id: uuid.UUID
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    statement_source_id: uuid.UUID | None = None
    comparison_snapshot_id: uuid.UUID | None = None
    comparison_account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    reconciliation_type: Literal[
        "bank",
        "cash",
        "receivables",
        "payables",
        "confirmations",
        "intercompany",
        "inventory",
        "payroll",
        "fixed-assets",
        "vat",
        "gst",
        "tds-tcs",
    ] = "bank"
    tolerance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=28, decimal_places=8)
    date_tolerance: int = Field(default=0, ge=0, le=90)
    right_sign: Literal[1, -1] = 1
    max_group_size: int = Field(default=3, ge=1, le=6)

    @model_validator(mode="after")
    def one_destination(self):
        if bool(self.statement_source_id) == bool(self.comparison_snapshot_id):
            raise ValueError("Select exactly one destination source")
        if self.comparison_snapshot_id and not self.comparison_account_ids:
            raise ValueError("Destination account selection required")
        return self


class VouchInput(Strict):
    sample_id: uuid.UUID
    extraction_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    amount_tolerance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=28, decimal_places=8)
    date_tolerance: int = Field(default=0, ge=0, le=90)


class MappingInput(Strict):
    snapshot_id: uuid.UUID
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)


class FlowInput(Strict):
    snapshot_id: uuid.UUID
    max_journals: int = Field(default=1000, ge=1, le=10000)
    title: str = Field(default="Financial transaction investigation", min_length=1, max_length=200)
    note: str = Field(default="", max_length=6000)


OPERATIONS: dict[str, type[BaseModel]] = {
    "workflow-vat": VATSourceInput,
    "foundation-validation": ValidationInput,
    "workflow-ledger": LedgerSourceInput,
    "workflow-source": SourceInput,
    "country-workflow": WorkflowInput,
    "ocr": OCRInput,
    "source-table": TableInput,
    "lead": LeadInput,
    "ageing": AgeingInput,
    "reconciliation": ReconcileInput,
    "vouching": VouchInput,
    "mapping": MappingInput,
    "flow": FlowInput,
}


class JobInput(Strict):
    operation: Literal[
        "foundation-validation",
        "ocr",
        "source-table",
        "lead",
        "ageing",
        "reconciliation",
        "vouching",
        "mapping",
        "flow",
        "workflow-source",
        "workflow-ledger",
        "workflow-vat",
        "country-workflow",
    ]
    payload: dict

    @model_validator(mode="after")
    def typed_payload(self):
        self.payload = (
            OPERATIONS[self.operation].model_validate(self.payload).model_dump(mode="json")
        )
        return self


class Correction(Strict):
    expected_version: int = Field(ge=1)
    fields: dict[str, str | None] = Field(max_length=30)
    reason: str = Field(min_length=10, max_length=4000)


class MappingDecision(Strict):
    expected_version: int = Field(ge=1)
    assignments: dict[str, dict] = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=10, max_length=4000)


class Review(Strict):
    expected_version: int = Field(ge=1)
    action: Literal["approve", "reject", "accept", "request-evidence", "finding", "note", "submit"]
    item_id: str | None = Field(default=None, max_length=100)
    candidate_id: uuid.UUID | None = None
    comments: str = Field(min_length=10, max_length=6000)
    target_record_id: uuid.UUID | None = None
    assigned_reviewer: uuid.UUID | None = None


class GeneratePaper(Strict):
    reference: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=10, max_length=4000)
    assertions: list[str] = Field(default_factory=list, max_length=9)


class Tick(Strict):
    record_id: uuid.UUID
    expected_version: int = Field(ge=1)
    mark: Literal[
        "Agreed to GL",
        "Agreed to TB",
        "Agreed to invoice",
        "Agreed to bank statement",
        "Recalculated",
        "Confirmed externally",
        "Exception noted",
        "Reviewed",
    ]
    supporting_sources: list[dict] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=10, max_length=4000)
