"""Decimal-safe, tenant-scoped ML source contracts. No tax treatment is inferred here."""

from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountContract(SourceModel):
    id: str
    code: str
    name: str | None = None
    canonical_type: Literal["Assets", "Liabilities", "Equity", "Income", "Expenses"] | None = None
    source_type: str | None = None


class JournalHeader(SourceModel):
    id: str
    posting_date: date
    document_date: date | None = None
    complete: bool = False
    source: str | None = None
    manual: bool | None = None
    reversal_of: str | None = None
    created_by: str | None = None
    approved_by: str | None = None


class JournalLineContract(SourceModel):
    id: str
    journal_id: str
    account_id: str
    debit: Decimal = Field(ge=0, allow_inf_nan=False)
    credit: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    base_debit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    base_credit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    description: str | None = None
    counterparty: str | None = None
    cost_centre: str | None = None
    branch: str | None = None
    project: str | None = None
    vat_code: str | None = None
    related_party: bool | None = None

    @model_validator(mode="after")
    def signs(self):
        if self.debit and self.credit:
            raise ValueError("A line cannot contain both debit and credit")
        if (self.base_debit is None) != (self.base_credit is None):
            raise ValueError("Functional debit and credit must be supplied together")
        if self.base_debit and self.base_credit:
            raise ValueError("Functional amounts have conflicting signs")
        return self


class FinancialPopulation(SourceModel):
    schema_version: Literal["financial-population/2"] = "financial-population/2"
    tenant_id: str
    entity_id: str
    source_system: str
    period_start: date
    period_end: date
    functional_currency: str = Field(pattern=r"^[A-Z]{3}$")
    expected_line_count: int | None = Field(default=None, ge=0)
    usage_permission: Literal["tenant_authorized", "synthetic_only"]
    accounts: list[AccountContract]
    journals: list[JournalHeader]
    lines: list[JournalLineContract]

    @model_validator(mode="after")
    def integrity(self):
        if self.period_end < self.period_start:
            raise ValueError("Invalid financial period")
        for collection in (self.accounts, self.journals, self.lines):
            if len({r.id for r in collection}) != len(collection):
                raise ValueError("Duplicate source identifiers")
        if self.expected_line_count is not None and self.expected_line_count != len(self.lines):
            raise ValueError("Import completeness mismatch")
        accounts = {a.id for a in self.accounts}
        journals = {j.id: j for j in self.journals}
        totals: dict[str, dict[str, Decimal]] = {}
        for journal in self.journals:
            if not self.period_start <= journal.posting_date <= self.period_end:
                raise ValueError("Posting date outside financial period")
        for line in self.lines:
            if line.account_id not in accounts or line.journal_id not in journals:
                raise ValueError("Missing journal/account reference")
            if line.currency != self.functional_currency and line.base_debit is None:
                if journals[line.journal_id].complete:
                    raise ValueError(
                        "Complete foreign-currency journals require functional amounts"
                    )
            amount = (
                (line.base_debit - line.base_credit)
                if line.base_debit is not None and line.base_credit is not None
                else line.debit - line.credit
            )
            currency = self.functional_currency if line.base_debit is not None else line.currency
            bucket = totals.setdefault(line.journal_id, {})
            bucket[currency] = bucket.get(currency, Decimal(0)) + amount
        for journal in self.journals:
            if journal.complete and (journal.id not in totals or any(totals[journal.id].values())):
                raise ValueError("Complete journal is unbalanced or empty")
        return self

    def manifest(self):
        content = self.model_dump_json()
        return {
            "schema_version": self.schema_version,
            "sha256": sha256(content.encode()).hexdigest(),
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "period": [self.period_start.isoformat(), self.period_end.isoformat()],
            "usage_permission": self.usage_permission,
            "line_count": len(self.lines),
            "incomplete_journals": sum(not j.complete for j in self.journals),
            "production_quality_evidence": False,
        }


def chronological_splits(
    journals: list[JournalHeader],
    train_end: date,
    validation_end: date,
    connected: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Connected/duplicate/reversal groups go to their latest partition, never earlier."""
    if validation_end <= train_end:
        raise ValueError("Chronological boundaries must increase")
    by_id = {j.id: j for j in journals}
    parent = {key: key for key in by_id}

    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    links = list(connected or []) + [
        (j.id, j.reversal_of) for j in journals if j.reversal_of in by_id
    ]
    for left, right in links:
        if left not in parent or right not in parent:
            raise ValueError("Connected source is outside the authorized population")
        parent[root(left)] = root(right)
    rank = {
        j.id: 0 if j.posting_date <= train_end else 1 if j.posting_date <= validation_end else 2
        for j in journals
    }
    group_rank: dict[str, int] = {}
    for key in parent:
        group_rank[root(key)] = max(group_rank.get(root(key), 0), rank[key])
    return {key: ("train", "validation", "test")[group_rank[root(key)]] for key in parent}
