import asyncio
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, text

from app.modules.audit_log.service import record as audit_log
from app.modules.enterprise_ai.catalogue import TOOLS, plan
from app.modules.enterprise_ai.models import Event, Proposal, Workflow
from app.modules.enterprise_ai.schemas import ToolInput
from app.modules.enterprise_ai.security import digest, scope, serial, source, validate_dependencies

TERMINAL = {"COMPLETED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"}


async def locked(db, ctx, key):
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"ai11:{ctx.tenant_id}:{key}"},
    )


async def event(db, ctx, run, key, kind, body):
    obj = Event(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=run.engagement_id,
        run_id=run.id,
        key=key,
        kind=kind,
        body=serial(body),
        sha256=digest(body),
    )
    db.add(obj)
    audit_log(db, ctx, "enterprise-ai." + kind, run.id, key, {"sha256": obj.sha256})
    await db.flush()
    return obj


async def get(db, ctx, eid, identifier, permission="ai.investigation.read"):
    await scope(db, ctx, eid, permission)
    obj = await db.scalar(
        select(Workflow).where(
            Workflow.tenant_id == ctx.tenant_id,
            Workflow.engagement_id == eid,
            Workflow.id == identifier,
        )
    )
    # Investigator results are private to their initiator by default.
    if not obj or obj.created_by != ctx.user_id:
        raise HTTPException(404, "Resource unavailable")
    return obj


async def history(db, ctx, run, validate=True):
    rows = (
        await db.scalars(
            select(Event)
            .where(Event.tenant_id == ctx.tenant_id, Event.run_id == run.id)
            .order_by(Event.created_at, Event.id)
        )
    ).all()
    if validate:
        for row in rows:
            if row.kind == "step":
                result = row.body["result"]
                await scope(db, ctx, run.engagement_id, TOOLS[result["tool"]][1])
                await validate_dependencies(db, ctx, run.engagement_id, result["sources"])
    return rows


async def create(db, ctx, data):
    eng = await scope(db, ctx, data.engagement_id, "ai.investigation.create")
    await scope(db, ctx, eng.id, "ai.workflow.run")
    if eng.status.upper() in {"CANCELLED", "ARCHIVED", "COMPLETED"}:
        raise HTTPException(409, "Engagement is read-only")
    if data.template_id:
        template = await get(db, ctx, eng.id, data.template_id, "ai.workflow.run")
        if template.state != "TEMPLATE_ACTIVE":
            raise HTTPException(409, "Active validated template required")
        task, steps = "template:" + str(template.id), template.plan
    else:
        try:
            task, steps = plan(data.task, data.prompt)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
    await locked(db, ctx, f"create:{ctx.user_id}:{data.idempotency_key}")
    old = await db.scalar(
        select(Workflow).where(
            Workflow.tenant_id == ctx.tenant_id,
            Workflow.created_by == ctx.user_id,
            Workflow.idempotency_key == data.idempotency_key,
        )
    )
    if old:
        if (
            old.engagement_id != data.engagement_id
            or old.task != task
            or old.inputs != data.inputs.model_dump(mode="json")
            or old.prompt != data.prompt
        ):
            raise HTTPException(409, "Idempotency key payload differs")
        return old
    # Check the complete plan before any source read. Missing specialist permission
    # denies the command atomically rather than leaking partial source existence.
    for tool in steps:
        await scope(db, ctx, eng.id, TOOLS[tool][1])
    obj = Workflow(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eng.id,
        idempotency_key=data.idempotency_key,
        task=task,
        prompt=data.prompt,
        state="CREATED",
        plan=steps,
        inputs=data.inputs.model_dump(mode="json"),
    )
    db.add(obj)
    await db.flush()
    await event(
        db,
        ctx,
        obj,
        "created",
        "planned",
        {
            "task": task,
            "steps": steps,
            "agent_depth": 1,
            "parallelism": 1,
            "max_steps": 12,
            "model_calls": 0,
        },
    )
    return obj


