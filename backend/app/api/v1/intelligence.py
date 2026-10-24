"""Connected accounting/document workflows using immutable source and result versions."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field, ValidationError
from sqlalchemy import select

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.schemas import RecordInput, RecordPatch, Source
from app.modules.audit_log.service import record
from app.modules.intelligence import jobs, service
from app.modules.intelligence import schemas as s
from app.modules.intelligence.models import IntelligenceEvent, IntelligenceJob

router = APIRouter(prefix="/intelligence", tags=["Accounting intelligence"])


@router.get("/capabilities")
async def capabilities(ctx: Actor):
    return {
        "engine_version": "accounting-intelligence-1",
        "operations": list(s.OPERATIONS),
        "lead_sections": s.SECTIONS,
        "ocr": {
            "providers": ["pdfium-text", "rapidocr-local"],
            "external_document_transfer": False,
            "max_pages": 20,
            "max_bytes": 25 * 1024 * 1024,
            "requires_clean_evidence": True,
            "scores_calibrated": False,
        },
        "limits": {
            "vouching_items": 2000,
            "documents_per_run": 200,
            "matching_rows_per_side": 20000,
            "graph_journals": 10000,
        },
        "statutory_qualification": False,
    }


@router.post("/engagements/{eid}/jobs", status_code=202)
async def submit(
    eid: uuid.UUID,
    data: s.JobInput,
    db: DB,
    ctx: Actor,
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
):
    return audit.serialize(
        await jobs.submit(db, ctx, eid, data, idempotency_key, request.state.request_id)
    )


@router.get("/engagements/{eid}/jobs")
async def job_list(eid: uuid.UUID, db: DB, ctx: Actor, limit: int = Query(50, ge=1, le=100)):
    await service.scope(db, ctx, eid)
    rows = (
        await db.scalars(
            select(IntelligenceJob)
            .where(IntelligenceJob.tenant_id == ctx.tenant_id, IntelligenceJob.engagement_id == eid)
            .order_by(IntelligenceJob.created_at.desc(), IntelligenceJob.id)
            .limit(limit)
        )
    ).all()
    return {"items": [audit.serialize(row) for row in rows], "limit": limit}


@router.get("/engagements/{eid}/jobs/{jid}")
async def job_details(eid: uuid.UUID, jid: uuid.UUID, db: DB, ctx: Actor):
    await service.scope(db, ctx, eid)
    obj = await db.scalar(
        select(IntelligenceJob).where(
            IntelligenceJob.tenant_id == ctx.tenant_id,
            IntelligenceJob.engagement_id == eid,
            IntelligenceJob.id == jid,
        )
    )
    if not obj:
        raise HTTPException(404, "Job not found")
    return audit.serialize(obj)


class JobAction(s.Strict):
    version: int = Field(ge=1)
    action: Literal["cancel", "retry"]


@router.post("/engagements/{eid}/jobs/{jid}/actions")
async def job_action(
    eid: uuid.UUID, jid: uuid.UUID, data: JobAction, db: DB, ctx: Actor, request: Request
):
    await service.scope(db, ctx, eid)
    obj = await db.scalar(
        select(IntelligenceJob)
        .where(
            IntelligenceJob.tenant_id == ctx.tenant_id,
            IntelligenceJob.engagement_id == eid,
            IntelligenceJob.id == jid,
        )
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Job not found")
    if obj.created_by != ctx.user_id:
        raise HTTPException(403, "Only the submitting user may control this job")
    await service.scope(db, ctx, eid, obj.operation)
    if obj.version != data.version:
        raise HTTPException(409, "Job version conflict")
    if data.action == "cancel":
        if obj.status not in {"pending", "running"}:
            raise HTTPException(409, "Only active jobs can be canceled")
        obj.status = "canceled"
    elif data.action == "retry":
        if obj.status not in {"failed", "canceled"} or obj.attempts >= 3:
            raise HTTPException(
                409,
                "Retry requires a failed/canceled job with fewer than three attempts; otherwise submit a corrected new job",
            )
        obj.status = "pending"
        obj.progress = 0
        obj.error_category = None
        obj.error_details = None
    else:
        raise HTTPException(422, "Unknown job action")
    await db.flush()
    await db.refresh(obj)
    record(
        db,
        ctx,
        "intelligence.job." + data.action,
        obj.id,
        request.state.request_id,
        {"engagement_id": str(eid)},
    )
    await db.commit()
    if data.action == "retry":
        from app.workers.intelligence import run

        try:
            run.apply_async(args=[str(obj.id), str(ctx.tenant_id)], queue="intelligence")
        except Exception:
            raise HTTPException(503, "Broker unavailable; retry remains pending") from None
    return audit.serialize(obj)


@router.get("/engagements/{eid}/events")
async def events(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    kind: str | None = None,
    after: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    await service.scope(db, ctx, eid)
    query = select(IntelligenceEvent).where(
        IntelligenceEvent.tenant_id == ctx.tenant_id, IntelligenceEvent.engagement_id == eid
    )
    if kind:
        query = query.where(IntelligenceEvent.kind == kind)
    if after:
        query = query.where(IntelligenceEvent.id > after)
    rows = (await db.scalars(query.order_by(IntelligenceEvent.id).limit(limit + 1))).all()
    items = []
    for row in rows[:limit]:
        try:
            await service.event(db, ctx, eid, row.id)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        items.append(
            {
                "id": str(row.id),
                "root_id": str(row.root_id),
                "kind": row.kind,
                "version": row.version,
                "sha256": row.sha256,
                "created_at": row.created_at.isoformat(),
                "created_by": str(row.created_by),
                "review_status": row.body.get("review_status", "UNVERIFIED"),
                "label": row.body.get("source_filename")
                or row.body.get("section")
                or row.body.get("title")
                or row.kind,
                "freshness": "CURRENT" if await service.current(db, ctx, row) else "STALE",
            }
        )
    return {
        "items": items,
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        "limit": limit,
    }


@router.get("/engagements/{eid}/events/{identifier}")
async def event_details(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    obj = await service.event(db, ctx, eid, identifier)
    body = dict(obj.body)
    totals = {}
    for key in [
        "rows",
        "items",
        "suggestions",
        "source_rows",
        "destination_rows",
        "unmatched_left",
        "unmatched_right",
        "matches",
        "edges",
    ]:
        if isinstance(body.get(key), list):
            totals[key] = len(body[key])
            body[key] = body[key][offset : offset + limit]
    return {
        **audit.serialize(obj),
        "body": body,
        "collection_totals": totals,
        "offset": offset,
        "limit": limit,
        "freshness": "CURRENT" if await service.current(db, ctx, obj) else "STALE",
        "latest_version": await service.head(db, ctx, obj),
    }


@router.post("/engagements/{eid}/events/{identifier}/corrections", status_code=201)
async def correct(
    eid: uuid.UUID, identifier: uuid.UUID, data: s.Correction, db: DB, ctx: Actor, request: Request
):
    eng = await service.scope(db, ctx, eid, "ocr", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.kind != "ocr":
        raise HTTPException(422, "Only OCR fields use this correction workflow")
    if obj.version != data.expected_version:
        raise HTTPException(409, "Extraction version conflict")
    from app.modules.intelligence.documents import FIELDS, MONEY, money

    if not set(data.fields) <= {*FIELDS, "gstin", "trn", "cgst", "sgst", "igst"}:
        raise HTTPException(422, "Unknown extracted field")
    fields = dict(obj.body["fields"])
    locations = dict(obj.body.get("field_locations", {}))
    for key, value in data.fields.items():
        if value is not None:
            if len(value) > 1000:
                raise HTTPException(422, "Corrected field exceeds limit")
            if key in MONEY:
                try:
                    value = money(value)
                except ValueError:
                    raise HTTPException(422, "Invalid corrected amount") from None
            if key.endswith("date"):
                try:
                    value = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    raise HTTPException(422, "Corrected date must use YYYY-MM-DD") from None
            if key == "currency" and (len(value) != 3 or not value.isalpha()):
                raise HTTPException(422, "ISO currency required")
        fields[key] = value
        locations[key] = {
            "origin": "HUMAN_CORRECTION",
            "actor": str(ctx.user_id),
            "prior_event_id": str(obj.id),
            "reason": data.reason,
        }
    body = {
        **obj.body,
        "fields": fields,
        "field_locations": locations,
        "correction_reason": data.reason,
        "review_status": "UNVERIFIED",
        "contributors": sorted({*obj.body.get("contributors", []), str(ctx.user_id)}),
    }
    result = await service.append(
        db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
    )
    return audit.serialize(result)


@router.get("/engagements/{eid}/inputs")
async def inputs(eid: uuid.UUID, db: DB, ctx: Actor):
    """Bounded authorized source choices; large accounting lists remain in the existing workbenches."""
    from app.modules.accounting.models import ImportBatch, ImportSnapshot, SamplingRun
    from app.modules.audit_execution.models import AuditRecord, EvidenceVersion

    eng = await service.scope(db, ctx, eid)
    await engagement_permissions(db, ctx, eid, "accounting.read")
    snapshots = (
        await db.scalars(
            select(ImportSnapshot)
            .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
            .where(
                ImportSnapshot.tenant_id == ctx.tenant_id,
                ImportSnapshot.entity_id == eng.entity_id,
                ImportSnapshot.period_id == eng.period_id,
                ImportBatch.status == "active",
            )
            .order_by(ImportSnapshot.created_at.desc())
            .limit(100)
        )
    ).all()
    samples = (
        await db.scalars(
            select(SamplingRun)
            .where(
                SamplingRun.tenant_id == ctx.tenant_id,
                SamplingRun.entity_id == eng.entity_id,
                SamplingRun.period_id == eng.period_id,
                SamplingRun.status == "completed",
            )
            .order_by(SamplingRun.created_at.desc())
            .limit(100)
        )
    ).all()
    evidence = (
        await db.scalars(
            select(EvidenceVersion)
            .join(AuditRecord, AuditRecord.id == EvidenceVersion.record_id)
            .where(
                EvidenceVersion.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.status != "ARCHIVED",
            )
            .order_by(EvidenceVersion.created_at.desc())
            .limit(100)
        )
    ).all()
    return {
        "snapshots": [
            dict(id=str(r.id), label=f"Snapshot {r.id}", sha256=r.sha256) for r in snapshots
        ],
        "samples": [dict(id=str(r.id), label=f"{r.method} • seed {r.seed}") for r in samples],
        "evidence": [
            dict(
                id=str(r.id),
                record_id=str(r.record_id),
                label=r.filename,
                scan_status=r.scan_status,
                version=r.number,
            )
            for r in evidence
        ],
        "limit": 100,
    }


@router.get("/engagements/{eid}/accounts")
async def account_choices(
    eid: uuid.UUID,
    snapshot_id: uuid.UUID,
    db: DB,
    ctx: Actor,
    search: str = Query("", max_length=100),
):
    from sqlalchemy import or_

    from app.modules.accounting.models import Account, SourceRecord

    eng = await service.scope(db, ctx, eid)
    snap, _ = await service.snapshot(db, ctx, eng, snapshot_id)
    query = select(Account).where(
        Account.tenant_id == ctx.tenant_id,
        Account.entity_id == eng.entity_id,
        Account.code.in_(
            select(SourceRecord.canonical["account_code"].astext).where(
                SourceRecord.tenant_id == ctx.tenant_id, SourceRecord.batch_id == snap.batch_id
            )
        ),
    )
    if search:
        query = query.where(
            or_(
                Account.code.contains(search, autoescape=True),
                Account.name.icontains(search, autoescape=True),
            )
        )
    rows = (await db.scalars(query.order_by(Account.code).limit(1001))).all()
    return {
        "items": [{"id": str(r.id), "code": r.code, "name": r.name} for r in rows[:1000]],
        "truncated": len(rows) > 1000,
    }


@router.post("/engagements/{eid}/events/{identifier}/review", status_code=201)
async def review(
    eid: uuid.UUID, identifier: uuid.UUID, data: s.Review, db: DB, ctx: Actor, request: Request
):
    eng = await service.scope(db, ctx, eid, mutable=True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.version != data.expected_version:
        raise HTTPException(409, "Result version conflict")
    reviewer = data.action in {"approve", "reject"}
    needed = (
        "audit.evidence.review"
        if obj.kind in {"ocr", "source-table"} and reviewer
        else "workingpaper.approve"
        if reviewer
        else {
            "finding": "audit.finding.create",
            "note": "workingpaper.review",
            "request-evidence": "audit.evidence.upload",
        }.get(data.action, "audit.testing.execute")
    )
    await engagement_permissions(db, ctx, eid, needed)
    if reviewer and str(ctx.user_id) in obj.body.get("contributors", [str(obj.created_by)]):
        raise HTTPException(403, "Independent reviewer required")
    body = dict(obj.body)
    if data.action == "accept" and obj.kind == "reconciliation":
        matches = [dict(i) for i in body["matches"]]
        selected_match = next((i for i in matches if data.item_id in i["left_ids"]), None)
        if not selected_match:
            raise HTTPException(
                422, "Select a proposed match using its original source transaction"
            )
        selected_match.update(
            auditor_status="ACCEPTED",
            auditor=str(ctx.user_id),
            auditor_comments=data.comments,
            auditor_at=datetime.now(UTC).isoformat(),
        )
        body.update(
            matches=matches,
            review_status="PREPARED",
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
        )
        return audit.serialize(
            await service.append(
                db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
            )
        )
    if data.action in {"finding", "note", "request-evidence"}:
        if obj.kind not in {"vouching", "reconciliation"} or not data.item_id:
            raise HTTPException(422, "Select a vouching or reconciliation source item")
        collection = (
            obj.body["items"]
            if obj.kind == "vouching"
            else [*obj.body["source_rows"], *obj.body["destination_rows"]]
        )
        item = next((i for i in collection if i["id"] == data.item_id), None)
        if not item:
            raise HTTPException(404, "Vouching item not found")
        from app.db.models.platform import LegalEntity

        entity = await db.get(LegalEntity, eng.entity_id)
        if not entity:
            raise HTTPException(404, "Entity not found")
        source = [{"kind": "intelligence", "id": str(obj.id)}]
        if obj.kind == "vouching" or any(i["id"] == data.item_id for i in obj.body["source_rows"]):
            source.append({"kind": "journal", "id": data.item_id})
        if data.action == "request-evidence":
            kind = "requests"
            content: dict = {
                "client_id": str(entity.client_id),
                "question": data.comments,
                "sources": source,
            }
        elif data.action == "note":
            if not data.target_record_id:
                raise HTTPException(
                    422, "Select the actual working paper or audit record for the review note"
                )
            kind = "review-notes"
            content = {
                "target_id": str(data.target_record_id),
                "assigned_reviewer": str(data.assigned_reviewer or ctx.user_id),
                "narrative": data.comments,
                "sources": source,
            }
        else:
            kind = "findings"
            content = {
                "finding_type": "missing_evidence" if obj.kind == "vouching" else "reconciliation",
                "severity": "medium",
                "narrative": data.comments,
                "financial_impact": None,
                "sources": source,
            }
        created = await audit.create(
            db,
            ctx,
            eid,
            kind,
            RecordInput(
                reference=f"INT-{str(uuid.uuid4())[:8]}",
                title="Documentary support: " + data.item_id[:8],
                body=content,
            ),
            request.state.request_id,
        )
        if obj.kind == "reconciliation":
            body.update(
                exceptions=[
                    *body.get("exceptions", []),
                    {
                        "item_id": data.item_id,
                        "record_id": created["id"],
                        "kind": kind,
                        "reason": data.comments,
                        "actor": str(ctx.user_id),
                    },
                ],
                review_status="PREPARED",
                contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
            )
            return audit.serialize(
                await service.append(
                    db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
                )
            )
        items = [dict(i) for i in body["items"]]
        selected_item = next(i for i in items if i["id"] == data.item_id)
        selected_item["linked_records"] = [
            *selected_item.get("linked_records", []),
            {"id": created["id"], "kind": kind, "reason": data.comments},
        ]
        if data.action == "finding":
            selected_item.update(
                auditor_status="EXCEPTION_RECORDED",
                auditor=str(ctx.user_id),
                auditor_comments=data.comments,
            )
        body.update(
            items=items,
            review_status="PREPARED",
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
        )
        result = await service.append(
            db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
        )
        return audit.serialize(result)
    if data.action == "accept":
        if obj.kind != "vouching" or not data.item_id or not data.candidate_id:
            raise HTTPException(422, "Select a vouching item and candidate extraction")
        items = [dict(i) for i in body["items"]]
        item = next((i for i in items if i["id"] == data.item_id), None)
        if not item or not any(
            c["extraction_id"] == str(data.candidate_id) for c in item["candidates"]
        ):
            raise HTTPException(422, "Candidate is not part of this scoped result")
        item.update(
            auditor_status="ACCEPTED",
            accepted_extraction_id=str(data.candidate_id),
            auditor=str(ctx.user_id),
            auditor_comments=data.comments,
            auditor_at=datetime.now(UTC).isoformat(),
        )
        body.update(
            items=items,
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
            review_status="PREPARED",
        )
    else:
        if data.action == "approve":
            for dependency in obj.dependencies:
                if dependency["type"] == "event":
                    supporting = await service.event(
                        db, ctx, eid, uuid.UUID(dependency["id"]), True
                    )
                    if (
                        supporting.kind == "source-table"
                        and supporting.body.get("review_status") != "REVIEWED"
                    ):
                        raise HTTPException(
                            409,
                            "Supporting table needs independent review before approving derived results",
                        )
        if obj.kind == "vouching" and data.action == "approve":
            if not body.get("items") or any(
                i.get("auditor_status") not in {"ACCEPTED", "EXCEPTION_RECORDED"}
                for i in body["items"]
            ):
                raise HTTPException(
                    409,
                    "Every item needs a documented auditor decision or a separate exception workflow",
                )
            for item in body["items"]:
                if item.get("auditor_status") == "EXCEPTION_RECORDED":
                    if not item.get("linked_records"):
                        raise HTTPException(409, "Documented exception record required")
                    for linked in item["linked_records"]:
                        await audit.get_record(db, ctx, eid, uuid.UUID(linked["id"]), lock=False)
                    continue
                extraction = await service.event(
                    db, ctx, eid, uuid.UUID(item["accepted_extraction_id"]), True
                )
                if extraction.body.get("review_status") != "REVIEWED":
                    raise HTTPException(
                        409, "Accepted supporting extraction needs independent field review"
                    )
        body.update(
            review_status="REVIEWED" if data.action == "approve" else "REJECTED",
            reviewer=str(ctx.user_id),
            reviewed_at=datetime.now(UTC).isoformat(),
            review_comments=data.comments,
        )
    result = await service.append(
        db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
    )
    return audit.serialize(result)


@router.post("/engagements/{eid}/events/{identifier}/working-paper", status_code=201)
async def generate_paper(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: s.GeneratePaper,
    db: DB,
    ctx: Actor,
    request: Request,
):
    eng = await service.scope(db, ctx, eid, "lead", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.body.get("review_status") != "REVIEWED":
        raise HTTPException(
            409, "Independently reviewed source result required before working-paper generation"
        )
    summary = {
        key: value
        for key, value in obj.body.items()
        if key
        in {
            "section",
            "totals",
            "totals_by_currency",
            "control_comparison",
            "source_totals",
            "destination_totals",
            "sampling_method",
            "seed",
            "review_status",
            "as_of",
            "rationale",
        }
    }
    tables = [
        {
            "title": "System-generated source calculations",
            "values": summary,
            "source_event_id": str(obj.id),
            "source_sha256": obj.sha256,
            "input_version": obj.version,
        }
    ]
    if isinstance(obj.body.get("rows"), list):
        tables.append(
            {
                "title": "Source schedule",
                "rows": obj.body["rows"][:1000],
                "total_rows": len(obj.body["rows"]),
                "bounded": len(obj.body["rows"]) > 1000,
            }
        )
    paper = RecordInput(
        reference=data.reference,
        title=data.title,
        body={
            "folder": obj.kind.title(),
            "assertions": data.assertions,
            "sources": [{"kind": "intelligence", "id": str(obj.id)}],
            "sections": [
                {"heading": "Objective — auditor authored", "text": data.objective},
                {
                    "heading": "System-generated source information",
                    "text": f"Derived from immutable {obj.kind} result {obj.id}, version {obj.version}, SHA-256 {obj.sha256}. Machine output is not a performed audit procedure or reviewed conclusion.",
                },
                {
                    "heading": "Procedures performed — auditor to complete",
                    "text": "No procedures are represented as performed by generation. Record actual testing and evidence assessment.",
                },
            ],
            "financial_tables": tables,
            "conclusion": "Draft only. Auditor must document actual work, exceptions, evidence sufficiency and conclusion before independent review.",
        },
    )
    return await audit.create(db, ctx, eng.id, "working-papers", paper, request.state.request_id)


@router.post("/engagements/{eid}/events/{identifier}/mapping-decisions", status_code=201)
async def mapping_decisions(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: s.MappingDecision,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.accounting.schemas import AccountAssignment

    eng = await service.scope(db, ctx, eid, "mapping", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.kind != "mapping" or obj.version != data.expected_version:
        raise HTTPException(409, "Mapping proposal version conflict")
    allowed = {r["account_code"] for r in obj.body["suggestions"]}
    if not set(data.assignments) <= allowed:
        raise HTTPException(422, "Assignments must reference accounts in this proposal")
    try:
        assignments = {
            code: AccountAssignment.model_validate(value).model_dump(mode="json")
            for code, value in data.assignments.items()
        }
    except ValidationError:
        raise HTTPException(422, "Invalid human account classification") from None
    return audit.serialize(
        await service.append(
            db,
            ctx,
            eng,
            "mapping",
            {
                **obj.body,
                "human_assignments": assignments,
                "decision_reason": data.reason,
                "contributors": sorted({*obj.body.get("contributors", []), str(ctx.user_id)}),
                "review_status": "PREPARED",
            },
            obj.dependencies,
            request.state.request_id,
            obj,
        )
    )


@router.post("/engagements/{eid}/events/{identifier}/apply-mapping", status_code=201)
async def apply_mapping(
    eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor, request: Request
):
    from app.api.v1.accounting import mapping
    from app.db.models.platform import LegalEntity
    from app.modules.accounting.schemas import MappingCreate

    eng = await service.scope(db, ctx, eid, "mapping", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if (
        obj.kind != "mapping"
        or obj.body.get("review_status") != "REVIEWED"
        or not obj.body.get("human_assignments")
    ):
        raise HTTPException(409, "Documented human assignments and independent approval required")
    entity = await db.get(LegalEntity, eng.entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    profile = await mapping(
        MappingCreate(
            client_id=entity.client_id,
            entity_id=entity.id,
            period_id=eng.period_id,
            name="Reviewed intelligence mapping",
            mapping={"accounts": obj.body["human_assignments"]},
            approved=True,
        ),
        db,
        ctx,
        request,
    )
    record(
        db,
        ctx,
        "intelligence.mapping.applied",
        obj.id,
        request.state.request_id,
        {"proposal_id": str(obj.id), "proposal_sha256": obj.sha256, "profile_id": profile["id"]},
    )
    return profile


@router.post("/engagements/{eid}/ticks", status_code=201)
async def tick(eid: uuid.UUID, data: s.Tick, db: DB, ctx: Actor, request: Request):
    eng = await service.scope(db, ctx, eid, "lead", True)
    paper = await audit.get_record(db, ctx, eid, data.record_id, mutable=True)
    if paper.kind != "working-papers" or paper.version != data.expected_version:
        raise HTTPException(409, "Working-paper version conflict")
    for source in data.supporting_sources:
        await audit.source_record(db, ctx, eng, Source.model_validate(source))
    marker = {
        "mark": data.mark,
        "actor": str(ctx.user_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "supporting_sources": data.supporting_sources,
        "rationale": data.rationale,
        "applied_to_version": paper.version,
        "evidence_sufficiency_determined": False,
    }
    tables = list(paper.body.get("financial_tables", []))
    existing = next((t for t in tables if t.get("title") == "Auditor tick marks"), None)
    if existing:
        tables = [
            {**t, "marks": [*t["marks"], marker]} if t.get("title") == "Auditor tick marks" else t
            for t in tables
        ]
    else:
        tables.append({"title": "Auditor tick marks", "marks": [marker]})
    return await audit.update(
        db,
        ctx,
        eid,
        paper.id,
        RecordPatch(
            version=paper.version,
            reference=paper.reference,
            title=paper.title,
            body={**paper.body, "financial_tables": tables},
        ),
        request.state.request_id,
    )


@router.get("/engagements/{eid}/events/{identifier}/export")
async def export_result(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    request: Request,
    format: str = Query("xlsx", pattern="^(xlsx|pdf|docx)$"),
):
    obj = await service.event(db, ctx, eid, identifier)
    await engagement_permissions(db, ctx, eid, "audit.export")
    from starlette.concurrency import run_in_threadpool

    from app.modules.intelligence.exports import render

    content, media = await run_in_threadpool(render, audit.serialize(obj), format)
    record(
        db,
        ctx,
        "intelligence.exported",
        obj.id,
        request.state.request_id,
        {"format": format, "sha256": obj.sha256},
    )
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{obj.kind}-{str(obj.id)[:8]}.{format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/engagements/{eid}/evidence/{identifier}/preview")
async def preview(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    request: Request,
    page: int = Query(1, ge=1, le=20),
    member: str | None = Query(None, max_length=500),
):
    from starlette.concurrency import run_in_threadpool

    from app.modules.intelligence.documents import preview_page
    from app.modules.lineage.storage import ObjectStore, hash_file

    eng = await service.scope(db, ctx, eid)
    version, _ = await service.evidence(db, ctx, eng, identifier)

    def render_page():
        with ObjectStore().local(version.object_key, version.object_version) as path:
            if hash_file(path) != version.sha256:
                raise ValueError("Evidence integrity verification failed")
            return preview_page(path, version.media_type, page, member)

    try:
        content = await run_in_threadpool(render_page)
    except (ValueError, OSError, KeyError, EOFError):
        raise HTTPException(422, "Preview unavailable for this document and page") from None
    record(
        db,
        ctx,
        "intelligence.evidence.previewed",
        version.id,
        request.state.request_id,
        {"page": page},
    )
    return Response(
        content,
        media_type="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
