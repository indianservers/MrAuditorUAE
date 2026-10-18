import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select

from app.core.dependencies import DB, Context, require
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.audit_execution.schemas import BODIES as AUDIT_BODIES
from app.modules.audit_execution.schemas import RecordInput
from app.modules.ifrs.calculations import serial
from app.modules.vat import calculations as calc
from app.modules.vat import schemas as s
from app.modules.vat import service
from app.modules.vat.adapters import SandboxASP
from app.modules.vat.catalogue import AI_TASKS, KINDS, SOURCES
from app.modules.vat.models import DemoDataset, VATRun

for name, schema in s.BODIES.items():
    AUDIT_BODIES["vat-" + name] = schema
    PREPARE["vat-" + name], APPROVE["vat-" + name] = KINDS[name]
router = APIRouter(prefix="/vat", tags=["VAT and e-invoicing"])
Actor = Annotated[Context, Depends(require(""))]


@router.get("/legislation")
async def legislation(ctx: Annotated[Context, Depends(require("vat.read"))]):
    return {
        "items": [{"id": key, **value} for key, value in SOURCES.items()],
        "automatically_approved": False,
        "as_of": "2026-10-18",
    }


@router.get("/demo-status")
async def demo_status(db: DB, ctx: Annotated[Context, Depends(require("vat.read"))]):
    rows = (
        await db.scalars(select(DemoDataset).where(DemoDataset.tenant_id == ctx.tenant_id))
    ).all()
    # The UI only needs a synthetic banner. Never expose other engagements' manifest data.
    return {
        "items": [
            {"id": str(x.id), "seed_version": x.seed_version, "status": x.status, "synthetic": True}
            for x in rows
        ]
    }


@router.get("/engagements/{eid}/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    eng = await audit.engagement(db, ctx, eid, "vat.read")
    from app.modules.audit_execution.access import engagement_permissions

    permissions, roles = await engagement_permissions(db, ctx, eid, "vat.read")
    return {
        "engagement": audit.serialize(eng),
        "permissions": sorted(permissions),
        "roles": sorted(roles),
        "schemas": {key: body.model_json_schema() for key, body in s.BODIES.items()},
        "ai_tasks": AI_TASKS,
    }


@router.get("/engagements/{eid}/records/{kind}")
async def records(
    eid: uuid.UUID,
    kind: str,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = Query("", max_length=200),
    direction: str | None = None,
):
    await audit.engagement(db, ctx, eid, "vat.read")
    if kind not in KINDS and kind != "ai":
        raise HTTPException(404, "Unknown VAT area")
    conditions = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "vat-" + kind,
        or_(
            AuditRecord.title.icontains(search, autoescape=True),
            AuditRecord.body["invoice_number"].astext.icontains(search, autoescape=True),
            AuditRecord.body["supplier_name"].astext.icontains(search, autoescape=True),
        ),
    ]
    if direction:
        if direction not in {"sale", "purchase"}:
            raise HTTPException(422, "Unknown VAT direction")
        conditions.append(AuditRecord.body["direction"].astext == direction)
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(*conditions)
            .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [audit.serialize(x) for x in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/records/{kind}", status_code=201)
async def create(
    eid: uuid.UUID, kind: str, data: RecordInput, db: DB, ctx: Actor, request: Request
):
    if kind not in KINDS:
        raise HTTPException(422, "Unknown editable VAT kind")
    return await audit.create(db, ctx, eid, "vat-" + kind, data, request.state.request_id)


@router.post("/engagements/{eid}/invoices/{rid}/validate")
async def validate_invoice(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "vat.read")
    obj, _, value = await service.invoice_result(db, ctx, eid, rid)
    return {"id": str(obj.id), "version": obj.version, **serial(value)}


@router.post("/engagements/{eid}/invoices/{rid}/extract/{evidence_id}", status_code=201)
async def extract_document(
    eid: uuid.UUID, rid: uuid.UUID, evidence_id: uuid.UUID, db: DB, ctx: Actor
):
    from decimal import Decimal, InvalidOperation

    from starlette.concurrency import run_in_threadpool

    from app.modules.lineage.storage import ObjectStore
    from app.modules.vat.documents import extract_text_pdf

    await audit.engagement(db, ctx, eid, "vat.invoice.prepare", True)
    obj, inv, _ = await service.invoice_result(db, ctx, eid, rid)
    if evidence_id not in inv.evidence_record_ids and evidence_id != inv.ocr_evidence_id:
        raise HTTPException(422, "Document must be linked to this source invoice")
    evidence = await service.evidence(db, ctx, eid, evidence_id)
    latest = await db.scalar(
        select(EvidenceVersion)
        .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == evidence_id)
        .order_by(EvidenceVersion.number.desc())
        .limit(1)
    )
    if not latest or latest.media_type != "application/pdf":
        raise HTTPException(422, "Clean approved PDF evidence required")
    try:
        with ObjectStore().local(latest.object_key, latest.object_version) as path:
            extracted = await run_in_threadpool(extract_text_pdf, path)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from None
    comparisons = []
    for field, value in extracted["fields"].items():
        expected = getattr(inv, field)
        try:
            equal = (
                Decimal(value.replace(",", "")) == expected
                if field.startswith("declared_")
                else value == expected
            )
        except InvalidOperation:
            equal = False
        comparisons.append(
            {"field": field, "extracted": value, "source": str(expected), "matches": equal}
        )
    extracted["comparisons"] = comparisons
    extracted["uncertainties"] = [
        "Text-layer extraction can omit or misidentify fields; no visual/OCR verification performed"
    ]
    _, p, _ = await service.profile_inputs(db, ctx, eid, inv.profile_id)
    saved = await service.save(
        db,
        ctx,
        eid,
        "invoice-extraction",
        p,
        {"invoice_id": str(rid), "evidence_id": str(evidence_id), "document_sha256": latest.sha256},
        [service.dep(obj), service.dep(evidence)],
        extracted,
        obj.id,
    )
    return {"id": str(saved.id), "results": saved.results}


