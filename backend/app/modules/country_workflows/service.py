"""Adapters reuse the existing authorization, object store, jobs and event receipts."""

from decimal import Decimal, localcontext
from uuid import UUID

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.db.models.platform import FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.sources import MAX_BYTES, parse_csv
from app.modules.intelligence import service as intelligence
from app.modules.lineage.storage import ObjectStore, hash_file


async def payroll_rule_documents(db, ctx, eng, rows, *, label="Payroll rule", contributors=None):
    from sqlalchemy import func, select

    from app.modules.audit_execution.models import EvidenceVersion

    documents: dict[str, EvidenceVersion] = {}
    receipts: list[dict] = []
    for rule in rows:
        identifier = rule["source_evidence_version_id"]
        if identifier not in documents:
            if len(documents) >= 50:
                raise HTTPException(422, f"{label} evidence is limited to fifty retained documents")
            document, receipt = await intelligence.evidence(db, ctx, eng, UUID(identifier))
            latest = await db.scalar(
                select(func.max(EvidenceVersion.number)).where(
                    EvidenceVersion.tenant_id == ctx.tenant_id,
                    EvidenceVersion.record_id == document.record_id,
                )
            )
            if document.number != latest:
                raise HTTPException(
                    409, f"{label} document was superseded; prepare a current reviewed source"
                )
            documents[identifier] = document
            if contributors is not None and document.created_by is not None:
                contributors.add(str(document.created_by))
            receipts.append(receipt)
        if documents[identifier].sha256 != rule["source_sha256"]:
            raise HTTPException(422, f"{label} document hash differs from its retained evidence")

    def verify():
        size = 0
        for document in documents.values():
            with ObjectStore().local(document.object_key, document.object_version) as path:
                size += path.stat().st_size
                if size > 100 * 1024 * 1024 or hash_file(path) != document.sha256:
                    raise ValueError(
                        f"{label} evidence exceeds its verification bound or failed original-file integrity"
                    )

    await run_in_threadpool(verify)
    return receipts


