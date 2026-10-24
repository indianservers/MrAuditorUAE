import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from app.core.dependencies import DB, Context, require
from app.db.models.platform import Engagement, LegalEntity
from app.modules.audit_log.service import record
from app.modules.jurisdictions import workspace as platform
from app.modules.jurisdictions.models import (
    CountryPreference,
    GraphLayout,
    GroupRelationship,
    OrganizationJurisdiction,
    ReportingContextEvent,
)
from app.modules.jurisdictions.packages import RELEASES, package
from app.modules.jurisdictions.profiles import Strict, profile

router = APIRouter(prefix="/jurisdictions", tags=["Country packages"])
Actor = Annotated[Context, Depends(require(""))]


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(pattern=r"^[A-Z]{2}$")
    version: int = Field(ge=0)


@router.get("/packages")
async def packages(ctx: Actor):
    return {
        "items": [package(c) for c in sorted(RELEASES, key=lambda c: RELEASES[c]["name"])],
        "default_country": "AE",
    }


@router.get("/settings")
async def settings(db: DB, ctx: Actor):
    row = await db.scalar(
        select(CountryPreference).where(
            CountryPreference.tenant_id == ctx.tenant_id, CountryPreference.user_id == ctx.user_id
        )
    )
    organization = await db.scalar(
        select(OrganizationJurisdiction).where(OrganizationJurisdiction.tenant_id == ctx.tenant_id)
    )
    country = row.country if row else organization.country if organization else "AE"
    return {
        "country": country,
        "version": row.version if row else 0,
        "package": package(country),
        "profile": profile(country).model_dump(mode="json"),
        "scope": "Current user in this firm; engagement history is unchanged",
    }


@router.patch("/settings")
async def update_settings(data: Preference, db: DB, ctx: Actor, request: Request):
    package(data.country)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"country:{ctx.tenant_id}:{ctx.user_id}"},
    )
    row = await db.scalar(
        select(CountryPreference)
        .where(
            CountryPreference.tenant_id == ctx.tenant_id, CountryPreference.user_id == ctx.user_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if data.version != (row.version if row else 0):
        raise HTTPException(409, "Country preference version conflict; reload settings")
    if row:
        row.country = data.country
        row.version += 1
    else:
        row = CountryPreference(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            user_id=ctx.user_id,
            country=data.country,
        )
        db.add(row)
    await db.flush()
    record(
        db,
        ctx,
        "workspace.country.changed",
        row.id,
        request.state.request_id,
        {"country": row.country, "version": row.version},
    )
    return await settings(db, ctx)


@router.get("/profiles/{country}")
async def profile_details(country: str, ctx: Actor):
    return profile(country)


@router.get("/organization")
async def organization_settings(db: DB, ctx: Actor):
    row = await db.scalar(
        select(OrganizationJurisdiction).where(OrganizationJurisdiction.tenant_id == ctx.tenant_id)
    )
    return {
        "country": row.country if row else "AE",
        "version": row.version if row else 0,
        "can_manage": "tenant.manage" in ctx.permissions,
    }


@router.patch("/organization")
async def organization_update(
    data: Preference,
    db: DB,
    ctx: Annotated[Context, Depends(require("tenant.manage"))],
    request: Request,
):
    package(data.country)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"organization-country:{ctx.tenant_id}"},
    )
    row = await db.scalar(
        select(OrganizationJurisdiction)
        .where(OrganizationJurisdiction.tenant_id == ctx.tenant_id)
        .with_for_update()
    )
    if data.version != (row.version if row else 0):
        raise HTTPException(409, "Organization settings version conflict")
    if row:
        row.country = data.country
        row.version += 1
    else:
        db.add(
            OrganizationJurisdiction(
                tenant_id=ctx.tenant_id, created_by=ctx.user_id, country=data.country
            )
        )
    await db.flush()
    record(
        db,
        ctx,
        "organization.country.changed",
        ctx.tenant_id,
        request.state.request_id,
        {"country": data.country},
    )
    return await organization_settings(db, ctx)


@router.get("/modules")
async def module_registry(
    db: DB,
    ctx: Actor,
    country: str = "AE",
    eid: uuid.UUID | None = None,
    search: str = Query("", max_length=200),
):
    return await platform.modules(db, ctx, country, eid, search)


@router.get("/engagements/{eid}/workspace")
async def engagement_workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    return await platform.workspace(db, ctx, eid)


