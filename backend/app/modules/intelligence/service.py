"""Source-bound accounting operations. Outputs are append-only and independently reviewable."""

import csv
import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from app.db.models.platform import FinancialPeriod
from app.modules.accounting.models import (
    Account,
    ImportBatch,
    ImportSnapshot,
    Journal,
    JournalLine,
    SamplingItem,
    SamplingRun,
)
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.audit_log.service import record
from app.modules.intelligence import schemas as s
from app.modules.intelligence.models import IntelligenceEvent
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.workspace import resolved
from app.modules.lineage.freshness import mapping_receipt
from app.modules.lineage.storage import ObjectStore, hash_file

PERMISSIONS = {
    "workflow-vat": "workingpaper.create",
    "foundation-validation": "workingpaper.create",
    "workflow-ledger": "workingpaper.create",
    "workflow-source": "audit.evidence.upload",
    "country-workflow": "workingpaper.create",
    "ocr": "audit.evidence.upload",
    "source-table": "audit.evidence.upload",
    "lead": "workingpaper.create",
    "ageing": "workingpaper.create",
    "reconciliation": "workingpaper.create",
    "vouching": "audit.testing.execute",
    "mapping": "accounting.map",
    "flow": "analytics.read",
}


async def scope(db, ctx, eid, operation=None, mutable=False):
    eng = await audit.engagement(
        db, ctx, eid, PERMISSIONS[operation] if operation else "audit.read", mutable, lock=mutable
    )
    if operation in {
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
    }:
        await engagement_permissions(db, ctx, eid, "accounting.read")
    if operation == "workflow-vat":
        await engagement_permissions(db, ctx, eid, "vat.read")
    return eng


async def restricted_permission(db, ctx, eid, body):
    from app.modules.country_workflows.diligence_schemas import (
        DILIGENCE_ROW_TYPES,
        DILIGENCE_WORKFLOWS,
    )

    if body.get("table_type") in DILIGENCE_ROW_TYPES or body.get("workflow") in DILIGENCE_WORKFLOWS:
        await engagement_permissions(db, ctx, eid, "audit.evidence.review")


async def event(db, ctx, eid, identifier, require_current=False, auth_seen=None):
    auth_seen = set() if auth_seen is None else auth_seen
    if identifier in auth_seen or len(auth_seen) >= 100:
        raise HTTPException(409, "Source authorization depth or cycle limit")
    auth_seen = auth_seen | {identifier}
    await scope(db, ctx, eid)
    obj = await db.scalar(
        select(IntelligenceEvent).where(
            IntelligenceEvent.tenant_id == ctx.tenant_id,
            IntelligenceEvent.engagement_id == eid,
            IntelligenceEvent.id == identifier,
        )
    )
    if not obj:
        raise HTTPException(404, "Intelligence result not found")
    if getattr(obj, "kind", None) == "business-action":
        from app.modules.enterprise_ai.business import case_scope

        await case_scope(db, ctx, eid, obj.body["use_case_id"])
        for dependency in obj.dependencies:
            if dependency["type"] == "record":
                await audit.get_record(db, ctx, eid, uuid.UUID(dependency["id"]), lock=False)
    if obj.kind == "tax-close-rollup":
        for dependency in obj.dependencies:
            if dependency["type"] == "record":
                await audit.get_record(db, ctx, eid, uuid.UUID(dependency["id"]), lock=False)
    if obj.kind == "tax-connected-assessment":
        from app.modules.regulatory.reporting import engines

        for dependency in obj.dependencies:
            if dependency["type"] == "calculation":
                await engagement_permissions(db, ctx, eid, engines()[dependency["module"]][1])
            elif dependency["type"] == "dmtt":
                await engagement_permissions(db, ctx, eid, "dmtt.read")
    await restricted_permission(db, ctx, eid, obj.body)
    if obj.kind not in {
        "ocr",
        "source-table",
        "tick",
        "statutory-checklist",
        "report-template",
        "statutory-report",
        "tax-connected-assessment",
        "tax-close-rollup",
    }:
        await engagement_permissions(db, ctx, eid, "accounting.read")
    for dependency in obj.dependencies:
        if dependency["type"] == "calculation":
            from app.modules.regulatory.reporting import engines

            engine = engines().get(dependency["module"])
            if not engine:
                raise HTTPException(409, "Unsupported source calculation module")
            await engagement_permissions(db, ctx, eid, engine[1])
        elif dependency["type"] == "event":
            await event(db, ctx, eid, uuid.UUID(dependency["id"]), auth_seen=auth_seen)
    if obj.kind == "statutory-report":
        for block in obj.body["blocks"]:
            if block.get("calculation_module"):
                await engagement_permissions(
                    db,
                    ctx,
                    eid,
                    "tax.profile.read"
                    if block["calculation_module"] == "tax"
                    else block["calculation_module"] + ".read",
                )
            if block.get("source_kind") == "record":
                await audit.get_record(db, ctx, eid, uuid.UUID(block["source_id"]), lock=False)
            elif block.get("source_kind") == "intelligence":
                parent = await db.get(IntelligenceEvent, uuid.UUID(block["source_id"]))
                if not parent or parent.kind == "statutory-report":
                    raise HTTPException(
                        409, "Nested report sources require a separately qualified source adapter"
                    )
                await event(db, ctx, eid, parent.id, auth_seen=auth_seen)
    bindings = list(obj.body.get("fact_sources", {}).values())
    if obj.kind == "statutory-checklist":
        bindings += [
            binding
            for item in obj.body["items"]
            for binding in item.get("fact_sources", {}).values()
        ]
    for binding in bindings:
        if binding["kind"] == "record":
            await audit.get_record(db, ctx, eid, uuid.UUID(binding["id"]), lock=False)
        else:
            await event(db, ctx, eid, uuid.UUID(binding["id"]), auth_seen=auth_seen)
    if require_current and not await current(db, ctx, obj):
        raise HTTPException(
            409,
            "Intelligence result changed or source is stale; regenerate or select the reviewed current version",
        )
    return obj


