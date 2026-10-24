"""Read-time dependency checks over immutable source receipts; no delayed invalidation."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.accounting.models import Account, ImportBatch, ImportSnapshot


def state(current, reasons=None):
    return {
        "status": "CURRENT" if current else "STALE",
        "reasons": reasons or [],
        "last_verified_at": datetime.now(UTC).isoformat(),
        "automatic_retraining": False,
    }


async def snapshot_current(db, tenant, identifier):
    return bool(
        await db.scalar(
            select(ImportSnapshot.id)
            .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
            .where(
                ImportSnapshot.tenant_id == tenant,
                ImportSnapshot.id == uuid.UUID(str(identifier)),
                ImportBatch.status == "active",
            )
        )
    )


async def mapping_receipt(db, tenant, entity):
    return [
        {
            "id": str(row.id),
            "mapping_version": row.mapping_version,
            "classification": row.classification,
            "statement_group": row.statement_group,
            "parent_code": row.parent_code,
            "mapping_profile_id": str(row.mapping_profile_id) if row.mapping_profile_id else None,
            "source_group": row.source_group,
            "contra": row.contra,
        }
        for row in (
            await db.scalars(
                select(Account)
                .where(Account.tenant_id == tenant, Account.entity_id == entity)
                .order_by(Account.id)
            )
        ).all()
    ]


async def ml_current(db, ctx, obj, visited=None):
    from app.core.operations_contracts import current as operations_current

    if not await operations_current(db, ctx, obj):
        return False
    from app.db.models.platform import Engagement
    from app.modules.ml.models import MLEvent

    visited = visited or set()
    if obj.id in visited:
        return False
    visited.add(obj.id)
    if obj.kind == "dataset":
        if obj.body.get("synthetic") and not obj.body.get("source_snapshots"):
            return True  # Explicit standalone synthetic fixture; makes no live-ledger claim.
        receipts = obj.body.get("source_snapshots")
        if not receipts:
            return False  # Legacy ledger datasets must be regenerated with verifiable lineage.
        eng = await db.get(Engagement, obj.engagement_id)
        current = set(
            str(i)
            for i in (
                await db.scalars(
                    select(ImportSnapshot.id)
                    .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
                    .where(
                        ImportSnapshot.tenant_id == ctx.tenant_id,
                        ImportSnapshot.entity_id == eng.entity_id,
                        ImportSnapshot.period_id == eng.period_id,
                        ImportBatch.kind.in_(["gl", "journals"]),
                        ImportBatch.status == "active",
                    )
                )
            ).all()
        )
        if current != {r["id"] for r in receipts}:
            return False
        for receipt in receipts:
            snap = await db.get(ImportSnapshot, uuid.UUID(receipt["id"]))
            if not snap or snap.sha256 != receipt["sha256"]:
                return False
        return obj.body.get("account_mapping_receipt") == await mapping_receipt(
            db, ctx.tenant_id, eng.entity_id
        )
    identifiers = [obj.parent_id] if obj.parent_id else []
    for key in ["dataset_id", "model_id"]:
        if obj.body.get(key):
            identifiers.append(uuid.UUID(obj.body[key]))
    for identifier in set(identifiers):
        parent = await db.scalar(
            select(MLEvent).where(
                MLEvent.id == identifier,
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == obj.engagement_id,
            )
        )
        if not parent or not await ml_current(db, ctx, parent, set(visited)):
            return False
    return True


async def require_ml_current(db, ctx, obj):
    if not await ml_current(db, ctx, obj):
        raise HTTPException(
            409, "ML source superseded or account mapping changed; regenerate features and review"
        )


async def analytics_current(db, ctx, run):
    if not await snapshot_current(db, ctx.tenant_id, run.snapshot_id):
        return False
    if "account_mapping_snapshot" in run.parameters:
        live = sorted(
            [
                [r.code, r.classification, r.contra, r.source_group]
                for r in (
                    await db.scalars(
                        select(Account).where(
                            Account.tenant_id == ctx.tenant_id, Account.entity_id == run.entity_id
                        )
                    )
                ).all()
            ],
            key=lambda r: r[0],
        )
        # An analytics snapshot may use only a subset of the entity chart.
        by_code = {r[0]: r for r in live}
        return all(by_code.get(row[0]) == row for row in run.parameters["account_mapping_snapshot"])
    return True
