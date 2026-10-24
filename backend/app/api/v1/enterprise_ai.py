import copy

import uuid

from typing import Annotated



from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import func, select



from app.core.dependencies import DB, Context, require

from app.db.models.platform import AIModelConfiguration, AIProviderConfig

from app.modules.audit_execution.service import serialize

from app.modules.enterprise_ai import documents, service

from app.modules.enterprise_ai.business import Execute

from app.modules.enterprise_ai.catalogue import RECIPES, TOOLS, agents

from app.modules.enterprise_ai.models import Event, Extraction, Proposal, Schedule, Workflow

from app.modules.enterprise_ai.schemas import (

    CitationInput,

    Command,

    Control,

    Correction,

    Decision,

    ExtractInput,

    Graph,

    MatchInput,

    ProposalInput,

    ScheduleInput,

    TemplateInput,

    validate_graph,

)

from app.modules.enterprise_ai.security import digest, scope, validate_dependencies



router = APIRouter(prefix="/ai", tags=["Enterprise AI investigations"])

Actor = Annotated[Context, Depends(require("ai.investigation.read"))]





@router.get("/engagements/{eid}/runtime-status")

async def runtime_status(eid: uuid.UUID, db: DB, ctx: Actor):

    from app.core.config import settings

    from app.db.models.platform import AIExecution

    from app.modules.enterprise_ai.runtime_status import language_state



    await scope(db, ctx, eid)

    config = settings()

    model = await db.scalar(select(AIModelConfiguration).where(AIModelConfiguration.name == config.ai_model))

    provider = await db.get(AIProviderConfig, model.provider_id) if model else None

    last = await db.scalar(select(AIExecution).where(

        AIExecution.tenant_id == ctx.tenant_id,

        AIExecution.model_id == model.id,

    ).order_by(AIExecution.created_at.desc(), AIExecution.id.desc()).limit(1)) if model else None

    return {

        "language": language_state(adapter=provider.adapter if provider else None,

            enabled=bool(model and model.enabled), credentials_present=bool(config.ai_api_key),

            external_approved=config.audit_ai_external_approved, last=last),

        "local_ml": {"runtime": "TensorFlow.js Node CPU", "state": "inspect_model_registry",

            "readiness": "per-model deployment and artifact validation required",

            "allowed_modes": ["trained_model", "statistical_baseline", "rules_baseline", "diagnostic_mock", "unavailable"]},

    }





@router.get("/engagements/{eid}/use-cases")

async def business_cases(eid: uuid.UUID, db: DB, ctx: Actor):

    import json

    from pathlib import Path



    from app.modules.enterprise_ai.business import case_scope, module_url

    from app.modules.jurisdictions.ae.use_cases import CASES, ENGINE_TOOLS

    from app.modules.jurisdictions.ae.advanced_specs import spec



    await case_scope(db, ctx, eid, 1)

    sources = json.loads((Path(__file__).resolve().parents[2] / "modules/jurisdictions/ae/source_register.json").read_text(encoding="utf-8"))

    return {

        "legal_source_register": sources,

        "country": "AE",

        "version": "mr-auditor-uae/4",

        "engine_connections": ENGINE_TOOLS,
        "inference_modes":["trained_model","statistical_baseline","rules_baseline","diagnostic_mock","unavailable"],

        "items": [

            {**case.model_dump(), "advanced_contract": spec(case.id) if case.id >= 51 else None, "module_url": module_url(case, eid),

             "calculation_module_url": module_url(case.model_copy(update={"workflow": None}), eid) if case.calculation else None}

            for case in CASES.values()

        ],

    }





@router.get("/engagements/{eid}/use-cases/{identifier}/contract")