async def head(db, ctx, obj):
    from app.core.read_projection import read_once

    return await read_once(
        db, ctx, "intelligence-head", str(obj.root_id), lambda: _head(db, ctx, obj)
    )


async def _head(db, ctx, obj):
    return await db.scalar(
        select(func.max(IntelligenceEvent.version)).where(
            IntelligenceEvent.tenant_id == ctx.tenant_id, IntelligenceEvent.root_id == obj.root_id
        )
    )


async def current(db, ctx, obj, visited=None):
    if obj.tenant_id != ctx.tenant_id:
        return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") == "bank-account-evidence"
    ):
        from app.modules.country_workflows.bank_observation_scope import saved_scope

        try:
            saved_scope(obj.body)
        except ValueError:
            return False
    # EVP has enforced strict raw record boundaries since its introduction.
    if (
        getattr(obj, "kind", None) == "workflow-source"
        and obj.body.get("native_format") == "uae-wps-sif"
    ):
        from app.modules.country_workflows.native_sources import WPS_RECORD_CONTRACT

        metadata = obj.body.get("native_metadata")
        if (
            not isinstance(metadata, dict)
            or metadata.get("record_boundary_contract") != WPS_RECORD_CONTRACT
        ):
            return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") == "india-payroll-rules"
    ):
        from app.modules.country_workflows.payroll_calculations import CONTRACT

        if obj.body.get("payroll_rule_selection_contract") != CONTRACT:
            return False
    if getattr(obj, "kind", None) in {"workflow-source", "country-workflow"} and (
        obj.body.get("workflow")
        in {"india-msme-payment-timing", "india-msme-interest", "india-msme-annual-tax"}
        or str(obj.body.get("table_type") or "").startswith("msme-")
    ):
        from app.modules.country_workflows.msme_evidence import current_contract as msme_current

        if not msme_current(obj.body, obj.dependencies):
            return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") == "india-msme-interest"
    ):
        from app.modules.country_workflows.msme_interest_schemas import CONTRACT

        if obj.body.get("msme_interest_contract") != CONTRACT or obj.body.get(
            "msme_interest_document_binding"
        ) not in {"RETAINED_DOCUMENT_BYTES_VERIFIED", "NO_INTEREST_FACTS_CLAIMED"}:
            return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") == "india-msme-annual-tax"
    ):
        from app.modules.country_workflows.msme_tax_schemas import CONTRACT

        if obj.body.get("msme_tax_contract") != CONTRACT or obj.body.get(
            "msme_tax_document_binding"
        ) not in {"RETAINED_DOCUMENT_BYTES_VERIFIED", "NO_TAX_FACTS_CLAIMED"}:
            return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") == "merchant-settlement-bridge"
    ):
        from app.modules.country_workflows.merchant_settlements import CONTRACT

        if obj.body.get("merchant_settlement_contract") != CONTRACT:
            return False
    if getattr(obj, "kind", None) == "tax-close-rollup":
        from app.modules.regulatory.exposure_rollup import CONTRACT, implementation_hash

        if (
            obj.body.get("contract") != CONTRACT
            or obj.body.get("implementation_sha256") != implementation_hash()
        ):
            return False
    if getattr(obj, "kind", None) in {"report-template", "statutory-report"}:
        from app.modules.regulatory.report_requirements import current_contract

        if not current_contract(obj.body):
            return False
        from app.modules.regulatory.tax_forms import IndiaTaxAuditScope, has_tax_scope_contract

        if not has_tax_scope_contract(obj.body, obj.dependencies):
            return False
        if obj.body.get("category") == "india-tax-audit":
            from app.db.models.platform import Engagement

            eng = await db.get(Engagement, obj.engagement_id)
            period = await db.get(FinancialPeriod, eng.period_id) if eng and eng.period_id else None
            if period is None or not IndiaTaxAuditScope.model_validate(
                obj.body["tax_audit_scope"]
            ).covered_by(period.start_date, period.end_date):
                return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") in {"india-withholding-liability", "india-withholding-credit"}
        and obj.body.get("assessment_contract_version") != "withholding-assessment/1"
    ):
        return False
    if (
        getattr(obj, "kind", None) == "country-workflow"
        and obj.body.get("workflow") == "india-withholding"
        and (obj.body.get("blocked") is not True or obj.body.get("review_status") == "REVIEWED")
    ):
        return False  # Retained role-unassessed approvals cannot feed new workpapers or actions.
    if getattr(obj, "kind", None) == "business-action":
        from app.modules.enterprise_ai.security import digest
        from app.modules.jurisdictions.ae.use_cases import MANIFEST

        if obj.body.get("case_catalogue_sha256") != digest(MANIFEST):
            return False
        if obj.body.get("use_case_id", 0) >= 51:
            from app.modules.jurisdictions.ae.advanced import contract_sha256

            if obj.body.get("advanced_contract_sha256") != contract_sha256():
                return False
        if obj.body.get("action") == "inspect-provenance":
            from app.modules.jurisdictions.ae.provenance import corpus

            if (
                digest(await corpus(db, ctx, obj.engagement_id))
                != obj.body["output"]["population_sha256"]
            ):
                return False
        if obj.body.get("action") == "rule-impact":
            from app.modules.jurisdictions.ae.rule_impact import fingerprint as impact_fingerprint

            if (
                await impact_fingerprint(db, ctx, obj.engagement_id)
                != obj.body["output"]["population_sha256"]
            ):
                return False
        if obj.body.get("action") == "file-readiness":
            rows = (
                await db.scalars(
                    select(AuditRecord)
                    .where(
                        AuditRecord.tenant_id == ctx.tenant_id,
                        AuditRecord.engagement_id == obj.engagement_id,
                    )
                    .order_by(AuditRecord.id)
                    .limit(2001)
                )
            ).all()
            if (
                digest([[str(r.id), r.version, r.status] for r in rows])
                != obj.body["output"]["file_population_sha256"]
            ):
                return False
            if (
                digest(await audit.completion(db, ctx, obj.engagement_id))
                != obj.body["output"]["completion_sha256"]
            ):
                return False
    from app.core.operations_contracts import current as operations_current

    if not await operations_current(db, ctx, obj):
        return False
    visited = set() if visited is None else visited
    if obj.id in visited or len(visited) > 100:
        return False
    if await head(db, ctx, obj) != obj.version:
        return False
    visited = visited | {obj.id}
    for dependency in obj.dependencies:
        if not isinstance(dependency, dict):
            return False
        kind = dependency.get("type")
        if kind == "context":
            from app.db.models.platform import Engagement

            eng = await db.get(Engagement, obj.engagement_id)
            package, context = await resolved(db, ctx, eng)
            if (
                context["version"] != dependency["version"]
                or package.package_sha256 != dependency["sha256"]
            ):
                return False
        elif kind == "snapshot":
            snapshot = await db.get(ImportSnapshot, uuid.UUID(dependency["id"]))
            batch = await db.get(ImportBatch, snapshot.batch_id) if snapshot else None
            if (
                not snapshot
                or snapshot.sha256 != dependency["sha256"]
                or not batch
                or batch.status != "active"
            ):
                return False
        elif kind == "regulatory":
            from datetime import date

            from app.db.models.platform import Engagement
            from app.modules.regulatory.service import selection

            eng = await db.get(Engagement, obj.engagement_id)
            period = await db.get(FinancialPeriod, eng.period_id)
            try:
                if dependency.get("span_start") and dependency.get("span_end"):
                    from app.modules.regulatory.rule_spans import selection_over_span

                    chosen = await selection_over_span(
                        db,
                        ctx,
                        dependency["rule_key"],
                        period.start_date,
                        period.end_date,
                        date.fromisoformat(dependency["span_start"]),
                        date.fromisoformat(dependency["span_end"]),
                    )
                else:
                    chosen = await selection(
                        db,
                        ctx,
                        dependency["rule_key"],
                        period.start_date,
                        period.end_date,
                        date.fromisoformat(dependency["transaction_date"])
                        if dependency.get("transaction_date")
                        else None,
                    )
            except HTTPException as error:
                if error.status_code == 409:
                    return False  # Preserve readable history when its rule/source can no longer be qualified.
                raise
            if (
                not chosen
                or str(chosen.id) != dependency["id"]
                or chosen.sha256 != dependency["sha256"]
            ):
                return False
        elif kind == "mapping":
            if (
                await mapping_receipt(db, ctx.tenant_id, uuid.UUID(dependency["entity_id"]))
                != dependency["receipt"]
            ):
                return False
        elif kind == "mapping-profile":
            from app.modules.accounting.models import MappingProfile

            profile = await db.get(MappingProfile, uuid.UUID(dependency["id"]))
            if (
                not profile
                or not profile.approved
                or profile.version != dependency["version"]
                or fingerprint(profile.mapping) != dependency["sha256"]
            ):
                return False
        elif kind == "calculation":
            from app.modules.regulatory.reporting import engines

            model, permission, check = engines()[dependency["module"]]
            await engagement_permissions(db, ctx, obj.engagement_id, permission)
            calculated = await db.get(model, uuid.UUID(dependency["id"]))
            if (
                not calculated
                or calculated.sha256 != dependency["sha256"]
                or not await check(db, ctx, obj.engagement_id, calculated)
            ):
                return False
        elif kind == "dmtt":
            from app.modules.dmtt import service as dmtt
            from app.modules.ml.models import MLEvent

            await engagement_permissions(db, ctx, obj.engagement_id, "dmtt.read")
            item = await db.get(MLEvent, uuid.UUID(dependency["id"]))
            if (
                not item
                or item.engagement_id != obj.engagement_id
                or item.sha256 != dependency["sha256"]
                or not await dmtt.current(db, ctx, obj.engagement_id, item)
            ):
                return False
        elif kind == "event":
            parent = await db.get(IntelligenceEvent, uuid.UUID(dependency["id"]))
            if (
                not parent
                or parent.tenant_id != ctx.tenant_id
                or parent.engagement_id != obj.engagement_id
                or parent.sha256 != dependency["sha256"]
                or not await current(db, ctx, parent, visited)
            ):
                return False
        elif kind == "record":
            row = await db.get(AuditRecord, uuid.UUID(dependency["id"]))
            if (
                not row
                or row.tenant_id != ctx.tenant_id
                or row.engagement_id != obj.engagement_id
                or row.version != dependency["version"]
                or row.status == "ARCHIVED"
            ):
                return False
            if row.kind == "working-papers" and obj.body.get("action") != "file-readiness":
                from app.modules.lineage.working_papers import freshness

                if await freshness(db, ctx, row, visiting=visited) != "CURRENT":
                    return False
        elif kind == "evidence":
            version = await db.get(EvidenceVersion, uuid.UUID(dependency["id"]))
            latest = await db.scalar(
                select(func.max(EvidenceVersion.number)).where(
                    EvidenceVersion.tenant_id == ctx.tenant_id,
                    EvidenceVersion.record_id == uuid.UUID(dependency["record_id"]),
                )
            )
            if (
                not version
                or version.sha256 != dependency["sha256"]
                or version.scan_status != "CLEAN"
                or latest != version.number
            ):
                return False
        else:
            return False  # Unknown receipt schemas cannot establish provenance.
    return True


