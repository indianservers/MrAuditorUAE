import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.platform import LegalEntity
from app.modules.accounting import models as accounting
from app.modules.audit_execution.models import AuditRecord
from app.modules.enterprise_ai.catalogue import TOOLS
from app.modules.enterprise_ai.schemas import ToolInput, ToolResult
from app.modules.enterprise_ai.security import scope, serial, source


def ref(obj):
    return {
        "id": str(obj.id),
        "type": "record",
        "version": obj.version,
        "kind": obj.kind,
        "reference": obj.reference,
    }


async def journal_source(db, ctx, eid, identifier):
    eng = await scope(db, ctx, eid, "accounting.read")
    obj = await db.scalar(
        select(accounting.JournalLine)
        .join(accounting.ImportBatch, accounting.ImportBatch.id == accounting.JournalLine.batch_id)
        .where(
            accounting.JournalLine.tenant_id == ctx.tenant_id,
            accounting.JournalLine.entity_id == eng.entity_id,
            accounting.JournalLine.period_id == eng.period_id,
            accounting.JournalLine.id == identifier,
            accounting.ImportBatch.status == "active",
        )
    )
    if not obj:
        raise HTTPException(404, "Resource unavailable")
    return obj


async def snapshot_source(db, ctx, eid, identifier):
    eng = await scope(db, ctx, eid, "accounting.read")
    obj = await db.scalar(
        select(accounting.ImportSnapshot)
        .join(
            accounting.ImportBatch, accounting.ImportBatch.id == accounting.ImportSnapshot.batch_id
        )
        .where(
            accounting.ImportSnapshot.id == identifier,
            accounting.ImportSnapshot.tenant_id == ctx.tenant_id,
            accounting.ImportSnapshot.entity_id == eng.entity_id,
            accounting.ImportSnapshot.period_id == eng.period_id,
            accounting.ImportBatch.status == "active",
        )
    )
    if not obj:
        raise HTTPException(409, "Financial snapshot is no longer current in this engagement")
    return obj


async def calculation_source(db, ctx, eid, module, identifier):
    from app.modules.ifrs import service as ifrs
    from app.modules.tax import service as tax
    from app.modules.tp import service as tp
    from app.modules.vat import service as vat

    services = {
        "ifrs": (ifrs.run, ifrs.current_dependencies),
        "tax": (tax.run, tax.dependencies_current),
        "vat": (vat.run, vat.current),
        "tp": (tp.get_run, tp.current),
    }
    if module not in services:
        raise HTTPException(422, "Unsupported calculation source")
    permission = {"tax": "tax.profile.read"}.get(module, module + ".read")
    await scope(db, ctx, eid, permission)
    getter, current = services[module]
    obj = await getter(db, ctx, eid, identifier)
    if module == "ifrs" and obj.kind == "financials":
        await tax.financial_source(db, ctx, eid, identifier)
    if not await current(db, ctx, eid, obj):
        raise HTTPException(409, "Calculation dependencies are stale")
    return obj


