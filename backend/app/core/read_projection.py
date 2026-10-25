"""Bounded reuse for one explicitly opted-in read projection and transaction.

Never use this as an authorization or freshness cache for mutations. Database
transaction changes, another actor/session, context exit and errors all prevent
reuse. Dependency traversal and its cycle/depth checks remain with the caller.
"""

from collections.abc import Awaitable, Callable, Hashable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

MAX_ENTRIES = 512


def transaction(db):
    session = getattr(db, "sync_session", None)
    if session is None:
        return None
    nested = getattr(session, "get_nested_transaction", lambda: None)()
    return nested if nested is not None else session.get_transaction()


@dataclass
class Projection:
    db: Any
    actor: tuple[str, str]
    transaction: Any
    values: dict[tuple, Any] = field(default_factory=dict)
    closed: bool = False


_active: ContextVar[Projection | None] = ContextVar("read_projection", default=None)


@contextmanager
def read_projection(db, ctx) -> Iterator[None]:
    projection = Projection(db, (str(ctx.tenant_id), str(ctx.user_id)), transaction(db))
    token = _active.set(projection)
    try:
        yield
    finally:
        projection.closed = True
        projection.values.clear()
        _active.reset(token)


async def read_once[T](
    db, ctx, namespace: str, key: Hashable, produce: Callable[[], Awaitable[T]]
) -> T:
    active = _active.get()
    if (
        active is None
        or active.closed
        or active.db is not db
        or active.actor != (str(ctx.tenant_id), str(ctx.user_id))
        or active.transaction is None
        or active.transaction is not transaction(db)
    ):
        return await produce()
    identity = (namespace, key)
    if identity in active.values:
        return active.values[identity]
    value = await produce()
    if (
        not active.closed
        and active.transaction is transaction(db)
        and len(active.values) < MAX_ENTRIES
    ):
        active.values[identity] = value
    return value
