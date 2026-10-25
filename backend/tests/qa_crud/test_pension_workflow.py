"""Owned database/API/storage verification with explicit scanner/broker doubles."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_pension_workflow import pension_fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def prepared(c, monkeypatch):
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "pension-source-reviewer")
    await grant(c, h, base, reviewer)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    response = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-pension-rule.pdf",
                b"%PDF-1.4\nSYNTHETIC PENSION ARITHMETIC ONLY\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201, response.text
    retained = response.json()
    bases, rules, reported = pension_fixture()
    for rule in rules:
        rule.update(source_evidence_version_id=retained["id"], source_sha256=retained["sha256"])
    sources = {
        "bases": await source(
            c,
            h,
            eid,
            bases,
            "Synthetic pension salary and continuity",
            "pension-bases",
            {"AED": "30000.03"},
        ),
        "rules": await source(c, h, eid, rules, "Synthetic pension rules", "pension-rules", {}),
        "reported": await source(
            c,
            h,
            eid,
            reported,
            "Synthetic authority contribution report",
            "pension-reported",
            {"AED": "2500"},
        ),
    }
    payload = dict(
        workflow="uae-pension-review",
        source_ids={role: item["id"] for role, item in sources.items()},
        as_of="2026-06-30",
        currency="AED",
        title="Synthetic sourced pension contributions",
        rationale="Independent salary basis, membership continuity, legal source and reported contribution fixtures",
    )
    return h, eid, base, reviewer, record, retained, sources, payload, rules


async def test_independent_sources_calculation_export_and_original_rule_replacement(
    environment, monkeypatch
):
    c = environment
    h, eid, base, reviewer, record, retained, sources, payload, _ = await prepared(c, monkeypatch)
    await execute(c, h, eid, "country-workflow", payload, failed="Independently review all pension")
    for role, item in sources.items():
        assert (await decision(c, h, eid, item)).status_code == 403
        response = await decision(c, reviewer[0], eid, item)
        assert response.status_code == 201, response.text
        payload["source_ids"][role] = response.json()["id"]
    result = await execute(c, h, eid, "country-workflow", payload)
    body = result["body"]
    assert body["expected_total"] == "2500.00" and body["expected_total_complete"]
    assert not body["blocked"] and body["exception_count"] == 0
    assert any(
        item["type"] == "evidence" and item["id"] == retained["id"]
        for item in result["dependencies"]
    )
    assert (await decision(c, h, eid, result)).status_code == 403
    final = await actor(h, "Firm Administrator", "pension-final-reviewer")
    await grant(c, h, base, final)
    reviewed = await decision(c, final[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    approved = reviewed.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{approved['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    changed = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-pension-rule-v2.pdf",
                b"%PDF-1.4\nSYNTHETIC CHANGED PENSION RULE\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    original = await c.get(path, headers=h)
    assert original.status_code == 200 and original.json()["freshness"] == "STALE"
    assert original.json()["sha256"] == approved["sha256"]
    await execute(c, h, eid, "country-workflow", payload, failed="source")


async def test_rule_hash_and_country_cannot_be_asserted_without_support(environment, monkeypatch):
    c = environment
    h, eid, _, _, _, _, _, _, rules = await prepared(c, monkeypatch)
    rules[0]["source_sha256"] = "b" * 64
    await source(
        c,
        h,
        eid,
        rules,
        "Synthetic mismatched pension document",
        "pension-rules",
        {},
        failed="document hash differs",
    )


async def test_pension_sources_are_unavailable_for_an_india_engagement(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    india_h, india_eid, _ = await india_context(c)
    bases, _, _ = pension_fixture()
    await source(
        c,
        india_h,
        india_eid,
        bases,
        "Synthetic pension wrong country",
        "pension-bases",
        {"AED": "30000.03"},
        failed="UAE engagement",
    )