@router.post("/engagements/{eid}/computations/{pid}", status_code=201)
async def compute(eid: uuid.UUID, pid: uuid.UUID, db: DB, ctx: Actor):
    try:
        obj = await service.compute(db, ctx, eid, pid)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None
    return {
        "id": str(obj.id),
        "kind": obj.kind,
        "sha256": obj.sha256,
        "results": {k: v for k, v in obj.results.items() if k != "reconciliations"},
    }


@router.get("/engagements/{eid}/runs")
async def runs(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await audit.engagement(db, ctx, eid, "vat.read")
    conditions = [VATRun.tenant_id == ctx.tenant_id, VATRun.engagement_id == eid]
    rows = (
        await db.scalars(
            select(VATRun)
            .where(*conditions)
            .order_by(VATRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {"id": str(x.id), "kind": x.kind, "sha256": x.sha256, "created_at": x.created_at}
            for x in rows
        ],
        "total": await db.scalar(select(func.count()).select_from(VATRun).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }


@router.get("/engagements/{eid}/runs/{rid}")
async def result(
    eid: uuid.UUID,
    rid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    obj = await service.run(db, ctx, eid, rid)
    rows = obj.results.get("reconciliations", [])
    return {
        "id": str(obj.id),
        "kind": obj.kind,
        "sha256": obj.sha256,
        "dependencies_current": await service.current(db, ctx, eid, obj),
        "results": {
            **obj.results,
            "reconciliations": rows[offset : offset + limit],
            "exceptions": obj.results.get("exceptions", [])[:100],
        },
        "rows_total": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/assessments/{rid}", status_code=201)
async def assess(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "vat.calculate", True)
    obj = await service.record(db, ctx, eid, rid, approved=True)
    _, p, selected = await service.profile_inputs(db, ctx, eid, uuid.UUID(obj.body["profile_id"]))
    if obj.kind == "vat-einvoicing":
        value = calc.readiness(s.EInvoicing.model_validate(service.clean(obj.body)), p.legal_as_of)
    elif obj.kind == "vat-recovery":
        data = s.Recovery.model_validate(service.clean(obj.body))
        value = {
            "recoverable": calc.money(data.total_input * data.approved_recovery_percentage),
            "adjustment": calc.money(
                data.total_input * data.approved_recovery_percentage - data.previously_recovered
            ),
            "state": "ASSESSED" if data.statutory_conditions_confirmed else "REVIEW_REQUIRED",
            "scope": "Manual reviewed allocation/CAS methodology; separately approved adjustment required for return impact",
        }
    else:
        raise HTTPException(422, "No standalone assessment for this kind")
    deps = [service.dep(obj)] + [service.dep(x) for x, _ in selected.values()]
    for evidence_id in service.evidence_ids(obj.body):
        deps.append(service.dep(await service.evidence(db, ctx, eid, evidence_id)))
    saved = await service.save(db, ctx, eid, obj.kind, p, obj.body, deps, value, obj.id)
    return {"id": str(saved.id), "results": saved.results}


@router.post("/engagements/{eid}/sandbox", status_code=201)
async def sandbox(eid: uuid.UUID, data: s.SandboxRequest, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "einvoice.sandbox", True)
    original = await db.scalar(
        select(VATRun).where(
            VATRun.tenant_id == ctx.tenant_id,
            VATRun.engagement_id == eid,
            VATRun.kind == "asp-sandbox",
            VATRun.idempotency_key == data.idempotency_key,
        )
    )
    if original:
        if original.inputs != data.model_dump(mode="json"):
            raise HTTPException(409, "Idempotency key already used for different payload")
        return {"id": str(original.id), "results": original.results, "replayed": True}
    obj, inv, value = await service.invoice_result(db, ctx, eid, data.invoice_id)
    if obj.status not in service.APPROVED or not value["valid"]:
        raise HTTPException(409, "Approved validated invoice required for sandbox")
    _, p, _ = await service.profile_inputs(db, ctx, eid, inv.profile_id)
    payload = {
        "invoice_number": inv.invoice_number,
        "currency": "AED",
        "document_type": inv.document_type,
        "net": str(value["net"]),
        "tax": str(value["tax"]),
        "gross": str(value["gross"]),
        "buyer_endpoint_id": data.buyer_endpoint_id,
        "supplier_endpoint_id": data.supplier_endpoint_id,
        "schema_version": data.schema_version,
    }
    outcome = await SandboxASP().send(payload, data.simulate)
    saved = await service.save(
        db,
        ctx,
        eid,
        "asp-sandbox",
        p,
        data.model_dump(mode="json"),
        [service.dep(obj)],
        {**outcome, "payload": payload},
        obj.id,
        data.idempotency_key,
    )
    return {"id": str(saved.id), "results": saved.results, "replayed": False}


@router.get("/engagements/{eid}/runs/{rid}/export/json")
async def export(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor, request: Request):
    await audit.engagement(db, ctx, eid, "vat.export")
    obj = await service.run(db, ctx, eid, rid)
    approval = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.kind == "vat-return",
            AuditRecord.status.in_(service.APPROVED),
            AuditRecord.body["run_id"].astext == str(rid),
        )
    )
    from app.modules.audit_log.service import record as event

    approved = bool(approval and await service.current(db, ctx, eid, obj))
    event(db, ctx, "vat.export", rid, request.state.request_id, {"approved": approved})
    return Response(
        json.dumps(
            {
                "id": str(obj.id),
                "sha256": obj.sha256,
                "approved": approved,
                "inputs": obj.inputs,
                "dependencies": obj.dependencies,
                "results": obj.results,
            }
        ),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="AuditOS-VAT-{rid}.json"',
            "Cache-Control": "no-store",
        },
    )
