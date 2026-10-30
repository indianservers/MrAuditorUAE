import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import Field
from sqlalchemy import func, or_, select

from app.core.dependencies import DB, Context, require
from app.modules.accounting.schemas import SamplingRequest
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.models import AuditRecord, AuditRevision
from app.modules.audit_execution.schemas import BODIES, Action, RecordInput, RecordPatch, Strict
from app.modules.audit_log.service import record as log
from app.modules.demo.guard import DEMO_TENANT
from app.modules.grc import operations, service
from app.modules.grc import schemas as s
from app.modules.grc.catalogue import AI_TASKS, FRAMEWORKS, KINDS, MONITOR_RULES
from app.modules.grc.models import GRCRun, MonitorAlert, MonitorSchedule

for kind, body in s.BODIES.items():
    BODIES["grc-" + kind] = body
    PREPARE["grc-" + kind] = KINDS[kind][0]
    APPROVE["grc-" + kind] = KINDS[kind][1]
router = APIRouter(prefix="/grc", tags=["Internal audit ERM and controls"])
Actor = Annotated[Context, Depends(require("grc.read"))]


class FilingTransition(Strict):
    version: int = Field(ge=1)
    stage: str = Field(
        pattern="^(not_started|preparing|under_review|approved_for_submission|submitted|acknowledged)$"
    )
    submission_evidence_id: uuid.UUID | None = None
    acknowledgment_evidence_id: uuid.UUID | None = None


@router.post("/engagements/{eid}/compliance-reminders")
async def compliance_reminders(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.grc.notifications import compliance_reminders as record_reminders

    await audit.engagement(db, ctx, eid, "compliance.manage", True)
    return await record_reminders(db, ctx, eid, date.today())


@router.post("/engagements/{eid}/obligations/{rid}/filing-stage")
async def filing_stage(
    eid: uuid.UUID, rid: uuid.UUID, data: FilingTransition, db: DB, ctx: Actor, request: Request
):
    from app.modules.grc.filing import transition

    return await transition(db, ctx, eid, rid, data, request.state.request_id)


@router.get("/engagements/{eid}/compliance-calendar")
async def compliance_calendar(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.grc.deadlines import local_today, missing_obligation_period, state
    from app.modules.lineage.working_papers import freshness

    await audit.engagement(db, ctx, eid, "grc.read")
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "grc-obligation",
            )
            .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
            .limit(200)
        )
    ).all()
    items = []
    for obj in rows:
        await service.authorize_record(db, ctx, obj)
        current = await freshness(db, ctx, obj)
        items.append(
            {
                "record_id": str(obj.id),
                "version": obj.version,
                "reference": obj.reference,
                "jurisdiction": obj.body.get("jurisdiction"),
                "jurisdiction_scope": obj.body.get("jurisdiction_scope"),
                "obligation_period_start": obj.body.get("obligation_period_start"),
                "obligation_period_end": obj.body.get("obligation_period_end"),
                "deadline": obj.body.get("deadline"),
                "extension_deadline": obj.body.get("extension_deadline"),
                "deadline_kind": obj.body.get("deadline_kind", "unresolved"),
                "filing_stage": obj.body.get("filing_stage", "not_started"),
                "calendar_state": state(obj.body, local_today(obj.body)),
                "freshness": current,
                "reassessment_required": current != "CURRENT"
                or missing_obligation_period(obj.body),
                "review_status": obj.status,
                "owner_id": obj.body["owner_id"],
                "reviewer_id": obj.body.get("reviewer_id"),
            }
        )
    return {"items": items, "bounded_to": 200, "external_submission_performed": False}


@router.get("/frameworks")
async def frameworks(ctx: Actor):
    return {
        "frameworks": FRAMEWORKS,
        "monitor_rules": {
            key: {"requirements": v[0], "input_type": v[1], "existing_rule": v[2]}
            for key, v in MONITOR_RULES.items()
        },
        "ai_tasks": AI_TASKS,
        "proprietary_standard_text": False,
    }


