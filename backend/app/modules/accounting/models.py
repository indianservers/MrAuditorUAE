"""Canonical immutable financial facts; mutable lifecycle resides on batch/run records."""

import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import Base
from app.db.models.platform import Owned

Money = Numeric(28, 8)


class Scope(Owned):
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"), index=True)
    period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financial_periods.id"), index=True)

    @declared_attr.directive
    def __table_args__(cls):
        return (
            UniqueConstraint("tenant_id", "id"),
            ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
            ForeignKeyConstraint(
                ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
            ),
            ForeignKeyConstraint(
                ["tenant_id", "period_id"], ["financial_periods.tenant_id", "financial_periods.id"]
            ),
        )


class Connection(Scope, Base):
    __tablename__ = "accounting_connections"
    provider: Mapped[str]
    name: Mapped[str]
    region: Mapped[str] = mapped_column(default="ae")
    organization_id: Mapped[str | None]
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="configured")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class SyncRun(Scope, Base):
    __tablename__ = "connection_sync_runs"
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounting_connections.id"))
    status: Mapped[str] = mapped_column(default="pending")
    completeness: Mapped[str] = mapped_column(default="insufficient_evidence")
    manifest: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_category: Mapped[str | None]


class MappingProfile(Scope, Base):
    __tablename__ = "account_mappings"
    name: Mapped[str]
    version: Mapped[int]
    mapping: Mapped[dict] = mapped_column(JSONB)
    approved: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "entity_id", "name", "version"),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
    )


class ImportBatch(Scope, Base):
    __tablename__ = "import_batches"
    kind: Mapped[str]
    source_system: Mapped[str]
    status: Mapped[str] = mapped_column(default="uploaded")
    fingerprint: Mapped[str]
    options: Mapped[dict] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(default=0)
    valid_count: Mapped[int] = mapped_column(default=0)
    progress: Mapped[int] = mapped_column(default=0)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batches.id"))
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "entity_id", "period_id", "kind", "fingerprint"),
        CheckConstraint("progress BETWEEN 0 AND 100"),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "period_id"], ["financial_periods.tenant_id", "financial_periods.id"]
        ),
    )


class ImportFile(Scope, Base):
    __tablename__ = "import_files"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), unique=True)
    filename: Mapped[str]
    object_key: Mapped[str]
    object_version: Mapped[str]
    sha256: Mapped[str]
    size: Mapped[int]


class ImportSnapshot(Scope, Base):
    __tablename__ = "import_snapshots"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), unique=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_files.id"))
    manifest: Mapped[dict] = mapped_column(JSONB)
    sha256: Mapped[str]


class ValidationResult(Scope, Base):
    __tablename__ = "import_validation_results"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), index=True)
    row_number: Mapped[int | None]
    rule: Mapped[str]
    status: Mapped[str]
    message: Mapped[str]
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)


class SourceRecord(Scope, Base):
    __tablename__ = "source_records"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    row_number: Mapped[int]
    source_id: Mapped[str]
    sha256: Mapped[str]
    raw: Mapped[dict] = mapped_column(JSONB)
    canonical: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("batch_id", "row_number"),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"], ["import_snapshots.tenant_id", "import_snapshots.id"]
        ),
    )


class Account(Scope, Base):
    __tablename__ = "accounts"
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
    classification: Mapped[str | None]
    statement_group: Mapped[str | None]
    source_group: Mapped[str | None]
    contra: Mapped[bool] = mapped_column(default=False)
    parent_code: Mapped[str | None]
    mapping_version: Mapped[int] = mapped_column(default=0)
    mapping_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("account_mappings.id"))
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "entity_id", "code"),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"], ["legal_entities.tenant_id", "legal_entities.id"]
        ),
    )


class Journal(Scope, Base):
    __tablename__ = "journal_entries"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), index=True)
    reference: Mapped[str]
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("batch_id", "reference"),
    )


class JournalLine(Scope, Base):
    __tablename__ = "journal_lines"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_records.id"), unique=True
    )
    journal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    posting_date: Mapped[date] = mapped_column(index=True)
    document_date: Mapped[date | None]
    debit: Mapped[Decimal] = mapped_column(Money)
    credit: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    functional_currency: Mapped[str] = mapped_column(String(3))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    base_debit: Mapped[Decimal] = mapped_column(Money)
    base_credit: Mapped[Decimal] = mapped_column(Money)
    opening: Mapped[bool]
    description: Mapped[str] = mapped_column(Text)
    counterparty: Mapped[str | None]
    attributes: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0)"),
        ForeignKeyConstraint(
            ["tenant_id", "journal_id"], ["journal_entries.tenant_id", "journal_entries.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "account_id"], ["accounts.tenant_id", "accounts.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "source_record_id"], ["source_records.tenant_id", "source_records.id"]
        ),
    )


class TrialBalance(Scope, Base):
    __tablename__ = "trial_balance_snapshots"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    currency: Mapped[str]
    status: Mapped[str]
    evidence: Mapped[dict] = mapped_column(JSONB)


class TrialBalanceLine(Scope, Base):
    __tablename__ = "trial_balance_lines"
    trial_balance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trial_balance_snapshots.id"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    opening: Mapped[Decimal] = mapped_column(Money)
    debit: Mapped[Decimal] = mapped_column(Money)
    credit: Mapped[Decimal] = mapped_column(Money)
    closing: Mapped[Decimal] = mapped_column(Money)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("closing = opening + debit - credit"),
    )


class Currency(Owned, Base):
    __tablename__ = "currencies"
    code: Mapped[str]
    precision: Mapped[int]
    rounding: Mapped[str] = mapped_column(default="ROUND_HALF_EVEN")
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        CheckConstraint("precision BETWEEN 0 AND 8"),
    )


