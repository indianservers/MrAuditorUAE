"""Bounded expansion over real result, evidence, sample and journal references."""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select

from app.modules.accounting.models import (
    ImportBatch,
    ImportSnapshot,
    JournalLine,
    SamplingItem,
    SamplingRun,
)
from app.modules.audit_execution.models import EvidenceVersion
from app.modules.intelligence import service
from app.modules.intelligence.models import IntelligenceEvent
from app.modules.jurisdictions.packages import fingerprint
from app.modules.lineage.freshness import mapping_receipt


async def graph(db, ctx, eid, requested=(), limit=100):
    latest = (
        await db.scalars(
            select(IntelligenceEvent)
            .where(
                IntelligenceEvent.tenant_id == ctx.tenant_id, IntelligenceEvent.engagement_id == eid
            )
            .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id)
            .limit(limit + 1)
        )
    ).all()
    referenced = (
        (
            await db.scalars(
                select(IntelligenceEvent).where(
                    IntelligenceEvent.tenant_id == ctx.tenant_id,
                    IntelligenceEvent.engagement_id == eid,
                    IntelligenceEvent.id.in_(requested),
                )
            )
        ).all()
        if requested
        else []
    )
    rows = {r.id: r for r in [*latest[:limit], *referenced]}
    nodes = {}
    edges = []
    for obj in rows.values():
        try:
            await service.event(db, ctx, eid, obj.id)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        identifier = str(obj.id)
        nodes[identifier] = {
            "id": identifier,
            "type": "calculation",
            "kind": "intelligence:" + obj.kind,
            "label": obj.kind.upper()
            + ": "
            + str(
                obj.body.get("section")
                or obj.body.get("source_filename")
                or obj.body.get("title")
                or identifier[:8]
            ),
            "status": obj.body.get("review_status", "UNVERIFIED"),
            "version": obj.version,
            "freshness": "CURRENT" if await service.current(db, ctx, obj) else "STALE",
            "sha256": obj.sha256,
            "api": f"intelligence/engagements/{eid}/events/{identifier}",
            "url": f"/intelligence/{eid}/{obj.kind}?event={identifier}",
            "assigned_user": str(obj.created_by),
            "last_updated": obj.created_at.isoformat(),
        }
        for index, dep in enumerate(obj.dependencies):
            source = dep.get("id")
            if dep["type"] == "mapping":
                digest = fingerprint(dep["receipt"])
                source = "mapping:" + dep["entity_id"] + ":" + digest
                active = await mapping_receipt(db, ctx.tenant_id, uuid.UUID(dep["entity_id"]))
                nodes.setdefault(
                    source,
                    {
                        "id": source,
                        "type": "mapping",
                        "kind": "mapping-receipt",
                        "label": f"Account mapping receipt / {len(dep['receipt'])} accounts",
                        "status": "IMMUTABLE_RECEIPT",
                        "sha256": digest,
                        "freshness": "CURRENT" if active == dep["receipt"] else "STALE",
                        "url": "/financials/mapping",
                    },
                )
            if not source:
                continue
            if dep["type"] == "snapshot":
                snapshot = await db.get(ImportSnapshot, uuid.UUID(source))
                if snapshot:
                    batch = await db.get(ImportBatch, snapshot.batch_id)
                    nodes.setdefault(
                        source,
                        {
                            "id": source,
                            "type": "snapshot",
                            "kind": "source-snapshot",
                            "label": "Committed accounting snapshot " + source[:8],
                            "status": "IMMUTABLE",
                            "freshness": "CURRENT"
                            if batch and batch.status == "active"
                            else "STALE",
                            "sha256": snapshot.sha256,
                            "api": f"accounting/imports/{snapshot.batch_id}",
                        },
                    )
            elif dep["type"] == "evidence":
                version = await db.get(EvidenceVersion, uuid.UUID(source))
                if version:
                    latest_number = await db.scalar(
                        select(func.max(EvidenceVersion.number)).where(
                            EvidenceVersion.tenant_id == ctx.tenant_id,
                            EvidenceVersion.record_id == version.record_id,
                        )
                    )
                    nodes.setdefault(
                        source,
                        {
                            "id": source,
                            "type": "evidence-version",
                            "kind": "evidence",
                            "label": version.filename + f" / v{version.number}",
                            "status": version.scan_status,
                            "freshness": "CURRENT"
                            if version.scan_status == "CLEAN" and version.number == latest_number
                            else "STALE",
                            "sha256": version.sha256,
                            "api": f"engagements/{eid}/audit/evidence-files/{version.record_id}",
                            "url": f"/engagements/{eid}/evidence?record={version.record_id}",
                        },
                    )
            edges.append(
                {
                    "id": f"intelligence:{source}:{identifier}:{index}",
                    "source": source,
                    "target": identifier,
                    "path": dep["type"] + " input",
                    "freshness": nodes[identifier]["freshness"],
                    "expected_version": dep.get("version"),
                }
            )
        sample_id = obj.body.get("sample_id")
        if sample_id:
            sample = await db.get(SamplingRun, uuid.UUID(sample_id))
            if sample:
                nodes.setdefault(
                    sample_id,
                    {
                        "id": sample_id,
                        "type": "sample",
                        "kind": "sampling",
                        "label": f"{sample.method} sample / seed {sample.seed}",
                        "status": sample.status,
                        "freshness": "CURRENT",
                        "api": f"sampling/runs/{sample_id}",
                    },
                )
                edges.append(
                    {
                        "id": f"sample:{sample_id}:{identifier}",
                        "source": sample_id,
                        "target": identifier,
                        "path": "documented sampling selection",
                        "freshness": nodes[identifier]["freshness"],
                    }
                )
                selected = (
                    await db.scalars(
                        select(SamplingItem.line_id)
                        .where(
                            SamplingItem.tenant_id == ctx.tenant_id,
                            SamplingItem.run_id == sample.id,
                        )
                        .order_by(SamplingItem.line_id)
                        .limit(20)
                    )
                ).all()
                for lid in selected:
                    line = await db.get(JournalLine, lid)
                    key = str(lid)
                    nodes.setdefault(
                        key,
                        {
                            "id": key,
                            "type": "journal-line",
                            "kind": "journal",
                            "label": "Selected journal line " + key[:8],
                            "status": "IMMUTABLE",
                            "freshness": "CURRENT",
                            "api": f"accounting/lineage/{line.id}",
                        },
                    )
                    edges.append(
                        {
                            "id": f"selection:{key}:{sample_id}",
                            "source": key,
                            "target": sample_id,
                            "path": "selected original journal line",
                            "freshness": "CURRENT",
                        }
                    )
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "truncated": len(latest) > limit,
        "scope": "Maximum 100 intelligence outputs and 20 journal lines per sample; full source details remain available",
    }
