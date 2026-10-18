"""Persisted archive/restore checks with immutable revision history."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import PAPER, action, actor, approve, create, grant, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_draft_archive_restore_history(environment):
    c = environment
    h, _, _, base = await setup(c)
    obj = await create(c, h, base, "working-papers", PAPER, "CRUD-UNICODE-دبي")
    url = base + "/records/" + obj["id"]
    archived = await action(c, h, base, obj, "archive")
    assert archived["status"] == "ARCHIVED"
    assert (await c.get(url, headers=h)).json()["status"] == "ARCHIVED"
    assert not (await c.get(base + "/working-papers", headers=h)).json()["items"]
    assert (await c.get(base + "/working-papers?status=ARCHIVED", headers=h)).json()["items"][0][
        "id"
    ] == obj["id"]
    assert (
        await c.patch(
            url,
            headers=h,
            json={
                "version": obj["version"],
                "title": "Stale overwrite",
                "reference": obj["reference"],
                "body": PAPER,
            },
        )
    ).status_code == 409
    await action(c, h, base, archived, "archive", 409)
    restored = await action(c, h, base, archived, "restore")
    assert restored["id"] == obj["id"] and restored["status"] == obj["status"]
    assert restored["version"] == obj["version"] + 2
    assert len((await c.get(url + "/history", headers=h)).json()["versions"]) == 3
    assert (await c.delete(url, headers=h)).status_code == 405
    await action(c, h, base, restored, "restore", 409)


async def test_reviewed_record_cannot_be_archived(environment):
    c = environment
    h, _, _, base = await setup(c)
    reviewer = await actor(h, "Audit Manager", "crud-reviewer")
    await grant(c, h, base, reviewer)
    obj = await create(c, h, base, "working-papers", PAPER)
    obj = await approve(c, h, reviewer[0], base, obj)
    await action(c, h, base, obj, "archive", 409)


async def test_client_restore_and_conflict(environment):
    c = environment
    h, _, _, _ = await setup(c)
    row = (
        await c.post(
            "/api/v1/clients", headers=h, json={"code": "CRUD-RESTORE", "name": "SYNTHETIC دبي"}
        )
    ).json()
    url = "/api/v1/clients/" + row["id"]
    archive = await c.patch(
        url,
        headers=h,
        json={
            "version": row["version"],
            "status": "archived",
            "lifecycle_reason": "Synthetic unused client archival",
        },
    )
    assert archive.status_code == 200, archive.text
    assert (
        await c.patch(
            url, headers=h, json={"version": row["version"], "name": "Concurrent overwrite"}
        )
    ).status_code == 409
    restore = await c.patch(
        url,
        headers=h,
        json={
            "version": archive.json()["version"],
            "status": "active",
            "lifecycle_reason": "Synthetic client restoration review",
        },
    )
    assert restore.status_code == 200, restore.text
    assert restore.json()["id"] == row["id"] and restore.json()["name"] == row["name"]
    assert (
        await c.post(
            "/api/v1/clients", headers=h, json={"code": row["code"], "name": "Duplicate synthetic"}
        )
    ).status_code == 409


@pytest.mark.parametrize("reason", ["", "short", "         "])
async def test_archive_requires_meaningful_reason(environment, reason):
    c = environment
    h, _, _, base = await setup(c)
    obj = await create(c, h, base, "working-papers", PAPER)
    result = await c.post(
        base + "/records/" + obj["id"] + "/actions",
        headers=h,
        json={"action": "archive", "comments": reason, "version": obj["version"]},
    )
    assert result.status_code == 422


async def test_referenced_draft_archive_is_blocked(environment):
    c = environment
    h, _, _, base = await setup(c)
    source = await create(c, h, base, "working-papers", PAPER)
    await create(
        c, h, base, "working-papers", {**PAPER, "sources": [{"kind": "record", "id": source["id"]}]}
    )
    await action(c, h, base, source, "archive", 409)


async def test_cross_tenant_and_read_only_role_cannot_archive(environment):
    c = environment
    h, _, _, base = await setup(c)
    obj = await create(c, h, base, "working-papers", PAPER)
    reader = await actor(h, "Read-only Reviewer", "crud-reader")
    await grant(c, h, base, reader)
    await action(c, reader[0], base, obj, "archive", 403)
    await action(
        c, {**h, "X-Tenant-ID": "00000000-0000-4000-8000-000000000001"}, base, obj, "archive", 403
    )


async def test_restore_revalidates_archived_dependency(environment):
    c = environment
    h, _, _, base = await setup(c)
    source = await create(c, h, base, "working-papers", PAPER)
    child = await create(
        c, h, base, "working-papers", {**PAPER, "sources": [{"kind": "record", "id": source["id"]}]}
    )
    child = await action(c, h, base, child, "archive")
    await action(c, h, base, source, "archive")
    await action(c, h, base, child, "restore", 409)