class ExchangeRate(Scope, Base):
    __tablename__ = "exchange_rates"
    source_currency: Mapped[str]
    target_currency: Mapped[str]
    effective_date: Mapped[date]
    rate: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    source: Mapped[str]
    __table_args__ = (UniqueConstraint("tenant_id", "id"), CheckConstraint("rate > 0"))


class AnalyticsRun(Scope, Base):
    __tablename__ = "audit_analytics_runs"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    status: Mapped[str] = mapped_column(default="pending")
    progress: Mapped[int] = mapped_column(default=0)
    parameters: Mapped[dict] = mapped_column(JSONB)
    ruleset_version: Mapped[str] = mapped_column(default="2.0.0")


class AuditRule(Owned, Base):
    __tablename__ = "audit_rules"
    code: Mapped[str]
    version: Mapped[str]
    definition: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "code", "version"),)


class RuleResult(Scope, Base):
    __tablename__ = "audit_rule_results"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_analytics_runs.id"), index=True)
    rule_id: Mapped[str]
    rule_version: Mapped[str]
    result: Mapped[dict] = mapped_column(JSONB)


class RiskScore(Scope, Base):
    __tablename__ = "risk_scores"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_analytics_runs.id"), index=True)
    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("journal_lines.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    band: Mapped[str]
    factors: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("score BETWEEN 0 AND 100"),
    )


class Finding(Scope, Base):
    __tablename__ = "audit_findings"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_analytics_runs.id"), index=True)
    line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journal_lines.id"))
    rule_id: Mapped[str]
    status: Mapped[str] = mapped_column(default="requires_review")
    evidence: Mapped[dict] = mapped_column(JSONB)


class SamplingRun(Scope, Base):
    __tablename__ = "sampling_runs"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    method: Mapped[str]
    seed: Mapped[int]
    parameters: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(default="completed")


class SamplingItem(Scope, Base):
    __tablename__ = "sampling_items"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sampling_runs.id"), index=True)
    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("journal_lines.id"))
    hits: Mapped[int] = mapped_column(default=1)
    __table_args__ = (UniqueConstraint("tenant_id", "id"), UniqueConstraint("run_id", "line_id"))


class ReconciliationRun(Scope, Base):
    __tablename__ = "reconciliation_runs"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    comparison_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_snapshots.id")
    )
    status: Mapped[str]
    result: Mapped[dict] = mapped_column(JSONB)


class ReconciliationException(Scope, Base):
    __tablename__ = "reconciliation_exceptions"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    account_code: Mapped[str | None]
    details: Mapped[dict] = mapped_column(JSONB)


class Transformation(Scope, Base):
    __tablename__ = "data_transformations"
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"))
    version: Mapped[str]
    definition: Mapped[dict] = mapped_column(JSONB)


class IntegrityCheck(Scope, Base):
    __tablename__ = "source_integrity_checks"
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    algorithm: Mapped[str] = mapped_column(default="sha256")
    expected: Mapped[str]
    observed: Mapped[str]
    status: Mapped[str]


class UploadSession(Scope, Base):
    __tablename__ = "upload_sessions"
    filename: Mapped[str]
    total_size: Mapped[int]
    sha256: Mapped[str]
    options: Mapped[dict] = mapped_column(JSONB)
    chunks: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(default="pending")
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batches.id"))


class FinancialSuggestion(Scope, Base):
    __tablename__ = "financial_ai_suggestions"
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_executions.id"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_snapshots.id"))
    task: Mapped[str]
    suggestion: Mapped[dict] = mapped_column(JSONB)
    review_status: Mapped[str] = mapped_column(default="pending_review")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


Index(
    "ix_active_accounting_scope",
    ImportBatch.tenant_id,
    ImportBatch.entity_id,
    ImportBatch.period_id,
    ImportBatch.kind,
    unique=True,
    postgresql_where=text("status = 'active'"),
)
Index(
    "ix_lines_scope_account_date",
    JournalLine.tenant_id,
    JournalLine.entity_id,
    JournalLine.period_id,
    JournalLine.account_id,
    JournalLine.posting_date,
)
Index(
    "ix_lines_tenant_created_id",
    JournalLine.tenant_id,
    JournalLine.created_at,
    JournalLine.id,
)

# Enforce both tenant and legal-entity/period alignment at the database boundary.
for mapper in list(Base.registry.mappers):
    table = cast(Table, mapper.local_table)
    if issubclass(mapper.class_, Scope):
        table.append_constraint(
            ForeignKeyConstraint(
                ["tenant_id", "client_id", "entity_id"],
                ["legal_entities.tenant_id", "legal_entities.client_id", "legal_entities.id"],
            )
        )
        table.append_constraint(
            ForeignKeyConstraint(
                ["tenant_id", "entity_id", "period_id"],
                [
                    "financial_periods.tenant_id",
                    "financial_periods.entity_id",
                    "financial_periods.id",
                ],
            )
        )
        for fk in list(table.foreign_keys):
            remote = fk.column.table
            if (
                fk.column.name == "id"
                and fk.parent.name != "tenant_id"
                and "tenant_id" in remote.c
                and remote.name not in {"currencies", "audit_rules"}
            ):
                cols = ["tenant_id", fk.parent.name]
                if not any(
                    [c.name for c in con.columns] == cols for con in table.foreign_key_constraints
                ):
                    table.append_constraint(
                        ForeignKeyConstraint(
                            cols, [remote.name + ".tenant_id", remote.name + "." + fk.column.name]
                        )
                    )
