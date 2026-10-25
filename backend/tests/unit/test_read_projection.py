"""Read-view reuse is bounded, actor/session/transaction-specific and disposable."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import read_projection as views


def context():
    session = SimpleNamespace(transaction=object())
    session.get_transaction = lambda: session.transaction
    return SimpleNamespace(sync_session=session), SimpleNamespace(
        tenant_id="tenant", user_id="user"
    )


@pytest.mark.parametrize("value", [None, False, 0, "ok"])
async def test_only_explicit_view_reuses_completed_values(value):
    db, ctx = context()
    produce = AsyncMock(return_value=value)
    await views.read_once(db, ctx, "test", "a", produce)
    await views.read_once(db, ctx, "test", "a", produce)
    assert produce.await_count == 2
    with views.read_projection(db, ctx):
        assert await views.read_once(db, ctx, "test", "a", produce) == value
        assert await views.read_once(db, ctx, "test", "a", produce) == value
    assert produce.await_count == 3
    await views.read_once(db, ctx, "test", "a", produce)
    assert produce.await_count == 4


@pytest.mark.parametrize(
    "change", ["user", "tenant", "session", "transaction", "savepoint", "no-transaction"]
)
async def test_identity_and_transaction_changes_bypass_reuse(change):
    db, ctx = context()
    produce = AsyncMock(side_effect=range(10))
    with views.read_projection(db, ctx):
        assert await views.read_once(db, ctx, "test", "a", produce) == 0
        if change == "user":
            ctx = SimpleNamespace(tenant_id=ctx.tenant_id, user_id="other")
        elif change == "tenant":
            ctx = SimpleNamespace(tenant_id="other", user_id=ctx.user_id)
        elif change == "session":
            db, _ = context()
        elif change == "transaction":
            db.sync_session.transaction = object()
        elif change == "savepoint":
            nested = object()
            db.sync_session.get_nested_transaction = lambda: nested
        else:
            db.sync_session.transaction = None
        assert await views.read_once(db, ctx, "test", "a", produce) == 1


async def test_errors_and_overflow_are_not_cached(monkeypatch):
    db, ctx = context()
    monkeypatch.setattr(views, "MAX_ENTRIES", 1)
    failure = AsyncMock(side_effect=ValueError("unverified"))
    produce = AsyncMock(side_effect=range(10))
    with views.read_projection(db, ctx):
        for _ in range(2):
            with pytest.raises(ValueError):
                await views.read_once(db, ctx, "test", "error", failure)
        assert await views.read_once(db, ctx, "test", "a", produce) == 0
        assert await views.read_once(db, ctx, "test", "b", produce) == 1
        assert await views.read_once(db, ctx, "test", "b", produce) == 2
        assert await views.read_once(db, ctx, "test", "a", produce) == 0
    assert failure.await_count == 2


async def test_child_task_cannot_reuse_a_closed_view():
    db, ctx = context()
    produce = AsyncMock(side_effect=range(10))
    gate = asyncio.Event()

    async def child():
        await gate.wait()
        return await views.read_once(db, ctx, "test", "a", produce)

    with views.read_projection(db, ctx):
        assert await views.read_once(db, ctx, "test", "a", produce) == 0
        task = asyncio.create_task(child())
    gate.set()
    assert await task == 1


async def test_nested_views_do_not_share_results_or_destroy_outer_view():
    db, ctx = context()
    produce = AsyncMock(side_effect=range(10))
    with views.read_projection(db, ctx):
        assert await views.read_once(db, ctx, "test", "a", produce) == 0
        with views.read_projection(db, ctx):
            assert await views.read_once(db, ctx, "test", "a", produce) == 1
        assert await views.read_once(db, ctx, "test", "a", produce) == 0


async def test_professional_permissions_and_locks_are_always_checked(monkeypatch):
    from app.modules.audit_execution import access, service

    db, ctx = context()
    permissions = AsyncMock(return_value=(frozenset({"audit.read"}), {"role"}))
    engagement = AsyncMock(return_value=object())
    monkeypatch.setattr(access, "_engagement_permissions", permissions)
    monkeypatch.setattr(service, "_engagement", engagement)
    with views.read_projection(db, ctx):
        for _ in range(2):
            await access.engagement_permissions(db, ctx, "eng", "audit.read")
            await service.engagement(db, ctx, "eng", lock=False)
        assert permissions.await_count == engagement.await_count == 1
        for _ in range(2):
            await access.engagement_permissions(db, ctx, "eng", "workingpaper.approve")
            await service.engagement(db, ctx, "eng", mutable=True)
            await service.engagement(db, ctx, "eng", lock=True)
        assert permissions.await_count == 3 and engagement.await_count == 5


async def test_cycle_and_depth_checks_are_not_replaced_by_cached_freshness():
    from uuid import uuid4

    from app.modules.intelligence import service

    db, ctx = context()
    db.scalar = AsyncMock(return_value=1)
    nodes = [
        SimpleNamespace(
            id=uuid4(),
            root_id=uuid4(),
            version=1,
            tenant_id=ctx.tenant_id,
            engagement_id="eng",
            kind="lead",
            body={},
            dependencies=[],
            sha256="a" * 64,
        )
        for _ in range(103)
    ]
    by_id = {node.id: node for node in nodes}
    db.get = AsyncMock(side_effect=lambda model, identifier: by_id.get(identifier))

    def link(left, right):
        left.dependencies = [{"type": "event", "id": str(right.id), "sha256": right.sha256}]

    link(nodes[0], nodes[1])
    with views.read_projection(db, ctx):
        assert await service.current(db, ctx, nodes[0])
        link(nodes[1], nodes[0])
        assert not await service.current(db, ctx, nodes[0])
        for left, right in zip(nodes, nodes[1:], strict=False):
            link(left, right)
        assert not await service.current(db, ctx, nodes[0])
    nodes[0].dependencies = []
    db.scalar.return_value = 2
    with views.read_projection(db, ctx):
        assert not await service.current(db, ctx, nodes[0])
