"""Synthetic benefit rules reuse retained evidence, independent review and staleness."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_practice_audit_workflows import (
    benefit_employee,
    benefit_rule,
    part_time_employee,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_benefit_rule_document_binding_review_export_and_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "benefit-rule-reviewer")
    await grant(c, h, base, reviewer)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-benefit-rule.pdf",
                b"%PDF-1.4\nSYNTHETIC ONLY\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    bare = {
        k: v
        for k, v in benefit_rule().items()
        if k not in {"source_sha256", "source_evidence_version_id"}
    }
    rules = await source(
        c,
        h,
        eid,
        [bare, {**bare, "id": "PART-TIME-RULE", "work_model": "part-time"}],
        "Synthetic benefit rules",
        "benefit-rules",
        {},
        rule_document_version_id=document["id"],
    )
    assert rules["body"]["rows"][0]["source_sha256"] == document["sha256"]
    employees = await source(
        c,
        h,
        eid,
        [benefit_employee(), part_time_employee(id="E2")],
        "Synthetic benefit employee",
        "benefit-employees",
        {"AED": "3150"},
    )
    payload = {
        "workflow": "uae-benefit-review",
        "source_ids": {"employees": employees["id"], "rules": rules["id"]},
        "as_of": "2026-06-30",
        "currency": "AED",
        "title": "Synthetic retained-rule benefit review",
        "rationale": "Synthetic service facts and independently reviewed retained rule evidence",
    }
    await execute(c, h, eid, "country-workflow", payload, failed="Independently review")
    assert (await decision(c, h, eid, rules)).status_code == 403
    approved = await decision(c, reviewer[0], eid, rules)
    assert approved.status_code == 201, approved.text
    payload["source_ids"]["rules"] = approved.json()["id"]
    result = await execute(c, h, eid, "country-workflow", payload)
    row = result["body"]["rows"][0]
    assert (
        row["expected_benefit"] == "2100.00" and row["rule_document_sha256"] == document["sha256"]
    )
    assert row["rule_document_version_id"] == document["id"]
    part_time = next(item for item in result["body"]["rows"] if item["id"] == "E2")
    assert part_time["expected_benefit"] == "1050.00"
    assert part_time["benefit_proportion"] == "0.5" and part_time["state"] == "MATCHED"
    assert any(
        dep["type"] == "evidence" and dep["id"] == document["id"] for dep in result["dependencies"]
    )
    final_reviewer = await actor(h, "Firm Administrator", "benefit-final-reviewer")
    await grant(c, h, base, final_reviewer)
    premature = await decision(c, final_reviewer[0], eid, result)
    assert premature.status_code == 409, premature.text
    reviewed_employees = await decision(c, reviewer[0], eid, employees)
    assert reviewed_employees.status_code == 201, reviewed_employees.text
    payload["source_ids"]["employees"] = reviewed_employees.json()["id"]
    regenerated = await execute(c, h, eid, "country-workflow", payload)
    final = await decision(c, final_reviewer[0], eid, regenerated)
    assert final.status_code == 201, final.text
    result = final.json()
    assert result["body"]["review_status"] == "REVIEWED"
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    bad = {
        **benefit_rule(),
        "source_evidence_version_id": document["id"],
        "source_sha256": "b" * 64,
    }
    await source(
        c,
        h,
        eid,
        [bad],
        "Synthetic wrong benefit hash",
        "benefit-rules",
        {},
        failed="document hash differs",
    )
    replaced = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-benefit-rule-v2.pdf",
                b"%PDF-1.4\nSYNTHETIC REPLACEMENT\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert replaced.status_code == 201, replaced.text
    for identifier in (approved.json()["id"], result["id"]):
        detail = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{identifier}", headers=h
        )
        assert detail.status_code == 200 and detail.json()["freshness"] == "STALE"