async def append(db, ctx, eng, kind, body, dependencies, request_id, prior=None):
    await restricted_permission(db, ctx, eng.id, body)
    identifier = uuid.uuid4()
    if prior:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"intelligence:{ctx.tenant_id}:{prior.root_id}"},
        )
        if await head(db, ctx, prior) != prior.version:
            raise HTTPException(409, "Result version conflict")
    package, context = await resolved(db, ctx, eng)
    if not any(d["type"] == "context" for d in dependencies):
        dependencies = [
            *dependencies,
            {"type": "context", "version": context["version"], "sha256": package.package_sha256},
        ]
    payload = {
        **body,
        "country": package.country,
        "reporting_framework": context["framework"],
        "context_version": context["version"],
        "package_version": package.package_version,
        "engine_version": "accounting-intelligence-1",
        "requires_professional_review": True,
    }
    from app.core.operations_contracts import receipt

    payload["operations_execution"] = await receipt(
        db, ctx, kind=kind, body=body, dependencies=dependencies, eng=eng
    )
    obj = IntelligenceEvent(
        id=identifier,
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eng.id,
        root_id=prior.root_id if prior else identifier,
        version=prior.version + 1 if prior else 1,
        kind=kind,
        body=payload,
        dependencies=dependencies,
        sha256=fingerprint({"body": payload, "dependencies": dependencies}),
    )
    db.add(obj)
    await db.flush()
    record(
        db,
        ctx,
        "intelligence." + kind,
        obj.id,
        request_id,
        {"engagement_id": str(eng.id), "version": obj.version, "sha256": obj.sha256},
    )
    return obj


