"""Pagination reaches old source versions without weakening event authorization."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import Session, tenant_context
from app.modules.intelligence.models import IntelligenceEvent
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


async def test_newest_keyset_history_crosses_100_events_and_keeps_stable_ties(environment):
    c = environment
    h, _, eid, _ = await setup(c)
    stamp = datetime(2026, 6, 30, tzinfo=UTC)
    identifiers = [uuid.uuid4() for _ in range(105)]
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        for identifier in identifiers:
            db.add(
                IntelligenceEvent(
                    id=identifier,
                    tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                    engagement_id=uuid.UUID(eid),
                    root_id=identifier,
                    version=1,
                    kind="source-table",
                    body={"table_kind": "bank", "source_filename": "SYNTHETIC history source"},
                    dependencies=[],
                    sha256="a" * 64,
                    created_at=stamp,
                )
            )
    path = f"/api/v1/intelligence/engagements/{eid}/events"
    first = await c.get(path + "?newest=true&limit=100", headers=h)
    assert first.status_code == 200, first.text
    first = first.json()
    ordered = sorted(map(str, identifiers), reverse=True)
    assert [row["id"] for row in first["items"]] == ordered[:100]
    assert first["truncated"] and first["next_before"] == ordered[99]
    # A concurrent new result must not shift the older-page boundary.
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        identifier = uuid.uuid4()
        db.add(
            IntelligenceEvent(
                id=identifier,
                tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                engagement_id=uuid.UUID(eid),
                root_id=identifier,
                version=1,
                kind="ocr",
                body={},
                dependencies=[],
                sha256="b" * 64,
                created_at=stamp + timedelta(seconds=1),
            )
        )
    tail = await c.get(
        path, headers=h, params={"newest": "true", "before": first["next_before"], "limit": 100}
    )
    assert tail.status_code == 200, tail.text
    assert [row["id"] for row in tail.json()["items"]] == ordered[100:]
    assert tail.json()["next_before"] is None and not tail.json()["truncated"]
    assert (await c.get(path, headers=h, params={"before": ordered[99]})).status_code == 422
    assert (
        await c.get(
            path, headers=h, params={"newest": "true", "before": ordered[99], "after": ordered[0]}
        )
    ).status_code == 422
    assert (
        await c.get(path, headers=h, params={"newest": "true", "before": str(uuid.uuid4())})
    ).status_code == 404
    assert (
        await c.get(
            path, headers=h, params={"newest": "true", "before": ordered[99], "kind": "ocr"}
        )
    ).status_code == 404
    legacy = await c.get(path, headers=h, params={"limit": 100})
    assert legacy.status_code == 200 and legacy.json()["next_cursor"]
    assert legacy.json()["next_before"] is None
