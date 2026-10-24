"""Adapters reuse the existing authorization, object store, jobs and event receipts."""

from decimal import Decimal, localcontext

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.db.models.platform import FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.sources import MAX_BYTES, parse_csv
from app.modules.intelligence import service as intelligence
from app.modules.lineage.storage import ObjectStore, hash_file


async def compute(db, ctx, eng, operation, data, package, dependencies):
    if operation == "workflow-vat":
        from app.modules.country_workflows.vat_source import compute as vat_source

        return await vat_source(db, ctx, eng, data, package, dependencies)
    from app.modules.audit_execution.access import engagement_permissions
    from app.modules.country_workflows.diligence_schemas import (
        DILIGENCE_ROW_TYPES,
        DILIGENCE_WORKFLOWS,
    )

    if (operation == "workflow-source" and data.table_type in DILIGENCE_ROW_TYPES) or (
        operation == "country-workflow" and data.workflow in DILIGENCE_WORKFLOWS
    ):
        await engagement_permissions(db, ctx, eng.id, "audit.evidence.review")
    if operation == "workflow-ledger":
        snapshot, receipt = await intelligence.snapshot(db, ctx, eng, data.snapshot_id)
        batch = await db.get(ImportBatch, snapshot.batch_id)
        if not batch or batch.kind not in {"gl", "journals"}:
            raise HTTPException(
                422,
                "A committed GL/journal snapshot is required; a trial balance is not a transaction population",
            )
        period = await db.get(FinancialPeriod, eng.period_id)
        entity = await db.get(LegalEntity, eng.entity_id)
        if not period or not entity or entity.functional_currency != data.currency:
            raise HTTPException(
                422, "Select the legal entity functional-currency ledger explicitly"
            )
        if data.source_kind == "balance-controls":
            from app.modules.reconciliation.service import balance

            if data.as_of != period.end_date or data.nil_reason:
                raise HTTPException(422, "GL balance controls require period end and cannot be nil")
            values = await balance(db, ctx, snapshot.id)
            selected = [
                r for r in values["lines"] if str(r["id"]) in {str(i) for i in data.account_ids}
            ]
            if len(selected) != 1:
                raise HTTPException(422, "Select one account from this snapshot")
            value = selected[0]["closing"] * (-1 if data.balance_side == "payable" else 1)
            return {
                "table_type": "balance-controls",
                "rows": [
                    {
                        "id": "control:" + str(selected[0]["id"]),
                        "account": data.bank_account,
                        "side": data.balance_side,
                        "currency": data.currency,
                        "as_of": data.as_of.isoformat(),
                        "amount": str(value),
                    }
                ],
                "row_count": 1,
                "control_totals": {data.currency: str(value)},
                "population_completeness": "COMMITTED_LEDGER_ACCOUNT_SELECTION",
                "review_status": "UNVERIFIED",
                "title": data.label,
                "source_identity": "snapshot:" + str(snapshot.id) + ":" + str(data.account_ids[0]),
                "source_sha256": snapshot.sha256,
                "source_snapshot_id": str(snapshot.id),
                "contributors": [str(ctx.user_id)],
                "parser_version": "gl-balance-control-1",
                "sign_basis": "payable-credit-normal"
                if data.balance_side == "payable"
                else "receivable-debit-normal",
            }, [*dependencies, receipt]
        from_date = data.from_date or period.start_date
        if not period.start_date <= from_date <= data.as_of <= period.end_date:
            raise HTTPException(
                422, "Ledger date range must be ordered and within the engagement period"
            )
        entries = await intelligence.ledger(
            db, ctx, eng, snapshot, data.account_ids, data.as_of, from_date
        )
        if len(entries) > 5000:
            raise HTTPException(
                422, "Bank workflow source exceeds 5,000 rows; select a bounded account population"
            )
        if not entries and not data.nil_reason:
            raise HTTPException(
                422, "An empty committed-ledger selection needs an explicit nil rationale"
            )
        if entries and data.nil_reason:
            raise HTTPException(422, "A populated ledger cannot be declared nil")
        if any(r["currency"] != data.currency for r in entries):
            raise HTTPException(
                422,
                "The selected ledger uses functional-currency amounts; select that currency explicitly",
            )
        rows = [
            {
                "id": r["id"],
                "account": data.bank_account,
                "reference": r["reference"],
                "date": r["date"],
                "currency": r["currency"],
                "amount": r["amount"],
                "counterparty": r.get("counterparty") or "",
                "source_record_id": r["source_record_id"],
            }
            for r in entries
        ]
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            total = sum((Decimal(r["amount"]) for r in rows), Decimal(0))
        return {
            "table_type": "transactions",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": {data.currency: str(total)},
            "population_completeness": "COMMITTED_LEDGER_ACCOUNT_SELECTION",
            "review_status": "UNVERIFIED",
            "title": data.label,
            "source_identity": "snapshot:" + str(snapshot.id) + ":" + str(data.account_ids[0]),
            "source_sha256": snapshot.sha256,
            "source_snapshot_id": str(snapshot.id),
            "source_range": {"from": from_date.isoformat(), "through": data.as_of.isoformat()},
            "account_ids": [str(i) for i in data.account_ids],
            "nil_reason": data.nil_reason,
            "contributors": [str(ctx.user_id)],
            "parser_version": "committed-ledger-1",
        }, [*dependencies, receipt]
    if operation == "workflow-source":
        evidence, receipt = await intelligence.evidence(db, ctx, eng, data.evidence_version_id)
        from app.modules.country_workflows.native_sources import parse_native

        supported_media = {
            "canonical-csv": {"text/csv"},
            "camt053": {"application/xml", "text/xml"},
            "swift-mt940": {"text/plain"},
            "uae-wps-sif": {"text/csv"},
            "india-inv01-json": {"application/json"},
            "india-epfo-ecr": {"text/plain"},
        }
        if evidence.media_type not in supported_media[data.file_format]:
            raise HTTPException(
                422, "Retained evidence media type does not match the selected source format"
            )

        def load():
            with ObjectStore().local(evidence.object_key, evidence.object_version) as path:
                if path.stat().st_size > MAX_BYTES or hash_file(path) != evidence.sha256:
                    raise ValueError("Evidence exceeds size bound or hash verification failed")
                if data.file_format == "canonical-csv":
                    return parse_csv(path.read_bytes(), data)
                return parse_native(path.read_bytes(), data, package.country, evidence.filename)

        result = await run_in_threadpool(load)
        return {
            **result,
            "evidence_version_id": str(evidence.id),
            "evidence_sha256": evidence.sha256,
            "source_sha256": evidence.sha256,
            "source_identity": "evidence:" + str(evidence.id),
            "source_filename": evidence.filename,
            "contributors": [str(ctx.user_id)],
        }, [*dependencies, receipt]
    period = await db.get(FinancialPeriod, eng.period_id)
    if not period or not period.start_date <= data.as_of <= period.end_date:
        raise HTTPException(422, "Reconciliation date must be within the engagement period")
    if data.tax_year_start and data.tax_year_start > data.as_of:
        raise HTTPException(422, "Tax year cannot start after the reconciliation date")
    if data.period_start and data.period_start != period.start_date:
        raise HTTPException(422, "Reporting-period start must equal the engagement period start")
    sources = {}
    hashes = set()
    evidence_versions = set()
    contributors = {str(ctx.user_id)}
    for role, identifier in data.source_ids.items():
        source = await intelligence.event(db, ctx, eng.id, identifier, True)
        if source.kind != "workflow-source":
            raise HTTPException(422, "Select canonical country-workflow source events")
        identity = (
            source.body.get("source_identity") or "evidence:" + source.body["evidence_version_id"]
        )
        digest = source.body.get("source_sha256") or source.body["evidence_sha256"]
        if identity in evidence_versions:
            raise HTTPException(
                422, "The same evidence version cannot establish independent source roles"
            )
        declared_nil = not source.body["rows"] and bool(source.body.get("nil_reason"))
        if digest in hashes and not declared_nil:
            raise HTTPException(
                422, "Identical source files cannot establish independent source roles"
            )
        hashes.add(digest)
        evidence_versions.add(identity)
        sources[role] = source.body
        contributors.update(source.body.get("contributors", [str(source.created_by)]))
        dependencies.append(intelligence.event_receipt(source))
    if data.workflow == "bank-brs":
        book_range = sources.get("books", {}).get("source_range")
        if book_range and book_range["through"] != data.as_of.isoformat():
            raise HTTPException(
                422, "Committed bank-ledger source range must end on the reconciliation date"
            )
    result = await run_in_threadpool(calculate, data, package.country, sources)
    return {**result, "contributors": sorted(contributors)}, dependencies