async def withholding_documents(db, ctx, eng, rows, *, contributors=None):
    bindings = [
        {
            "source_evidence_version_id": row["assessment_evidence_version_id"],
            "source_sha256": row["assessment_sha256"],
        }
        for row in rows
        if row["record_status"] == "current" and row.get("assessment_evidence_version_id")
    ]
    return await payroll_rule_documents(
        db, ctx, eng, bindings, label="Withholding assessment", contributors=contributors
    )


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
        if data.table_type.startswith("pension-") and package.country != "AE":
            raise HTTPException(422, "Pension sources require a UAE engagement")
        evidence, receipt = await intelligence.evidence(db, ctx, eng, data.evidence_version_id)
        supporting = None
        supporting_contributors = set()
        if evidence.created_by is not None:
            supporting_contributors.add(str(evidence.created_by))
        if data.supporting_table_id:
            supporting = await intelligence.event(db, ctx, eng.id, data.supporting_table_id, True)
            if (
                supporting.kind != "source-table"
                or supporting.body.get("review_status") != "REVIEWED"
            ):
                raise HTTPException(409, "Select an independently reviewed supporting table")
            dependencies.append(intelligence.event_receipt(supporting))
            root = await intelligence.event(db, ctx, eng.id, supporting.root_id)
            supporting_contributors.update(
                [
                    str(root.created_by),
                    str(supporting.created_by),
                    *root.body.get("contributors", []),
                    *supporting.body.get("contributors", []),
                ]
            )
        from app.modules.country_workflows.native_sources import parse_native

        supported_media = {
            "canonical-csv": {
                "text/csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/pdf",
            }
            if supporting is not None
            else {"text/csv"},
            "camt053": {"application/xml", "text/xml"},
            "swift-mt940": {"text/plain"},
            "uae-wps-sif": {"text/csv"},
            "india-inv01-json": {"application/json"},
            "india-epfo-ecr": {"text/plain"},
            "india-gstr2b-json": {"application/json"},
        }
        if evidence.media_type not in supported_media[data.file_format]:
            if evidence.media_type == "application/pdf" and supporting is None:
                raise HTTPException(422, "Prepare and independently review a mapped PDF supporting table before using it in a workflow")
            raise HTTPException(
                422, "Retained evidence media type does not match the selected source format"
            )
        defaults = None
        if data.file_format != "canonical-csv" and (
            data.column_mapping
            or data.ignored_columns
            or data.mapping_rationale
            or data.delimiter != ","
        ):
            raise HTTPException(422, "CSV mappings and delimiters apply only to CSV sources")
        if data.rule_document_version_id:
            if (
                data.table_type not in {"payroll-rules", "pension-rules", "benefit-rules", "withholding-records", "fx-rates"}
                or data.file_format != "canonical-csv"
            ):
                raise HTTPException(
                    422,
                    "A source document can be selected only for canonical payroll/pension/benefit rules, withholding assessments or exchange rates",
                )
            rule_document, _ = await intelligence.evidence(
                db, ctx, eng, data.rule_document_version_id
            )
            defaults = {
                "source_evidence_version_id": str(rule_document.id),
                "source_sha256": rule_document.sha256,
            }
            if data.table_type == "withholding-records":
                defaults = {
                    "assessment_evidence_version_id": str(rule_document.id),
                    "assessment_sha256": rule_document.sha256,
                }

        def load():
            with ObjectStore().local(evidence.object_key, evidence.object_version) as path:
                if path.stat().st_size > MAX_BYTES or hash_file(path) != evidence.sha256:
                    raise ValueError("Evidence exceeds size bound or hash verification failed")
                if supporting is not None:
                    from app.modules.country_workflows.table_source import from_supporting_table

                    return from_supporting_table(supporting.body, data)
                if data.file_format == "canonical-csv":
                    return parse_csv(path.read_bytes(), data, defaults)
                return parse_native(path.read_bytes(), data, package.country, evidence.filename)

        result = await run_in_threadpool(load)
        if data.table_type in {"payroll-rules", "pension-rules", "benefit-rules", "fx-rates"}:
            dependencies.extend(
                await payroll_rule_documents(
                    db, ctx, eng, result["rows"], contributors=supporting_contributors,
                    label="Exchange rate" if data.table_type == "fx-rates" else "Payroll rule",
                )
            )
        if data.table_type == "withholding-records":
            dependencies.extend(
                await withholding_documents(
                    db, ctx, eng, result["rows"], contributors=supporting_contributors
                )
            )
        return {
            **result,
            "evidence_version_id": str(evidence.id),
            "evidence_sha256": evidence.sha256,
            "source_sha256": evidence.sha256,
            "source_identity": "evidence:" + str(evidence.id),
            "source_filename": evidence.filename,
            "contributors": sorted(
                {
                    str(ctx.user_id),
                    *supporting_contributors,
                }
            ),
            **(
                {
                    "rule_document_version_id": str(data.rule_document_version_id),
                    "rule_document_binding": "SELECTED_RETAINED_DOCUMENT",
                }
                if defaults
                else {}
            ),
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
        if source.body.get("parser_version") == "published-pension-profiles/1" and (
            data.workflow != "uae-pension-review" or role != "rules"
        ):
            raise HTTPException(422, "Published pension profiles can feed only the UAE pension rules role")
        if source.body.get("parser_version") == "published-payroll-profiles/1" and (
            data.workflow != "india-payroll-rules" or role != "rules"
        ):
            raise HTTPException(422, "Published payroll profiles can feed only the India payroll rules role")
        if source.body.get("parser_version") == "published-benefit-profiles/1" and (
            data.workflow != "uae-benefit-review" or role != "rules"
        ):
            raise HTTPException(422, "Published benefit profiles can feed only the UAE benefit rules role")
        if data.workflow == "uae-pension-review" and source.body.get("review_status") != "REVIEWED":
            raise HTTPException(409, "Independently review all pension bases, rules and reported sources before calculation")
        if data.workflow == "obligation-bank-allocations" and source.body.get("review_status") != "REVIEWED":
            raise HTTPException(409, "Independently review all obligation, reported, bank and allocation sources before settlement review")
        if source.body.get("parser_version") == "import-vat-box-bridge/1" and (data.workflow != "uae-vat-return" or role != "books"):
            raise HTTPException(422, "Derived import boxes can feed only the books role of VAT201 comparison, not filed return evidence")
        if (
            data.workflow in {"india-payroll-rules", "uae-benefit-review"}
            and role == "rules"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review the payroll/benefit rule source before calculating expected dues",
            )
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
    if data.workflow == "uae-benefit-review" and sources["rules"].get("parser_version") == "published-benefit-profiles/1":
        from app.modules.country_workflows.benefit_source import verify

        dependencies.extend(await verify(db, ctx, eng, sources, data, contributors))
    elif data.workflow == "india-payroll-rules" and sources["rules"].get("parser_version") == "published-payroll-profiles/1":
        from app.modules.country_workflows.payroll_source import verify as verify_payroll

        dependencies.extend(await verify_payroll(db, ctx, eng, sources, data, contributors))
    elif data.workflow == "uae-pension-review" and sources["rules"].get("parser_version") == "published-pension-profiles/1":
        from app.modules.country_workflows.payroll_source import verify as verify_pension

        dependencies.extend(await verify_pension(db, ctx, eng, sources, data, contributors, profile_kind="pension"))
    elif data.workflow in {"india-payroll-rules", "uae-benefit-review", "uae-pension-review"}:
        dependencies.extend(
            await payroll_rule_documents(
                db, ctx, eng, sources["rules"]["rows"], contributors=contributors
            )
        )
    if data.workflow in {"india-withholding-liability", "india-withholding-credit"}:
        dependencies.extend(
            await withholding_documents(
                db,
                ctx,
                eng,
                [row for source in sources.values() for row in source["rows"]],
                contributors=contributors,
            )
        )
    if data.workflow == "bank-brs":
        book_range = sources.get("books", {}).get("source_range")
        if book_range and book_range["through"] != data.as_of.isoformat():
            raise HTTPException(
                422, "Committed bank-ledger source range must end on the reconciliation date"
            )
    result = await run_in_threadpool(calculate, data, package.country, sources)
    return {**result, "contributors": sorted(contributors)}, dependencies
