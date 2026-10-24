"""Authenticated webhook repair always rebuilds the controlled ledger population."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.accounting.models import Connection
from app.modules.accounting.service import scoped
from app.modules.connectors.models import ConnectorState
from app.modules.connectors.native_service import direct_sync


async def repair_connection(db, ctx, connection_id):
    connection = await scoped(db, ctx, Connection, connection_id, True)
    if connection.provider != "quickbooks" or connection.config.get("edition", "online") != "online":
        raise HTTPException(422, "Repair requires QuickBooks Online")
    events = (await db.scalars(select(ConnectorState).where(
        ConnectorState.tenant_id == ctx.tenant_id,
        ConnectorState.connection_id == connection_id,
        ConnectorState.namespace == "event",
        ConnectorState.payload["state"].astext == "repair_pending",
    ).order_by(ConnectorState.created_at).limit(10000))).all()
    since = min((datetime.fromisoformat(e.payload["last_updated"]) for e in events), default=None)
    # CDC cannot recover older changes. Full GL extraction remains mandatory in
    # both cases and the source response, including deletion hints, is evidence.
    cdc_since = (since - timedelta(seconds=1)).isoformat() if since and since > datetime.now(UTC) - timedelta(days=29) else None
    result = await direct_sync(db, ctx, connection_id, repair_since=cdc_since)
    if result["status"] == "completed":
        for event in events:
            event.payload = {**event.payload, "state": "repaired_pending_review",
                             "repair_run_id": result["id"], "repaired_at": datetime.now(UTC).isoformat()}
    result["repair"] = {"captured_events": len(events), "cdc_requested": bool(cdc_since),
                        "mode": "full_period_refresh", "activation": "review_required"}
    return result
