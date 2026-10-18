import uuid
from datetime import date
from typing import Annotated, Literal
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import DB, Context, require
from app.modules.accounting.models import ImportBatch, JournalLine
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import BODIES as AUDIT_BODIES
from app.modules.audit_execution.schemas import RecordInput
from app.modules.audit_log.service import record as event
from app.modules.ifrs.calculations import serial
from app.modules.tp import schemas as s
from app.modules.tp import service
from app.modules.tp.catalogue import AI_TASKS, KINDS, SOURCES
from app.modules.tp.imports import parse
from app.modules.tp.models import Observation, TPRun
from app.modules.tp.tax_bridge import TaxLink

for kind, schema in s.BODIES.items():
    AUDIT_BODIES["tp-" + kind] = schema
for kind, (prepare, approve) in KINDS.items():
    PREPARE["tp-" + kind] = prepare
    APPROVE["tp-" + kind] = approve
Actor = Annotated[Context, Depends(require(""))]
router = APIRouter(prefix="/tp", tags=["Transfer pricing"])


@router.get("/client-documents")
async def client_documents(db: DB, ctx: Annotated[Context, Depends(require("portal.read"))]):
    from app.modules.tp.publication import authorized_releases

    rows = await authorized_releases(db, ctx)
    return {
        "items": [
            {
                "id": str(x.id),
                "title": x.title,
                "document_type": x.body["client_document"]["document_type"],
                "annual_version": x.body["client_document"]["annual_version"],
                "issued_at": x.body["client_document"]["issued_at"],
                "status": "ISSUED",
            }
            for x in rows
        ],
        "scope": "Explicitly issued immutable client-safe PDF versions only",
    }


@router.get("/client-documents/{rid}/download")
async def client_document_download(
    rid: uuid.UUID,
    db: DB,
    ctx: Annotated[Context, Depends(require("portal.read"))],
    request: Request,
):
    from app.modules.tp.publication import authorized_releases, download

    rows = await authorized_releases(db, ctx, rid)
    if not rows:
        raise HTTPException(404, "Issued document not found")
    payload = await run_in_threadpool(download, rows[0].body["client_document"])
    event(db, ctx, "tp.client_document.downloaded", rid, request.state.request_id)
    return Response(
        payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="AuditOS-TP-issued-{rid}.pdf"'},
    )


@router.get("/legislation")
async def legislation(ctx: Annotated[Context, Depends(require("tp.read"))]):
    return {
        "items": [{"id": key, **value} for key, value in SOURCES.items()],
        "verified_as_of": "2026-10-18",
        "automatically_approved": False,
    }


@router.get("/engagements/{eid}/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    eng = await audit.engagement(db, ctx, eid, "tp.read")
    permissions, roles = await engagement_permissions(db, ctx, eid, "tp.read")
    counts: dict[str, dict[str, int]] = {}
    for kind, status, count in (
        await db.execute(
            select(AuditRecord.kind, AuditRecord.status, func.count())
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind.like("tp-%"),
            )
            .group_by(AuditRecord.kind, AuditRecord.status)
        )
    ).all():
        counts.setdefault(kind, {})[status] = count
    return {
        "record_counts": counts,
        "engagement": audit.serialize(eng),
        "permissions": sorted(permissions),
        "roles": sorted(roles),
        "schemas": {key: value.model_json_schema() for key, value in s.BODIES.items()},
        "ai_tasks": AI_TASKS,
        "methodology_version": "auditos-tp/1.0",
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
    status: str | None = None,
    sort: Literal["title", "-created_at"] = "-created_at",
):
    await audit.engagement(db, ctx, eid, "tp.read")
    if kind not in KINDS and kind != "ai":
        raise HTTPException(404, "Unknown TP workpaper")
    where = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "tp-" + kind,
        AuditRecord.title.icontains(search, autoescape=True),
    ]
    if status:
        where.append(AuditRecord.status == status)
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(*where)
            .order_by(
                AuditRecord.title if sort == "title" else AuditRecord.created_at.desc(),
                AuditRecord.id,
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [audit.serialize(x) for x in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*where)),
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/records/{kind}", status_code=201)
async def create(
    eid: uuid.UUID, kind: str, data: RecordInput, db: DB, ctx: Actor, request: Request
):
    if kind not in s.BODIES:
        raise HTTPException(404, "Unsupported TP source")
    return await audit.create(db, ctx, eid, "tp-" + kind, data, request.state.request_id)


