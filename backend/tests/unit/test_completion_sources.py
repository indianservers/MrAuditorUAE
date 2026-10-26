import uuid
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException

from app.modules.audit_execution import completion_sources as module


def row(status="APPROVED", kind="working-papers"):
    return NS(id=uuid.uuid4(), status=status, kind=kind, body={"private": "must not appear"})


@pytest.mark.parametrize("state", ["STALE", "BLOCKED", "UNVERIFIED", "UNKNOWN"])
async def test_every_noncurrent_reviewed_record_blocks_release(monkeypatch, state):
    records = [row(), row("LOCKED"), row("CLOSED"), row("ARCHIVED"), row("IN_PROGRESS")]
    calls = []

    async def freshness(db, ctx, record, **kwargs):
        calls.append((record.id, kwargs))
        return state if record.id == records[1].id else "CURRENT"

    monkeypatch.setattr(module, "freshness", freshness)
    result = await module.reviewed_source_control(None, None, records)
    assert not result["passed"] and result["checked_records"] == 2
    assert result["record_ids"] == [str(records[1].id)]
    assert result["source_issues"] == [
        dict(record_id=str(records[1].id), kind="working-papers", freshness=state)
    ]
    assert calls[0][1]["cache"] is calls[1][1]["cache"]
    assert all("expected" not in kwargs for _, kwargs in calls)
    assert "private" not in str(result)


@pytest.mark.parametrize(
    "error",
    [
        ValueError("bad receipt"),
        KeyError("missing"),
        TypeError("invalid legacy receipt"),
        HTTPException(403),
        HTTPException(404),
        HTTPException(409),
        HTTPException(422),
    ],
)
async def test_unverifiable_receipts_never_pass(monkeypatch, error):
    async def freshness(*args, **kwargs):
        raise error

    monkeypatch.setattr(module, "freshness", freshness)
    result = await module.reviewed_source_control(None, None, [row()])
    assert not result["passed"]
    assert result["source_issues"][0]["freshness"] in {"BLOCKED", "UNVERIFIED"}


async def test_unexpected_backend_failure_is_not_silently_classified_as_current(monkeypatch):
    async def freshness(*args, **kwargs):
        raise HTTPException(503)

    monkeypatch.setattr(module, "freshness", freshness)
    with pytest.raises(HTTPException) as caught:
        await module.reviewed_source_control(None, None, [row()])
    assert caught.value.status_code == 503


async def test_large_review_population_is_not_truncated_to_a_history_preview(monkeypatch):
    records = [row(kind="testing") for _ in range(1001)]

    async def freshness(db, ctx, record, **kwargs):
        return "STALE" if record is records[-1] else "CURRENT"

    monkeypatch.setattr(module, "freshness", freshness)
    result = await module.reviewed_source_control(None, None, records)
    assert result["checked_records"] == 1001 and not result["passed"]
    assert result["record_ids"] == [str(records[-1].id)]