@router.get("/engagements/{eid}/lifecycle")
async def engagement_lifecycle(eid: uuid.UUID, db: DB, ctx: Actor):
    return await platform.lifecycle(db, ctx, eid)


@router.get("/engagements/{eid}/activity")
async def engagement_activity(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.db.models.platform import AuditEvent
    from app.modules.audit_execution import service as audit
    from app.modules.audit_execution.models import AuditRecord

    await audit.engagement(db, ctx, eid, lock=False)
    ids = [eid]
    rows = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.engagement_id == eid
            )
        )
    ).all()
    for row in rows:
        try:
            await audit.get_record(db, ctx, eid, row.id, lock=False)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        ids.append(row.id)
    events = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == ctx.tenant_id, AuditEvent.resource_id.in_(ids))
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(e.id),
                "action": e.action,
                "created_at": e.created_at.isoformat(),
                "actor": str(e.created_by),
                "resource_id": str(e.resource_id),
            }
            for e in events
        ],
        "limit": 100,
    }


@router.get("/engagements/{eid}/context")
async def reporting_context(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.audit_execution import service as audit

    eng = await audit.engagement(db, ctx, eid, lock=False)
    _, current = await platform.resolved(db, ctx, eng)
    events = (
        await db.scalars(
            select(ReportingContextEvent)
            .where(
                ReportingContextEvent.tenant_id == ctx.tenant_id,
                ReportingContextEvent.engagement_id == eid,
            )
            .order_by(ReportingContextEvent.created_at)
        )
    ).all()
    return {
        "current": current,
        "events": [audit.serialize(e) for e in events],
        "user_id": str(ctx.user_id),
    }


@router.post("/engagements/{eid}/context", status_code=201)
async def request_context(
    eid: uuid.UUID, data: platform.ContextInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.audit_execution import service as audit
    from app.modules.jurisdictions.packages import fingerprint

    eng = await audit.engagement(db, ctx, eid, "audit.plan", True)
    _, current = await platform.resolved(db, ctx, eng)
    if data.base_version != current["version"]:
        raise HTTPException(409, "Reporting context version conflict")
    config = profile(data.country)
    if len({d.rule_id for d in data.applicability}) != len(data.applicability) or any(
        d.rule_id not in {r.id for r in config.rules}
        or not set(d.source_ids) <= {s.id for s in config.sources}
        for d in data.applicability
    ):
        raise HTTPException(
            422,
            "Applicability decisions must reference unique registered rules and known primary sources",
        )
    if config.status == "CONFIGURED_PROFILE" and data.framework not in config.accounting_standards:
        raise HTTPException(422, "Select a framework from the configured country profile")
    manifest = package(data.country)
    event = ReportingContextEvent(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        kind="REQUESTED",
        body={
            **data.model_dump(mode="json"),
            "profile": config.model_dump(mode="json"),
            "manifest": manifest,
            "package_version": manifest["version"],
            "package_sha256": fingerprint(manifest),
        },
    )
    db.add(event)
    await db.flush()
    record(
        db,
        ctx,
        "reporting.context.requested",
        event.id,
        request.state.request_id,
        {"engagement_id": str(eid)},
    )
    return audit.serialize(event)


class Decision(Strict):
    request_id: uuid.UUID
    approve: bool
    comments: str = Field(min_length=10, max_length=4000)


@router.post("/engagements/{eid}/context/decision", status_code=201)
async def decide_context(eid: uuid.UUID, data: Decision, db: DB, ctx: Actor, request: Request):
    from app.modules.audit_execution import service as audit

    eng = await audit.engagement(db, ctx, eid, "workingpaper.review", True)
    original = await db.scalar(
        select(ReportingContextEvent).where(
            ReportingContextEvent.tenant_id == ctx.tenant_id,
            ReportingContextEvent.engagement_id == eid,
            ReportingContextEvent.id == data.request_id,
            ReportingContextEvent.kind == "REQUESTED",
        )
    )
    if not original:
        raise HTTPException(404, "Context request not found")
    if original.created_by == ctx.user_id:
        raise HTTPException(403, "Independent context reviewer required")
    prior = (
        await db.scalars(
            select(ReportingContextEvent).where(
                ReportingContextEvent.tenant_id == ctx.tenant_id,
                ReportingContextEvent.engagement_id == eid,
                ReportingContextEvent.kind.in_(["APPROVED", "REJECTED"]),
            )
        )
    ).all()
    if any(e.body["request_id"] == str(original.id) for e in prior):
        raise HTTPException(409, "Request already decided")
    _, current = await platform.resolved(db, ctx, eng)
    if original.body["base_version"] != current["version"]:
        raise HTTPException(409, "Context changed; request a new reviewed amendment")
    event = ReportingContextEvent(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        kind="APPROVED" if data.approve else "REJECTED",
        body={
            **original.body,
            "request_id": str(original.id),
            "version": current["version"] + 1,
            "reviewer": str(ctx.user_id),
            "comments": data.comments,
        },
    )
    db.add(event)
    await db.flush()
    record(
        db,
        ctx,
        "reporting.context.decided",
        event.id,
        request.state.request_id,
        {"engagement_id": str(eid), "approved": data.approve},
    )
    return audit.serialize(event)


class Position(Strict):
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class Layout(Strict):
    version: int = Field(ge=0)
    graph_version: str = Field(max_length=100)
    positions: dict[str, Position] = Field(max_length=1500)


@router.get("/engagements/{eid}/layout")
async def get_layout(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.audit_execution import service as audit

    await audit.engagement(db, ctx, eid, lock=False)
    row = await db.scalar(
        select(GraphLayout).where(
            GraphLayout.tenant_id == ctx.tenant_id,
            GraphLayout.engagement_id == eid,
            GraphLayout.user_id == ctx.user_id,
        )
    )
    return {
        "version": row.version if row else 0,
        **(row.body if row else {"positions": {}, "graph_version": platform.REGISTRY["version"]}),
    }


@router.patch("/engagements/{eid}/layout")
async def save_layout(eid: uuid.UUID, data: Layout, db: DB, ctx: Actor, request: Request):
    projection = await platform.lifecycle(db, ctx, eid)
    if data.graph_version != projection["graph_version"]:
        raise HTTPException(409, "Graph definition changed; reload layout")
    if not set(data.positions) <= {n["id"] for n in projection["nodes"]}:
        raise HTTPException(422, "Layout contains inaccessible or unknown nodes")
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"graph-layout:{ctx.tenant_id}:{ctx.user_id}:{eid}"},
    )
    row = await db.scalar(
        select(GraphLayout)
        .where(
            GraphLayout.tenant_id == ctx.tenant_id,
            GraphLayout.engagement_id == eid,
            GraphLayout.user_id == ctx.user_id,
        )
        .with_for_update()
    )
    if data.version != (row.version if row else 0):
        raise HTTPException(409, "Layout version conflict")
    body = data.model_dump(mode="json", exclude={"version"})
    if row:
        row.body = body
        row.version += 1
    else:
        db.add(
            GraphLayout(
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                user_id=ctx.user_id,
                engagement_id=eid,
                body=body,
            )
        )
    await db.flush()
    record(db, ctx, "audit.graph.layout.saved", eid, request.state.request_id)
    return await get_layout(eid, db, ctx)


async def visible_entities(db, ctx):
    from app.modules.audit_execution.access import visible_engagements

    engagements = await visible_engagements(db, ctx)
    query = select(LegalEntity).where(LegalEntity.tenant_id == ctx.tenant_id)
    if engagements is not None:
        query = query.where(
            LegalEntity.id.in_(
                select(Engagement.entity_id).where(
                    Engagement.tenant_id == ctx.tenant_id, Engagement.id.in_(engagements)
                )
            )
        )
    return (await db.scalars(query)).all()


@router.get("/groups")
async def groups(db: DB, ctx: Annotated[Context, Depends(require("entities.read"))]):
    from app.modules.audit_execution.service import serialize

    entities = await visible_entities(db, ctx)
    ids = {e.id for e in entities}
    relationships = (
        await db.scalars(
            select(GroupRelationship).where(
                GroupRelationship.tenant_id == ctx.tenant_id,
                GroupRelationship.parent_id.in_(ids),
                GroupRelationship.child_id.in_(ids),
            )
        )
    ).all()
    return {
        "entities": [
            {
                "id": str(e.id),
                "name": e.name,
                "country": e.country,
                "functional_currency": e.functional_currency,
            }
            for e in entities
        ],
        "relationships": [serialize(r) for r in relationships],
        "scope": "Both parent and child must be authorized; relationships do not determine consolidation or tax applicability automatically",
    }


@router.get("/search")
async def universal_search(
    db: DB, ctx: Actor, q: str = Query("", min_length=1, max_length=100), country: str = "AE"
):
    from app.db.models.platform import Client
    from app.modules.audit_execution import service as audit
    from app.modules.audit_execution.access import visible_engagements
    from app.modules.audit_execution.models import AuditRecord

    package(country)
    result = []
    registry = await platform.modules(db, ctx, country, search=q)
    for item in registry["items"][:30]:
        result.append(
            {
                "id": item["id"],
                "category": "Module",
                "label": item["name"] + " · " + item["availability"],
                "url": item["url"] or "/modules?search=" + item["name"],
            }
        )
    if "audit.read" not in ctx.permissions:
        return {"items": result, "truncated": False}
    visible = await visible_engagements(db, ctx)
    query = (
        select(Engagement)
        .join(LegalEntity, LegalEntity.id == Engagement.entity_id)
        .where(Engagement.tenant_id == ctx.tenant_id, LegalEntity.country == country)
    )
    if visible is not None:
        query = query.where(Engagement.id.in_(visible))
    authorized_ids = query.with_only_columns(Engagement.id)
    matched_query = query.where(
        Engagement.name.ilike(f"%{q}%")
        | LegalEntity.name.ilike(f"%{q}%")
        | LegalEntity.client_id.in_(
            select(Client.id).where(Client.tenant_id == ctx.tenant_id, Client.name.ilike(f"%{q}%"))
        )
    )
    engagements = (await db.scalars(matched_query.order_by(Engagement.id).limit(21))).all()
    for eng in engagements[:20]:
        await audit.engagement(db, ctx, eng.id, lock=False)
        entity = await db.get(LegalEntity, eng.entity_id)
        if entity is None:
            raise HTTPException(409, "Engagement entity unavailable")
        client = await db.get(Client, entity.client_id)
        if client is None:
            raise HTTPException(409, "Engagement client unavailable")
        for category, identifier, name, url in [
            ("Engagement", str(eng.id), eng.name, f"/engagements/{eng.id}/workspace"),
            ("Entity", str(entity.id), entity.name, "/clients"),
            ("Client", str(client.id), client.name, "/clients"),
        ]:
            if q.lower() in name.lower():
                result.append({"id": identifier, "category": category, "label": name, "url": url})
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id.in_(authorized_ids),
                (AuditRecord.title.ilike(f"%{q}%") | AuditRecord.reference.ilike(f"%{q}%")),
            )
            .order_by(AuditRecord.id)
            .limit(51)
        )
    ).all()
    for row in rows[:50]:
        try:
            await audit.get_record(db, ctx, row.engagement_id, row.id, lock=False)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        result.append(
            {
                "id": str(row.id),
                "category": "Findings"
                if row.kind == "findings"
                else "Reports"
                if row.kind.startswith("ifrs-")
                else "Working papers",
                "label": row.reference + ": " + row.title,
                "url": f"/engagements/{row.engagement_id}/{row.kind}?record={row.id}",
            }
        )
    if "accounting.read" in ctx.permissions:
        from app.modules.accounting.models import Account

        entity_ids = {e.id for e in await visible_entities(db, ctx) if e.country == country}
        account_rows = (
            await db.scalars(
                select(Account)
                .where(
                    Account.tenant_id == ctx.tenant_id,
                    Account.entity_id.in_(entity_ids),
                    (Account.name.ilike(f"%{q}%") | Account.code.ilike(f"%{q}%")),
                )
                .limit(20)
            )
        ).all()
        for account in account_rows:
            result.append(
                {
                    "id": str(account.id),
                    "category": "Ledger",
                    "label": account.code + " · " + account.name,
                    "url": "/financials/general-ledger?account=" + str(account.id),
                }
            )
    unique = {(r["category"], r["id"]): r for r in result}
    return {
        "items": list(unique.values())[:100],
        "truncated": len(engagements) > 20 or len(rows) > 50 or len(unique) > 100,
        "scope": "Bounded matches across authorized engagements in selected incorporation country; use full registers for exhaustive search",
    }