@router.post("/engagements/{eid}/datasets/{rid}/import", status_code=201)
async def import_comparables(
    eid: uuid.UUID,
    rid: uuid.UUID,
    db: DB,
    ctx: Actor,
    file: Annotated[UploadFile, File()],
    request: Request,
):
    await audit.engagement(db, ctx, eid, "tp.benchmark.import", True)
    dataset, license = await service.licensed_dataset(db, ctx, eid, rid)
    data = await file.read(10 * 1024 * 1024 + 1)
    try:
        rows = await run_in_threadpool(parse, data, file.filename or "")
    except (ValueError, UnicodeError, KeyError, BadZipFile, ParseError, StopIteration) as exc:
        raise HTTPException(422, str(exc)) from None
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": str(ctx.tenant_id) + str(rid)},
    )
    existing = (
        await db.scalars(
            select(Observation).where(
                Observation.tenant_id == ctx.tenant_id, Observation.dataset_id == rid
            )
        )
    ).all()
    if existing:
        if {(x.company_key, x.fiscal_year, x.sha256) for x in existing} == {
            (x.company_key, x.fiscal_year, digest) for x, digest in rows
        }:
            return {"imported": len(existing), "replayed": True}
        raise HTTPException(409, "Dataset version is immutable; import a new dataset record")
    values = []
    for item, digest in rows:
        if license.license_type == "synthetic" and "synthetic" not in item.name.lower():
            raise HTTPException(422, "Synthetic observations must be named explicitly")
        if item.observation_date > license.observation_date:
            raise HTTPException(422, "Observation is later than dataset snapshot")
        base = item.model_dump()
        facts = {
            key: serial(base.pop(key))
            for key in [
                "activity",
                "independence",
                "related_party_exposure",
                "extraordinary_events",
                "observation_date",
                "tenor",
                "credit_risk",
                "security",
                "seniority",
                "rate_type",
            ]
        }
        values.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": ctx.tenant_id,
                "created_by": ctx.user_id,
                "engagement_id": eid,
                "dataset_id": rid,
                **base,
                "facts": facts,
                "sha256": digest,
            }
        )
    for index in range(0, len(values), 250):
        await db.execute(insert(Observation), values[index : index + 250])
    event(
        db,
        ctx,
        "tp.observations.imported",
        rid,
        request.state.request_id,
        {"rows": len(values), "dataset_version": license.data_version},
    )
    return {"imported": len(values), "replayed": False, "dataset_version": license.data_version}