async def invoke(db, ctx, eid, name, data: ToolInput):
    rows: Any
    model: Any
    if name not in TOOLS:
        raise HTTPException(422, "Unapproved tool")
    agent, permission, operation = TOOLS[name]
    eng = await scope(db, ctx, eid, permission)
    result = ToolResult(status="COMPLETED", agent=agent, tool=name)
    if operation == "case-inputs":
        from app.modules.enterprise_ai.business import inputs
        if data.use_case_id is None:
            raise HTTPException(422, "Select a UAE use case before collecting inputs")
        result.data = await inputs(db, ctx, eid, data.use_case_id, min(data.limit, 49))
        result.sources = [{"id": row["id"], "type": "record", "version": row["version"]} for row in result.data["items"]]
        if not result.sources:
            result.status = "MISSING"
        result.uncertainty.append("Required facts and approved specialist inputs must be verified; metadata collection is not calculation or legal advice")
        result.sources.append(result.data["context_receipt"])
    elif operation == "connection-health":
        connections = (await db.scalars(select(accounting.Connection).where(
            accounting.Connection.tenant_id == ctx.tenant_id, accounting.Connection.entity_id == eng.entity_id,
            accounting.Connection.period_id == eng.period_id,
        ).order_by(accounting.Connection.created_at.desc()).limit(data.limit))).all()
        items = []
        for connection in connections:
            sync = await db.scalar(select(accounting.SyncRun).where(
                accounting.SyncRun.tenant_id == ctx.tenant_id, accounting.SyncRun.connection_id == connection.id,
            ).order_by(accounting.SyncRun.created_at.desc()).limit(1))
            successful = await db.scalar(select(accounting.SyncRun).where(
                accounting.SyncRun.tenant_id == ctx.tenant_id, accounting.SyncRun.connection_id == connection.id,
                accounting.SyncRun.status == "completed",
            ).order_by(accounting.SyncRun.created_at.desc()).limit(1))
            item = {"connection_id": str(connection.id), "provider": connection.provider,
                          "configured_status": connection.status, "last_sync_status": sync.status if sync else None,
                          "last_sync_at": sync.created_at.isoformat() if sync else None,
                          "last_successful_sync_at": successful.created_at.isoformat() if successful else None,
                          "completeness": sync.completeness if sync else "not_verified",
                          "error_category": sync.error_category if sync else None,
                          "live_authority_connection": False}
            items.append(item)
            from app.modules.enterprise_ai.security import digest
            result.sources.append({"type": "connector", "id": str(connection.id), "sha256": digest(item)})
        result.data = {"items": items, "scope": "Stored connector status; no secrets or live authority probes"}
    elif operation in {"search", "excerpt"}:
        from app.modules.enterprise_ai.documents import authorized_chunk, search

        if operation == "excerpt":
            if not data.source_id:
                raise HTTPException(422, "Chunk ID required")
            rows = [await authorized_chunk(db, ctx, eid, data.source_id)]
        else:
            rows = await search(db, ctx, eid, data.query, min(data.limit, 10))
        result.data = {"items": rows, "retrieval": "keyword", "semantic": "NOT_CONFIGURED"}
        result.sources = [
            {"type": "chunk", "id": r["id"], "version": r["record_version"]} for r in rows
        ]
    elif operation == "shared-workflows":
        from app.modules.intelligence import service as intelligence
        from app.modules.intelligence.models import IntelligenceEvent

        candidates = (await db.scalars(select(IntelligenceEvent).where(
            IntelligenceEvent.tenant_id == ctx.tenant_id,
            IntelligenceEvent.engagement_id == eid,
            IntelligenceEvent.kind == "country-workflow",
        ).order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc()).limit(data.limit))).all()
        items = []
        for obj in candidates:
            try:
                await intelligence.event(db, ctx, eid, obj.id)
            except HTTPException as exc:
                if exc.status_code == 403:
                    continue
                raise
            if not await intelligence.current(db, ctx, obj):
                continue
            items.append({"id": str(obj.id), "workflow": obj.body.get("workflow"),
                          "execution_mode": "deterministic_engine", "ml_execution_mode": None,
                          "calculation_mode": "deterministic_engine",
                          "review_status": obj.body.get("review_status", "UNVERIFIED"),
                          "blocked": obj.body.get("blocked"), "exception_count": obj.body.get("exception_count"),
                          "rows_preview": obj.body.get("rows", [])[:5],
                          "row_count": len(obj.body.get("rows", [])),
                          "limitations": obj.body.get("limitations", [])})
            result.sources.append({"id": str(obj.id), "type": "intelligence", "sha256": obj.sha256})
        result.data = {"items": items, "language_model_dependency": False,
                       "professional_conclusion": False}
        result.uncertainty.append("Retained deterministic engine results; previews are bounded and review status is explicit")
    elif operation == "ledger":
        entity = await db.get(LegalEntity, eng.entity_id)
        from app.api.v1.accounting import page

        rows = await page(
            db,
            ctx,
            accounting.JournalLine,
            0,
            data.limit,
            client_id=entity.client_id,
            entity_id=eng.entity_id,
            period_id=eng.period_id,
        )
        # Targeted structured filtering, never model-authored SQL.
        if data.query:
            conditions = [
                accounting.JournalLine.tenant_id == ctx.tenant_id,
                accounting.JournalLine.entity_id == eng.entity_id,
                accounting.JournalLine.period_id == eng.period_id,
                accounting.ImportBatch.status == "active",
                accounting.JournalLine.description.icontains(data.query, autoescape=True),
            ]
            objects = (
                await db.scalars(
                    select(accounting.JournalLine)
                    .join(
                        accounting.ImportBatch,
                        accounting.ImportBatch.id == accounting.JournalLine.batch_id,
                    )
                    .where(*conditions)
                    .order_by(accounting.JournalLine.posting_date, accounting.JournalLine.id)
                    .limit(data.limit)
                )
            ).all()
            from app.api.v1.accounting import serialize

            rows = {"items": [serialize(o) for o in objects], "limit": data.limit}
        result.data = rows
        result.sources = [
            {"type": "journal", "id": r["id"], "snapshot_id": r["snapshot_id"]}
            for r in rows["items"]
        ]
        result.uncertainty = ["Bounded transaction excerpt; not a population-wide conclusion"]
    elif operation == "balance":
        from app.modules.reconciliation.service import balance

        snapshot = await db.scalar(
            select(accounting.ImportSnapshot)
            .join(
                accounting.ImportBatch,
                accounting.ImportBatch.id == accounting.ImportSnapshot.batch_id,
            )
            .where(
                accounting.ImportSnapshot.tenant_id == ctx.tenant_id,
                accounting.ImportSnapshot.entity_id == eng.entity_id,
                accounting.ImportSnapshot.period_id == eng.period_id,
                accounting.ImportBatch.status == "active",
                accounting.ImportBatch.kind.in_(["gl", "journals", "tb"]),
            )
            .order_by(accounting.ImportSnapshot.created_at.desc())
            .limit(1)
        )
        if snapshot:
            result.data = serial(await balance(db, ctx, snapshot.id))
            result.sources = [
                {"type": "snapshot", "id": str(snapshot.id), "sha256": snapshot.sha256}
            ]
            # Preserve exact deterministic totals, bound account context.
            if "lines" in result.data:
                result.data["lines"] = result.data["lines"][: data.limit]
            result.uncertainty = [
                "Deterministic existing balance service; account excerpt may be truncated"
            ]
    elif operation in {"ifrs-run", "tax-run", "vat-run"}:
        from app.modules.ifrs.models import CalculationRun
        from app.modules.tax.models import TaxRun
        from app.modules.vat.models import VATRun

        module = operation.split("-")[0]
        model = {"ifrs": CalculationRun, "tax": TaxRun, "vat": VATRun}[module]
        rows = (
            await db.scalars(
                select(model)
                .where(
                    model.tenant_id == ctx.tenant_id,
                    model.engagement_id == eid,
                    model.kind
                    == {"ifrs": "financials", "tax": "corporate-tax", "vat": "vat201"}[module],
                )
                .order_by(model.created_at.desc())
                .limit(min(data.limit, 5))
            )
        ).all()
        items = []
        for row in rows:
            try:
                obj = await calculation_source(db, ctx, eid, module, row.id)
            except HTTPException as exc:
                if exc.status_code == 409:
                    result.uncertainty.append("A stale calculation was omitted")
                    continue
                raise
            values = serial(obj.results)
            if len(json.dumps(values)) > 12000:
                values = {"limitation": "Open original calculation for full tables"}
            items.append(
                {"id": str(obj.id), "kind": obj.kind, "results": values, "sha256": obj.sha256}
            )
            result.sources.append({"id": str(obj.id), "type": "run", "module": module})
        result.data = {"items": items}
    elif operation in {"inference", "model", "dmtt-run"}:
        from app.modules.ml.models import MLEvent
        from app.modules.ml.service import get

        kind = "dmtt_calculation" if operation == "dmtt-run" else operation
        rows = (
            await db.scalars(
                select(MLEvent)
                .where(
                    MLEvent.tenant_id == ctx.tenant_id,
                    MLEvent.engagement_id == eid,
                    MLEvent.kind == kind,
                )
                .order_by(MLEvent.created_at.desc())
                .limit(min(data.limit, 5))
            )
        ).all()
        items = []
        for obj in rows:
            if operation != "dmtt-run":
                await get(db, ctx, obj.id)
                from app.modules.lineage.freshness import require_ml_current

                try:
                    await require_ml_current(db, ctx, obj)
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
                    result.uncertainty.append("A stale ML result was omitted; regenerate from current sources")
                    continue
                value = {
                    k: v
                    for k, v in obj.body.items()
                    if k
                    not in {
                        "artifacts",
                        "dataset",
                        "model_artifacts",
                        "object_key",
                        "object_version",
                    }
                }

                # No private object locators in nested model metadata.
                def scrub(v):
                    if isinstance(v, dict):
                        return {
                            k: scrub(x)
                            for k, x in v.items()
                            if k not in {"object_key", "object_version", "credential_reference"}
                        }
                    return [scrub(x) for x in v[:5]] if isinstance(v, list) else v

                value = scrub(value)
                value.setdefault("execution_mode", "unavailable")
                result.sources.append({"id": str(obj.id), "type": "ml"})
            else:
                from app.modules.enterprise_ai.security import validate_dependencies

                await validate_dependencies(db, ctx, eid, obj.body.get("dependencies", []))
                value = obj.body.get("results", {})
                result.sources.extend(obj.body.get("dependencies", []))
            items.append({"id": str(obj.id), "kind": kind, "facts": value})
        result.data = {"items": items, "professional_conclusion": False}
        result.uncertainty.append("Existing stored results only; ML scores do not establish fraud")
    elif operation in {"analytics", "reconciliation"}:
        from app.api.v1.accounting import page

        model = (
            accounting.AnalyticsRun if operation == "analytics" else accounting.ReconciliationRun
        )
        result.data = await page(
            db, ctx, model, 0, min(data.limit, 5), entity_id=eng.entity_id, period_id=eng.period_id
        )
        result.data["items"] = [
            row for row in result.data["items"] if row.get("status") == "completed"
        ]
        current_items = []
        for row in result.data["items"]:
            try:
                snapshot = await snapshot_source(db, ctx, eid, uuid.UUID(row["snapshot_id"]))
            except HTTPException:
                result.uncertainty.append(
                    "A historical run on a superseded financial population was omitted"
                )
                continue
            current_items.append(row)
            result.sources.append(
                {"type": "snapshot", "id": str(snapshot.id), "sha256": snapshot.sha256}
            )
        result.data["items"] = current_items
        result.uncertainty.append("Stored run summaries; open original exceptions for testing")
    elif operation == "alerts":
        from app.modules.grc.models import MonitorAlert
        from app.modules.grc.service import owner_scoped

        if await owner_scoped(db, ctx, eid):
            raise HTTPException(403, "Professional monitoring access required")
        rows = (
            await db.scalars(
                select(MonitorAlert)
                .where(MonitorAlert.tenant_id == ctx.tenant_id, MonitorAlert.engagement_id == eid)
                .order_by(MonitorAlert.created_at.desc())
                .limit(data.limit)
            )
        ).all()
        result.data = {
            "items": [{"id": str(o.id), "rule": o.rule_key, "signals": o.signals} for o in rows]
        }
        result.uncertainty.append("Monitoring candidates require source-linked investigation")
    elif operation == "quality":
        result.data = {
            "professional_approval": False,
            "check": "Source validation occurs before every step and result read",
        }
    else:
        kinds = (
            ["ifrs-revenue", "ifrs-disclosure", "ifrs-note", "ifrs-lease"]
            if operation == "ifrs-records"
            else [operation]
        )
        ids = (
            await db.scalars(
                select(AuditRecord.id)
                .where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    AuditRecord.kind.in_(kinds),
                    AuditRecord.status.in_(["APPROVED", "LOCKED"]),
                )
                .order_by(AuditRecord.created_at.desc())
                .limit(data.limit)
            )
        ).all()
        items = []
        for identifier in ids:
            try:
                obj = await source(db, ctx, eid, identifier)
            except HTTPException as exc:
                if exc.status_code == 403:
                    result.uncertainty.append("Restricted source omitted")
                    continue
                raise
            body = {
                k: v
                for k, v in obj.body.items()
                if k not in {"owner_id", "team_ids", "review_approvers"}
            }
            if len(json.dumps(body)) > 8000:
                body = {"limitation": "Open original approved source for full detail"}
            items.append(
                {"id": str(obj.id), "reference": obj.reference, "kind": obj.kind, "facts": body}
            )
            result.sources.append(ref(obj))
        result.data = {"items": items}
    if not result.data or result.data.get("items") == []:
        result.status = "MISSING"
        result.uncertainty.append("No authorized current source available for this step")
    # Bound all handoffs independently of ledger size or evidence size.
    if len(json.dumps(serial(result.data))) > 24000:
        result.data = {"limitation": "Result exceeds context limit; use the source workspace"}
        result.status = "LIMITED"
    return result