@router.get("/engagements/{eid}/node")
async def node_details(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    node_id: str = Query(max_length=100),
    direction: str = Query("upstream", pattern="^(upstream|downstream)$"),
):
    data = await platform.lifecycle(db, ctx, eid)
    node = next((n for n in data["nodes"] if n["id"] == node_id), None)
    if not node:
        raise HTTPException(404, "Authorized graph node not found in this projection")
    upstream = [e for e in data["edges"] if e["target"] == node_id]
    downstream = [e for e in data["edges"] if e["source"] == node_id]
    return {
        "node": node,
        "upstream": upstream,
        "downstream": downstream,
        "direction": direction,
        "truncated": data["truncated"],
        "graph_version": data["graph_version"],
    }


class Relationship(Strict):
    parent_id: uuid.UUID
    child_id: uuid.UUID
    ownership_percent: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=6)
    effective_from: date
    effective_to: date | None = None
    reason: str = Field(min_length=10, max_length=4000)


@router.post("/groups", status_code=201)
async def create_relationship(
    data: Relationship,
    db: DB,
    ctx: Annotated[Context, Depends(require("entities.write"))],
    request: Request,
):
    from app.modules.audit_execution.service import serialize

    ids = {e.id for e in await visible_entities(db, ctx)}
    if not {data.parent_id, data.child_id} <= ids:
        raise HTTPException(404, "Authorized entities not found")
    if data.parent_id == data.child_id or (
        data.effective_to and data.effective_to < data.effective_from
    ):
        raise HTTPException(422, "Invalid structural relationship or effective period")
    obj = GroupRelationship(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        parent_id=data.parent_id,
        child_id=data.child_id,
        status="IN_REVIEW",
        body=data.model_dump(mode="json"),
    )
    db.add(obj)
    await db.flush()
    record(db, ctx, "group.relationship.requested", obj.id, request.state.request_id, obj.body)
    return serialize(obj)