async def step(db, ctx, eid, identifier):
    from app.modules.enterprise_ai.tools import invoke

    await locked(db, ctx, str(identifier))
    run = await get(db, ctx, eid, identifier, "ai.workflow.run")
    if run.task == "readonly-template":
        raise HTTPException(
            409, "Create a run from the template; template configuration cannot execute"
        )
    if run.state in TERMINAL | {"PAUSED", "WAITING_FOR_APPROVAL"}:
        return run
    rows = await history(db, ctx, run)
    done = [r for r in rows if r.kind == "step"]
    index = len(done)
    if index >= len(run.plan):
        return run
    name = run.plan[index]
    started = time.monotonic()
    run.state = "RUNNING"
    try:
        async with db.begin_nested():
            async with asyncio.timeout(90):
                result = await invoke(db, ctx, eid, name, ToolInput.model_validate(run.inputs))
    except HTTPException as exc:
        # Reauthorization failures stop execution; no data-bearing failed handoff.
        if exc.status_code in {401, 403, 404}:
            run.state = "FAILED"
            await event(
                db,
                ctx,
                run,
                f"denial:{index}",
                "denied",
                {"step": index, "tool": name, "category": "authorization_or_unavailable"},
            )
            return run
        from app.modules.enterprise_ai.schemas import ToolResult

        result = ToolResult(
            status="FAILED",
            agent=TOOLS[name][0],
            tool=name,
            uncertainty=["Source validation failed; inspect original workspace"],
            data={"error_category": "source_validation", "message": str(exc.detail)[:500]},
        )
    except Exception as exc:
        from app.modules.enterprise_ai.schemas import ToolResult

        result = ToolResult(
            status="FAILED",
            agent=TOOLS[name][0],
            tool=name,
            uncertainty=["Tool failed within execution limit; inspect trace"],
            data={"error_category": "timeout" if isinstance(exc, TimeoutError) else "tool_failure"},
        )
    await event(
        db,
        ctx,
        run,
        f"step:{index}",
        "step",
        {
            "index": index,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "permission": TOOLS[name][1],
            "result": result.model_dump(mode="json"),
            "tokens": 0,
            "cost": "0",
            "usage_basis": "deterministic tool; no provider invoked",
        },
    )
    statuses = [r.body["result"]["status"] for r in done] + [result.status]
    if index + 1 == len(run.plan):
        run.state = (
            "COMPLETED" if all(s == "COMPLETED" for s in statuses) else "PARTIALLY_COMPLETED"
        )
        run.outputs = {
            "summary": "Source collection completed. Findings and treatment require independent professional review.",
            "source_coverage": {s: statuses.count(s) for s in set(statuses)},
            "deterministic_signal": "See typed tool receipts",
            "ml_signal": "Separate stored ML tool receipt; not proof of fraud",
            "ai_explanation": "NOT_REQUESTED",
            "auditor_conclusion": "NOT_RECORDED",
            "human_review_required": True,
        }
    await db.flush()
    await db.refresh(run)
    return run


async def propose(db, ctx, eid, data):
    await scope(db, ctx, eid, "ai.approval.request")
    run = await get(db, ctx, eid, data.run_id)
    if run.state not in {"COMPLETED", "PARTIALLY_COMPLETED"}:
        raise HTTPException(409, "Completed source collection required")
    rows = await history(db, ctx, run)
    collected = {
        s["id"]
        for e in rows
        if e.kind == "step"
        for s in e.body["result"]["sources"]
        if s.get("type", "record") == "record"
    }
    if not {str(x) for x in data.record_ids} <= collected:
        raise HTTPException(422, "Proposal must cite records collected by this investigation")
    deps = []
    for rid in data.record_ids:
        obj = await source(db, ctx, eid, rid)
        deps.append({"id": str(obj.id), "version": obj.version, "type": "record"})
    await scope(db, ctx, eid, "workingpaper.create")
    payload = {
        "action": "create-draft-workpaper",
        "agent": "orchestrator",
        "requesting_user": str(ctx.user_id),
        "before": None,
        "after": {"title": data.title, "narrative": data.narrative},
        "sources": deps,
    }
    await locked(db, ctx, f"proposal:{run.id}:{digest(payload)}")
    existing = await db.scalar(
        select(Proposal).where(
            Proposal.tenant_id == ctx.tenant_id,
            Proposal.run_id == run.id,
            Proposal.payload_hash == digest(payload),
        )
    )
    if existing:
        return existing
    proposal = Proposal(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        run_id=run.id,
        action="create-draft-workpaper",
        payload=payload,
        dependencies=deps,
        payload_hash=digest(payload),
    )
    db.add(proposal)
    await db.flush()
    await event(
        db,
        ctx,
        run,
        "proposal:" + str(proposal.id),
        "proposal",
        {"proposal_id": str(proposal.id), "payload_hash": proposal.payload_hash},
    )
    return proposal


