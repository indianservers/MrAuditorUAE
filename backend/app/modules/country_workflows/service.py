"""Adapters reuse the existing authorization, object store, jobs and event receipts."""

from datetime import date
from decimal import Decimal, localcontext
from uuid import UUID

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.db.models.platform import FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.sources import MAX_BYTES, parse_csv
from app.modules.intelligence import service as intelligence
from app.modules.jurisdictions.packages import fingerprint
from app.modules.lineage.storage import ObjectStore, hash_file


async def payroll_rule_documents(
    db, ctx, eng, rows, *, label="Payroll rule", contributors=None, max_documents=50
):
    from sqlalchemy import func, select

    from app.modules.audit_execution.models import EvidenceVersion

    documents: dict[str, EvidenceVersion] = {}
    receipts: list[dict] = []
    for rule in rows:
        identifier = rule["source_evidence_version_id"]
        if identifier not in documents:
            if len(documents) >= max_documents:
                raise HTTPException(
                    422, f"{label} evidence exceeds its {max_documents}-document verification bound"
                )
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
        if data.table_type.startswith("msme-") and package.country != "IN":
            raise HTTPException(422, "MSE supplier/invoice sources require an India engagement")
        if data.table_type == "esic-members" and package.country != "IN":
            raise HTTPException(422, "ESIC member sources require an India engagement")
        if (
            data.table_type in {"gst-summary-metrics", "gst-document-series"}
            and package.country != "IN"
        ):
            raise HTTPException(422, "GST summary metric sources require an India engagement")
        if data.table_type.startswith("pension-") and package.country != "AE":
            raise HTTPException(422, "Pension sources require a UAE engagement")
        evidence, receipt = await intelligence.evidence(db, ctx, eng, data.evidence_version_id)
        part_documents = {}
        if data.gstr2b_parts:
            if package.country != "IN":
                raise HTTPException(
                    422, "GSTR-2B response-part assembly requires an India engagement"
                )
            part_documents[str(evidence.id)] = evidence
            for part in data.gstr2b_parts:
                original, _ = await intelligence.evidence(db, ctx, eng, part.evidence_version_id)
                part_documents[str(original.id)] = original
            if any(
                document.media_type != "application/json" for document in part_documents.values()
            ):
                raise HTTPException(
                    422, "GSTR-2B manifests and numbered responses must be original JSON evidence"
                )
        supporting = None
        supporting_contributors = set()
        if evidence.created_by is not None:
            supporting_contributors.add(str(evidence.created_by))
        gstr1_context = None
        if data.file_format in {"india-gstr1-documents-json", "india-gstr1-document-series-json"}:
            if package.country != "IN":
                raise HTTPException(422, "GSTR-1 invoice/note sources require an India engagement")
            gstr1_context, _ = await intelligence.evidence(
                db, ctx, eng, data.gstr1_context_evidence_version_id
            )
            if gstr1_context.sha256 == evidence.sha256:
                raise HTTPException(
                    422, "Retain GSTR-1 request context separately from the document response"
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    [
                        {
                            "source_evidence_version_id": str(gstr1_context.id),
                            "source_sha256": gstr1_context.sha256,
                        }
                    ],
                    label="GSTR-1 request context",
                    contributors=supporting_contributors,
                )
            )
        esic_context = None
        if data.file_format == "india-esic-members-xls":
            esic_context, _ = await intelligence.evidence(
                db, ctx, eng, data.esic_context_evidence_version_id
            )
            if esic_context.sha256 == evidence.sha256:
                raise HTTPException(
                    422, "Retain ESIC employer/month context separately from the workbook"
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    [
                        {
                            "source_evidence_version_id": str(esic_context.id),
                            "source_sha256": esic_context.sha256,
                        }
                    ],
                    label="ESIC workbook context",
                    contributors=supporting_contributors,
                )
            )
        arrear_context = None
        if data.file_format == "india-epfo-arrear-ecr-v2":
            if package.country != "IN":
                raise HTTPException(422, "Arrear ECR requires an India engagement")
            arrear_context, _ = await intelligence.evidence(
                db, ctx, eng, data.arrear_context_evidence_version_id
            )
            if arrear_context.sha256 == evidence.sha256:
                raise HTTPException(
                    422, "Arrear member text cannot also establish independent filing context"
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    [
                        {
                            "source_evidence_version_id": str(arrear_context.id),
                            "source_sha256": arrear_context.sha256,
                        }
                    ],
                    label="Arrear filing context",
                    contributors=supporting_contributors,
                )
            )
        if part_documents:
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    [
                        {"source_evidence_version_id": identifier, "source_sha256": document.sha256}
                        for identifier, document in part_documents.items()
                    ],
                    label="GSTR-2B original files",
                    contributors=supporting_contributors,
                    max_documents=101,
                )
            )
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
            "india-esic-members-xls": {"application/vnd.ms-excel"},
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
            "uae-wps-sif-evp": {"text/csv"},
            "india-inv01-json": {"application/json"},
            "india-epfo-ecr": {"text/plain"},
            "india-epfo-arrear-ecr-v2": {"text/plain"},
            "india-gstr1-documents-json": {"application/json"},
            "india-gstr1-summary-json": {"application/json"},
            "india-gstr1-document-series-json": {"application/json"},
            "india-gstr2b-json": {"application/json"},
        }
        if data.workbook_sheet is not None:
            supported_media["canonical-csv"] = {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        if evidence.media_type not in supported_media[data.file_format]:
            if evidence.media_type == "application/pdf" and supporting is None:
                raise HTTPException(
                    422,
                    "Prepare and independently review a mapped PDF supporting table before using it in a workflow",
                )
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
                data.table_type
                not in {
                    "payroll-rules",
                    "pension-rules",
                    "benefit-rules",
                    "withholding-records",
                    "fx-rates",
                    "grant-budgets",
                }
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

        for prefix, identifier in (
            ("cost", data.inventory_cost_document_version_id),
            ("nrv", data.inventory_nrv_document_version_id),
        ):
            if identifier is not None:
                document, _ = await intelligence.evidence(db, ctx, eng, identifier)
                defaults = {
                    **(defaults or {}),
                    prefix + "_evidence_version_id": str(document.id),
                    prefix + "_source_sha256": document.sha256,
                }
        for prefix in ("request", "response", "followup"):
            identifier = getattr(data, "confirmation_" + prefix + "_document_version_id")
            if identifier is not None:
                document, _ = await intelligence.evidence(db, ctx, eng, identifier)
                defaults = {
                    **(defaults or {}),
                    prefix + "_evidence_version_id": str(document.id),
                    prefix + "_source_sha256": document.sha256,
                }

        def load():
            if part_documents:
                from app.modules.country_workflows.gstr2b_parts import assemble

                content = {}
                for identifier, original in part_documents.items():
                    with ObjectStore().local(
                        original.object_key, original.object_version
                    ) as original_path:
                        if (
                            original_path.stat().st_size > MAX_BYTES
                            or hash_file(original_path) != original.sha256
                        ):
                            raise ValueError(
                                "Original GSTR-2B file exceeds its size bound or failed integrity verification"
                            )
                        content[identifier] = original_path.read_bytes()
                return assemble(content[str(evidence.id)], content, data)
            with ObjectStore().local(evidence.object_key, evidence.object_version) as path:
                if path.stat().st_size > MAX_BYTES or hash_file(path) != evidence.sha256:
                    raise ValueError("Evidence exceeds size bound or hash verification failed")
                if supporting is not None:
                    from app.modules.country_workflows.table_source import from_supporting_table

                    return from_supporting_table(supporting.body, data)
                if data.file_format == "canonical-csv":
                    if data.workbook_sheet is not None:
                        from app.modules.country_workflows.workbook_source import parse_workbook

                        with path.open("rb") as original:
                            workbook_content = original.read(MAX_BYTES + 1)
                        return parse_workbook(
                            workbook_content, data, defaults, expected_sha256=evidence.sha256
                        )
                    return parse_csv(path.read_bytes(), data, defaults)
                return parse_native(path.read_bytes(), data, package.country, evidence.filename)

        result = await run_in_threadpool(load)
        if gstr1_context is not None:
            result["native_metadata"].update(
                context_sha256=gstr1_context.sha256,
                context_filename=gstr1_context.filename,
                context_basis="INDEPENDENTLY_ASSESSED_RETAINED_REQUEST_SCOPE_NOT_MACHINE_AUTHENTICATED",
            )
        if esic_context is not None:
            result["native_metadata"].update(
                context_sha256=esic_context.sha256, context_filename=esic_context.filename
            )
        if arrear_context is not None:
            result["native_metadata"].update(
                arrear_context_sha256=arrear_context.sha256,
                arrear_context_filename=arrear_context.filename,
            )
        if data.table_type.startswith("media-"):
            from app.modules.country_workflows.adverse_media import documents as media_documents

            bindings = media_documents(result["rows"])
            if any(
                str(binding["source_evidence_version_id"]) == str(evidence.id)
                or binding["source_sha256"] == evidence.sha256
                for binding in bindings
            ):
                raise HTTPException(
                    422, "Media schedules require distinct retained supporting documents"
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    bindings,
                    contributors=supporting_contributors,
                    label="Adverse media support",
                )
            )
        if data.table_type in {"grant-budgets", "grant-allocations"}:
            from app.modules.country_workflows.grant_utilisation import documents as grant_documents

            bindings = grant_documents(result["rows"], data.table_type)
            if any(
                str(binding["source_evidence_version_id"]) == str(evidence.id)
                or binding["source_sha256"] == evidence.sha256
                for binding in bindings
            ):
                raise HTTPException(
                    422,
                    "Grant schedules require distinct retained mandate/recovery-assessment documents",
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    bindings,
                    contributors=supporting_contributors,
                    label="Grant mandate/recovery assessment",
                )
            )
        if data.table_type in {"party-confirmations", "inventory-custody-confirmations"}:
            from app.modules.country_workflows.party_confirmations import (
                documents as confirmation_documents,
            )

            bindings = confirmation_documents(result["rows"])
            bindings.extend(
                {
                    "source_evidence_version_id": defaults[prefix + "_evidence_version_id"],
                    "source_sha256": defaults[prefix + "_source_sha256"],
                }
                for prefix in ("request", "response", "followup")
                if defaults and prefix + "_evidence_version_id" in defaults
            )
            if any(
                str(binding["source_evidence_version_id"]) == str(evidence.id)
                or binding["source_sha256"] == evidence.sha256
                for binding in bindings
            ):
                raise HTTPException(
                    422,
                    "Party confirmation assessments need distinct retained request/response/follow-up documents"
                    if data.table_type == "party-confirmations"
                    else "Custody confirmation assessments need distinct retained request/response/follow-up documents",
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    bindings,
                    contributors=supporting_contributors,
                    label="Party confirmation documents"
                    if data.table_type == "party-confirmations"
                    else "Inventory custody documents",
                )
            )
        if data.table_type == "inventory-valuations":
            from app.modules.country_workflows.inventory_valuation import documents

            copies = documents(result["rows"])
            copies.extend(
                {
                    "source_evidence_version_id": defaults[prefix + "_evidence_version_id"],
                    "source_sha256": defaults[prefix + "_source_sha256"],
                }
                for prefix in ("cost", "nrv")
                if defaults and prefix + "_evidence_version_id" in defaults
            )
            if any(
                str(copy["source_evidence_version_id"]) == str(evidence.id)
                or copy["source_sha256"] == evidence.sha256
                for copy in copies
            ):
                raise HTTPException(
                    422, "Inventory valuation assessments need distinct retained cost/NRV documents"
                )
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    copies,
                    contributors=supporting_contributors,
                    label="Inventory valuation documents",
                )
            )
        if data.table_type in {"payroll-rules", "pension-rules", "benefit-rules", "fx-rates"}:
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    result["rows"],
                    contributors=supporting_contributors,
                    label="Exchange rate" if data.table_type == "fx-rates" else "Payroll rule",
                )
            )
        if data.table_type == "withholding-records":
            dependencies.extend(
                await withholding_documents(
                    db, ctx, eng, result["rows"], contributors=supporting_contributors
                )
            )
        msme_context = None
        if data.table_type.startswith("msme-"):
            from app.modules.country_workflows.msme_evidence import prepare as prepare_msme_context

            msme_context, context_receipts = await prepare_msme_context(
                db, ctx, eng, data, evidence, result["rows"], supporting_contributors
            )
            dependencies.extend(context_receipts)
        return {
            **result,
            **(
                {
                    "msme_evidence_contract": "retained-msme-context/1",
                    "msme_evidence_context": msme_context,
                }
                if data.table_type.startswith("msme-")
                else {}
            ),
            "evidence_version_id": str(evidence.id),
            "evidence_sha256": evidence.sha256,
            "source_sha256": fingerprint(
                {key: value.sha256 for key, value in part_documents.items()}
            )
            if part_documents
            else evidence.sha256,
            "source_identity": ("gstr2b-parts:" if part_documents else "evidence:")
            + str(evidence.id),
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
                if defaults and data.rule_document_version_id is not None
                else {}
            ),
            **(
                {"inventory_document_bindings": defaults}
                if defaults and data.table_type == "inventory-valuations"
                else {}
            ),
            **(
                {"confirmation_document_bindings": defaults}
                if defaults
                and data.table_type in {"party-confirmations", "inventory-custody-confirmations"}
                else {}
            ),
        }, [*dependencies, receipt]
    period = await db.get(FinancialPeriod, eng.period_id)
    if data.workflow == "india-msme-payment-timing" and package.country != "IN":
        raise HTTPException(422, "MSE payment timing requires an India engagement")
    if not period or not period.start_date <= data.as_of <= period.end_date:
        raise HTTPException(422, "Reconciliation date must be within the engagement period")
    if data.tax_year_start and data.tax_year_start > data.as_of:
        raise HTTPException(422, "Tax year cannot start after the reconciliation date")
    if data.workflow == "payroll-ledger-rollforward":
        if data.period_start is None or not period.start_date <= data.period_start <= data.as_of:
            raise HTTPException(
                422, "Payroll accounting window must be within the engagement period"
            )
    elif data.workflow in {"merchant-settlement-bridge", "merchant-reserve-rollforward"}:
        if data.period_start is None or not period.start_date <= data.period_start <= data.as_of:
            raise HTTPException(
                422, "Merchant settlement review window must be within the engagement period"
            )
    elif data.workflow == "grant-utilisation":
        if data.period_start is None or not period.start_date <= data.period_start <= data.as_of:
            raise HTTPException(
                422, "Grant expenditure review window must be within the engagement period"
            )
    elif data.period_start and data.period_start != period.start_date:
        raise HTTPException(422, "Reporting-period start must equal the engagement period start")
    if data.workflow == "bank-account-evidence":
        from app.modules.country_workflows.bank_accounts import owner_name

        entity = await db.get(LegalEntity, eng.entity_id)
        if entity is None or owner_name(data.bank_owner_name) != owner_name(entity.name):
            raise HTTPException(
                422, "Bank owner name scope must equal the engagement legal entity name"
            )
    sources = {}
    hashes = set()
    evidence_versions = set()
    contributors = {str(ctx.user_id)}
    for role, identifier in data.source_ids.items():
        source = await intelligence.event(db, ctx, eng.id, identifier, True)
        if (
            data.workflow == "uae-benefit-review"
            and "service_calendar" in data.source_ids
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review employees, rules and dated service-calendar sources before calculation",
            )
        if source.body.get("parser_version") == "withholding-obligations/1" and (
            data.workflow != "obligation-bank-allocations"
            or role not in source.body.get("allowed_source_roles", [])
        ):
            raise HTTPException(
                422,
                "Withholding obligations can establish only their assessed bank-allocation purpose",
            )
        if data.workflow == "tax-turnover-bridge":
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(
                    409,
                    "Independently review every turnover scope, books, return and adjustment source",
                )
            if any(
                not period.start_date
                <= date.fromisoformat(row["period_start"])
                <= date.fromisoformat(row["period_end"])
                <= period.end_date
                for row in source.body.get("rows", [])
            ):
                raise HTTPException(
                    422, "Turnover source periods must be within the engagement financial period"
                )
        if source.kind != "workflow-source":
            raise HTTPException(422, "Select canonical country-workflow source events")
        if (
            data.workflow == "adverse-media-review"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review all media subjects, searches, mentions and policy sources before comparison",
            )
        if (
            data.workflow in {"merchant-settlement-bridge", "merchant-reserve-rollforward"}
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review all merchant sources before comparison",
            )
        if data.workflow == "grant-utilisation" and source.body.get("review_status") != "REVIEWED":
            raise HTTPException(
                409,
                "Independently review all grant mandate, expenditure, allocation and ledger-control sources before comparison",
            )
        if (
            data.workflow == "ownership-lookthrough"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review ownership edges and country/date policy before look-through",
            )
        if (
            data.workflow == "expense-cutoff"
            and {"recognitions", "postings"} & set(data.source_ids)
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review cutoff documents, recognition allocations and ledger postings before comparison",
            )
        if (
            data.workflow == "inventory-valuation-control"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review inventory books, valuation evidence and GL controls before comparison",
            )
        if data.workflow == "procurement-match" and source.body.get("review_status") != "REVIEWED":
            raise HTTPException(
                409, "Independently review all procurement sources before comparison"
            )
        if (
            data.workflow in {"party-balance-confirmations", "inventory-custody-confirmations"}
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review open items, GL controls and confirmation assessments before comparison"
                if data.workflow == "party-balance-confirmations"
                else "Independently review custody book positions, quantities and correspondence before comparison",
            )
        if data.workflow == "india-esic-population":
            from app.modules.country_workflows.esic_population import month_bounds

            if source.body.get("table_type") != "esic-members":
                raise HTTPException(422, "Select controlled ESIC member populations for both roles")
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(
                    409,
                    "Independently review both ESIC member and wage populations before comparison",
                )
            if any(
                not period.start_date
                <= month_bounds(row["period"])[0]
                <= month_bounds(row["period"])[1]
                <= data.as_of
                for row in source.body["rows"]
            ):
                raise HTTPException(
                    422, "ESIC wage month must be fully within the engagement reporting period"
                )
        if (
            data.workflow == "bank-account-evidence"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review all bank account evidence source populations before comparison",
            )
        if (
            data.workflow
            in {
                "india-invoice-register",
                "india-gstr1-summary",
                "india-gstr1-documents",
                "india-document-series",
            }
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review both source populations before invoice/register, outward GST or summary comparison",
            )
        if (
            data.workflow == "uae-vat-return"
            and data.vat201_layout in {"emirate-20", "ecommerce-20"}
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review emirate allocation and filed VAT201 sources before comparison",
            )
        if (
            data.workflow == "payroll-ledger-rollforward"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review payroll accounting allocations and both GL balances before comparison",
            )
        if source.body.get("parser_version") == "bank-clearance-carryforward/1":
            if data.workflow != "bank-subsequent-clearance" or role != "outstanding":
                raise HTTPException(
                    422,
                    "Carried bank residuals can establish only the outstanding role of subsequent clearance",
                )
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(
                    409,
                    "Independently review carried bank residuals before the next clearance window",
                )
        if (
            source.body.get("native_format") == "india-epfo-arrear-ecr-v2"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review the arrear month attribution and retained context before comparison",
            )
        if (
            data.workflow == "inventory-count-bridge"
            and data.stock_bridge_mode == "bidirectional-controlled"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review every controlled inventory source before count-date bridging",
            )
        if (
            source.body.get("parser_version") == "india-gstr2b-json-parts-1"
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409, "Independently review the assembled GSTR-2B retrieval batch before matching"
            )
        if source.body.get("parser_version") == "benefit-settlement-obligations/1":
            if data.workflow != "obligation-bank-allocations" or role != "expected":
                raise HTTPException(
                    422, "Derived gratuity can establish only expected settlement obligations"
                )
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(
                    409, "Independently review derived gratuity obligations before allocation"
                )
        if source.body.get("parser_version") == "contribution-obligations/1":
            if (
                data.workflow not in {"statutory-dues", "obligation-bank-allocations"}
                or role != "expected"
            ):
                raise HTTPException(
                    422,
                    "Derived contribution obligations can establish only expected remittances, not returns or payments",
                )
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(
                    409,
                    "Independently review derived contribution obligations before settlement comparison",
                )
        if source.body.get("parser_version") == "published-pension-profiles/1" and (
            data.workflow != "uae-pension-review" or role != "rules"
        ):
            raise HTTPException(
                422, "Published pension profiles can feed only the UAE pension rules role"
            )
        if source.body.get("parser_version") == "published-payroll-profiles/1" and (
            data.workflow != "india-payroll-rules" or role != "rules"
        ):
            raise HTTPException(
                422, "Published payroll profiles can feed only the India payroll rules role"
            )
        if source.body.get("parser_version") == "published-benefit-profiles/1" and (
            data.workflow != "uae-benefit-review" or role != "rules"
        ):
            raise HTTPException(
                422, "Published benefit profiles can feed only the UAE benefit rules role"
            )
        if data.workflow == "uae-pension-review" and source.body.get("review_status") != "REVIEWED":
            raise HTTPException(
                409,
                "Independently review all pension bases, rules and reported sources before calculation",
            )
        if (
            data.workflow in {"obligation-bank-allocations", "india-msme-payment-timing"}
            and source.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409,
                "Independently review all obligation, reported, bank and allocation sources before settlement review",
            )
        if source.body.get("parser_version") == "uae-vat201-composition/1":
            if data.workflow != "uae-vat-return" or role != "books":
                raise HTTPException(
                    422,
                    "Composed VAT201 sources can establish only books, not filed-return evidence",
                )
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(
                    409, "Independently review the composed VAT201 source before matching"
                )
        if source.body.get("parser_version") == "import-vat-box-bridge/1" and (
            data.workflow != "uae-vat-return" or role != "books"
        ):
            raise HTTPException(
                422,
                "Derived import boxes can feed only the books role of VAT201 comparison, not filed return evidence",
            )
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
    if (
        data.workflow == "tax-turnover-bridge"
        and sources.get("books", {}).get("parser_version") == "turnover-books-composition/1"
    ):
        from app.modules.country_workflows.turnover_composition import origins as turnover_origins
        from app.modules.country_workflows.turnover_composition import (
            verify as verify_turnover_books,
        )

        dependencies.extend(
            await verify_turnover_books(db, ctx, eng, sources["books"], contributors)
        )
        book_origins = await turnover_origins(db, ctx, eng, data.source_ids["books"])
        for role in ("scope", "return", "adjustments"):
            if book_origins & await turnover_origins(db, ctx, eng, data.source_ids[role]):
                raise HTTPException(
                    422,
                    "Composed books and independent turnover roles share underlying source evidence",
                )
    msme_contexts = None
    if data.workflow == "india-msme-payment-timing":
        from app.modules.country_workflows.msme_evidence import verify as verify_msme_context

        msme_contexts = []
        for role in ("assessments", "invoices"):
            dependencies.extend(
                await verify_msme_context(db, ctx, eng, sources[role], contributors)
            )
            if sources[role].get("msme_evidence_context"):
                msme_contexts.append(sources[role]["msme_evidence_context"])
    media_documents_receipts = None
    if data.workflow == "adverse-media-review":
        from app.modules.country_workflows.adverse_media import documents as media_documents

        bindings = media_documents([row for source in sources.values() for row in source["rows"]])
        if any(
            str(binding["source_evidence_version_id"]) == source.get("evidence_version_id")
            or binding["source_sha256"] == source.get("evidence_sha256")
            for binding in bindings
            for source in sources.values()
        ):
            raise HTTPException(
                422,
                "Media supporting documents must be distinct from all calculation source schedules",
            )
        media_documents_receipts = await payroll_rule_documents(
            db, ctx, eng, bindings, contributors=contributors, label="Adverse media support"
        )
        dependencies.extend(media_documents_receipts)
    grant_documents_receipts = None
    if data.workflow == "grant-utilisation":
        from app.modules.country_workflows.grant_utilisation import documents as grant_documents

        bindings = grant_documents(sources["budgets"]["rows"], "grant-budgets") + grant_documents(
            sources["allocations"]["rows"], "grant-allocations"
        )
        if any(
            str(binding["source_evidence_version_id"]) == source.get("evidence_version_id")
            or binding["source_sha256"] == source.get("evidence_sha256")
            for binding in bindings
            for source in sources.values()
        ):
            raise HTTPException(
                422,
                "Mandate and credit recovery documents must be distinct from all calculation source schedules",
            )
        grant_documents_receipts = await payroll_rule_documents(
            db,
            ctx,
            eng,
            bindings,
            contributors=contributors,
            label="Grant mandate/recovery assessment",
        )
        dependencies.extend(grant_documents_receipts)
    if (
        data.workflow == "uae-benefit-review"
        and sources["rules"].get("parser_version") == "published-benefit-profiles/1"
    ):
        from app.modules.country_workflows.benefit_source import verify

        dependencies.extend(await verify(db, ctx, eng, sources, data, contributors))
    elif (
        data.workflow == "india-payroll-rules"
        and sources["rules"].get("parser_version") == "published-payroll-profiles/1"
    ):
        from app.modules.country_workflows.payroll_source import verify as verify_payroll

        dependencies.extend(await verify_payroll(db, ctx, eng, sources, data, contributors))
    elif (
        data.workflow == "uae-pension-review"
        and sources["rules"].get("parser_version") == "published-pension-profiles/1"
    ):
        from app.modules.country_workflows.payroll_source import verify as verify_pension

        dependencies.extend(
            await verify_pension(db, ctx, eng, sources, data, contributors, profile_kind="pension")
        )
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
    for source_role, source_body in sources.items():
        if source_body.get("parser_version") == "withholding-obligations/1":
            from app.modules.country_workflows.withholding_obligations import (
                verify as verify_withholding_obligations,
            )

            dependencies.extend(
                await verify_withholding_obligations(
                    db, ctx, eng, source_body, data, source_role, contributors
                )
            )
    if sources.get("expected", {}).get("parser_version") == "benefit-settlement-obligations/1":
        from app.modules.country_workflows.benefit_settlement_source import (
            verify as verify_benefits,
        )

        dependencies.extend(await verify_benefits(db, ctx, eng, sources["expected"], contributors))
    if sources.get("expected", {}).get("parser_version") == "contribution-obligations/1":
        from app.modules.country_workflows.contribution_source import verify as verify_contributions

        dependencies.extend(
            await verify_contributions(db, ctx, eng, sources["expected"], contributors)
        )
    if sources.get("books", {}).get("parser_version") == "uae-vat201-composition/1":
        from app.modules.country_workflows.vat_composition import verify as verify_composition

        dependencies.extend(
            await verify_composition(
                db, ctx, eng, sources["books"], contributors, data.source_ids["return"]
            )
        )
    for source in sources.values():
        if source.get("native_format") == "india-epfo-arrear-ecr-v2":
            context = source["native_metadata"]
            dependencies.extend(
                await payroll_rule_documents(
                    db,
                    ctx,
                    eng,
                    [
                        {
                            "source_evidence_version_id": context[
                                "arrear_context_evidence_version_id"
                            ],
                            "source_sha256": context["arrear_context_sha256"],
                        }
                    ],
                    label="Arrear filing context",
                    contributors=contributors,
                )
            )
    if data.workflow in {"party-balance-confirmations", "inventory-custody-confirmations"}:
        from app.modules.country_workflows.party_confirmations import (
            documents as confirmation_documents,
        )

        dependencies.extend(
            await payroll_rule_documents(
                db,
                ctx,
                eng,
                confirmation_documents(sources["responses"]["rows"]),
                contributors=contributors,
                label="Party confirmation documents"
                if data.workflow == "party-balance-confirmations"
                else "Inventory custody documents",
            )
        )
    if data.workflow == "inventory-valuation-control":
        from app.modules.country_workflows.inventory_valuation import documents

        dependencies.extend(
            await payroll_rule_documents(
                db,
                ctx,
                eng,
                documents(sources["valuations"]["rows"]),
                contributors=contributors,
                label="Inventory valuation documents",
            )
        )
    if data.workflow == "bank-brs":
        book_range = sources.get("books", {}).get("source_range")
        if book_range and book_range["through"] != data.as_of.isoformat():
            raise HTTPException(
                422, "Committed bank-ledger source range must end on the reconciliation date"
            )
    import_nil_receipt = None
    if data.import_nil_scope is not None:
        nil = data.import_nil_scope
        if any(source.get("review_status") != "REVIEWED" for source in sources.values()):
            raise HTTPException(
                409, "Independently review every import source before declaring a nil population"
            )
        if any(
            str(nil.context_evidence_version_id) == source.get("evidence_version_id")
            or nil.context_sha256 == source.get("evidence_sha256")
            for source in sources.values()
        ):
            raise HTTPException(
                422, "Nil context must be separate from the import population files"
            )
        receipts = await payroll_rule_documents(
            db,
            ctx,
            eng,
            [
                {
                    "source_evidence_version_id": str(nil.context_evidence_version_id),
                    "source_sha256": nil.context_sha256,
                }
            ],
            label="Nil import context",
            contributors=contributors,
        )
        dependencies.extend(receipts)
        import_nil_receipt = receipts[0]
    bank_account_review = None
    if data.bank_account_review_id is not None:
        from app.modules.country_workflows.bank_binding import resolve

        body, receipt, account_contributors = await resolve(db, ctx, eng, data)
        bank_account_review = (body, receipt)
        contributors.update(account_contributors)
        dependencies.append(receipt)
    esic_population_review = None
    if data.esic_population_review_id is not None:
        from app.modules.country_workflows.esic_binding import resolve as resolve_esic

        if any(source.get("review_status") != "REVIEWED" for source in sources.values()):
            raise HTTPException(
                409,
                "Independently review every contribution source before binding ESIC population evidence",
            )
        body, receipt, esic_contributors = await resolve_esic(db, ctx, eng, data)
        esic_population_review = (body, receipt)
        dependencies.append(receipt)
        contributors.update(esic_contributors)
    result = await run_in_threadpool(
        calculate,
        data,
        package.country,
        sources,
        bank_account_review=bank_account_review,
        import_nil_receipt=import_nil_receipt,
        esic_population_review=esic_population_review,
    )
    if media_documents_receipts is not None:
        result["media_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
        result["retained_media_documents"] = media_documents_receipts
    if msme_contexts is not None:
        from app.modules.country_workflows.msme_evidence import CONTRACT, UNRESOLVED, VERIFIED

        result["msme_evidence_contract"] = CONTRACT
        result["retained_msme_contexts"] = msme_contexts
        result["msme_document_binding"] = VERIFIED if msme_contexts else UNRESOLVED
    if grant_documents_receipts is not None:
        result["grant_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
        result["retained_grant_documents"] = grant_documents_receipts
    if data.workflow == "obligation-bank-allocations":
        from app.modules.country_workflows.bank_consumption import manifest

        result["bank_consumption_manifest"] = manifest(data, sources["bank"], result)
    return {**result, "contributors": sorted(contributors)}, dependencies