@router.get("/engagements/{eid}/observations")
async def observations(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    dataset_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    country: str | None = None,
    industry: str | None = None,
    search: str = Query("", max_length=200),
):
    await audit.engagement(db, ctx, eid, "tp.read")
    await service.licensed_dataset(db, ctx, eid, dataset_id)
    where = [
        Observation.tenant_id == ctx.tenant_id,
        Observation.engagement_id == eid,
        Observation.dataset_id == dataset_id,
        Observation.name.icontains(search, autoescape=True),
    ]
    if country:
        where.append(Observation.country == country)
    if industry:
        where.append(Observation.industry == industry)
    rows = (
        await db.scalars(
            select(Observation)
            .where(*where)
            .order_by(Observation.company_key, Observation.fiscal_year)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [audit.serialize(x) for x in rows],
        "total": await db.scalar(select(func.count()).select_from(Observation).where(*where)),
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/calculate/{rid}", status_code=201)
async def calculate(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor, background: bool = False):
    if background:
        await audit.engagement(db, ctx, eid, "tp.calculate", True)
        await service.record(db, ctx, eid, rid, approved=True)
        import hashlib
        import json

        versions = (
            await db.execute(
                select(AuditRecord.id, AuditRecord.version, AuditRecord.status)
                .where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    or_(AuditRecord.kind.like("tp-%"), AuditRecord.kind.like("ifrs-%")),
                )
                .order_by(AuditRecord.id)
            )
        ).all()
        signature = hashlib.sha256(
            json.dumps([(str(a), b, c) for a, b, c in versions]).encode()
        ).hexdigest()
        from app.workers.accounting import submit

        return await submit(
            db,
            ctx,
            "tp.calculate",
            {"engagement_id": str(eid), "record_id": str(rid), "source_signature": signature},
            "tp-background",
        )
    try:
        obj = await service.calculate(db, ctx, eid, rid)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None
    return {
        "id": str(obj.id),
        "kind": obj.kind,
        "sha256": obj.sha256,
        "results": {
            key: value
            for key, value in obj.results.items()
            if key not in {"population", "intervals", "rows", "company_results", "trace"}
        },
    }


@router.post("/engagements/{eid}/matrix/{pid}", status_code=201)
async def matrix(eid: uuid.UUID, pid: uuid.UUID, db: DB, ctx: Actor):
    obj = await service.matrix(db, ctx, eid, pid)
    return {
        "id": str(obj.id),
        "kind": obj.kind,
        "sha256": obj.sha256,
        "results": {
            "rows_total": len(obj.results["rows"]),
            **{k: v for k, v in obj.results.items() if k != "rows"},
        },
    }


@router.post("/engagements/{eid}/jobs/{jid}/{operation}")
async def control_job(
    eid: uuid.UUID,
    jid: uuid.UUID,
    operation: Literal["retry", "cancel"],
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.api.v1.jobs import JobOut, cancel, retry
    from app.db.models.platform import BackgroundJob
    from app.modules.accounting.service import scoped

    await audit.engagement(db, ctx, eid, "tp.calculate", True)
    job = await scoped(db, ctx, BackgroundJob, jid, True)
    if job.job_type != "tp.calculate" or job.payload.get("engagement_id") != str(eid):
        raise HTTPException(404, "TP calculation job not found in this engagement")
    # Existing controls still enforce original owner, task permission and state.
    # The TP operation grant replaces the general diagnostic-jobs grant here.
    event(db, ctx, "tp.job." + operation, jid, request.state.request_id)
    result = await (retry(jid, db, ctx) if operation == "retry" else cancel(jid, db, ctx))
    return JobOut.model_validate(result)


@router.get("/engagements/{eid}/runs")
async def runs(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await audit.engagement(db, ctx, eid, "tp.read")
    where = [TPRun.tenant_id == ctx.tenant_id, TPRun.engagement_id == eid]
    rows = (
        await db.scalars(
            select(TPRun)
            .where(*where)
            .order_by(TPRun.created_at.desc(), TPRun.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(x.id),
                "kind": x.kind,
                "record_id": str(x.record_id) if x.record_id else None,
                "created_at": x.created_at,
            }
            for x in rows
        ],
        "total": await db.scalar(select(func.count()).select_from(TPRun).where(*where)),
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
    run = await service.get_run(db, ctx, eid, rid)
    result = dict(run.results)
    counts = {}
    for key in [
        "rows",
        "intervals",
        "population",
        "company_results",
        "trace",
        "missing_observation_ids",
    ]:
        if key in result and isinstance(result[key], list):
            counts[key] = len(result[key])
            result[key] = result[key][offset : offset + limit]
    return {
        "id": str(run.id),
        "kind": run.kind,
        "sha256": run.sha256,
        "dependencies_current": await service.current(db, ctx, eid, run),
        "results": result,
        "row_counts": counts,
        "offset": offset,
        "limit": limit,
    }


@router.get("/engagements/{eid}/graph/{pid}")
async def graph(eid: uuid.UUID, pid: uuid.UUID, db: DB, ctx: Actor, on: date | None = None):
    from datetime import date

    await audit.engagement(db, ctx, eid, "tp.relationship.read")
    await service.profile_inputs(db, ctx, eid, pid)
    when = on or date.today()
    parties = await service.selected(db, ctx, eid, "party", pid)
    edges = [
        x
        for x in await service.selected(db, ctx, eid, "relationship", pid)
        if date.fromisoformat(x.body["effective_from"]) <= when
        and (not x.body.get("effective_to") or date.fromisoformat(x.body["effective_to"]) >= when)
    ]
    from app.modules.tp.relationships import ownership_candidates

    try:
        candidates = ownership_candidates([{"id": str(x.id), **x.body} for x in edges])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        **candidates,
        "nodes": [
            {
                "id": str(x.id),
                "name": x.body["name"],
                "party_type": x.body["party_type"],
                "jurisdiction": x.body["jurisdiction"],
                "entity_id": x.body.get("entity_id"),
            }
            for x in parties
        ],
        "edges": [{"id": str(x.id), **x.body} for x in edges],
        "as_of": str(when),
        "scope": "Approved dated factual relationships; path ownership is a candidate, never a universal legal determination",
    }


@router.get("/engagements/{eid}/candidates/{pid}")
async def candidates(
    eid: uuid.UUID,
    pid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    eng = await audit.engagement(db, ctx, eid, "tp.relationship.read")
    await service.profile_inputs(db, ctx, eid, pid)
    parties = await service.selected(db, ctx, eid, "party", pid)
    names = {x.body["name"].strip().lower() for x in parties}
    names.update(
        x.body.get("identifiers", "").strip().lower() for x in parties if x.body.get("identifiers")
    )
    name_match = func.lower(func.trim(JournalLine.counterparty)).in_(sorted(names))
    keyword_match = JournalLine.description.op("~*")(
        r"\m(intercompany|affiliate|related.party|director|royalty|treasury|management.fee|loan)\M"
    )
    where = [
        JournalLine.tenant_id == ctx.tenant_id,
        JournalLine.entity_id == eng.entity_id,
        JournalLine.period_id == eng.period_id,
        ImportBatch.status == "active",
        or_(name_match, keyword_match),
    ]
    query = (
        select(JournalLine, name_match.label("name_match"))
        .join(ImportBatch, ImportBatch.id == JournalLine.batch_id)
        .where(*where)
    )
    rows = (
        await db.execute(
            query.order_by(JournalLine.posting_date, JournalLine.id).offset(offset).limit(limit)
        )
    ).all()
    total = await db.scalar(
        select(func.count())
        .select_from(JournalLine)
        .join(ImportBatch, ImportBatch.id == JournalLine.batch_id)
        .where(*where)
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "journal_id": str(row.journal_id),
                "posting_date": str(row.posting_date),
                "counterparty": row.counterparty,
                "description": row.description,
                "base_amount": str(row.base_debit - row.base_credit),
                "source_amount": str(row.debit - row.credit),
                "source_currency": row.currency,
                "exchange_rate": str(row.exchange_rate),
                "currency": row.functional_currency,
                "reason": "exact approved party name/identifier"
                if match
                else "descriptive keyword only",
                "confidence": "candidate only",
                "automatic_classification": False,
            }
            for row, match in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
        "scope": "Exact-name and keyword candidates only; identifiers are compared literally; no inferred legal determination",
    }


@router.post("/engagements/{eid}/runs/{rid}/tax-adjustment", status_code=201)
async def link_tax(
    eid: uuid.UUID, rid: uuid.UUID, data: TaxLink, db: DB, ctx: Actor, request: Request
):
    await audit.engagement(db, ctx, eid, "tp.review", True)
    from app.modules.tp.tax_bridge import create_adjustment

    return await create_adjustment(db, ctx, eid, rid, data.model_dump(), request.state.request_id)


@router.get("/engagements/{eid}/runs/{rid}/export/{format}")
async def export(
    eid: uuid.UUID,
    rid: uuid.UUID,
    format: Literal["json", "pdf", "docx", "xlsx"],
    db: DB,
    ctx: Actor,
    request: Request,
):
    await audit.engagement(db, ctx, eid, "tp.report.export")
    run = await service.get_run(db, ctx, eid, rid)
    await service.export_allowed(db, ctx, eid, run)
    from app.modules.tp.exports import render

    approvals = await service.released(db, ctx, eid, run)
    payload, media_type = await run_in_threadpool(render, run, format, bool(approvals))
    event(
        db,
        ctx,
        "tp.export",
        rid,
        request.state.request_id,
        {"format": format, "released": bool(approvals), "sha256": run.sha256},
    )
    return Response(
        payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="AuditOS-TP-{rid}.{format}"'},
    )
