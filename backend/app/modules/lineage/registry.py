"""Engagement dependency registry over immutable calculation and feature receipts."""

from typing import Any

from sqlalchemy import select

from app.modules.audit_execution.access import engagement_permissions
from app.modules.ifrs.models import CalculationRun
from app.modules.ml.models import MLEvent
from app.modules.tax.models import TaxRun
from app.modules.tp.models import TPRun
from app.modules.vat.models import VATRun


async def registry(db, ctx, eid, offset=0, limit=100):
    from app.modules.ifrs.service import current_dependencies
    from app.modules.lineage.freshness import ml_current, state
    from app.modules.tax.service import dependencies_current
    from app.modules.tp.service import current as tp_current
    from app.modules.vat.service import current as vat_current

    permissions, _ = await engagement_permissions(db, ctx, eid, "audit.read")
    items = []
    modules: list[tuple[str, str, Any, Any]] = [
        ("ifrs", "ifrs.read", CalculationRun, current_dependencies),
        ("tax", "tax.profile.read", TaxRun, dependencies_current),
        ("vat", "vat.read", VATRun, vat_current),
        ("tp", "tp.read", TPRun, tp_current),
        ("ml", "ml.read", MLEvent, None),
    ]
    for module, permission, model, check in modules:
        if permission not in permissions:
            continue
        rows = (
            await db.scalars(
                select(model)
                .where(model.tenant_id == ctx.tenant_id, model.engagement_id == eid)
                .order_by(model.created_at.desc(), model.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        for row in rows:
            current = await check(db, ctx, eid, row) if check else await ml_current(db, ctx, row)
            items.append(
                {
                    "module": module,
                    "id": str(row.id),
                    "kind": row.kind,
                    "dependencies": row.dependencies
                    if check
                    else {
                        "parent_id": str(row.parent_id) if row.parent_id else None,
                        "source_snapshots": row.body.get("source_snapshots", []),
                    },
                    "freshness": state(current),
                    "required_action": None
                    if current
                    else "Controlled regeneration and independent review",
                    "history_preserved": True,
                }
            )
    return {
        "items": items,
        "offset_per_module": offset,
        "limit_per_module": limit,
        "validation": "Synchronous on every read; no asynchronous invalidation gap",
        "automatic_recalculation": False,
    }
