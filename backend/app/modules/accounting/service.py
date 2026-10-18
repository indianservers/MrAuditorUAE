"""Transactional ingestion, immutable source staging and set-based ledger activation."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import HTTPException
from sqlalchemy import Boolean, Date, Numeric, cast, func, insert, literal, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.db.models.platform import Client, FinancialPeriod, LegalEntity
from app.modules.accounting.models import (
    Account,
    ImportBatch,
    ImportFile,
    ImportSnapshot,
    IntegrityCheck,
    Journal,
    JournalLine,
    MappingProfile,
    SourceRecord,
    SyncRun,
    Transformation,
    ValidationResult,
)
from app.modules.accounting.schemas import ImportOptions, ScopeInput
from app.modules.audit_log.service import record
from app.modules.ingestion.parser import ImportProblem, normalize, rows
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.saas.storage import put_private

NORMALIZER_VERSION = "2.0.0"


def scope_values(obj: Any) -> dict:
    return {
        key: getattr(obj, key)
        for key in ["tenant_id", "client_id", "entity_id", "period_id", "created_by"]
    }


async def scoped(
    db: AsyncSession, ctx: Context, model: Any, identifier: uuid.UUID, lock: bool = False
):
    query = select(model).where(model.tenant_id == ctx.tenant_id, model.id == identifier)
    if lock:
        query = query.with_for_update()
    result = await db.scalar(query)
    if result is None:
        raise HTTPException(404, "Accounting resource not found")
    return result


async def check_scope(db: AsyncSession, ctx: Context, data: ScopeInput):
    client = await scoped(db, ctx, Client, data.client_id)
    entity = await scoped(db, ctx, LegalEntity, data.entity_id)
    period = await scoped(db, ctx, FinancialPeriod, data.period_id)
    if entity.client_id != client.id or period.entity_id != entity.id:
        raise HTTPException(422, "Client, entity and period scope mismatch")
    return entity, period


async def upload(
    db: AsyncSession,
    ctx: Context,
    data: ImportOptions,
    filename: str,
    stream: BinaryIO,
    request_id: str,
):
    await check_scope(db, ctx, data)
    if data.source_sync_run_id:
        sync = await scoped(db, ctx, SyncRun, data.source_sync_run_id)
        if (sync.client_id, sync.entity_id, sync.period_id) != (
            data.client_id,
            data.entity_id,
            data.period_id,
        ):
            raise HTTPException(422, "Source sync scope mismatch")
    if Path(filename).suffix.lower() not in (
        {".csv", ".xlsx", ".xml", ".json"} if data.source_system == "tally" else {".csv", ".xlsx"}
    ):
        raise HTTPException(422, "Only CSV/XLSX accepted")
    if data.profile_id:
        profile = await scoped(db, ctx, MappingProfile, data.profile_id)
        if profile.entity_id != data.entity_id:
            raise HTTPException(422, "Mapping profile scope mismatch")
        data = data.model_copy(update={"mapping": profile.mapping.get("columns", {})})
    # UploadFile and resume assembly provide seekable private spools.
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
        from app.core.config import settings

        if size > settings().max_upload_bytes:
            raise HTTPException(413, "Source exceeds upload limit")
    stream.seek(0)
    stored = {"sha256": digest.hexdigest()}
    fingerprint = hashlib.sha256(
        (stored["sha256"] + json.dumps(data.model_dump(mode="json"), sort_keys=True)).encode()
    ).hexdigest()
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": str(ctx.tenant_id) + fingerprint},
    )
    existing = await db.scalar(
        select(ImportBatch).where(
            ImportBatch.tenant_id == ctx.tenant_id,
            ImportBatch.entity_id == data.entity_id,
            ImportBatch.period_id == data.period_id,
            ImportBatch.kind == data.kind,
            ImportBatch.fingerprint == fingerprint,
        )
    )
    if existing:
        return existing
    try:
        stored = await put_private(db, ctx, stream)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    values = {
        "tenant_id": ctx.tenant_id,
        "created_by": ctx.user_id,
        "client_id": data.client_id,
        "entity_id": data.entity_id,
        "period_id": data.period_id,
    }
    batch = ImportBatch(
        **values,
        kind=data.kind,
        source_system=data.source_system,
        fingerprint=fingerprint,
        options=data.model_dump(mode="json"),
        supersedes_id=data.supersedes_id,
    )
    db.add(batch)
    await db.flush()
    file = ImportFile(**values, batch_id=batch.id, filename=Path(filename).name, **stored)
    db.add(file)
    await db.flush()
    manifest = {
        "file_sha256": stored["sha256"],
        "connector_version": NORMALIZER_VERSION,
        "mapping_profile": str(data.profile_id) if data.profile_id else None,
        "options": data.model_dump(mode="json"),
        "source_system": data.source_system,
    }
    snapshot = ImportSnapshot(
        **values,
        batch_id=batch.id,
        file_id=file.id,
        manifest=manifest,
        sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
    )
    db.add(snapshot)
    await db.flush()
    record(db, ctx, "accounting.uploaded", batch.id, request_id)
    return batch


async def preview(db: AsyncSession, ctx: Context, batch_id: uuid.UUID):
    batch = await scoped(db, ctx, ImportBatch, batch_id)
    file = await db.scalar(
        select(ImportFile).where(
            ImportFile.batch_id == batch.id, ImportFile.tenant_id == ctx.tenant_id
        )
    )
    if file is None:
        raise HTTPException(409, "Source file missing")
    options = ImportOptions.model_validate(batch.options)
    from itertools import islice

    with ObjectStore().local(file.object_key, file.object_version) as path:
        try:
            return {
                "rows": [
                    {"row_number": n, "values": r}
                    for n, r in islice(rows(path, file.filename, options), 20)
                ],
                "preview_only": True,
            }
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from None


async def validate(db: AsyncSession, ctx: Context, batch_id: uuid.UUID, request_id: str):
    batch = await scoped(db, ctx, ImportBatch, batch_id, lock=True)
    if batch.status != "uploaded":
        return batch
    options = ImportOptions.model_validate(batch.options)
    entity, period = await check_scope(db, ctx, options)
    file = await db.scalar(
        select(ImportFile).where(
            ImportFile.batch_id == batch.id, ImportFile.tenant_id == ctx.tenant_id
        )
    )
    snapshot = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.batch_id == batch.id, ImportSnapshot.tenant_id == ctx.tenant_id
        )
    )
    if file is None or snapshot is None:
        raise HTTPException(409, "Source snapshot missing")
    scope = scope_values(batch)
    count = valid = errors = 0
    pending: list[dict] = []
    issues = []

    def issue(rule, status, message, row=None, evidence=None):
        issues.append(
            dict(
                id=uuid.uuid4(),
                **scope,
                batch_id=batch.id,
                row_number=row,
                rule=rule,
                status=status,
                message=message,
                evidence=evidence or {},
            )
        )

    async def flush():
        if pending:
            await db.execute(insert(SourceRecord), pending)
            pending.clear()
        if issues:
            await db.execute(insert(ValidationResult), issues)
            issues.clear()

    with ObjectStore().local(file.object_key, file.object_version) as path:
        observed = hash_file(path)
        db.add(
            IntegrityCheck(
                **scope,
                snapshot_id=snapshot.id,
                expected=file.sha256,
                observed=observed,
                status="passed" if observed == file.sha256 else "failed",
            )
        )
        if observed != file.sha256:
            issue("source_integrity", "failed", "Source file hash mismatch")
            errors += 1
        else:
            try:
                for index, raw in rows(path, file.filename, options):
                    count += 1
                    canonical = None
                    try:
                        canonical, warnings = normalize(
                            raw,
                            options,
                            period.start_date,
                            period.end_date,
                            entity.functional_currency,
                            index,
                        )
                        valid += 1
                        for warning in warnings:
                            issue(warning, "warning", warning.replace("_", " "), index)
                    except ImportProblem as exc:
                        errors += 1
                        issue("row_validation", "failed", str(exc), index)
                    pending.append(
                        dict(
                            id=uuid.uuid4(),
                            **scope,
                            batch_id=batch.id,
                            snapshot_id=snapshot.id,
                            row_number=index,
                            source_id=(canonical or {}).get("source_id", f"row:{index}"),
                            sha256=hashlib.sha256(
                                json.dumps(raw, sort_keys=True).encode()
                            ).hexdigest(),
                            raw=raw,
                            canonical=canonical,
                        )
                    )
                    if len(pending) >= 1000:
                        await flush()
            except (ImportProblem, ValueError, OSError) as exc:
                issue("file_validation", "failed", str(exc))
                errors += 1
    await flush()
    if count == 0:
        issue("population", "failed", "No accounting rows")
        errors += 1
    duplicates = await db.scalar(
        text(
            "SELECT count(*) FROM (SELECT source_id FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch GROUP BY source_id HAVING count(*)>1) d"
        ),
        {"tenant": ctx.tenant_id, "batch": batch.id},
    )
    if duplicates:
        issue(
            "duplicate_source_ids",
            "failed",
            "Duplicate source identifiers",
            evidence={"groups": duplicates},
        )
        errors += 1
    if options.kind in {"gl", "journals"}:
        unbalanced = await db.execute(
            text(
                "SELECT canonical->>'journal_ref' AS ref, SUM((canonical->>'base_debit')::numeric)-SUM((canonical->>'base_credit')::numeric) AS difference FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch AND canonical IS NOT NULL GROUP BY canonical->>'journal_ref' HAVING SUM((canonical->>'base_debit')::numeric)<>SUM((canonical->>'base_credit')::numeric)"
            ),
            {"tenant": ctx.tenant_id, "batch": batch.id},
        )
        for ref, difference in unbalanced:
            issue(
                "journal_balance",
                "failed",
                "Unbalanced journal",
                evidence={"journal": ref, "difference": str(difference)},
            )
            errors += 1
        if not errors:
            issue("journal_balance", "passed", "All journal totals balance")
    else:
        issue("journal_balance", "not_testable", "Journal data not supplied")
    if options.expected_rows is not None and count != options.expected_rows:
        issue(
            "source_count",
            "failed",
            "Source control count mismatch",
            evidence={"expected": options.expected_rows, "observed": count},
        )
        errors += 1
    elif options.expected_rows is None:
        issue("source_count", "not_testable", "No independent source control count")
    else:
        issue("source_count", "passed", "Source control count matches")
    totals = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM((canonical->>'base_debit')::numeric),0), COALESCE(SUM((canonical->>'base_credit')::numeric),0) FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch"
            ),
            {"tenant": ctx.tenant_id, "batch": batch.id},
        )
    ).one()
    for label, expected, observed in [
        ("debit", options.expected_debit, totals[0]),
        ("credit", options.expected_credit, totals[1]),
    ]:
        status = (
            "not_testable" if expected is None else "passed" if expected == observed else "failed"
        )
        issue(
            "source_total_" + label,
            status,
            "Independent source total " + status,
            evidence={
                "expected": str(expected) if expected is not None else None,
                "observed": str(observed),
            },
        )
        if status == "failed":
            errors += 1
    if options.kind != "coa":
        codes = await db.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(
                SourceRecord.batch_id == batch.id,
                SourceRecord.tenant_id == ctx.tenant_id,
                SourceRecord.canonical.is_not(None),
                ~SourceRecord.canonical["account_code"].astext.in_(
                    select(Account.code).where(
                        Account.tenant_id == ctx.tenant_id,
                        Account.entity_id == batch.entity_id,
                        Account.classification.is_not(None),
                    )
                ),
            )
        )
        issue(
            "account_mapping",
            "warning" if codes else "passed",
            "Unapproved account classifications require review",
            evidence={"unmapped_rows": codes},
        )
    if options.kind in {"gl", "journals"}:
        issue(
            "ledger_debit_credit_totals",
            "passed" if totals[0] == totals[1] else "failed",
            "Aggregate functional-currency debit/credit comparison",
            evidence={"debit": str(totals[0]), "credit": str(totals[1])},
        )
        conflicts = await db.scalar(
            text(
                "SELECT count(*) FROM (SELECT canonical->>'journal_ref' FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch AND canonical IS NOT NULL GROUP BY canonical->>'journal_ref' HAVING count(DISTINCT canonical->>'posting_date')>1) d"
            ),
            {"tenant": ctx.tenant_id, "batch": batch.id},
        )
        if conflicts:
            issue(
                "journal_reference_dates",
                "failed",
                "Journal reference spans multiple posting dates",
                evidence={"conflicting_references": conflicts},
            )
            errors += 1
    for tested_rule in [
        "account_identifiers",
        "posting_dates",
        "financial_period_consistency",
        "transaction_currency_consistency",
        "functional_amount_precision",
        "debit_credit_combinations",
    ]:
        issue(
            tested_rule,
            "passed" if valid == count and count > 0 else "not_testable",
            "See row validation failures"
            if valid != count
            else "All normalized source rows satisfied this guard",
        )
    if not duplicates:
        issue("duplicate_source_ids", "passed", "No duplicate source identifiers")
    for missing_control in [
        "opening_balance_reconciliation",
        "closing_balance_reconciliation",
        "orphaned_journal_lines",
    ]:
        issue(
            missing_control,
            "not_testable",
            "Compare committed ledger to independent source controls using the reconciliation API",
        )
    for rule in [
        "control_accounts",
        "reversal_identification",
        "suspense_concentration",
        "negative_balance_review",
        "manual_adjustments",
    ]:
        issue(
            rule,
            "not_testable",
            "Requires approved mapping or analytics context; see analytics rules",
        )
    await flush()
    batch.row_count = count
    batch.valid_count = valid
    batch.status = "blocked" if errors else "validated"
    batch.progress = 100
    db.add(
        Transformation(
            **scope,
            batch_id=batch.id,
            version=NORMALIZER_VERSION,
            definition={"sign": "debit_positive", "options": batch.options},
        )
    )
    record(db, ctx, "accounting.validated", batch.id, request_id)
    await db.flush()
    await db.refresh(batch)
    return batch


async def commit(db: AsyncSession, ctx: Context, batch_id: uuid.UUID, request_id: str):
    batch = await scoped(db, ctx, ImportBatch, batch_id, lock=True)
    if batch.status == "active":
        return batch
    if batch.status != "validated":
        raise HTTPException(409, "Only a validated import can be activated")
    population_kind = "ledger" if batch.kind in {"gl", "journals"} else batch.kind
    key = f"{ctx.tenant_id}:{batch.entity_id}:{batch.period_id}:{population_kind}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key})
    active = await db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.tenant_id == ctx.tenant_id,
            ImportBatch.entity_id == batch.entity_id,
            ImportBatch.period_id == batch.period_id,
            ImportBatch.kind == batch.kind,
            ImportBatch.status == "active",
        )
        .with_for_update()
    )
    if active:
        if batch.supersedes_id != active.id:
            raise HTTPException(409, "Explicit supersedes_id is required to replace active data")
        active.status = "superseded"
        await db.flush()
    # GL and journal imports represent the same population: never activate both.
    if batch.kind in {"gl", "journals"}:
        other = await db.scalar(
            select(ImportBatch.id).where(
                ImportBatch.tenant_id == ctx.tenant_id,
                ImportBatch.entity_id == batch.entity_id,
                ImportBatch.period_id == batch.period_id,
                ImportBatch.kind.in_(["gl", "journals"]),
                ImportBatch.status == "active",
            )
        )
        if other:
            raise HTTPException(409, "An active journal/GL population already exists")
    snapshot = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.tenant_id == ctx.tenant_id, ImportSnapshot.batch_id == batch.id
        )
    )
    if snapshot is None:
        raise HTTPException(409, "Source snapshot missing")
    values = scope_values(batch)
    source = SourceRecord.canonical
    query = (
        select(
            source["account_code"].astext,
            func.min(source["account_name"].astext),
            func.min(source["source_group"].astext),
        )
        .where(SourceRecord.batch_id == batch.id, SourceRecord.tenant_id == ctx.tenant_id)
        .group_by(text("1"))
    )
    account_rows = []
    for code, name, source_group in await db.execute(query):
        account_rows.append(
            dict(
                id=uuid.uuid4(),
                **values,
                code=code,
                name=name,
                classification=None,
                statement_group=None,
                source_group=source_group,
                contra=False,
                parent_code=None,
                mapping_version=0,
            )
        )
    for offset in range(0, len(account_rows), 1000):
        await db.execute(
            pg_insert(Account)
            .values(account_rows[offset : offset + 1000])
            .on_conflict_do_nothing(index_elements=["tenant_id", "entity_id", "code"])
        )
    # Reuse previously approved code/group rules for newly seen, still-unmapped accounts.
    profiles = (
        await db.scalars(
            select(MappingProfile)
            .where(
                MappingProfile.tenant_id == ctx.tenant_id,
                MappingProfile.entity_id == batch.entity_id,
                MappingProfile.approved.is_(True),
            )
            .order_by(MappingProfile.created_at.desc(), MappingProfile.id.desc())
        )
    ).all()
    for profile in profiles:
        for selector, rules in [
            ("code", profile.mapping.get("accounts", {})),
            ("source_group", profile.mapping.get("groups", {})),
        ]:
            for match, assignment in rules.items():
                if assignment.get("classification") not in {
                    "Assets",
                    "Liabilities",
                    "Equity",
                    "Income",
                    "Expenses",
                }:
                    continue
                attributes = {
                    key: value
                    for key, value in assignment.items()
                    if key
                    in {
                        "classification",
                        "statement_group",
                        "contra",
                        "parent_code",
                        "source_group",
                    }
                }
                from sqlalchemy import update

                await db.execute(
                    update(Account)
                    .where(
                        Account.tenant_id == ctx.tenant_id,
                        Account.entity_id == batch.entity_id,
                        Account.mapping_version == 0,
                        getattr(Account, selector) == match,
                    )
                    .values(
                        **attributes, mapping_version=profile.version, mapping_profile_id=profile.id
                    )
                )
    if batch.kind in {"gl", "journals"}:
        # INSERT SELECT avoids Python objects or one round trip per ledger line.
        refs = (
            select(source["journal_ref"].astext.label("reference"))
            .where(SourceRecord.batch_id == batch.id, SourceRecord.tenant_id == ctx.tenant_id)
            .distinct()
            .subquery()
        )
        cols = ["id", *values.keys(), "batch_id", "reference"]
        expr: list[Any] = [
            func.gen_random_uuid(),
            *[literal(v) for v in values.values()],
            literal(batch.id),
            refs.c.reference,
        ]
        await db.execute(insert(Journal).from_select(cols, select(*expr)))
        cols = [
            "id",
            *values.keys(),
            "batch_id",
            "snapshot_id",
            "source_record_id",
            "journal_id",
            "account_id",
            "posting_date",
            "document_date",
            "debit",
            "credit",
            "currency",
            "functional_currency",
            "exchange_rate",
            "base_debit",
            "base_credit",
            "opening",
            "description",
            "counterparty",
            "attributes",
        ]

        def val(key):
            return source[key].astext

        expr = [
            func.gen_random_uuid(),
            *[literal(v) for v in values.values()],
            literal(batch.id),
            literal(snapshot.id),
            SourceRecord.id,
            Journal.id,
            Account.id,
            cast(val("posting_date"), Date),
            cast(val("document_date"), Date),
            cast(val("debit"), Numeric),
            cast(val("credit"), Numeric),
            val("currency"),
            val("functional_currency"),
            cast(val("exchange_rate"), Numeric),
            cast(val("base_debit"), Numeric),
            cast(val("base_credit"), Numeric),
            cast(val("opening"), Boolean),
            func.coalesce(val("description"), ""),
            val("counterparty"),
            source,
        ]
        query = (
            select(*expr)
            .select_from(SourceRecord)
            .join(
                Account,
                (Account.tenant_id == SourceRecord.tenant_id)
                & (Account.entity_id == SourceRecord.entity_id)
                & (Account.code == val("account_code")),
            )
            .join(
                Journal,
                (Journal.tenant_id == SourceRecord.tenant_id)
                & (Journal.batch_id == SourceRecord.batch_id)
                & (Journal.reference == val("journal_ref")),
            )
            .where(SourceRecord.batch_id == batch.id, SourceRecord.tenant_id == ctx.tenant_id)
        )
        await db.execute(insert(JournalLine).from_select(cols, query))
    if batch.kind in {"gl", "journals"}:
        observed = await db.scalar(
            select(func.count())
            .select_from(JournalLine)
            .where(JournalLine.tenant_id == ctx.tenant_id, JournalLine.batch_id == batch.id)
        )
        if observed != batch.valid_count:
            raise HTTPException(409, "Ledger activation completeness check failed")
    batch.status = "active"
    from app.modules.grc.imports import enqueue as enqueue_monitoring

    await enqueue_monitoring(db, batch)
    record(db, ctx, "accounting.activated", batch.id, request_id)
    await db.flush()
    await db.refresh(batch)
    return batch