async def business_advanced_contract(eid: uuid.UUID, identifier: int, db: DB, ctx: Actor):

    from app.modules.enterprise_ai.business import case_scope

    from app.modules.jurisdictions.ae.advanced import Schedule, ROW_MODELS

    from app.modules.jurisdictions.ae.advanced_specs import spec

    await case_scope(db, ctx, eid, identifier)

    if identifier < 51:

        raise HTTPException(422, "Advanced contracts belong to cases 51–200")

    return {**spec(identifier), "schedule_schema":Schedule.model_json_schema(), "row_schema":ROW_MODELS[identifier].model_json_schema(), "execution_action":"advanced-review", "input_kind":"working-papers", "independent_approval_required":True}





@router.get("/engagements/{eid}/use-cases/{identifier}/alerts")

async def business_source_alerts(eid: uuid.UUID, identifier: int, db: DB, ctx: Actor):

    from app.modules.enterprise_ai.business import case_scope

    from app.modules.jurisdictions.ae.advanced_lineage import inbox

    await case_scope(db, ctx, eid, identifier)

    return await inbox(db, ctx, eid, identifier)





@router.get("/engagements/{eid}/use-cases/{identifier}/inputs")

async def business_inputs(eid: uuid.UUID, identifier: int, db: DB, ctx: Actor):

    from app.modules.enterprise_ai.business import inputs



    return await inputs(db, ctx, eid, identifier)





@router.post("/engagements/{eid}/use-cases/{identifier}/actions", status_code=201)

async def business_action(eid: uuid.UUID, identifier: int, data: Execute, db: DB, ctx: Actor):

    from pydantic import ValidationError



    from app.modules.enterprise_ai.business import execute



    try:

        return await execute(db, ctx, eid, identifier, data, "business:" + data.idempotency_key)

    except ValidationError as exc:

        raise HTTPException(422, exc.errors(include_context=False)) from None

    except (ValueError, ArithmeticError) as exc:

        raise HTTPException(422, str(exc)) from None





@router.get("/engagements/{eid}/use-cases/{identifier}/source-records/{record_id}")

async def business_source_record(eid: uuid.UUID, identifier: int, record_id: uuid.UUID, db: DB, ctx: Actor):

    from app.modules.audit_execution import service as audit

    from app.modules.enterprise_ai.business import case_scope

    await case_scope(db, ctx, eid, identifier)

    record = await audit.get_record(db, ctx, eid, record_id, lock=False)

    return audit.serialize(record)





@router.get("/agents")

async def registry(ctx: Actor):

    return {

        "items": agents(),

        "templates": RECIPES,

        "limits": {"tools": 12, "parallelism": 1, "depth": 1, "step_seconds": 90},

        "semantic_provider": "Existing gateway; deterministic collection does not invoke a model",

    }





@router.get("/tools")

async def tools(ctx: Actor):

    from app.modules.enterprise_ai.schemas import ToolInput



    return {

        "controlled_actions": {

            "schema": Execute.model_json_schema(),

            "endpoint": "/ai/engagements/{engagement_id}/use-cases/{use_case_id}/actions",

            "execution": "Explicit authorized requests only; same services and approval controls as specialist UI",

            "consequential_actions": "Posting, sending, filing and bank changes are excluded",

        },

        "items": [

            {"id": k, "agent": v[0], "permission": v[1], "read_only": True,

             "consequence": "read_only", "input_schema": ToolInput.model_json_schema(),

             "scope": "server-authorized tenant/entity/engagement/period; caller cannot override tenant"}

            for k, v in TOOLS.items()

        ],

    }





@router.post("/command", status_code=201)

async def command(data: Command, db: DB, ctx: Actor):

    return serialize(await service.create(db, ctx, data))





@router.get("/engagements/{eid}/investigations")

