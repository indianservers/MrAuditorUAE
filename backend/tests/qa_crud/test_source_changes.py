"""Real PostgreSQL regressions for source replacement and lifecycle consistency."""

import os
import uuid
from decimal import Decimal

import pytest

from app.core.dependencies import Context
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.accounting.models import ImportSnapshot
from app.modules.ml import service as ml
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import setup
from tests.phase5.test_reporting import CSV, prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable QA database required"
)


async def replacement(c, h, eid, snapshot_id, amount="55", scale=1):
    engagement = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    entity = (await c.get("/api/v1/entities/" + engagement["entity_id"], headers=h)).json()
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        original = await db.get(ImportSnapshot, uuid.UUID(snapshot_id))
        bid = str(original.batch_id)
    payload = CSV.replace(b",50,0,L3", f",{amount},0,L3".encode()).replace(
        b",0,50,L4", f",0,{amount},L4".encode()
    )
    if scale != 1:
        import csv
        import io

        rows = list(csv.reader(io.StringIO(payload.decode())))
        for row in rows[1:]:
            row[4] = str(Decimal(row[4]) * scale)
            row[5] = str(Decimal(row[5]) * scale)
        stream = io.StringIO()
        csv.writer(stream, lineterminator="\n").writerows(rows)
        payload = stream.getvalue().encode()
    opts = {
        "client_id": entity["client_id"],
        "entity_id": entity["id"],
        "period_id": engagement["period_id"],
        "source_complete": True,
        "expected_rows": 6,
        "expected_debit": str((Decimal(120) + Decimal(amount)) * scale),
        "expected_credit": str((Decimal(120) + Decimal(amount)) * scale),
        "supersedes_id": bid,
    }
    return await committed(c, h, opts, payload)


@pytest.mark.parametrize("scale", [1, 20000])
async def test_ifrs_current_status_invalidates_after_real_import_supersession(environment, scale):
    c = environment
    h, eid, base, reviewer, partner, profile, mapping, note, ready = await prepared(c, scale=scale)
    run = await c.post(
        f"/api/v1/ifrs/engagements/{eid}/financial-statements/{profile['id']}", headers=h
    )
    assert run.status_code == 201, run.text
    before = run.json()
    url = f"/api/v1/ifrs/engagements/{eid}/runs/{before['id']}"
    assert (await c.get(url + "/validate", headers=h)).json()["dependencies_current"] is True
    _, replacement_snapshot = await replacement(
        c, h, eid, profile["body"]["snapshot_id"], scale=scale
    )
    check = await c.get(url + "/validate", headers=h)
    assert check.status_code == 200
    assert check.json()["dependencies_current"] is False
    registry = await c.get(base + "/dependencies", headers=h)
    assert registry.status_code == 200, registry.text
    result = next(r for r in registry.json()["items"] if r["id"] == before["id"])
    assert result["freshness"]["status"] == "STALE"
    assert result["history_preserved"] is True
    assert (await c.get(url, headers=h)).json()["sha256"] == before["sha256"]
    assert (
        await c.post(
            f"/api/v1/ifrs/engagements/{eid}/financial-statements/{profile['id']}", headers=h
        )
    ).status_code == 409

    revised = await ready(
        "profile",
        {
            **{k: v for k, v in profile["body"].items() if not k.startswith("review_")},
            "snapshot_id": replacement_snapshot,
        },
    )
    await ready(
        "mapping",
        {
            **{k: v for k, v in mapping["body"].items() if not k.startswith("review_")},
            "profile_id": revised["id"],
        },
    )
    regenerated = await c.post(
        f"/api/v1/ifrs/engagements/{eid}/financial-statements/{revised['id']}", headers=h
    )
    assert regenerated.status_code == 201, regenerated.text
    assert (
        Decimal(regenerated.json()["results"]["totals"]["profit"])
        - Decimal(before["results"]["totals"]["profit"])
        == Decimal(5) * scale
    )


async def test_ml_dataset_excludes_superseded_lines_and_marks_old_features_stale(environment):
    c = environment
    h, eid, base, reviewer, partner, profile, *_ = await prepared(c)
    uid = decode_token(h["Authorization"].split()[1])
    ctx = Context(
        uid, uuid.UUID(h["X-Tenant-ID"]), frozenset(ROLE_PERMISSIONS["Firm Administrator"])
    )
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        old = await ml.execute_job(db, ctx, {"operation": "dataset", "engagement_id": eid})
    await replacement(c, h, eid, profile["body"]["snapshot_id"])
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        new = await ml.execute_job(db, ctx, {"operation": "dataset", "engagement_id": eid})
    latest = await c.get("/api/v1/ml/events/" + new["id"], headers=h)
    assert latest.status_code == 200
    assert latest.json()["body"]["total_rows"] == 6
    previous = await c.get("/api/v1/ml/events/" + old["id"], headers=h)
    assert previous.status_code == 200
    assert previous.json()["freshness"]["status"] == "STALE"
    blocked = await c.post(
        "/api/v1/ml/training-jobs",
        headers=h,
        json={"source_id": old["id"], "family": "autoencoder"},
    )
    assert blocked.status_code == 409, blocked.text
    engagement = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    entity = (await c.get("/api/v1/entities/" + engagement["entity_id"], headers=h)).json()
    changed = await c.post(
        "/api/v1/accounting/mappings",
        headers=h,
        json={
            "client_id": entity["client_id"],
            "entity_id": entity["id"],
            "period_id": engagement["period_id"],
            "name": "SYNTHETIC changed chart",
            "approved": True,
            "mapping": {"accounts": {"100": {"classification": "Expenses"}}},
        },
    )
    assert changed.status_code == 201, changed.text
    assert (await c.get("/api/v1/ml/events/" + new["id"], headers=h)).json()["freshness"][
        "status"
    ] == "STALE"


async def test_archived_client_hidden_from_active_list_and_blocks_new_children(environment):
    c = environment
    h, opts, eid, base = await setup(c)
    client = await c.post(
        "/api/v1/clients",
        headers=h,
        json={"code": "CRUD-ARCHIVE", "name": "SYNTHETIC archived company", "status": "archived"},
    )
    assert client.status_code == 201, client.text
    identifier = client.json()["id"]
    result = await c.get("/api/v1/clients?search=SYNTHETIC%20archived", headers=h)
    assert result.json()["total"] == 0
    assert (await c.get("/api/v1/clients?status=archived", headers=h)).json()["total"] == 1
    child = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": identifier,
            "name": "SYNTHETIC invalid child",
            "country": "AE",
            "jurisdiction": "SYNTHETIC QA",
            "functional_currency": "AED",
            "presentation_currency": "AED",
        },
    )
    assert child.status_code == 409


async def test_client_archival_cannot_bypass_active_engagement_guard(environment):
    c = environment
    h, options, eid, base = await setup(c)
    old = (await c.get("/api/v1/clients/" + options["client_id"], headers=h)).json()
    changed = await c.patch(
        "/api/v1/clients/" + old["id"],
        headers=h,
        json={
            "version": old["version"],
            "status": "archived",
            "lifecycle_reason": "Synthetic archival with unfinished engagement",
        },
    )
    assert changed.status_code == 409, changed.text