@router.get("/engagements/{eid}/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.audit_execution.access import engagement_permissions

    eng = await audit.engagement(db, ctx, eid, "grc.read")
    permissions, roles = await engagement_permissions(db, ctx, eid, "grc.read")
    return {
        "engagement": audit.serialize(eng),
        "permissions": sorted(permissions),
        "roles": sorted(roles),
        "schemas": {key: v.model_json_schema() for key, v in s.BODIES.items()},
        "kind_permissions": KINDS,
    }


@router.get("/engagements/{eid}/dashboard")
async def dashboard(eid: uuid.UUID, db: DB, ctx: Actor):
    return await operations.dashboard(db, ctx, eid)


@router.get("/engagements/{eid}/records/{kind}")
async def listing(
    eid: uuid.UUID,
    kind: str,
    db: DB,
    ctx: Actor,
    search: str = Query("", max_length=200),
    status: str | None = None,
    owner_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await audit.engagement(db, ctx, eid, "grc.read")
    if kind not in s.BODIES:
        raise HTTPException(404, "Unknown GRC register")
    where = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "grc-" + kind,
        or_(
            AuditRecord.title.icontains(search, autoescape=True),
            AuditRecord.reference.icontains(search, autoescape=True),
        ),
    ]
    if status:
        where.append(AuditRecord.status == status)
    if owner_id:
        where.append(AuditRecord.body["owner_id"].astext == str(owner_id))
    if await service.owner_scoped(db, ctx, eid):
        visible = [
            AuditRecord.body["owner_id"].astext == str(ctx.user_id),
            AuditRecord.prepared_by == ctx.user_id,
        ]
        if kind in {"framework", "policy", "scoring"}:
            visible.append(AuditRecord.status.in_(service.APPROVED))
        where.append(or_(*visible))
    query = (
        select(AuditRecord)
        .where(*where)
        .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.scalars(query)).all()
    return {
        "items": [audit.serialize(x) for x in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*where)),
        "limit": limit,
        "offset": offset,
    }


@router.post("/engagements/{eid}/records/{kind}", status_code=201)
async def create(
    eid: uuid.UUID, kind: str, data: RecordInput, db: DB, ctx: Actor, request: Request
):
    if kind not in s.BODIES:
        raise HTTPException(404, "Unknown GRC source")
    return await audit.create(db, ctx, eid, "grc-" + kind, data, request.state.request_id)


@router.patch("/engagements/{eid}/records/{rid}")
async def update(
    eid: uuid.UUID, rid: uuid.UUID, data: RecordPatch, db: DB, ctx: Actor, request: Request
):
    await service.record(db, ctx, eid, rid, approved=False)
    return await audit.update(db, ctx, eid, rid, data, request.state.request_id)


@router.post("/engagements/{eid}/records/{rid}/actions")
async def action(
    eid: uuid.UUID, rid: uuid.UUID, data: Action, db: DB, ctx: Actor, request: Request
):
    await service.record(db, ctx, eid, rid, approved=False)
    result = await audit.action(db, ctx, eid, rid, data, request.state.request_id)
    if result["status"] == "APPROVED":
        from app.modules.grc.notifications import assigned

        paper = await db.get(AuditRecord, rid)
        if not paper:
            raise HTTPException(409, "Approved workpaper disappeared")
        await assigned(db, ctx, paper)
        if (
            paper.kind in {"grc-assessment", "grc-plan", "grc-kri", "grc-sod-access", "grc-test"}
            and "grc.calculate" in ctx.permissions
        ):
            await operations.calculate(db, ctx, eid, rid)
    return result


