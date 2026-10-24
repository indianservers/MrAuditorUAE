"""Permission-filtered read projections and reviewed reporting context changes."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import func, select

from app.db.models.platform import Client, FinancialPeriod, LegalEntity
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.models import AuditRecord
from app.modules.jurisdictions.models import ReportingContextEvent
from app.modules.jurisdictions.packages import fingerprint, package
from app.modules.jurisdictions.profiles import (
    ApplicabilityDecision,
    JurisdictionProfile,
    Strict,
    profile,
    resolve_rules,
)


class Module(Strict):
    id: str
    category: str = Field(pattern="^(0[1-9]|1[0-3])$")
    name: str
    countries: list[str]
    route: str | None
    kind: str | None
    permission: str
    state: Literal["PLANNED", "AVAILABLE_SCOPED", "PHASE1"]
    description: str


REGISTRY = json.loads((Path(__file__).parent / "module_registry.json").read_text(encoding="utf8"))
MODULES = [Module.model_validate(row) for row in REGISTRY["items"]]
if len({m.id for m in MODULES}) != len(MODULES):
    raise ValueError("Duplicate module identifiers")


class ContextInput(Strict):
    country: str = Field(pattern="^[A-Z]{2}$")
    framework: str = Field(min_length=2, max_length=200)
    entity_type: str = Field(min_length=2, max_length=100)
    as_of: date
    base_version: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=4000)
    applicability: list[ApplicabilityDecision] = Field(default_factory=list, max_length=100)


async def resolved(db, ctx, eng):
    from app.modules.jurisdictions.service import original_binding

    initial = await original_binding(db, ctx, eng)
    events = (
        await db.scalars(
            select(ReportingContextEvent)
            .where(
                ReportingContextEvent.tenant_id == ctx.tenant_id,
                ReportingContextEvent.engagement_id == eng.id,
                ReportingContextEvent.kind == "APPROVED",
            )
            .order_by(ReportingContextEvent.created_at.desc(), ReportingContextEvent.id.desc())
        )
    ).all()
    if events:
        body = dict(max(events, key=lambda e: e.body["version"]).body)
        config = JurisdictionProfile.model_validate(body["profile"])
        body["rule_resolution"] = resolve_rules(
            config,
            date.fromisoformat(body["as_of"]),
            body["entity_type"],
            [ApplicabilityDecision.model_validate(d) for d in body.get("applicability", [])],
        )
        binding = SimpleNamespace(
            country=body["country"],
            package_version=body["package_version"],
            package_sha256=body["package_sha256"],
            manifest=body["manifest"],
        )
        return binding, body
    period = await db.get(FinancialPeriod, eng.period_id)
    return initial, {
        "version": 0,
        "country": initial.country,
        "framework": "UNCONFIGURED — professional selection required",
        "entity_type": "UNCONFIGURED",
        "as_of": period.end_date.isoformat(),
        "profile": profile(initial.country).model_dump(mode="json"),
        "initial_package_version": initial.package_version,
    }


async def modules(db, ctx, country, eid=None, search=""):
    package(country)
    codes = ctx.permissions
    counts: dict[str, int] = {}
    if eid:
        eng = await audit.engagement(db, ctx, eid, lock=False)
        binding, _ = await resolved(db, ctx, eng)
        country = binding.country
        codes, _ = await engagement_permissions(db, ctx, eid, "audit.read")
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
                counts[row.kind] = counts.get(row.kind, 0) + 1
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
    items = []
    for item in MODULES:
        if search.lower() not in (item.name + " " + item.description).lower():
            continue
        row = item.model_dump()
        available = not item.countries or country in item.countries
        permitted = item.permission in codes
        row["availability"] = (
            "UNAVAILABLE_COUNTRY"
            if not available
            else "RESTRICTED"
            if not permitted
            else item.state
        )
        row["url"] = (
            item.route.replace("{eid}", str(eid))
            if item.route and available and permitted and (eid or "{eid}" not in item.route)
            else None
        )
        row["requires_engagement"] = bool(item.route and "{eid}" in item.route and not eid)
        row["record_count"] = counts.get(item.kind or "", 0) if eid and permitted else None
        items.append(row)
    return {
        "version": REGISTRY["version"],
        "country": country,
        "categories": REGISTRY["categories"],
        "items": items,
    }


async def workspace(db, ctx, eid):
    eng = await audit.engagement(db, ctx, eid, lock=False)
    entity = await db.get(LegalEntity, eng.entity_id)
    period = await db.get(FinancialPeriod, eng.period_id)
    client = await db.get(Client, entity.client_id)
    binding, context = await resolved(db, ctx, eng)
    from app.modules.lineage.working_papers import graph

    projection = await graph(db, ctx, eid)
    records = [n for n in projection["nodes"] if n["type"] == "record"]
    permissions, _ = await engagement_permissions(db, ctx, eid, "audit.read")
    mapping = None
    if "accounting.read" in permissions:
        from app.modules.accounting.models import Account

        total, mapped = (
            await db.execute(
                select(func.count(Account.id), func.count(Account.classification)).where(
                    Account.tenant_id == ctx.tenant_id, Account.entity_id == entity.id
                )
            )
        ).one()
        mapping = {
            "total": total,
            "mapped": mapped,
            "source": "accounting/accounts?entity_id=" + str(entity.id),
        }
    counts: dict[str, int] = {}
    for row in records:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    blockers = [
        {"id": n["id"], "label": n["label"], "reason": n["freshness"], "url": n.get("url")}
        for n in projection["nodes"]
        if n["freshness"] != "CURRENT"
    ]
    if context["version"] == 0:
        blockers.insert(
            0,
            {
                "id": "reporting-context",
                "label": "Reporting context needs independent review",
                "reason": "UNCONFIGURED",
            },
        )
    completion = await audit.completion(db, ctx, eid)
    for check in completion["checks"]:
        if not check["passed"]:
            blockers.append(
                {
                    "id": "readiness:" + check["code"],
                    "label": check.get("description") or check["code"].replace("_", " "),
                    "reason": "REVIEW_REQUIRED",
                    "url": f"/engagements/{eid}/completion",
                }
            )
    from app.db.models.platform import Membership, Role, User
    from app.modules.audit_execution.models import AuditAccess

    team_rows = (
        await db.execute(
            select(User.id, User.email, Role.name)
            .join(Membership, Membership.user_id == User.id)
            .join(AuditAccess, AuditAccess.membership_id == Membership.id)
            .join(Role, Role.id == AuditAccess.role_id)
            .where(
                AuditAccess.tenant_id == ctx.tenant_id,
                AuditAccess.engagement_id == eid,
                AuditAccess.active.is_(True),
                Membership.status == "active",
                User.status == "active",
            )
        )
    ).all()
    return {
        "engagement": audit.serialize(eng),
        "entity": audit.serialize(entity),
        "client": {"id": str(client.id), "name": client.name},
        "period": audit.serialize(period),
        "reporting_context": context,
        "package": {
            "country": binding.country,
            "version": binding.package_version,
            "sha256": binding.package_sha256,
        },
        "record_statuses": counts,
        "mapping": mapping,
        "team": [
            {"user_id": str(uid), "email": email, "role": role} for uid, email, role in team_rows
        ],
        "records": records,
        "blockers": blockers,
        "source_freshness": [n for n in projection["nodes"] if n["type"] != "record"],
        "truncated": projection["truncated"],
        "metrics_scope": "Authorized records in bounded graph projection; no completion percentage or legal readiness certification",
    }


async def lifecycle(db, ctx, eid):
    from app.modules.lineage.working_papers import graph

    projection = await graph(db, ctx, eid)
    catalogue = await modules(db, ctx, projection["package"]["country"], eid)
    eng = await audit.engagement(db, ctx, eid, lock=False)
    root = {
        "id": "engagement:" + str(eid),
        "type": "engagement",
        "kind": "engagement",
        "label": eng.name,
        "status": eng.status,
        "freshness": "CONTEXT",
        "description": "Selected engagement; containment links do not assert evidence sufficiency.",
    }
    nodes = [root]
    edges = []
    assigned = {}
    for category in catalogue["categories"][:9]:
        cid = "category:" + category["id"]
        nodes.append(
            {
                "id": cid,
                "type": "category",
                "kind": category["id"],
                "category": category["id"],
                "label": category["name"],
                "status": "TAXONOMY",
                "freshness": "CONTEXT",
            }
        )
        edges.append(
            {
                "id": root["id"] + cid,
                "source": root["id"],
                "target": cid,
                "path": "contains category",
                "edge_type": "CONTAINS",
                "freshness": "CONTEXT",
            }
        )
    for item in catalogue["items"]:
        if int(item["category"]) > 9:
            continue
        mid = "module:" + item["id"]
        nodes.append(
            {
                "id": mid,
                "type": "module",
                "kind": item["id"],
                "category": item["category"],
                "label": item["name"],
                "status": item["availability"],
                "freshness": "CONTEXT",
                "url": item["url"],
                "description": item["description"],
                "countries": item["countries"],
                "record_count": item["record_count"],
            }
        )
        edges.append(
            {
                "id": "contains:" + mid,
                "source": "category:" + item["category"],
                "target": mid,
                "path": "registered submodule",
                "edge_type": "CONTAINS",
                "freshness": "CONTEXT",
            }
        )
        if item["kind"] and item["kind"] not in assigned:
            assigned[item["kind"]] = item
    for node in projection["nodes"]:
        item = assigned.get(node["kind"])
        fallback = "05" if node["kind"] == "working-papers" else "06"
        node["category"] = item["category"] if item else fallback
        parent = "module:" + item["id"] if item else "category:" + fallback
        edges.append(
            {
                "id": "record:" + node["id"],
                "source": parent,
                "target": node["id"],
                "path": "engagement record",
                "edge_type": "CONTAINS",
                "freshness": "CONTEXT",
            }
        )
    nodes += projection["nodes"]
    edges += [{**edge, "edge_type": "SOURCE_REFERENCE"} for edge in projection["edges"]]
    return {
        **projection,
        "nodes": nodes,
        "edges": edges,
        "graph_version": catalogue["version"],
        "projection_sha256": fingerprint(
            {"nodes": nodes, "edges": edges, "registry": catalogue["version"]}
        ),
        "categories": catalogue["categories"][:9],
    }
