"""Evidence-backed graph projections; immutable revisions retain dependency receipts."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.accounting.models import (
    AnalyticsRun,
    Finding,
    ImportBatch,
    ImportSnapshot,
    JournalLine,
    SamplingRun,
)
from app.modules.audit_execution.models import AuditRecord, AuditRevision
from app.modules.intelligence.models import IntelligenceEvent


def references(value, path="body"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from references(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from references(item, f"{path}[{index}]")
    elif isinstance(value, str):
        try:
            yield path, uuid.UUID(value)
        except ValueError:
            pass


async def capture(db, ctx, obj):
    refs = list(references(obj.body))
    identifiers = {identifier for _, identifier in refs}
    if not identifiers:
        return []
    records = {
        r.id: r
        for r in (
            await db.scalars(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.id.in_(identifiers)
                )
            )
        ).all()
    }
    snapshots = {
        r.id: r
        for r in (
            await db.scalars(
                select(ImportSnapshot).where(
                    ImportSnapshot.tenant_id == ctx.tenant_id, ImportSnapshot.id.in_(identifiers)
                )
            )
        ).all()
    }
    receipts = []
    population_sources = [
        (s["kind"], uuid.UUID(s["id"]))
        for s in obj.body.get("sources", [])
        if s.get("kind") in {"sample", "journal", "finding"}
    ]
    if getattr(obj, "kind", None) == "testing" and obj.body.get("sample_id"):
        population_sources.append(("sample", uuid.UUID(obj.body["sample_id"])))
    for source_kind, source_id in set(population_sources):
        source_model = {"sample": SamplingRun, "journal": JournalLine, "finding": Finding}[
            source_kind
        ]
        source = await db.scalar(
            select(source_model).where(
                source_model.tenant_id == ctx.tenant_id, source_model.id == source_id
            )
        )
        if not source:
            raise HTTPException(422, "Missing scoped audit population source")
        if source_kind == "finding":
            source = await db.get(AnalyticsRun, source.run_id)
        snap = await db.get(ImportSnapshot, source.snapshot_id)
        receipts.append(
            {
                "type": "snapshot",
                "id": str(snap.id),
                "sha256": snap.sha256,
                "path": "body.audit_population." + source_kind,
            }
        )
    from app.modules.ml.models import MLEvent

    ml_ids = {uuid.UUID(s["id"]) for s in obj.body.get("sources", []) if s.get("kind") == "ml"}
    ml = (
        {
            r.id: r
            for r in (
                await db.scalars(
                    select(MLEvent).where(
                        MLEvent.tenant_id == ctx.tenant_id, MLEvent.id.in_(ml_ids)
                    )
                )
            ).all()
        }
        if ml_ids
        else {}
    )
    intelligence = {
        r.id: r
        for r in (
            await db.scalars(
                select(IntelligenceEvent).where(
                    IntelligenceEvent.tenant_id == ctx.tenant_id,
                    IntelligenceEvent.id.in_(identifiers),
                )
            )
        ).all()
    }
    for path, identifier in refs:
        if identifier in ml:
            result = ml[identifier]
            if result.engagement_id != obj.engagement_id:
                raise HTTPException(422, "Cross-engagement ML evidence is not permitted")
            receipts.append(
                {"type": "ml", "id": str(identifier), "sha256": result.sha256, "path": path}
            )
            continue
        if identifier == obj.id:
            continue
        if identifier in records:
            row = records[identifier]
            if row.engagement_id != obj.engagement_id:
                members = (
                    {uuid.UUID(member["engagement_id"]) for member in obj.body.get("members", [])}
                    if getattr(obj, "kind", None) in {"tax-group", "ifrs-consolidation"}
                    else set()
                )
                comparative_link = (
                    getattr(obj, "kind", None) == "ifrs-profile"
                    and row.kind == "ifrs-profile"
                    and str(row.id) == obj.body.get("comparative_profile_id")
                    and str(row.engagement_id) == obj.body.get("comparative_engagement_id")
                )
                recipient_link = (
                    getattr(obj, "kind", None) == "tax-loss-transfer"
                    and str(row.id) == obj.body.get("recipient_profile_id")
                    and str(row.engagement_id) == obj.body.get("recipient_engagement_id")
                )
                posted_transfer_link = (
                    getattr(obj, "kind", None) == "tax-loss"
                    and str(row.id) == obj.body.get("transfer_source_id")
                    and row.kind == "tax-loss-transfer"
                    and row.status in {"APPROVED", "LOCKED"}
                    and row.body.get("recipient_engagement_id") == str(obj.engagement_id)
                    and row.body.get("recipient_profile_id") == obj.body.get("profile_id")
                )
                if (
                    row.engagement_id not in members
                    and not comparative_link
                    and not recipient_link
                    and not posted_transfer_link
                ):
                    raise HTTPException(
                        422, "Cross-engagement working-paper source requires an authorized link"
                    )
                # A tax group explicitly names its member engagements. Recheck access
                # to the actual referenced record; a shared tenant is insufficient.
                from app.modules.audit_execution import service as audit

                await audit.get_record(db, ctx, row.engagement_id, row.id, lock=False)
            receipts.append(
                {"type": "record", "id": str(identifier), "version": row.version, "path": path}
            )
        elif identifier in snapshots:
            receipts.append(
                {
                    "type": "snapshot",
                    "id": str(identifier),
                    "sha256": snapshots[identifier].sha256,
                    "path": path,
                }
            )
        elif identifier in intelligence:
            intel_row = intelligence[identifier]
            if intel_row.engagement_id != obj.engagement_id:
                raise HTTPException(
                    422, "Cross-engagement intelligence source requires an authorized link"
                )
            receipts.append(
                {
                    "type": "intelligence",
                    "id": str(identifier),
                    "version": intel_row.version,
                    "sha256": intel_row.sha256,
                    "path": path,
                }
            )
    return receipts


async def check(db, ctx, receipt, visiting=None):
    identifier = uuid.UUID(receipt["id"])
    if receipt["type"] == "ml":
        from app.modules.lineage.freshness import ml_current
        from app.modules.ml.service import get

        result = await get(db, ctx, identifier)
        return (
            "CURRENT"
            if result.sha256 == receipt["sha256"] and await ml_current(db, ctx, result)
            else "STALE"
        )
    if receipt["type"] == "intelligence":
        from app.modules.intelligence.service import current

        result = await db.get(IntelligenceEvent, identifier)
        return (
            "CURRENT"
            if result
            and result.sha256 == receipt["sha256"]
            and await current(db, ctx, result, visiting)
            else "STALE"
        )
    if receipt["type"] == "record":
        row = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.id == identifier
            )
        )
        if not row or row.status == "ARCHIVED":
            return "BLOCKED"
        return "CURRENT" if row.version == receipt["version"] else "STALE"
    row = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.tenant_id == ctx.tenant_id, ImportSnapshot.id == identifier
        )
    )
    batch = await db.get(ImportBatch, row.batch_id) if row else None
    return (
        "CURRENT"
        if row and row.sha256 == receipt["sha256"] and batch and batch.status == "active"
        else "STALE"
    )


async def receipts_for(db, obj):
    revision = await db.scalar(
        select(AuditRevision).where(
            AuditRevision.tenant_id == obj.tenant_id,
            AuditRevision.record_id == obj.id,
            AuditRevision.version == obj.version,
        )
    )
    return revision.snapshot.get("dependency_receipts") if revision else None


async def context_freshness(db, ctx, obj, expected=None):
    if expected is None:
        from app.db.models.platform import Engagement
        from app.modules.jurisdictions.workspace import resolved

        eng = await db.get(Engagement, obj.engagement_id)
        country, context = await resolved(db, ctx, eng)
        expected = {"version": context["version"], "sha256": country.package_sha256}
    if expected["version"] == 0:
        return "CURRENT"
    revision = await db.scalar(
        select(AuditRevision).where(
            AuditRevision.tenant_id == ctx.tenant_id,
            AuditRevision.record_id == obj.id,
            AuditRevision.version == obj.version,
        )
    )
    if not revision or "reporting_context" not in revision.snapshot:
        return "UNVERIFIED"
    return (
        "CURRENT"
        if revision.snapshot["reporting_context"]["version"] == expected["version"]
        and revision.snapshot["country_package"]["sha256"] == expected["sha256"]
        else "STALE"
    )


async def require_context_current(db, ctx, obj):
    if await context_freshness(db, ctx, obj) != "CURRENT":
        raise HTTPException(
            409, "Reporting context changed; reassess and review the input before a new calculation"
        )


async def freshness(db, ctx, obj, visiting=None, cache=None, expected=None):
    visiting = set() if visiting is None else visiting
    cache = {} if cache is None else cache
    if obj.id in cache:
        return cache[obj.id]
    if obj.id in visiting or len(visiting) >= 100:
        return "UNVERIFIED"
    visiting = visiting | {obj.id}
    context_state = await context_freshness(db, ctx, obj, expected)
    if context_state != "CURRENT":
        cache[obj.id] = context_state
        return context_state
    receipts = await receipts_for(db, obj)
    if receipts is None:
        return "UNVERIFIED" if await capture(db, ctx, obj) else "CURRENT"
    statuses = []
    for receipt in receipts:
        status = await check(db, ctx, receipt, visiting)
        if status == "CURRENT" and receipt["type"] == "record":
            source = await db.get(AuditRecord, uuid.UUID(receipt["id"]))
            status = await freshness(db, ctx, source, visiting, cache, expected)
        statuses.append(status)
    result = next((s for s in ["BLOCKED", "STALE", "UNVERIFIED"] if s in statuses), "CURRENT")
    cache[obj.id] = result
    return result


async def require_current(db, ctx, obj):
    if await freshness(db, ctx, obj) != "CURRENT":
        raise HTTPException(
            409,
            "Working-paper sources changed or are unverified; reassess and save a new draft before review",
        )


async def graph(db, ctx, eid, limit=300):
    from app.modules.audit_execution import service as audit
    from app.modules.audit_execution.access import engagement_permissions
    from app.modules.jurisdictions.workspace import resolved
    from app.modules.lineage.registry import registry

    eng = await audit.engagement(db, ctx, eid, lock=False)
    permissions, _ = await engagement_permissions(db, ctx, eid, "audit.read")
    country, context = await resolved(db, ctx, eng)
    expected = {"version": context["version"], "sha256": country.package_sha256}
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.engagement_id == eid)
            .order_by(AuditRecord.id)
            .limit(limit + 1)
        )
    ).all()
    allowed = {}
    for row in rows[:limit]:
        try:
            await audit.get_record(db, ctx, eid, row.id, lock=False)
            allowed[str(row.id)] = row
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
    nodes, edges, known = [], [], set(allowed)
    freshness_cache: dict[uuid.UUID, str] = {}
    for identifier, row in allowed.items():
        receipts = await receipts_for(db, row)
        legacy = receipts is None
        if legacy:
            receipts = await capture(db, ctx, row)
        current_freshness = await freshness(db, ctx, row, cache=freshness_cache, expected=expected)
        nodes.append(
            {
                "id": identifier,
                "type": "record",
                "kind": row.kind,
                "label": f"{row.reference}: {row.title}",
                "version": row.version,
                "status": row.status,
                "freshness": current_freshness,
                "url": f"/engagements/{eid}/{row.kind}?record={identifier}",
                "api": f"engagements/{eid}/audit/records/{identifier}",
                "legacy_receipt": legacy,
                "assigned_user": row.body.get("owner_id") or str(row.prepared_by),
                "last_updated": row.updated_at.isoformat(),
                "has_exceptions": bool(
                    row.kind in {"findings", "review-notes"}
                    and row.status not in {"RESOLVED", "CLEARED", "CLOSED", "ARCHIVED"}
                ),
            }
        )
        for receipt in receipts:
            source = receipt["id"]
            if receipt["type"] == "snapshot" and "accounting.read" in permissions:
                snapshot = await db.get(ImportSnapshot, uuid.UUID(source))
                if snapshot and source not in known:
                    nodes.append(
                        {
                            "id": source,
                            "type": "snapshot",
                            "kind": "source-snapshot",
                            "label": "Import snapshot " + source[:8],
                            "status": "IMMUTABLE",
                            "freshness": await check(db, ctx, receipt),
                            "sha256": snapshot.sha256,
                            "api": f"accounting/imports/{snapshot.batch_id}",
                        }
                    )
                    known.add(source)
            if source in known or receipt["type"] == "intelligence":
                edges.append(
                    {
                        "id": f"{source}:{identifier}:{receipt['path']}",
                        "source": source,
                        "target": identifier,
                        "path": receipt["path"],
                        "expected_version": receipt.get("version"),
                        "freshness": "UNVERIFIED" if legacy else await check(db, ctx, receipt),
                    }
                )
    from app.modules.intelligence.projection import graph as intelligence_graph

    requested = {
        receipt["id"]
        for row in allowed.values()
        for receipt in (await receipts_for(db, row) or [])
        if receipt["type"] == "intelligence"
    }
    intelligence = await intelligence_graph(db, ctx, eid, requested, min(limit, 100))
    for node in intelligence["nodes"]:
        if node["id"] not in known:
            nodes.append(node)
            known.add(node["id"])
    edges.extend(intelligence["edges"])
    calculated = await registry(db, ctx, eid, limit=min(limit, 100))
    for result in calculated["items"]:
        identifier = result["id"]
        if identifier in known:
            continue
        known.add(identifier)
        nodes.append(
            {
                "id": identifier,
                "type": "calculation",
                "kind": result["module"],
                "label": result["module"].upper() + " / " + result["kind"],
                "status": "IMMUTABLE_RESULT",
                "freshness": result["freshness"]["status"],
                "api": f"ml/events/{identifier}"
                if result["module"] == "ml"
                else f"{result['module']}/engagements/{eid}/runs/{identifier}",
            }
        )
    for result in calculated["items"]:
        identifier = result["id"]
        dependencies = result["dependencies"]
        inputs = (
            [d["id"] for d in dependencies]
            if isinstance(dependencies, list)
            else [dependencies.get("parent_id")]
            + [d["id"] for d in dependencies.get("source_snapshots", [])]
        )
        for source in inputs:
            if source and source not in known and "accounting.read" in permissions:
                snapshot = await db.get(ImportSnapshot, uuid.UUID(source))
                if snapshot:
                    batch = await db.get(ImportBatch, snapshot.batch_id)
                    nodes.append(
                        {
                            "id": source,
                            "type": "snapshot",
                            "kind": "source-snapshot",
                            "label": "Import snapshot " + source[:8],
                            "status": "IMMUTABLE",
                            "freshness": "CURRENT"
                            if batch and batch.status == "active"
                            else "STALE",
                            "sha256": snapshot.sha256,
                            "api": f"accounting/imports/{snapshot.batch_id}",
                        }
                    )
                    known.add(source)
            if source in known:
                edges.append(
                    {
                        "id": f"{source}:{identifier}",
                        "source": source,
                        "target": identifier,
                        "path": "calculation input",
                        "freshness": result["freshness"]["status"],
                    }
                )
    edges = [edge for edge in edges if edge["source"] in known and edge["target"] in known]
    by_id = {n["id"]: n for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for edge in edges:
            source, target = by_id[edge["source"]], by_id[edge["target"]]
            if (
                source["freshness"] in {"STALE", "BLOCKED", "UNVERIFIED"}
                and target["freshness"] == "CURRENT"
            ):
                target["freshness"] = source["freshness"]
                changed = True
        if not changed:
            break
    return {
        "nodes": nodes,
        "edges": edges,
        "package": {
            "country": country.country,
            "version": country.package_version,
            "sha256": country.package_sha256,
        },
        "truncated": intelligence["truncated"]
        or len(rows) > limit
        or any(
            sum(n.get("kind") == module for n in nodes) == 100
            for module in ["ifrs", "tax", "vat", "tp", "ml"]
        ),
        "scope": "Authorized engagement records only; external or inaccessible dependencies are not expanded",
        "approved_history_unchanged": True,
    }
