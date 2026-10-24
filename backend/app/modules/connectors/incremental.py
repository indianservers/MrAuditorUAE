"""Only vendor-documented document deltas; account-transaction GL stays a full extract."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.modules.connectors.models import ConnectorState
from app.modules.connectors.runtime import digest

ZOHO_MODIFIED = {"invoices", "bills", "creditnotes"}


def modified_filter(resource, watermark):
    if resource not in ZOHO_MODIFIED or not watermark:
        return {}
    stamp = datetime.fromisoformat(watermark)
    if stamp.tzinfo is None or stamp > datetime.now(UTC):
        raise ValueError("Invalid Zoho resource watermark")
    return {"last_modified_time": (stamp - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")}


async def commit_watermarks(db, ctx, connection_id, resources, started, run_id):
    for resource in resources:
        payload = {
            "resource": resource,
            "last_completed_start": started.isoformat(),
            "sync_run_id": str(run_id),
            "mode": "supporting_document_delta; full_gl_required",
            "deletion_detection": "not_supported_by_modified_filter",
        }
        await db.execute(
            insert(ConnectorState)
            .values(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                connection_id=connection_id,
                namespace="watermark",
                key=digest([str(connection_id), resource]),
                payload=payload,
                expires_at=None,
            )
            .on_conflict_do_update(
                constraint="uq_connector_state",
                set_={"payload": payload, "updated_at": datetime.now(UTC)},
            )
        )
