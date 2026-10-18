"""Explicit approved client-safe PDF snapshots; never expose internal TP records to portal users."""

import io
import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.db.models.platform import Engagement, LegalEntity
from app.modules.audit_execution.models import AuditRecord
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.saas.storage import put_private
from app.modules.tp import service
from app.modules.tp.exports import render


async def publish(db, ctx, eid, release):
    if release.body.get("client_document"):
        return
    run = await service.get_run(db, ctx, eid, uuid.UUID(release.body["document_run_id"]))
    await service.export_allowed(db, ctx, eid, run)
    payload, _ = await run_in_threadpool(render, run, "pdf", True, True)
    metadata = await put_private(db, ctx, io.BytesIO(payload))
    datasets = set()
    visited = set()

    async def sources(source):
        if source.id in visited:
            return
        visited.add(source.id)
        for item in source.dependencies:
            if item.get("kind") == "tp-dataset":
                datasets.add(item["id"])
            if item.get("type") == "run":
                await sources(await service.get_run(db, ctx, eid, uuid.UUID(item["id"])))

    await sources(run)
    release.body = {
        **release.body,
        "client_document": {
            **metadata,
            "dataset_ids": sorted(datasets),
            "document_type": run.kind,
            "annual_version": run.results["annual_version"],
            "issued_at": datetime.now(UTC).isoformat(),
            "run_sha256": run.sha256,
        },
    }


async def authorized_releases(db, ctx, rid=None):
    from app.api.v1.client_portal import permitted

    where = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.kind == "tp-release",
        AuditRecord.status.in_(service.APPROVED),
        AuditRecord.body["client_visible"].astext == "true",
        LegalEntity.client_id.in_(permitted(ctx)),
    ]
    if rid:
        where.append(AuditRecord.id == rid)
    records = (
        await db.scalars(
            select(AuditRecord)
            .join(Engagement, Engagement.id == AuditRecord.engagement_id)
            .join(LegalEntity, LegalEntity.id == Engagement.entity_id)
            .where(*where)
            .order_by(AuditRecord.created_at.desc())
            .limit(100)
        )
    ).all()
    permitted_rows = []
    for row in records:
        document = row.body.get("client_document")
        if not document:
            continue
        valid = True
        for dataset_id in document["dataset_ids"]:
            dataset = await db.get(AuditRecord, uuid.UUID(dataset_id))
            if (
                not dataset
                or dataset.status not in service.APPROVED
                or not dataset.body.get("allow_derived_export")
                or date.fromisoformat(dataset.body["valid_until"]) < date.today()
            ):
                valid = False
        if valid:
            permitted_rows.append(row)
    return permitted_rows


def download(document):
    store = ObjectStore()
    with store.local(document["object_key"], document["object_version"]) as path:
        if hash_file(path) != document["sha256"]:
            raise HTTPException(409, "Published document integrity verification failed")
        return path.read_bytes()