async def proposal(db, ctx, eid, identifier, permission="ai.investigation.read"):
    await scope(db, ctx, eid, permission)
    obj = await db.scalar(
        select(Proposal)
        .where(
            Proposal.tenant_id == ctx.tenant_id,
            Proposal.engagement_id == eid,
            Proposal.id == identifier,
        )
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Resource unavailable")
    await validate_dependencies(db, ctx, eid, obj.dependencies)
    return obj


async def decide(db, ctx, eid, identifier, data):
    obj = await proposal(db, ctx, eid, identifier, "ai.approval.decide")
    if obj.created_by == ctx.user_id:
        raise HTTPException(403, "Independent reviewer required")
    if (
        obj.version != data.version
        or obj.state != "AWAITING_APPROVAL"
        or obj.payload_hash != data.payload_hash
        or digest(obj.payload) != obj.payload_hash
    ):
        raise HTTPException(409, "Stale or already decided approval")
    await scope(db, ctx, eid, "workingpaper.approve")
    obj.state = "APPROVED" if data.decision == "approve" else "REJECTED"
    obj.decision = {
        "reviewer": str(ctx.user_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "decision": data.decision,
        "comments": data.comments,
        "payload_hash": obj.payload_hash,
    }

    run = await db.get(Workflow, obj.run_id)
    await event(db, ctx, run, "decision:" + str(obj.id), "decision", obj.decision)
    await db.flush()
    await db.refresh(obj)
    return obj


async def execute_proposal(db, ctx, eid, identifier):
    from app.core.dependencies import Context
    from app.modules.audit_execution import service as audit
    from app.modules.audit_execution.schemas import RecordInput

    obj = await proposal(db, ctx, eid, identifier, "ai.approval.request")
    if obj.created_by != ctx.user_id:
        raise HTTPException(403, "Requesting user must execute approved proposal")
    if obj.state == "RECORDED":
        return obj
    if obj.state != "APPROVED" or digest(obj.payload) != obj.payload_hash:
        raise HTTPException(409, "Exact approved payload required")
    # Reviewer must still have current source access and approval permission.
    reviewer = Context(uuid.UUID(obj.decision["reviewer"]), ctx.tenant_id, frozenset())
    await scope(db, reviewer, eid, "ai.approval.decide")
    await scope(db, reviewer, eid, "workingpaper.approve")
    await validate_dependencies(db, reviewer, eid, obj.dependencies)
    body = {
        "folder": "AI investigation drafts",
        "narrative": obj.payload["after"]["narrative"],
        "sections": [
            {"heading": "Proposed evidence review", "text": obj.payload["after"]["narrative"]}
        ],
        "sources": [{"kind": "record", "id": d["id"]} for d in obj.dependencies],
        "conclusion": "Draft only. No evidence sufficiency, tax position, risk assessment or audit opinion approved.",
    }
    created = await audit.create(
        db,
        ctx,
        eid,
        "working-papers",
        RecordInput(
            reference="AI11-" + str(obj.id), title=obj.payload["after"]["title"], body=body
        ),
        str(obj.id),
    )
    if created["status"] != "IN_PROGRESS":
        raise HTTPException(409, "Draft verification failed")
    obj.result = {
        "record_id": created["id"],
        "status": created["status"],
        "executed_at": datetime.now(UTC).isoformat(),
        "verified": True,
        "professional_approval": False,
    }
    obj.state = "RECORDED"
    run = await db.get(Workflow, obj.run_id)
    await event(db, ctx, run, "execution:" + str(obj.id), "executed-verified-recorded", obj.result)
    await db.flush()
    await db.refresh(obj)
    return obj
