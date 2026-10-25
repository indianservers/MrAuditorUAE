"""Withdrawal preserves legal history, blocks fallback and propagates freshness."""

import os
import uuid
from copy import deepcopy

import pytest

from app.db.session import Session, tenant_context
from app.modules.lineage.storage import ObjectStore
from app.modules.regulatory.models import RuleSourceDocument
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import decision, double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.qa_crud.test_regulatory_sources import decide, propose, rule_payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_withdrawal_blocks_fallback_preserves_history_and_requires_reviewed_replacement(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "withdrawal-reviewer")
    manager = await actor(h, "Tax Manager", "withdrawal-tax-manager")
    await grant(c, h, base, reviewer)
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    response = await c.post(
        path,
        headers=h,
        json={
            "country": country,
            "framework": "IFRS" if country == "AE" else "Ind AS",
            "entity_type": "company",
            "as_of": "2026-12-31" if country == "AE" else "2027-03-31",
            "base_version": 0,
            "reason": "Synthetic reporting context for rule withdrawal checks",
        },
    )
    assert response.status_code == 201, response.text
    reviewed_context = await c.post(
        path + "/decision",
        headers=reviewer[0],
        json={
            "request_id": response.json()["id"],
            "approve": True,
            "comments": "Independent synthetic rule withdrawal context assessment",
        },
    )
    assert reviewed_context.status_code == 201, reviewed_context.text
    payload = rule_payload(country, key="SYNTHETIC-WITHDRAWAL")
    payload["period_basis"] = "transaction_date"
    await retain(c, h, payload)
    old = await propose(c, h, payload)
    assert (await decide(c, reviewer[0], old)).status_code == 201
    assert (await decide(c, h, old, action="publish", sequence=2)).status_code == 201
    newer = {**deepcopy(payload), "effective_from": "2026-06-01", "expected_sequence": 3}
    document = await retain(c, h, newer)
    current = await propose(c, h, newer)
    assert (await decide(c, reviewer[0], current, sequence=4)).status_code == 201
    assert (await decide(c, h, current, action="publish", sequence=5)).status_code == 201
    assessment_path = f"/api/v1/regulatory/engagements/{eid}/assessments"

    async def assess(identifier, day):
        return await c.post(
            assessment_path,
            headers=h,
            json={
                "rule_ids": [identifier],
                "transaction_date": day,
                "facts": {"entity_type": "company"},
                "rationale": "Synthetic source-qualified applicability before rule withdrawal",
            },
        )

    may = await assess(old, "2026-05-31")
    june = await assess(current, "2026-06-30")
    assert may.status_code == june.status_code == 201, june.text
    # A later draft must not prevent emergency withdrawal of the active published version.
    draft = await propose(c, h, {**newer, "expected_sequence": 6, "effective_from": "2026-07-01"})
    assert (await decide(c, h, draft, action="withdraw", sequence=7)).status_code == 409
    denied_manager = await decide(c, manager[0], current, action="withdraw", sequence=7)
    assert denied_manager.status_code == 403 and "administrator may withdraw" in denied_manager.text
    assert (await decide(c, h, current, action="withdraw", sequence=6)).status_code == 409
    invalid_reason = await c.post(
        f"/api/v1/regulatory/rules/{current}/decisions",
        headers=h,
        json={"action": "withdraw", "expected_sequence": 7, "comments": " " * 20},
    )
    assert invalid_reason.status_code == 422
    # Source corruption must not obstruct withdrawal; restoring bytes cannot restore a withdrawn rule.
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        stored = await db.get(RuleSourceDocument, uuid.UUID(document["id"]))
        key, version = stored.object_key, stored.object_version
    with ObjectStore().local(key, version) as source_path:
        original = source_path.read_bytes()
        try:
            source_path.write_bytes(original.replace(b"SYNTHETIC", b"SYNTHETIX", 1))
            withdrawn = await decide(c, h, current, action="withdraw", sequence=7)
            assert withdrawn.status_code == 201, withdrawn.text
            assert withdrawn.json()["state"] == "WITHDRAWN"
        finally:
            source_path.write_bytes(original)
    assert (await decide(c, h, current, action="withdraw", sequence=8)).status_code == 409
    for identifier in (old, current):
        blocked = await assess(identifier, "2026-06-30")
        assert blocked.status_code == 409 and "withdrawn_rule" in blocked.text
    for saved, expected in ((may.json(), "CURRENT"), (june.json(), "STALE")):
        history = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}", headers=h
        )
        assert history.status_code == 200 and history.json()["freshness"] == expected
        assert history.json()["sha256"] == saved["sha256"]
    refused_review = await decision(c, reviewer[0], eid, june.json())
    assert refused_review.status_code == 409, refused_review.text
    impact = await c.get(f"/api/v1/regulatory/rules/{current}/impact", headers=h)
    assert impact.status_code == 200 and any(
        row["result_id"] == june.json()["id"] and row["freshness"] == "STALE"
        for row in impact.json()["items"]
    )
    # Restore the older content through a new, independently approved version, never a hidden fallback.
    replacement = {
        **payload,
        "expected_sequence": 8,
        "reverts_version_id": old,
        "amendment_reason": "Synthetic explicitly reviewed restoration of older source-qualified content",
    }
    replacement_id = await propose(c, h, replacement)
    assert (await decide(c, h, replacement_id, action="publish", sequence=9)).status_code == 409
    assert (await decide(c, reviewer[0], replacement_id, sequence=9)).status_code == 201
    assert (await decide(c, h, replacement_id, action="publish", sequence=10)).status_code == 201
    restored = await assess(replacement_id, "2026-06-30")
    assert restored.status_code == 201, restored.text
    original_rule = await c.get(f"/api/v1/regulatory/rules/{current}", headers=h)
    assert original_rule.json()["state"]["state"] == "WITHDRAWN"
