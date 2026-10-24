"""E05 to E09 handoff contract only. Deferred tax is deliberately not computed here."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.core.engine_contracts import Contract


class TaxBasisDifference(Contract):
    reference: str = Field(min_length=1, max_length=200)
    account_code: str
    carrying_amount: Decimal
    tax_base: Decimal
    source_evidence_ids: list[uuid.UUID] = Field(min_length=1)
    legal_rule_version_ids: list[uuid.UUID] = Field(min_length=1)
    classification: Literal["temporary", "permanent", "unresolved"]
    reversal_period: date | None = None


class DeferredTaxHandoff(Contract):
    schema_version: Literal["E05-E09/1"] = "E05-E09/1"
    tenant_id: uuid.UUID
    entity_id: uuid.UUID
    engagement_id: uuid.UUID
    period_id: uuid.UUID
    current_tax_run_id: uuid.UUID
    financial_run_id: uuid.UUID
    differences: list[TaxBasisDifference]
    current_tax_liability: Decimal
    loss_schedule_ids: list[uuid.UUID] = Field(default_factory=list)
    credit_schedule_ids: list[uuid.UUID] = Field(default_factory=list)
    recognition_and_recoverability: Literal["E09_REVIEW_REQUIRED"] = "E09_REVIEW_REQUIRED"
    deferred_tax_computed: Literal[False] = False
