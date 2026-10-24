"""Durable page replay and single-flight token rotation using independent transactions."""

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from app.db.session import tenant_context
from app.modules.connectors.models import ConnectorState
from app.modules.connectors.secrets import decrypt, encrypt
from app.modules.connectors.zoho import ConnectorError
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.saas.storage import put_private


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


class ConnectorRuntime:
    def __init__(self, factory, ctx, connection_id):
        self.factory, self.ctx, self.connection_id = factory, ctx, connection_id
        self.replayed = self.downloaded = 0
        self.last_object = None

    @classmethod
    def for_session(cls, db, ctx, connection_id):
        # Pure adapter/unit tests can use explicit fakes; production always has a bind.
        if getattr(db, "bind", None) is None:
            return None
        bind = db.bind.engine if isinstance(db.bind, AsyncConnection) else db.bind
        return cls(async_sessionmaker(bind, expire_on_commit=False), ctx, connection_id)

    async def get(self, namespace, key):
        async with self.factory() as db, db.begin():
            await tenant_context(db, self.ctx.tenant_id)
            row = await db.scalar(select(ConnectorState).where(
                ConnectorState.tenant_id == self.ctx.tenant_id,
                ConnectorState.namespace == namespace, ConnectorState.key == key,
            ))
            if row and (row.expires_at is None or row.expires_at > datetime.now(UTC)):
                return row.payload
        return None

    async def put(self, namespace, key, payload, ttl_hours=None):
        async with self.factory() as db, db.begin():
            await tenant_context(db, self.ctx.tenant_id)
            expires = datetime.now(UTC) + timedelta(hours=ttl_hours) if ttl_hours else None
            statement = insert(ConnectorState).values(
                id=uuid.uuid4(), tenant_id=self.ctx.tenant_id, created_by=self.ctx.user_id,
                connection_id=self.connection_id, namespace=namespace, key=key,
                payload=payload, expires_at=expires,
            ).on_conflict_do_update(constraint="uq_connector_state", set_={
                "payload": payload, "expires_at": expires, "updated_at": datetime.now(UTC),
            })
            await db.execute(statement)

    async def cached_read(self, session_key, request_key, fetch):
        key = digest([str(self.connection_id), session_key, request_key])
        cached = await self.get("checkpoint", key)
        if cached:
            with ObjectStore().local(cached["object_key"], cached["object_version"]) as path:
                if hash_file(path) != cached["sha256"]:
                    raise ConnectorError("Checkpoint source integrity mismatch")
                raw = path.read_bytes()
            from decimal import Decimal

            self.replayed += 1
            self.last_object = cached
            return json.loads(raw, parse_float=Decimal), raw
        data, raw = await fetch()
        stored = await self.persist_object(raw)
        await self.put("checkpoint", key, stored, ttl_hours=24)
        self.last_object = stored
        self.downloaded += 1
        return data, raw

    async def persist_object(self, raw):
        async with self.factory() as db, db.begin():
            await tenant_context(db, self.ctx.tenant_id)
            stored = await put_private(db, self.ctx, io.BytesIO(raw))
        return stored

    async def rotate_grant(self, grant_key, current, exchange, force=False):
        """Grant ciphertext and refresh rotation commit together under a cross-worker lock."""
        async with self.factory() as db, db.begin():
            await tenant_context(db, self.ctx.tenant_id)
            await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,29))"),
                             {"key": str(self.ctx.tenant_id) + grant_key})
            row = await db.scalar(select(ConnectorState).where(
                ConnectorState.tenant_id == self.ctx.tenant_id,
                ConnectorState.namespace == "grant", ConnectorState.key == grant_key,
            ))
            now = datetime.now(UTC)
            source = current
            if row:
                cached = decrypt(row.payload["ciphertext"])
                source = {**current, **{k: v for k, v in cached.items() if k in {"access_token", "refresh_token", "expires_in", "token_type"}}}
                newer = cached.get("access_token") != current.get("access_token")
                if (not force or newer) and datetime.fromisoformat(row.payload["refresh_after"]) > now:
                    return source
            updated = await exchange(source)
            payload = {"ciphertext": encrypt(updated), "refresh_after": (now + timedelta(minutes=5)).isoformat()}
            if row:
                row.payload = payload
            else:
                db.add(ConnectorState(
                    tenant_id=self.ctx.tenant_id, created_by=self.ctx.user_id,
                    connection_id=self.connection_id, namespace="grant", key=grant_key,
                    payload=payload, expires_at=None,
                ))
            return updated