class RelationshipDecision(Strict):
    version: int = Field(ge=1)
    action: str = Field(pattern="^(approve|reject|archive)$")
    reason: str = Field(min_length=10, max_length=4000)


@router.patch("/groups/{rid}")
async def review_relationship(
    rid: uuid.UUID,
    data: RelationshipDecision,
    db: DB,
    ctx: Annotated[Context, Depends(require("tenant.manage"))],
    request: Request,
):
    from app.modules.audit_execution.service import serialize

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"group:{ctx.tenant_id}"},
    )
    obj = await db.scalar(
        select(GroupRelationship)
        .where(GroupRelationship.tenant_id == ctx.tenant_id, GroupRelationship.id == rid)
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Relationship not found")
    visible_ids = {e.id for e in await visible_entities(db, ctx)}
    if not {obj.parent_id, obj.child_id} <= visible_ids:
        raise HTTPException(404, "Authorized relationship not found")
    if obj.version != data.version:
        raise HTTPException(409, "Relationship version conflict")
    if obj.created_by == ctx.user_id:
        raise HTTPException(403, "Independent administrator review required")
    if data.action == "archive":
        if obj.status not in {"APPROVED", "REJECTED"}:
            raise HTTPException(409, "Decide the relationship before archival")
        obj.status = "ARCHIVED"
    else:
        if obj.status != "IN_REVIEW":
            raise HTTPException(409, "Only pending relationships can be decided")
        if data.action == "approve":
            rows = (
                await db.scalars(
                    select(GroupRelationship).where(
                        GroupRelationship.tenant_id == ctx.tenant_id,
                        GroupRelationship.status == "APPROVED",
                    )
                )
            ).all()
            adjacency: dict[uuid.UUID, set[uuid.UUID]] = {}
            for row in rows:
                if row.parent_id == obj.parent_id and row.child_id == obj.child_id:
                    raise HTTPException(
                        409, "An approved relationship already exists; archive before replacement"
                    )
                adjacency.setdefault(row.parent_id, set()).add(row.child_id)
            seen = set()
            pending = [obj.child_id]
            while pending:
                current = pending.pop()
                if current == obj.parent_id:
                    raise HTTPException(
                        409, "Structural group cycle requires separate professional assessment"
                    )
                if current not in seen:
                    seen.add(current)
                    pending.extend(adjacency.get(current, []))
        obj.status = "APPROVED" if data.action == "approve" else "REJECTED"
    obj.version += 1
    await db.flush()
    await db.refresh(obj)
    record(
        db,
        ctx,
        "group.relationship." + data.action,
        obj.id,
        request.state.request_id,
        {"reason": data.reason, "version": obj.version},
    )
    return serialize(obj)
