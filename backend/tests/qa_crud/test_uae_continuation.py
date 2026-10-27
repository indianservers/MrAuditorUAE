import json
import os
import uuid
from pathlib import Path

import pytest

from app.modules.enterprise_ai.security import serial
from app.modules.jurisdictions.ae.advanced import Schedule, calculate
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.unit.test_uae_continuation import fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database only"
)


async def test_all_continuation_cases_approved_execution_source_invalidation_and_release_controls(
    environment,
):
    c = environment
    h, options, eid, base = await setup(c)
    reviewer = await actor(h, "Audit Manager", "advanced-reviewer")
    await grant(c, h, base, reviewer)
    partner = await actor(h, "Audit Partner", "advanced-partner")
    await grant(c, h, base, partner)
    # Synthetic reviewers are explicitly qualified for all specialist read scopes.
    from sqlalchemy import select

    from app.db.models.platform import Permission, RolePermission
    from app.db.session import Session, tenant_context

    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        for rid in [reviewer[2], partner[2]]:
            for code in [
                "accounting.read",
                "vat.read",
                "tax.profile.read",
                "tp.read",
                "dmtt.read",
                "ifrs.read",
            ]:
                pid = await db.scalar(select(Permission.id).where(Permission.code == code))
                present = await db.scalar(
                    select(RolePermission.role_id).where(
                        RolePermission.role_id == uuid.UUID(rid),
                        RolePermission.permission_id == pid,
                    )
                )
                if not present:
                    db.add(RolePermission(role_id=uuid.UUID(rid), permission_id=pid))
    proof = await create(
        c,
        h,
        base,
        "working-papers",
        dict(
            folder="SYNTHETIC",
            sections=[
                dict(
                    heading="Evidence",
                    text="SYNTHETIC approved policy and population; test fixture only",
                )
            ],
            conclusion="Reviewed synthetic inputs only",
        ),
    )
    proof = await approve(c, h, reviewer[0], base, proof)
    proof = await action(c, partner[0], base, proof, "approve")
    route = f"/api/v1/ai/engagements/{eid}/use-cases"
    listing = await c.get(route, headers=h)
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 200
    from tests.phase4.test_workflows import MATERIALITY

    materiality = await create(c, h, base, "materiality", MATERIALITY)
    materiality = await approve(c, h, partner[0], base, materiality)
    receipts = []
    first = None
    payload = None
    for i in range(101, 151):
        data = fixture(i)
        data["policy"]["source_id"] = proof["id"]
        for row in data["rows"]:
            row["evidence_id"] = proof["id"]
            for key in list(row):
                if key.endswith("_source_id"):
                    row[key] = proof["id"]
        if i == 149:
            data["rows"][0].update(
                parameter_source_id=materiality["id"],
                materiality=materiality["body"]["calculation"]["overall"],
                trivial_threshold=materiality["body"]["calculation"]["clearly_trivial"],
            )
        body = dict(
            folder="SYNTHETIC",
            sections=[dict(heading="Schedule", text=f"SYNTHETIC independent input case {i}")],
            conclusion="Input awaiting independent review",
            sources=[dict(kind="record", id=proof["id"])]
            + ([dict(kind="record", id=materiality["id"])] if i == 149 else []),
            advanced_input=data,
        )
        paper = await create(c, h, base, "working-papers", body)
        command = dict(
            action="advanced-review",
            record_id=paper["id"],
            idempotency_key=f"synthetic-advanced-{i}",
        )
        denied = await c.post(f"{route}/{i}/actions", headers=h, json=command)
        assert denied.status_code == 409, (i, denied.text)
        if i == 101:
            input_listing = await c.get(route + "/101/inputs", headers=h)
            preview_id = next(
                r["draft_preview_id"]
                for r in input_listing.json()["items"]
                if r["id"] == paper["id"]
            )
            preview = await c.get(
                f"/api/v1/intelligence/engagements/{eid}/events/{preview_id}", headers=h
            )
            assert (
                preview.status_code == 200
                and preview.json()["body"]["output"]["provisional"] is True
            )
            assert preview.json()["body"]["review_status"] == "UNVERIFIED"
            cyclic = {
                **paper["body"],
                "sources": [*paper["body"]["sources"], {"kind": "record", "id": paper["id"]}],
            }
            cycle = await c.patch(
                base + "/records/" + paper["id"],
                headers=h,
                json={
                    "version": paper["version"],
                    "reference": paper["reference"],
                    "title": paper["title"],
                    "body": cyclic,
                },
            )
            assert cycle.status_code == 422, cycle.text
            changed_body = {
                **paper["body"],
                "advanced_input": {
                    **data,
                    "rows": [
                        {**data["rows"][0], "request_text": "SYNTHETIC revised evidence request"}
                    ],
                },
            }
            updated = await c.patch(
                base + "/records/" + paper["id"],
                headers=h,
                json={
                    "version": paper["version"],
                    "reference": paper["reference"],
                    "title": paper["title"],
                    "body": changed_body,
                },
            )
            assert updated.status_code == 200, updated.text
            paper = updated.json()
            data = changed_body["advanced_input"]
            old_preview = await c.get(
                f"/api/v1/intelligence/engagements/{eid}/events/{preview_id}", headers=h
            )
            assert old_preview.json()["freshness"] == "STALE"
            new_listing = await c.get(route + "/101/inputs", headers=h)
            assert (
                next(
                    r["draft_preview_id"]
                    for r in new_listing.json()["items"]
                    if r["id"] == paper["id"]
                )
                != preview_id
            )
        submitted = await action(c, h, base, paper, "submit")
        await action(c, h, base, submitted, "approve", 403)
        paper = await action(c, reviewer[0], base, submitted, "approve")
        paper = await action(c, partner[0], base, paper, "approve")
        result = await c.post(f"{route}/{i}/actions", headers=h, json=command)
        assert result.status_code == 201, (i, result.text)
        value = result.json()
        out = value["body"]["output"]
        assert out["results"] == serial(calculate(Schedule.model_validate(data)))
        assert out["entity_id"] == options["entity_id"]
        assert len(value["dependencies"]) >= 3
        if i == 149:
            from copy import deepcopy

            incorrect = deepcopy(body)
            incorrect["advanced_input"]["rows"][0].update(materiality="1", trivial_threshold="1")
            wrong = await create(c, h, base, "working-papers", incorrect)
            wrong = await approve(c, h, reviewer[0], base, wrong)
            wrong = await action(c, partner[0], base, wrong, "approve")
            rejected = await c.post(
                f"{route}/149/actions",
                headers=h,
                json={
                    "action": "advanced-review",
                    "record_id": wrong["id"],
                    "idempotency_key": "wrong-native-materiality-rejected",
                },
            )
            assert rejected.status_code == 422, rejected.text
        repeated = await c.post(f"{route}/{i}/actions", headers=h, json=command)
        assert repeated.status_code == 201 and repeated.json()["id"] == value["id"]
        command["payload"] = {"rows": []}
        conflict = await c.post(f"{route}/{i}/actions", headers=h, json=command)
        assert conflict.status_code == 409
        if i == 101:
            first = value
            payload = {**command, "payload": {}}
        receipts.append(
            dict(
                use_case_id=i,
                unapproved=409,
                self_approval=403,
                engine_http=201,
                exact_result_match=True,
                idempotent=True,
            )
        )
    # An approved consultation input can retain substantive release blockers.
    quality = fixture(150)
    quality["policy"]["source_id"] = proof["id"]
    quality["rows"][0]["evidence_id"] = proof["id"]
    quality["rows"][0]["conclusion_approved"] = False
    quality_paper = await create(
        c,
        h,
        base,
        "working-papers",
        dict(
            folder="SYN",
            sections=[dict(heading="Consultation", text="SYNTHETIC unresolved conclusion")],
            conclusion="Input reviewed, release matter remains unresolved",
            sources=[dict(kind="record", id=proof["id"])],
            advanced_input=quality,
        ),
    )
    quality_paper = await approve(c, h, reviewer[0], base, quality_paper)
    quality_paper = await action(c, partner[0], base, quality_paper, "approve")
    completion = await c.get(base + "/completion-checks", headers=h)
    assert completion.status_code == 200
    check = next(
        c
        for c in completion.json()["checks"]
        if c["code"] == "quality_consultation_" + quality_paper["id"]
    )
    assert check["passed"] is False
    # Actual file readiness reads persisted population; a new draft invalidates the prior snapshot.
    file_check = await c.post(
        route + "/100/actions",
        headers=h,
        json=dict(action="file-readiness", idempotency_key="synthetic-file-readiness"),
    )
    assert file_check.status_code == 201, file_check.text
    assert file_check.json()["body"]["output"]["audit_opinion"] is None
    file_id = file_check.json()["id"]
    await create(
        c,
        h,
        base,
        "working-papers",
        dict(
            folder="SYN",
            sections=[dict(heading="New", text="SYN")],
            conclusion="Unreviewed new paper",
        ),
    )
    changed = await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{file_id}", headers=h)
    assert changed.status_code == 200 and changed.json()["freshness"] == "STALE"
    # Draft paper metadata must not be promoted to approved source receipts in the assistant plan.
    command = await c.post(
        "/api/v1/ai/command",
        headers=h,
        json={
            "engagement_id": eid,
            "task": "uae-112",
            "prompt": "SYNTHETIC collect approved allocation evidence with drafts present",
            "idempotency_key": "synthetic-advanced-collection-with-drafts",
            "inputs": {},
        },
    )
    assert command.status_code == 201, command.text
    final = None
    for _ in command.json()["plan"]:
        final = await c.post(
            f"/api/v1/ai/engagements/{eid}/investigations/{command.json()['id']}/step", headers=h
        )
        assert final.status_code == 200, final.text
    assert final.json()["state"] in {"COMPLETED", "PARTIALLY_COMPLETED"}
    # Source reopen must invalidate the reviewed input and every dependent retained action.
    await action(c, reviewer[0], base, proof, "reopen")
    stale = await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{first['id']}", headers=h)
    assert stale.status_code == 200 and stale.json()["freshness"] == "STALE", stale.text
    inbox = await c.get(route + "/101/alerts", headers=reviewer[0])
    assert inbox.status_code == 200 and len(inbox.json()["items"]) == 1
    assert inbox.json()["items"][0]["previous_approved_version_preserved"]
    assert inbox.json()["email_or_push_delivered"] is False
    repeat = await c.post(f"{route}/101/actions", headers=h, json=payload)
    assert repeat.status_code == 409, repeat.text
    wrong_tenant = await c.get(route, headers={**h, "X-Tenant-ID": str(uuid.uuid4())})
    assert wrong_tenant.status_code in {403, 404}
    target = (
        Path(__file__).resolve().parents[3]
        / "docs/mr-auditor-business/evidence/continuation-case-results.json"
    )
    target.write_text(
        json.dumps(
            dict(
                synthetic=True,
                cases=receipts,
                source_reopen_invalidates=True,
                tenant_isolation=True,
            ),
            indent=2,
        )
    )