def event_receipt(obj):
    return {
        "type": "event",
        "id": str(obj.id),
        "root_id": str(obj.root_id),
        "version": obj.version,
        "sha256": obj.sha256,
    }


async def snapshot(db, ctx, eng, identifier, comparative=False):
    await engagement_permissions(db, ctx, eng.id, "accounting.read")
    row = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.tenant_id == ctx.tenant_id,
            ImportSnapshot.id == identifier,
            ImportSnapshot.entity_id == eng.entity_id,
        )
    )
    if not row:
        raise HTTPException(404, "Authorized accounting snapshot not found")
    batch = await db.get(ImportBatch, row.batch_id)
    if not batch or batch.status != "active":
        raise HTTPException(409, "Select an active committed source snapshot")
    if comparative:
        period = await db.get(FinancialPeriod, eng.period_id)
        previous = await db.get(FinancialPeriod, row.period_id)
        if not previous or previous.end_date >= period.start_date:
            raise HTTPException(
                422, "Comparative snapshot must be from an earlier financial period"
            )
    elif row.period_id != eng.period_id:
        raise HTTPException(422, "Snapshot outside engagement period")
    return row, {
        "type": "snapshot",
        "id": str(row.id),
        "sha256": row.sha256,
        "batch_id": str(row.batch_id),
    }


async def evidence(db, ctx, eng, identifier):
    version = await db.scalar(
        select(EvidenceVersion).where(
            EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.id == identifier
        )
    )
    if not version:
        raise HTTPException(404, "Evidence version not found")
    obj = await audit.get_record(db, ctx, eng.id, version.record_id, lock=False)
    if obj.kind != "evidence":
        raise HTTPException(422, "Evidence record required")
    if version.scan_status != "CLEAN":
        raise HTTPException(
            409, "Evidence is quarantined; a functioning malware scanner must mark it clean first"
        )
    return version, {
        "type": "evidence",
        "id": str(version.id),
        "record_id": str(version.record_id),
        "number": version.number,
        "sha256": version.sha256,
    }