async def investigations(

    eid: uuid.UUID,

    db: DB,

    ctx: Actor,

    limit: int = Query(50, ge=1, le=100),

    offset: int = Query(0, ge=0),

):

    await scope(db, ctx, eid)

    where = [

        Workflow.tenant_id == ctx.tenant_id,

        Workflow.engagement_id == eid,

        Workflow.created_by == ctx.user_id,

        Workflow.task != "readonly-template",

    ]

    rows = (

        await db.scalars(

            select(Workflow)

            .where(*where)

            .order_by(Workflow.created_at.desc())

            .limit(limit)

            .offset(offset)

        )

    ).all()

    # List only metadata: result content requires reauthorization on detail read.

    return {

        "items": [

            {

                "id": str(o.id),

                "task": o.task,

                "state": o.state,

                "version": o.version,

                "created_at": o.created_at.isoformat(),

            }

            for o in rows

        ],

        "total": await db.scalar(select(func.count()).select_from(Workflow).where(*where)),

    }





@router.get("/engagements/{eid}/investigations/{identifier}")

async def detail(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    run = await service.get(db, ctx, eid, identifier)

    rows = await service.history(db, ctx, run)

    return {**serialize(run), "events": [serialize(r) for r in rows]}





@router.post("/engagements/{eid}/investigations/{identifier}/step")

async def advance(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    return serialize(await service.step(db, ctx, eid, identifier))





@router.get("/engagements/{eid}/investigations/{identifier}/export/{kind}")

async def export(eid: uuid.UUID, identifier: uuid.UUID, kind: str, db: DB, ctx: Actor):

    from fastapi.responses import Response



    from app.modules.enterprise_ai.reporting import report



    await scope(db, ctx, eid, "audit.export")

    run = await service.get(db, ctx, eid, identifier)

    if run.state not in {"COMPLETED", "PARTIALLY_COMPLETED"} or kind not in {"pdf", "docx"}:

        raise HTTPException(422, "Completed source collection and PDF/DOCX format required")

    rows = await service.history(db, ctx, run)

    data = report(run, rows, kind)

    media = (

        "application/pdf"

        if kind == "pdf"

        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    )

    return Response(

        data,

        media_type=media,

        headers={

            "Content-Disposition": f'attachment; filename="investigation-{identifier}.{kind}"',

            "Content-Security-Policy": "sandbox; default-src 'none'",

        },

    )





@router.get("/engagements/{eid}/workspace")

async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):

    from app.modules.audit_execution.access import engagement_permissions



    eng = await scope(db, ctx, eid)

    permissions, roles = await engagement_permissions(db, ctx, eid, "ai.investigation.read")

    return {

        "engagement": serialize(eng),

        "permissions": sorted(permissions),

        "roles": sorted(roles),

        "capabilities": {

            "retrieval": "keyword",

            "semantic": "NOT_CONFIGURED",

            "ocr": "NOT_CONFIGURED",

            "consequential_executor": "create-draft-workpaper only",

            "external_model": "Explicit draft through approved existing gateway",

        },

    }





@router.post("/engagements/{eid}/investigations/{identifier}/draft")

async def draft(

    eid: uuid.UUID,

    identifier: uuid.UUID,

    db: DB,

    ctx: Actor,

    model: str = Query("mock-diagnostic", max_length=200),

):

    from app.modules.enterprise_ai.narrative import draft as generate



    return serialize(await generate(db, ctx, eid, identifier, model))





@router.post("/engagements/{eid}/investigations/{identifier}/dispatch", status_code=202)

async def dispatch(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    run = await service.get(db, ctx, eid, identifier, "ai.workflow.run")

    if run.task == "readonly-template":

        raise HTTPException(409, "Create a run from the template first")

    await service.history(db, ctx, run)

    await service.locked(db, ctx, str(identifier))

    if not await db.scalar(

        select(Event.id).where(

            Event.tenant_id == ctx.tenant_id, Event.run_id == identifier, Event.key == "queued"

        )

    ):

        await service.event(db, ctx, run, "queued", "queued", {"authorized_by": str(ctx.user_id)})

    await db.commit()

    from app.workers.enterprise_ai import work



    try:

        work.apply_async(

            args=[str(ctx.tenant_id), str(ctx.user_id), str(eid), str(identifier)],

            queue="enterprise-ai",

        )

    except Exception:

        raise HTTPException(

            503, "Broker unavailable; durable investigation can be redispatched"

        ) from None

    return {"id": str(identifier), "status": run.state}





@router.post("/engagements/{eid}/investigations/{identifier}/control")

async def control(eid: uuid.UUID, identifier: uuid.UUID, data: Control, db: DB, ctx: Actor):

    await service.locked(db, ctx, str(identifier))

    run = await service.get(db, ctx, eid, identifier, "ai.workflow.run")

    if run.task == "readonly-template":

        raise HTTPException(409, "Template configuration is immutable; save a new version")

    if run.version != data.version or run.state in service.TERMINAL:

        raise HTTPException(409, "Stale control or terminal workflow")

    if data.action == "resume":

        await service.history(db, ctx, run)

    run.state = {"pause": "PAUSED", "resume": "RESUMING", "cancel": "CANCELLED"}[data.action]

    await service.event(

        db, ctx, run, "control:" + str(run.version), "control", {"action": data.action}

    )

    await db.flush()

    await db.refresh(run)

    return serialize(run)





@router.post("/engagements/{eid}/approvals", status_code=201)

async def propose(eid: uuid.UUID, data: ProposalInput, db: DB, ctx: Actor):

    return serialize(await service.propose(db, ctx, eid, data))





@router.get("/engagements/{eid}/approvals")

async def approvals(eid: uuid.UUID, db: DB, ctx: Actor):

    permissions, _ = await __import__(

        "app.modules.audit_execution.access", fromlist=["engagement_permissions"]

    ).engagement_permissions(db, ctx, eid, "ai.investigation.read")

    where = [Proposal.tenant_id == ctx.tenant_id, Proposal.engagement_id == eid]

    if "ai.approval.decide" not in permissions:

        where.append(Proposal.created_by == ctx.user_id)

    rows = (

        await db.scalars(

            select(Proposal).where(*where).order_by(Proposal.created_at.desc()).limit(100)

        )

    ).all()

    items = []

    for obj in rows:

        try:

            await validate_dependencies(db, ctx, eid, obj.dependencies)

            items.append(serialize(obj))

        except HTTPException:

            # Do not disclose stale or no-longer-authorized source-bearing payloads.

            items.append(

                {"id": str(obj.id), "state": "SOURCE_UNAVAILABLE", "payload_redacted": True}

            )

    return {"items": items}





@router.post("/engagements/{eid}/approvals/{identifier}/decision")

async def decision(eid: uuid.UUID, identifier: uuid.UUID, data: Decision, db: DB, ctx: Actor):

    return serialize(await service.decide(db, ctx, eid, identifier, data))





@router.post("/engagements/{eid}/approvals/{identifier}/execute")

async def execute(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    return serialize(await service.execute_proposal(db, ctx, eid, identifier))





@router.post("/engagements/{eid}/documents", status_code=201)

async def extract(eid: uuid.UUID, data: ExtractInput, db: DB, ctx: Actor):

    return serialize(await documents.extract(db, ctx, eid, data))





@router.get("/engagements/{eid}/documents")

async def document_list(eid: uuid.UUID, db: DB, ctx: Actor):

    await scope(db, ctx, eid)

    rows = (

        await db.scalars(

            select(Extraction)

            .where(Extraction.tenant_id == ctx.tenant_id, Extraction.engagement_id == eid)

            .order_by(Extraction.created_at.desc())

            .limit(100)

        )

    ).all()

    items = []

    for row in rows:

        try:

            await documents.authorized_extraction(db, ctx, eid, row.id)

        except HTTPException:

            continue

        items.append(serialize(row))

    return {"items": items}





@router.post("/engagements/{eid}/documents/{identifier}/corrections", status_code=201)

async def correction(eid: uuid.UUID, identifier: uuid.UUID, data: Correction, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.documents.index")

    old = await documents.authorized_extraction(db, ctx, eid, identifier)

    if not set(data.fields) <= set(documents.FIELD_PATTERNS) or any(

        len(v) > 500 for v in data.fields.values()

    ):

        raise HTTPException(422, "Supported bounded fields required")

    documents.validate_corrections(data.fields)

    body = copy.deepcopy(old.body)

    for key, value in data.fields.items():

        if key not in body["fields"]:

            raise HTTPException(422, "Correction needs an existing page-linked field")

        body["fields"][key] = {

            **body["fields"][key],

            "value": value,

            "method": "human_correction",

            "quality": "unverified",

        }

    body["correction"] = {"reason": data.reason, "user_id": str(ctx.user_id), "parent": str(old.id)}

    obj, version = await documents.latest_evidence(db, ctx, eid, old.record_id)

    return serialize(

        await documents.save(

            db, ctx, eid, obj, version, body, old.classification, old.confidentiality, old.id

        )

    )





@router.get("/engagements/{eid}/documents/{identifier}/matches")

async def matches(

    eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor, journal_id: uuid.UUID | None = None

):

    from app.modules.enterprise_ai.schemas import ToolInput

    from app.modules.enterprise_ai.tools import invoke



    extraction = await documents.authorized_extraction(db, ctx, eid, identifier)

    result = await invoke(db, ctx, eid, "financial.get_general_ledger", ToolInput(limit=50))

    if journal_id:

        from app.api.v1.accounting import serialize as financial_serial

        from app.modules.enterprise_ai.tools import journal_source



        result.data = {"items": [financial_serial(await journal_source(db, ctx, eid, journal_id))]}

    items = [

        {"journal_id": row["id"], **documents.match_signals(extraction.body["fields"], row)}

        for row in result.data.get("items", [])

    ]

    for item in items:

        item["signals_hash"] = digest(

            {

                "extraction": str(identifier),

                "journal": item["journal_id"],

                "signals": item["signals"],

            }

        )

    return {

        "items": sorted(items, key=lambda x: -x["score"]),

        "coverage": "First 50 active ledger lines; candidate suggestions only",

        "extraction_id": str(identifier),

    }





@router.post("/engagements/{eid}/documents/{identifier}/matches", status_code=201)

async def match_decision(

    eid: uuid.UUID, identifier: uuid.UUID, data: MatchInput, db: DB, ctx: Actor

):

    from app.api.v1.accounting import serialize as financial_serial

    from app.modules.enterprise_ai.models import MatchDecision

    from app.modules.enterprise_ai.tools import journal_source



    await scope(db, ctx, eid, "audit.evidence.review")

    ext = await documents.authorized_extraction(db, ctx, eid, identifier)

    journal = await journal_source(db, ctx, eid, data.journal_id)

    signals = documents.match_signals(ext.body["fields"], financial_serial(journal))

    expected = digest(

        {

            "extraction": str(identifier),

            "journal": str(data.journal_id),

            "signals": signals["signals"],

        }

    )

    if data.signals_hash != expected:

        raise HTTPException(409, "Match signals changed")

    body = {

        **data.model_dump(mode="json"),

        "signals": signals,

        "auditor_conclusion": data.decision,

        "record_version": ext.record_version,

        "source_hash": ext.source_hash,

        "source_accounting_modified": False,

    }

    key = digest(body)

    await service.locked(db, ctx, "match:" + key)

    old = await db.scalar(

        select(MatchDecision).where(

            MatchDecision.tenant_id == ctx.tenant_id,

            MatchDecision.created_by == ctx.user_id,

            MatchDecision.payload_hash == key,

        )

    )

    if old:

        return serialize(old)

    obj = MatchDecision(

        tenant_id=ctx.tenant_id,

        created_by=ctx.user_id,

        engagement_id=eid,

        extraction_id=identifier,

        journal_id=data.journal_id,

        payload_hash=key,

        body=body,

    )

    db.add(obj)

    await db.flush()

    return serialize(obj)





@router.get("/engagements/{eid}/knowledge/search")

async def search(

    eid: uuid.UUID, db: DB, ctx: Actor, query: str = Query(min_length=1, max_length=200)

):

    return {

        "items": await documents.search(db, ctx, eid, query),

        "retrieval": "keyword",

        "semantic": "NOT_CONFIGURED",

        "regulatory_corpus": "No licensed or official text indexed automatically",

    }





@router.get("/engagements/{eid}/citations/{identifier}")

async def citation(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    return await documents.authorized_chunk(db, ctx, eid, identifier)





@router.post("/engagements/{eid}/citations/verify")

async def verify_citation(eid: uuid.UUID, data: CitationInput, db: DB, ctx: Actor):

    from app.modules.enterprise_ai.security import source

    from app.modules.enterprise_ai.tools import calculation_source, journal_source, snapshot_source



    await scope(db, ctx, eid)

    if data.kind == "chunk":

        return {"verified": True, "source": await documents.authorized_chunk(db, ctx, eid, data.id)}

    if data.kind == "record":

        obj = await source(db, ctx, eid, data.id)

        if data.version and obj.version != data.version:

            raise HTTPException(409, "Citation version is stale")

        result = {

            "id": str(obj.id),

            "kind": obj.kind,

            "version": obj.version,

            "reference": obj.reference,

            "status": obj.status,

            "body": obj.body,

        }

    elif data.kind == "journal":

        from app.api.v1.accounting import serialize as finance_serial



        result = finance_serial(await journal_source(db, ctx, eid, data.id))

    elif data.kind == "snapshot":

        obj = await snapshot_source(db, ctx, eid, data.id)

        result = {

            "id": str(obj.id),

            "sha256": obj.sha256,

            "entity_id": str(obj.entity_id),

            "period_id": str(obj.period_id),

            "current": True,

        }

    elif data.kind == "ml":

        from app.modules.ml.service import get



        obj = await get(db, ctx, data.id)

        if obj.engagement_id != eid:

            raise HTTPException(404, "Resource unavailable")

        result = {

            "id": str(obj.id),

            "kind": obj.kind,

            "sha256": obj.sha256,

            "detail": "Use the existing ML resource workspace for artifact-controlled prediction detail",

        }

    else:

        obj = await calculation_source(db, ctx, eid, data.kind, data.id)

        result = {"id": str(obj.id), "kind": obj.kind, "sha256": obj.sha256, "results": obj.results}

    return {"verified": True, "source": result, "professional_conclusion": False}





@router.get("/knowledge/sources")

async def regulatory_sources(ctx: Actor):

    from app.modules.dmtt.service import SOURCES as DMTT

    from app.modules.grc.catalogue import FRAMEWORKS

    from app.modules.tp.catalogue import SOURCES as TP

    from app.modules.vat.catalogue import SOURCES as VAT



    return {

        "official_source_metadata": {"vat": VAT, "transfer_pricing": TP, "dmtt": DMTT},

        "framework_metadata": FRAMEWORKS,

        "text_corpus": "NOT_INGESTED",

        "freshness": "Inherited versioned module registry metadata; verify original official publication and applicable period. Retired entries retain their lifecycle marker; metadata is not current legal advice.",

        "licensed_ifrs_isa_text": "NOT_AVAILABLE",

    }





@router.post("/engagements/{eid}/workflows/validate")

async def graph(eid: uuid.UUID, data: Graph, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.workflow.run")

    try:

        validate_graph(data)

    except ValueError as exc:

        raise HTTPException(422, str(exc)) from None

    for tool in data.nodes:

        await scope(db, ctx, eid, TOOLS[tool][1])

    return {

        "valid": True,

        "graph_hash": digest(data.model_dump()),

        "activation": "Validated read-only graph may be saved and explicitly activated by an authorized AI configurator",

    }





@router.post("/engagements/{eid}/workflows", status_code=201)

async def save_template(eid: uuid.UUID, data: TemplateInput, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.agent.configure")

    try:

        validate_graph(data)

    except ValueError as exc:

        raise HTTPException(422, str(exc)) from None

    for tool in data.nodes:

        await scope(db, ctx, eid, TOOLS[tool][1])

    await service.locked(db, ctx, "template:" + data.idempotency_key)

    existing = await db.scalar(

        select(Workflow).where(

            Workflow.tenant_id == ctx.tenant_id,

            Workflow.created_by == ctx.user_id,

            Workflow.idempotency_key == "template:" + data.idempotency_key,

        )

    )

    if existing:

        if existing.outputs.get("graph_hash") != digest(data.model_dump()):

            raise HTTPException(409, "Template idempotency payload differs")

        return serialize(existing)

    obj = Workflow(

        tenant_id=ctx.tenant_id,

        created_by=ctx.user_id,

        engagement_id=eid,

        idempotency_key="template:" + data.idempotency_key,

        task="readonly-template",

        prompt=data.title,

        state="TEMPLATE_ACTIVE",

        plan=data.nodes,

        inputs={},

        outputs={

            "graph": data.model_dump(),

            "graph_hash": digest(data.model_dump()),

            "tools_read_only": True,

            "activation": "Explicit authorized configuration; no confidential processing until run",

        },

    )

    db.add(obj)

    await db.flush()

    await service.event(

        db,

        ctx,

        obj,

        "template:activated",

        "template-activated",

        {"graph_hash": obj.outputs["graph_hash"], "actor": str(ctx.user_id)},

    )

    return serialize(obj)





@router.get("/engagements/{eid}/workflows")

async def templates(eid: uuid.UUID, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.workflow.run")

    rows = (

        await db.scalars(

            select(Workflow)

            .where(

                Workflow.tenant_id == ctx.tenant_id,

                Workflow.engagement_id == eid,

                Workflow.created_by == ctx.user_id,

                Workflow.task == "readonly-template",

            )

            .order_by(Workflow.created_at.desc())

            .limit(50)

        )

    ).all()

    return {"items": [serialize(row) for row in rows]}





@router.get("/providers")

async def providers(db: DB, ctx: Annotated[Context, Depends(require("ai.provider.manage"))]):

    if "ai.provider.manage" not in ctx.permissions:

        raise HTTPException(403, "AI provider administration permission required")

    rows = (

        (

            await db.execute(

                select(

                    AIModelConfiguration.name,

                    AIModelConfiguration.max_tokens,

                    AIModelConfiguration.enabled,

                    AIProviderConfig.adapter,

                ).join(AIProviderConfig, AIModelConfiguration.provider_id == AIProviderConfig.id)

            )

        )

        .mappings()

        .all()

    )

    return {

        "items": [dict(r) for r in rows],

        "configuration": "Existing gateway controls; credentials are never returned",

    }





@router.get("/engagements/{eid}/usage")

async def usage(eid: uuid.UUID, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.usage.read")

    count = await db.scalar(

        select(func.count())

        .select_from(Event)

        .where(

            Event.tenant_id == ctx.tenant_id,

            Event.engagement_id == eid,

            Event.kind == "step",

            Event.created_by == ctx.user_id,

        )

    )

    from sqlalchemy import Uuid



    from app.db.models.platform import AIUsageRecord



    executions = select(Event.body["execution_id"].astext.cast(Uuid)).where(

        Event.tenant_id == ctx.tenant_id,

        Event.engagement_id == eid,

        Event.kind == "narrative",

        Event.created_by == ctx.user_id,

    )

    usages = (

        await db.scalars(

            select(AIUsageRecord).where(

                AIUsageRecord.tenant_id == ctx.tenant_id, AIUsageRecord.execution_id.in_(executions)

            )

        )

    ).all()

    tokens = (

        None

        if any(x.input_tokens is None or x.output_tokens is None for x in usages)

        else sum((x.input_tokens or 0) + (x.output_tokens or 0) for x in usages)

    )

    return {

        "deterministic_steps": count,

        "model_tokens": tokens,

        "usage_sources": sorted({x.usage_source for x in usages}),

        "provider_cost": "NOT_CONFIGURED" if usages else "0",

        "basis": "Deterministic tools use no model tokens; narratives join actual existing gateway usage. Mock word estimates are not provider tokens. No configured price means no invented monetary cost.",

    }





@router.post("/engagements/{eid}/investigations/{identifier}/evaluate")

async def evaluate(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    from app.modules.enterprise_ai.evaluation import evaluate as run_evaluation



    await scope(db, ctx, eid, "ai.model.evaluate")

    run = await service.get(db, ctx, eid, identifier)

    await service.locked(db, ctx, f"evaluation:{identifier}")

    old = await db.scalar(

        select(Event).where(

            Event.tenant_id == ctx.tenant_id,

            Event.run_id == identifier,

            Event.key == "evaluation/v1",

        )

    )

    return serialize(

        old or await service.event(db, ctx, run, "evaluation/v1", "evaluation", run_evaluation())

    )





@router.get("/engagements/{eid}/security-events")

async def security_events(eid: uuid.UUID, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.auditlog.read")

    rows = (

        await db.scalars(

            select(Event)

            .where(Event.tenant_id == ctx.tenant_id, Event.engagement_id == eid)

            .order_by(Event.created_at.desc())

            .limit(100)

        )

    ).all()

    return {

        "items": [

            {

                "id": str(r.id),

                "run_id": str(r.run_id),

                "kind": r.kind,

                "sha256": r.sha256,

                "created_at": r.created_at.isoformat(),

            }

            for r in rows

        ]

    }





@router.post("/engagements/{eid}/schedules", status_code=201)

async def schedule(eid: uuid.UUID, data: ScheduleInput, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.workflow.schedule")

    if data.task not in RECIPES or data.next_due.tzinfo is None:

        raise HTTPException(422, "Supported task and timezone-aware next_due required")

    for tool in RECIPES[data.task]:

        await scope(db, ctx, eid, TOOLS[tool][1])

    obj = Schedule(

        tenant_id=ctx.tenant_id,

        created_by=ctx.user_id,

        engagement_id=eid,

        task=data.task,

        frequency=data.frequency,

        next_due=data.next_due,

        active=data.active,

        inputs=data.inputs.model_dump(mode="json"),

    )

    db.add(obj)

    await db.flush()

    return serialize(obj)





@router.get("/engagements/{eid}/schedules")

async def schedules(eid: uuid.UUID, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.workflow.schedule")

    rows = (

        await db.scalars(

            select(Schedule)

            .where(

                Schedule.tenant_id == ctx.tenant_id,

                Schedule.engagement_id == eid,

                Schedule.created_by == ctx.user_id,

            )

            .limit(100)

        )

    ).all()

    return {"items": [serialize(r) for r in rows]}





@router.post("/engagements/{eid}/schedules/{identifier}/pause")

async def pause_schedule(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):

    await scope(db, ctx, eid, "ai.workflow.schedule")

    obj = await db.scalar(

        select(Schedule)

        .where(

            Schedule.tenant_id == ctx.tenant_id,

            Schedule.engagement_id == eid,

            Schedule.created_by == ctx.user_id,

            Schedule.id == identifier,

        )

        .with_for_update()

    )

    if not obj:

        raise HTTPException(404, "Resource unavailable")

    obj.active = False

    await db.flush()

    await db.refresh(obj)

    return serialize(obj)