@router.get("/engagements/{eid}/records/{rid}/history")
async def history(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    await service.record(db, ctx, eid, rid, approved=False)
    rows = (
        await db.scalars(
            select(AuditRevision)
            .where(AuditRevision.tenant_id == ctx.tenant_id, AuditRevision.record_id == rid)
            .order_by(AuditRevision.version.desc())
            .limit(100)
        )
    ).all()
    return {"items": [audit.serialize(x) for x in rows]}


@router.post("/engagements/{eid}/records/{rid}/calculate", status_code=201)
async def calculate(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor, compact_sod: bool = False):
    run = await operations.calculate(db, ctx, eid, rid)
    result = audit.serialize(run)
    if compact_sod and run.kind == "sod-access" and run.results.get("sod_contract"):
        from app.modules.grc.sod_reporting import compact

        result["results"] = compact(run)
        result["inputs"] = {key: value for key, value in run.inputs.items() if key != "assignments"}
    return result


@router.get("/engagements/{eid}/runs/{rid}/sod")
async def sod_summary(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.grc.sod_reporting import read, summary

    run, state = await read(db, ctx, eid, rid)
    return summary(run, state)


@router.get("/engagements/{eid}/runs/{rid}/sod/export")
async def sod_export(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor, request: Request):
    from fastapi.responses import Response
    from starlette.concurrency import run_in_threadpool

    from app.modules.grc.sod_reporting import read, workbook

    run, state = await read(db, ctx, eid, rid)
    try:
        content = await run_in_threadpool(workbook, run, state)
    except ValueError as error:
        raise HTTPException(
            422,
            "Complete SoD workbook exceeds its representation bounds; partition the reviewed scope",
        ) from error
    log(
        db,
        ctx,
        "grc.sod.export",
        rid,
        request.state.request_id,
        {
            "engagement_id": str(eid),
            "record_versions_status": state["record_versions_status"],
            "snapshot_sha256": run.sha256,
        },
    )
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="sod-{rid}.xlsx"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/engagements/{eid}/runs/{rid}/sod/rows/{collection}")
async def sod_rows(
    eid: uuid.UUID,
    rid: uuid.UUID,
    collection: str,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    from app.modules.grc.sod_reporting import COLLECTIONS, read, rows

    collection = collection.replace("-", "_")
    if collection not in COLLECTIONS:
        raise HTTPException(404, "Unknown SoD row collection")
    run, state = await read(db, ctx, eid, rid)
    values = rows(run, collection)
    return dict(
        items=values[offset : offset + limit],
        total=len(values),
        offset=offset,
        limit=limit,
        **state,
    )


@router.post("/engagements/{eid}/internal-audits/{rid}/transitions", status_code=201)
async def transition(eid: uuid.UUID, rid: uuid.UUID, data: s.Transition, db: DB, ctx: Actor):
    return audit.serialize(await operations.transition(db, ctx, eid, rid, data))


@router.get("/engagements/{eid}/runs")
async def runs(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    record_id: uuid.UUID | None = None,
    compact_sod: bool = False,
):
    await audit.engagement(db, ctx, eid, "grc.read")
    if await service.owner_scoped(db, ctx, eid):
        raise HTTPException(403, "Professional read model permission required")
    where = [
        GRCRun.tenant_id == ctx.tenant_id,
        GRCRun.engagement_id == eid,
        GRCRun.kind.notin_(["board-package", "notification"]),
    ]
    if kind:
        where.append(GRCRun.kind == kind)
    if record_id:
        where.append(GRCRun.record_id == record_id)
    rows = (
        await db.scalars(
            select(GRCRun)
            .where(*where)
            .order_by(GRCRun.created_at.desc(), GRCRun.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for row in rows:
        item = audit.serialize(row)
        if compact_sod and row.kind == "sod-access" and row.results.get("sod_contract"):
            from app.modules.grc.sod_reporting import compact

            item["results"] = compact(row)
            item["inputs"] = {
                key: value for key, value in row.inputs.items() if key != "assignments"
            }
        items.append(item)
    return {
        "items": items,
        "total": await db.scalar(select(func.count()).select_from(GRCRun).where(*where)),
    }


class Execute(Strict):
    request_key: uuid.UUID = Field(default_factory=uuid.uuid4)


@router.post("/engagements/{eid}/monitoring/{rid}/execute", status_code=202)
async def execute(
    eid: uuid.UUID, rid: uuid.UUID, data: Execute, db: DB, ctx: Actor, request: Request
):
    await audit.engagement(db, ctx, eid, "monitor.job.execute", True)
    rule = await service.record(db, ctx, eid, rid, "monitor-rule")
    from app.workers.accounting import submit

    return await submit(
        db,
        ctx,
        "grc.monitor",
        {
            "engagement_id": str(eid),
            "rule_id": str(rid),
            "version": rule.version,
            "request_key": str(data.request_key),
        },
        request.state.request_id,
    )


@router.get("/engagements/{eid}/alerts")
async def alerts(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    rule_key: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await audit.engagement(db, ctx, eid, "monitor.alert.review")
    where = [MonitorAlert.tenant_id == ctx.tenant_id, MonitorAlert.engagement_id == eid]
    if rule_key:
        where.append(MonitorAlert.rule_key == rule_key)
    rows = (
        await db.scalars(
            select(MonitorAlert)
            .where(*where)
            .order_by(MonitorAlert.created_at.desc(), MonitorAlert.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {
                **audit.serialize(x),
                "source_provenance": {
                    "synthetic": True if ctx.tenant_id == DEMO_TENANT else None,
                    "basis": "guarded tenant classification",
                    "legacy_request_flag_retained": x.signals.get("synthetic"),
                },
            }
            for x in rows
        ],
        "total": await db.scalar(select(func.count()).select_from(MonitorAlert).where(*where)),
    }


@router.get("/engagements/{eid}/alerts/{identifier}/source")
async def alert_source(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):
    item = await service.alert(db, ctx, eid, identifier)
    if item.snapshot_id:
        from app.modules.accounting.models import JournalLine

        row = await db.scalar(
            select(JournalLine).where(
                JournalLine.tenant_id == ctx.tenant_id,
                JournalLine.id == item.source_id,
                JournalLine.snapshot_id == item.snapshot_id,
            )
        )
        return {
            "type": "journal",
            "record": audit.serialize(row) if row else None,
            "snapshot_id": str(item.snapshot_id),
        }
    source = await audit.get_record(db, ctx, eid, item.source_id, "grc.read")
    return {"type": "workpaper", "record": audit.serialize(source)}


@router.post("/engagements/{eid}/schedules", status_code=201)
async def schedule(eid: uuid.UUID, data: s.ScheduleInput, db: DB, ctx: Actor, request: Request):
    await audit.engagement(db, ctx, eid, "monitor.schedule.manage", True)
    rule = await service.record(db, ctx, eid, data.rule_id, "monitor-rule")
    if not data.next_due.tzinfo:
        raise HTTPException(422, "Timezone-aware schedule timestamp required")
    obj = MonitorSchedule(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        rule_id=rule.id,
        rule_version=rule.version,
        frequency=data.frequency,
        next_due=data.next_due,
    )
    db.add(obj)
    await db.flush()
    log(db, ctx, "grc.schedule.created", obj.id, request.state.request_id)
    return audit.serialize(obj)


@router.get("/engagements/{eid}/schedules")
async def schedules(eid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "monitor.job.execute")
    rows = (
        await db.scalars(
            select(MonitorSchedule)
            .where(MonitorSchedule.tenant_id == ctx.tenant_id, MonitorSchedule.engagement_id == eid)
            .order_by(MonitorSchedule.next_due)
            .limit(100)
        )
    ).all()
    return {"items": [audit.serialize(x) for x in rows]}


class ScheduleState(Strict):
    version: int = Field(ge=1)
    active: bool


@router.patch("/engagements/{eid}/schedules/{identifier}")
async def schedule_state(
    eid: uuid.UUID, identifier: uuid.UUID, data: ScheduleState, db: DB, ctx: Actor, request: Request
):
    await audit.engagement(db, ctx, eid, "monitor.schedule.manage", True)
    obj = await db.scalar(
        select(MonitorSchedule)
        .where(
            MonitorSchedule.tenant_id == ctx.tenant_id,
            MonitorSchedule.engagement_id == eid,
            MonitorSchedule.id == identifier,
        )
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Schedule not found")
    if obj.version != data.version:
        raise HTTPException(409, "Schedule version changed")
    rule = await service.record(db, ctx, eid, obj.rule_id, "monitor-rule")
    obj.active = data.active
    obj.rule_version = rule.version
    log(
        db,
        ctx,
        "grc.schedule.changed",
        obj.id,
        request.state.request_id,
        {"active": data.active, "version": obj.version},
    )
    await db.flush()
    await db.refresh(obj)
    return audit.serialize(obj)


@router.post("/engagements/{eid}/policies/{rid}/acknowledgments", status_code=201)
async def acknowledge(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "policy.acknowledge")
    policy = await service.record(db, ctx, eid, rid, "policy")
    if policy.body["effective_from"] > str(date.today()):
        raise HTTPException(409, "Policy is not yet effective")
    return audit.serialize(
        await service.run(
            db,
            ctx,
            eid,
            "policy-acknowledgment",
            {"policy_id": str(rid), "version": policy.version},
            {"user_id": str(ctx.user_id), "acknowledged": True},
            [service.dependency(policy)],
            policy.id,
        )
    )


@router.get("/engagements/{eid}/notifications")
async def notifications(eid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "grc.read")
    rows = (
        await db.scalars(
            select(GRCRun)
            .where(
                GRCRun.tenant_id == ctx.tenant_id,
                GRCRun.engagement_id == eid,
                GRCRun.kind == "notification",
                GRCRun.results["recipient_id"].astext == str(ctx.user_id),
            )
            .order_by(GRCRun.created_at.desc())
            .limit(100)
        )
    ).all()
    visible = []
    for row in rows:
        if not row.record_id:
            continue
        try:
            await service.record(db, ctx, eid, row.record_id, approved=False)
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        visible.append(audit.serialize(row))
    return {"items": visible}


@router.post("/engagements/{eid}/board/{rid}/publish", status_code=201)
async def publish(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.grc.reporting import publish as publish_package

    return audit.serialize(await publish_package(db, ctx, eid, rid))


BoardActor = Annotated[Context, Depends(require("governance.board.read"))]


@router.get("/engagements/{eid}/board/packages")
async def package_directory(eid: uuid.UUID, db: DB, ctx: BoardActor):
    from app.modules.audit_execution.access import engagement_permissions
    from app.modules.grc.reporting import published

    await engagement_permissions(db, ctx, eid, "governance.board.read")
    rows = (
        await db.scalars(
            select(GRCRun)
            .where(
                GRCRun.tenant_id == ctx.tenant_id,
                GRCRun.engagement_id == eid,
                GRCRun.kind == "board-package",
            )
            .order_by(GRCRun.created_at.desc())
            .limit(100)
        )
    ).all()
    items = []
    for row in rows:
        try:
            item = await published(db, ctx, eid, row.id)
        except HTTPException as exc:
            if exc.status_code in {403, 409, 410}:
                continue
            raise
        items.append(
            {
                "id": str(item.id),
                "title": item.results["title"],
                "published_at": item.created_at,
                "created_at": item.created_at,
                "valid_until": item.results["valid_until"],
                "synthetic": item.results["synthetic"],
            }
        )
    return {"items": items}


@router.get("/engagements/{eid}/rcm")
async def matrix(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    await audit.engagement(db, ctx, eid, "grc.read")
    if await service.owner_scoped(db, ctx, eid):
        raise HTTPException(403, "Professional matrix permission required")
    where = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "grc-link",
    ]
    links = (
        await db.scalars(
            select(AuditRecord)
            .where(*where)
            .order_by(AuditRecord.reference)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    ids = {uuid.UUID(x.body[k]) for x in links for k in ["risk_id", "control_id"]}
    rows = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.id.in_(ids),
            )
        )
    ).all()
    by_id = {str(x.id): x for x in rows}
    return {
        "items": [
            {
                "id": str(x.id),
                "reference": x.reference,
                "status": x.status,
                "risk": audit.serialize(by_id[x.body["risk_id"]]),
                "control": audit.serialize(by_id[x.body["control_id"]]),
                "rationale": x.body["rationale"],
            }
            for x in links
        ],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*where)),
    }


@router.post("/engagements/{eid}/samples", status_code=201)
async def sampling(eid: uuid.UUID, data: SamplingRequest, db: DB, ctx: Actor):
    from app.modules.audit_analytics.service import sampling as select_sample

    eng = await audit.engagement(db, ctx, eid, "grc.control.test", True)
    await service.snapshot(db, ctx, eng, data.snapshot_id)
    if data.size > 1000:
        raise HTTPException(422, "Partition control tests into samples of at most 1000 items")
    return await select_sample(db, ctx, data)


@router.post("/engagements/{eid}/sod/import", status_code=201)
async def import_access(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    request: Request,
    metadata: str = Form(max_length=20000),
    file: UploadFile = File(),
):
    import hashlib
    import json

    from app.modules.audit_execution.models import EvidenceVersion
    from app.modules.grc.sod_import import parse

    await audit.engagement(db, ctx, eid, "grc.sod.analyze", True)
    content = await file.read(4 * 1024 * 1024 + 1)
    await file.close()
    try:
        data = RecordInput.model_validate(json.loads(metadata))
        assignments = parse(content)
        body = s.SoDAccess.model_validate(
            {
                **data.body,
                "assignments": assignments,
                "source_hash": hashlib.sha256(content).hexdigest(),
            }
        )
    except (ValueError, UnicodeError):
        raise HTTPException(
            422, "Invalid access CSV or metadata; use the documented columns and ISO dates"
        ) from None
    evidence = await service.evidence(db, ctx, eid, body.source_evidence_id)
    version = await db.scalar(
        select(EvidenceVersion)
        .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == evidence.id)
        .order_by(EvidenceVersion.number.desc())
        .limit(1)
    )
    if not version or version.scan_status != "CLEAN" or version.sha256 != body.source_hash:
        raise HTTPException(
            409, "CSV must match its latest clean, independently approved evidence version"
        )
    return await audit.create(
        db,
        ctx,
        eid,
        "grc-sod-access",
        RecordInput(reference=data.reference, title=data.title, body=body.model_dump(mode="json")),
        request.state.request_id,
    )


@router.get("/engagements/{eid}/board/packages/{identifier}")
async def board_package(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: BoardActor):
    from app.modules.grc.reporting import published

    obj = await published(db, ctx, eid, identifier)
    return {
        "id": str(obj.id),
        "sha256": obj.sha256,
        "published_at": obj.created_at,
        "report": obj.results,
    }


@router.get("/engagements/{eid}/board/packages/{identifier}/export/{format}")
async def board_export(eid: uuid.UUID, identifier: uuid.UUID, format: str, db: DB, ctx: BoardActor):
    from fastapi.responses import Response

    from app.modules.grc.reporting import published, render

    obj = await published(db, ctx, eid, identifier)
    content, media = render(obj, format)
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="governance-{identifier}.{format}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