def read_table(
    version, kind, separator, date_format, worksheet=None, metadata=None, pdf_layout=None
):
    from app.modules.ingestion.parser import spreadsheet_rows
    from app.modules.intelligence.supporting_tables import headers, normalize

    metadata = {} if metadata is None else metadata
    supported = {
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/pdf",
    }
    if version.media_type not in supported:
        raise ValueError(
            "Supporting tables require CSV, macro-free XLSX or explicitly mapped bank PDF text"
        )
    with ObjectStore().local(version.object_key, version.object_version) as path:
        if path.stat().st_size > 10 * 1024 * 1024 or hash_file(path) != version.sha256:
            raise ValueError("Original evidence exceeds 10 MiB or failed hash verification")
        if version.media_type == "application/pdf":
            from app.modules.intelligence.pdf_tables import read_pdf_grid

            if kind != "bank" or not pdf_layout or worksheet:
                raise ValueError("PDF supporting tables require explicit bank row/column geometry")
            extracted = read_pdf_grid(path, pdf_layout, separator, date_format, version.sha256)
            metadata.update(extracted["metadata"])
            return extracted["rows"]
        if pdf_layout:
            raise ValueError("PDF layout parameters apply only to PDF evidence")
        if version.media_type == "text/csv":
            if worksheet:
                raise ValueError("Worksheet selection applies only to XLSX")
            metadata.update(source_format="CSV", worksheet=None)
            with path.open(encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                headers(reader.fieldnames or [], kind, metadata)
                return normalize(enumerate(reader, 2), kind, separator, date_format, metadata)
        metadata.update(source_format="XLSX")
        receipt: dict[str, Any] = {}
        records = spreadsheet_rows(
            path,
            worksheet,
            validate_headers=lambda fields: headers(fields, kind, metadata),
            max_rows=20000,
            receipt=receipt,
            exact_numbers=True,
        )
        try:
            return normalize(records, kind, separator, date_format, metadata, receipt)
        finally:
            records.close()


async def ledger(db, ctx, eng, source, account_ids, as_of=None, from_date=None):
    allowed = (
        await db.scalars(
            select(Account.id).where(
                Account.tenant_id == ctx.tenant_id,
                Account.entity_id == eng.entity_id,
                Account.id.in_(account_ids),
            )
        )
    ).all()
    if set(allowed) != set(account_ids):
        raise HTTPException(422, "Account selection outside authorized entity")
    query = (
        select(JournalLine, Journal.reference, Account.code)
        .join(Journal, Journal.id == JournalLine.journal_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            JournalLine.tenant_id == ctx.tenant_id,
            JournalLine.snapshot_id == source.id,
            JournalLine.account_id.in_(account_ids),
            JournalLine.opening.is_(False),
        )
        .order_by(JournalLine.id)
        .limit(20001)
    )
    if as_of is not None:
        query = query.where(JournalLine.posting_date <= as_of)
    if from_date is not None:
        query = query.where(JournalLine.posting_date >= from_date)
    rows = (await db.execute(query)).all()
    if len(rows) > 20000:
        raise HTTPException(422, "Matching population exceeds 20,000 lines; partition by account")
    return [
        {
            "id": str(line.id),
            "reference": reference,
            "account_code": code,
            "date": line.posting_date.isoformat(),
            "amount": str(line.base_debit - line.base_credit),
            "currency": line.functional_currency,
            "counterparty": line.counterparty,
            "source_record_id": str(line.source_record_id),
        }
        for line, reference, code in rows
    ]


async def compute(db, ctx, eng, operation, payload):
    data: Any = s.OPERATIONS[operation].model_validate(payload)
    if operation == "foundation-validation":
        from app.modules.intelligence.foundations import validate

        return await validate(db, ctx, eng, data)
    package, context = await resolved(db, ctx, eng)
    deps = [{"type": "context", "version": context["version"], "sha256": package.package_sha256}]
    if operation in {"workflow-source", "workflow-ledger", "workflow-vat", "country-workflow"}:
        from app.modules.country_workflows.service import compute as workflow_compute

        return await workflow_compute(db, ctx, eng, operation, data, package, deps)
    if operation in {"ocr", "source-table"}:
        version, receipt = await evidence(db, ctx, eng, data.evidence_version_id)
        deps.append(receipt)
        if operation == "source-table":
            table_metadata: dict[str, Any] = {}
            rows = await run_in_threadpool(
                read_table,
                version,
                data.table_kind,
                data.decimal_separator,
                data.date_format,
                data.worksheet,
                table_metadata,
                data.pdf_layout,
            )
            from app.modules.intelligence.reconciliation_scope import prepare as prepare_bank_scope

            rows, account_binding = prepare_bank_scope(
                rows, data.bank_account_label, data.bank_account_mapping_rationale
            )
            return {
                "bank_account_binding": account_binding,
                "evidence_version_id": str(version.id),
                "table_kind": data.table_kind,
                "table_metadata": table_metadata,
                "table_reader_version": "pdf-text-grid/1"
                if data.pdf_layout
                else "supporting-table-2",
                "contributors": sorted(
                    {str(ctx.user_id), *([str(version.created_by)] if version.created_by else [])}
                ),
                "rows": rows,
                "row_count": len(rows),
                "review_status": "UNVERIFIED",
                "source_filename": version.filename,
            }, deps
        from app.modules.intelligence.documents import extract_document

        def extract():
            with ObjectStore().local(version.object_key, version.object_version) as path:
                if hash_file(path) != version.sha256:
                    raise ValueError("Evidence hash mismatch")
                extracted = extract_document(
                    path,
                    version.media_type,
                    package.country,
                    data.model_dump(mode="json", exclude={"evidence_version_id"}),
                )
                if extracted.get("original_sha256") != version.sha256:
                    raise ValueError(
                        "Extraction receipt differs from the retained evidence version"
                    )
                return extracted

        result = await run_in_threadpool(extract)
        return {
            **result,
            "evidence_version_id": str(version.id),
            "source_filename": version.filename,
            "contributors": [str(ctx.user_id)],
        }, deps
    if operation == "lead":
        from app.modules.reconciliation.service import balance

        source, receipt = await snapshot(db, ctx, eng, data.snapshot_id)
        deps.extend(
            [
                receipt,
                {
                    "type": "mapping",
                    "entity_id": str(eng.entity_id),
                    "receipt": await mapping_receipt(db, ctx.tenant_id, eng.entity_id),
                },
            ]
        )
        values = await balance(db, ctx, source.id)
        selected = {str(i) for i in data.account_ids}
        rows = [r for r in values["lines"] if str(r["id"]) in selected]
        if {str(r["id"]) for r in rows} != selected:
            raise HTTPException(422, "Selected accounts missing from this snapshot")
        previous = {}
        if data.comparative_snapshot_id:
            prior, pr = await snapshot(db, ctx, eng, data.comparative_snapshot_id, True)
            deps.append(pr)
            previous = {r["code"]: r for r in (await balance(db, ctx, prior.id))["lines"]}
        for identifier, kind in [
            (data.materiality_id, "materiality"),
            (data.program_id, "programs"),
        ]:
            if identifier:
                obj = await audit.get_record(db, ctx, eng.id, identifier, lock=False)
                if obj.kind != kind or obj.status not in {"APPROVED", "LOCKED"}:
                    raise HTTPException(409, "Reviewed materiality/program reference required")
                deps.append({"type": "record", "id": str(obj.id), "version": obj.version})
        output = []
        for row in rows:
            comparative = (
                previous.get(row["code"], {}).get("closing")
                if data.comparative_snapshot_id
                else None
            )
            movement = None if comparative is None else row["closing"] - comparative
            output.append(
                {
                    "account_id": str(row["id"]),
                    "account_code": row["code"],
                    "name": row["name"],
                    "classification": row["classification"],
                    **{key: str(row[key]) for key in ["opening", "debit", "credit", "closing"]},
                    "prior_year": None if comparative is None else str(comparative),
                    "movement": None if movement is None else str(movement),
                    "variance_percent": None
                    if comparative in {None, Decimal(0)}
                    else str(movement / abs(comparative) * 100),
                }
            )
        totals = {
            key: str(sum((Decimal(row[key]) for row in output), Decimal(0)))
            for key in ["opening", "debit", "credit", "closing"]
        }
        return {
            "section": data.section,
            "rationale": data.rationale,
            "currency": values["functional_currency"],
            "rows": output,
            "totals": totals,
            "source_snapshot_id": str(source.id),
            "source_batch_id": str(source.batch_id),
            "mapping_receipt": deps[2]["receipt"],
            "sign_convention": "Debit positive; no assumption that every category has a debit balance",
            "review_status": "UNVERIFIED",
            "materiality_id": str(data.materiality_id) if data.materiality_id else None,
            "program_id": str(data.program_id) if data.program_id else None,
        }, deps
    if operation == "ageing":
        from app.modules.intelligence.matching import age_open_items

        source = await event(db, ctx, eng.id, data.source_id, True)
        if source.kind != "source-table" or source.body.get("table_kind") != "open-items":
            raise HTTPException(
                422,
                "An authoritative open-item source table is required; GL postings cannot be assumed unpaid",
            )
        deps.append(event_receipt(source))
        ageing_output = await run_in_threadpool(
            age_open_items,
            source.body["rows"],
            data.as_of,
            data.buckets,
            data.use_document_date_when_due_missing,
        )
        if data.control_snapshot_id:
            from app.modules.reconciliation.service import balance

            snap, sr = await snapshot(db, ctx, eng, data.control_snapshot_id)
            deps.append(sr)
            values = await balance(db, ctx, snap.id)
            selected = {str(i) for i in data.control_account_ids}
            if not selected:
                raise HTTPException(422, "Select the control accounts explicitly")
            if not selected <= {str(r["id"]) for r in values["lines"]}:
                raise HTTPException(422, "Control accounts are absent from this snapshot")
            control = sum(
                (r["closing"] for r in values["lines"] if str(r["id"]) in selected), Decimal(0)
            )
            amount = (
                ageing_output["totals_by_currency"]
                .get(values["functional_currency"], {})
                .get("total")
            )
            ageing_output["control_comparison"] = {
                "control_balance": str(control),
                "open_item_balance": amount,
                "difference": None if amount is None else str(Decimal(amount) - control),
                "note": "No cross-currency netting or automatic postings",
            }
        return {**ageing_output, "review_status": "UNVERIFIED"}, deps
    if operation == "reconciliation":
        from app.modules.intelligence.matching import reconcile_transactions

        if data.comparison_snapshot_id == data.snapshot_id:
            raise HTTPException(
                422, "Reconcile against an independent source snapshot or supporting table"
            )

        if data.reconciliation_type in {"gst", "tds-tcs"}:
            raise HTTPException(
                409,
                "India statutory reconciliation adapter is not qualified; use the generic accounting engine without legal tax conclusions",
            )
        if data.reconciliation_type == "vat" and "uae-vat" not in package.manifest.get(
            "capabilities", []
        ):
            raise HTTPException(409, "This country VAT reconciliation package is not implemented")
        source, sr = await snapshot(db, ctx, eng, data.snapshot_id)
        deps.append(sr)
        left = await ledger(db, ctx, eng, source, data.account_ids)
        if data.statement_source_id:
            other = await event(db, ctx, eng.id, data.statement_source_id, True)
            if other.kind != "source-table" or other.body["table_kind"] != "bank":
                raise HTTPException(422, "Select a bank/transaction source table")
            right = other.body["rows"]
            deps.append(event_receipt(other))
        else:
            other, orr = await snapshot(db, ctx, eng, data.comparison_snapshot_id)
            deps.append(orr)
            right = await ledger(db, ctx, eng, other, data.comparison_account_ids)
        right = [{**r, "amount": str(Decimal(r["amount"]) * data.right_sign)} for r in right]
        bank_scope = None
        if data.reconciliation_type == "bank":
            from app.modules.intelligence.reconciliation_scope import validate as bank_scope_check

            selected_code = await db.scalar(
                select(Account.code).where(
                    Account.tenant_id == ctx.tenant_id,
                    Account.entity_id == eng.entity_id,
                    Account.id == data.account_ids[0],
                )
            )
            bank_scope = bank_scope_check(
                selected_code, left, right, other.body if data.statement_source_id else None
            )
        result = await run_in_threadpool(
            reconcile_transactions,
            left,
            right,
            data.tolerance,
            data.date_tolerance,
            data.max_group_size,
        )
        return {
            **result,
            "reconciliation_type": data.reconciliation_type,
            "bank_account_scope": bank_scope,
            "parameters": data.model_dump(mode="json"),
            "review_status": "UNVERIFIED",
            "source_rows": left,
            "destination_rows": right,
        }, deps
    if operation == "vouching":
        from app.modules.intelligence.matching import compare_voucher

        sample = await db.scalar(
            select(SamplingRun).where(
                SamplingRun.tenant_id == ctx.tenant_id,
                SamplingRun.id == data.sample_id,
                SamplingRun.entity_id == eng.entity_id,
                SamplingRun.period_id == eng.period_id,
            )
        )
        if not sample:
            raise HTTPException(404, "Authorized sample not found")
        if sample.status != "completed":
            raise HTTPException(409, "Sampling must complete before vouching")
        _, sr = await snapshot(db, ctx, eng, sample.snapshot_id)
        deps.append(sr)
        entries = (
            await db.execute(
                select(JournalLine, Journal.reference)
                .join(SamplingItem, SamplingItem.line_id == JournalLine.id)
                .join(Journal, Journal.id == JournalLine.journal_id)
                .where(SamplingItem.tenant_id == ctx.tenant_id, SamplingItem.run_id == sample.id)
                .order_by(JournalLine.id)
                .limit(2001)
            )
        ).all()
        if len(entries) > 2000:
            raise HTTPException(
                422, "Vouching batch exceeds 2,000 selected items; partition the sample"
            )
        documents = []
        for identifier in data.extraction_ids:
            document = await event(db, ctx, eng.id, identifier, True)
            if document.kind != "ocr":
                raise HTTPException(422, "OCR extraction results required")
            if len(document.body.get("documents", [])) > 1:
                raise HTTPException(
                    422, "Select a single-document extraction; regenerate using its ZIP member name"
                )
            documents.append(document)
            deps.append(event_receipt(document))
        items = []
        for line, reference in entries:
            transaction = {
                "id": str(line.id),
                "reference": line.attributes.get("invoice_number") or reference,
                "reference_basis": "source invoice number"
                if line.attributes.get("invoice_number")
                else "voucher reference; may differ from invoice number",
                "counterparty": line.counterparty,
                "amount": str(abs(line.debit - line.credit)),
                "currency": line.currency,
                "date": (line.document_date or line.posting_date).isoformat(),
                "date_basis": "document date" if line.document_date else "posting-date fallback",
                "tax_amount": line.attributes.get("tax_amount"),
                "purchase_order": line.attributes.get("purchase_order"),
                "payment_reference": line.attributes.get("payment_reference"),
                "source_record_id": str(line.source_record_id),
            }
            candidates = [
                {
                    "extraction_id": str(document.id),
                    **compare_voucher(
                        transaction, document.body, data.amount_tolerance, data.date_tolerance
                    ),
                }
                for document in documents
            ]
            candidates.sort(
                key=lambda candidate: (-candidate["candidate_strength"], candidate["extraction_id"])
            )
            state = candidates[0]["machine_status"] if candidates else "NOT_MATCHED"
            if (
                len(candidates) > 1
                and candidates[0]["candidate_strength"] == candidates[1]["candidate_strength"]
            ):
                state = "AMBIGUOUS"
            items.append(
                {
                    "id": str(line.id),
                    "transaction": transaction,
                    "candidates": candidates[:10],
                    "machine_status": state,
                    "auditor_status": "NOT_REVIEWED",
                    "reviewer_status": "NOT_REVIEWED",
                }
            )
        return {
            "sample_id": str(sample.id),
            "sampling_method": sample.method,
            "seed": sample.seed,
            "selection_parameters": sample.parameters,
            "population_receipt": sample.result,
            "items": items,
            "review_status": "UNVERIFIED",
            "conclusion": "No documentary procedures or auditor conclusions are asserted by candidate generation",
        }, deps
    if operation == "mapping":
        source, sr = await snapshot(db, ctx, eng, data.snapshot_id)
        deps.extend(
            [
                sr,
                {
                    "type": "mapping",
                    "entity_id": str(eng.entity_id),
                    "receipt": await mapping_receipt(db, ctx.tenant_id, eng.entity_id),
                },
            ]
        )
        query = select(Account).where(
            Account.tenant_id == ctx.tenant_id, Account.entity_id == eng.entity_id
        )
        if data.account_ids:
            query = query.where(Account.id.in_(data.account_ids))
        accounts = (await db.scalars(query.order_by(Account.code).limit(1000))).all()
        rules = [
            ("cash", "Assets", "Cash and cash equivalents"),
            ("bank", "Assets", "Cash and cash equivalents"),
            ("receivable", "Assets", "Trade receivables"),
            ("payable", "Liabilities", "Trade payables"),
            ("capital", "Equity", "Capital"),
            ("sales", "Income", "Revenue"),
            ("revenue", "Income", "Revenue"),
            ("expense", "Expenses", "Operating expenses"),
        ]
        suggestions = []
        for account in accounts:
            proposed = next((r for r in rules if r[0] in account.name.casefold()), None)
            suggestions.append(
                {
                    "account_id": str(account.id),
                    "account_code": account.code,
                    "name": account.name,
                    "prior_classification": account.classification,
                    "mapping_version": account.mapping_version,
                    "suggested_classification": proposed[1] if proposed else None,
                    "statement_group": proposed[2] if proposed else None,
                    "evidence": "Name contains token: " + proposed[0]
                    if proposed
                    else "No deterministic suggestion",
                    "method": "NAME_TOKEN_CANDIDATE",
                    "execution_mode": "rules_baseline",
                    "feature_version": "account-name-tokens/1",
                    "confidence": None,
                    "limitation": "Account names alone do not establish reporting, tax or statutory classification",
                    "country_dimension": "Schedule III candidate requires statutory review"
                    if package.country == "IN"
                    else "IFRS presentation candidate requires reporting review",
                    "decision": "NOT_REVIEWED",
                }
            )
        return {
            "suggestions": suggestions,
            "execution_mode": "rules_baseline",
            "language_model_dependency": False,
            "snapshot_id": str(source.id),
            "review_status": "UNVERIFIED",
            "automatic_approval": False,
        }, deps
    if operation == "flow":
        source, sr = await snapshot(db, ctx, eng, data.snapshot_id)
        deps.append(sr)
        headers = (
            await db.scalars(
                select(Journal.id)
                .where(Journal.tenant_id == ctx.tenant_id, Journal.batch_id == source.batch_id)
                .order_by(Journal.id)
                .limit(data.max_journals + 1)
            )
        ).all()
        rows = (
            await db.execute(
                select(JournalLine, Account.name, Journal.reference)
                .join(Account, Account.id == JournalLine.account_id)
                .join(Journal, Journal.id == JournalLine.journal_id)
                .where(
                    JournalLine.tenant_id == ctx.tenant_id,
                    JournalLine.journal_id.in_(headers[: data.max_journals]),
                )
                .order_by(JournalLine.id)
                .limit(20001)
            )
        ).all()
        nodes = {}
        edges = []
        if len(rows) > 20000:
            raise HTTPException(
                422, "Investigation exceeds 20,000 posting lines; reduce selected journal count"
            )
        for line, name, reference in rows:
            aid = "account:" + str(line.account_id)
            jid = "journal:" + str(line.journal_id)
            nodes[aid] = {"id": aid, "label": name, "type": "account"}
            nodes[jid] = {"id": jid, "label": reference, "type": "journal"}
            edges.append(
                {
                    "id": str(line.id),
                    "source": aid if line.base_debit else jid,
                    "target": jid if line.base_debit else aid,
                    "amount": str(line.base_debit + line.base_credit),
                    "currency": line.functional_currency,
                    "source_line_id": str(line.id),
                    "source_record_id": str(line.source_record_id),
                    "counterparty": line.counterparty,
                    "posting_date": line.posting_date.isoformat(),
                }
            )
        return {
            "title": data.title,
            "note": data.note,
            "nodes": list(nodes.values()),
            "edges": edges,
            "truncated": len(headers) > data.max_journals,
            "journal_count": len(headers[: data.max_journals]),
            "meaning": "Accounting debit/credit incidence through journal nodes; not proof of cash movement, legal ownership or beneficial ownership",
            "review_status": "UNVERIFIED",
        }, deps
    raise HTTPException(422, "Unknown intelligence operation")
