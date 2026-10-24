"""Append source snapshots without overwriting activated accounting facts."""

import io
import json
import uuid

from sqlalchemy import select

from app.modules.connectors.controls import revision_summary
from app.modules.connectors.models import ConnectorState
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.saas.storage import put_private


async def append_revision(
    db, ctx, connection, run_id, fingerprints, comparable, *, source_kind="sync_run"
):
    previous = await db.scalar(
        select(ConnectorState)
        .where(
            ConnectorState.tenant_id == ctx.tenant_id,
            ConnectorState.connection_id == connection.id,
            ConnectorState.namespace == "source_revision",
        )
        .order_by(ConnectorState.created_at.desc())
        .limit(1)
    )
    old = {}
    if previous:
        pointer = previous.payload["index"]
        with ObjectStore().local(pointer["object_key"], pointer["object_version"]) as path:
            if hash_file(path) != pointer["sha256"]:
                raise ValueError("Prior source revision integrity mismatch")
            old = json.loads(path.read_bytes())
    stored = await put_private(
        db, ctx, io.BytesIO(json.dumps(fingerprints, sort_keys=True).encode())
    )
    reliable = comparable and (not previous or previous.payload.get("comparable", False))
    changes = revision_summary(old, fingerprints, reliable)
    payload = {
        **changes,
        "comparable": comparable,
        "index": stored,
        source_kind + "_id": str(run_id),
        "previous_revision_id": str(previous.id) if previous else None,
        "identity_warning": None
        if comparable
        else "snapshot_or_truncated_identity; changes_are_not_deletion_evidence",
    }
    db.add(
        ConnectorState(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            connection_id=connection.id,
            namespace="source_revision",
            key=str(uuid.uuid4()),
            payload=payload,
            expires_at=None,
        )
    )
    return {k: v for k, v in payload.items() if k != "index"}
