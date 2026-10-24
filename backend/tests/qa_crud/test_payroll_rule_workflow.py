import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_india_ecr_source import ECR
from tests.unit.test_payroll_rule_workflow import pf_fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def prepared(c, monkeypatch):
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "payroll-source-reviewer")
    await grant(c, h, base, reviewer)
    document = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    legal = await c.post(
        base + "/evidence-files/" + document["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-rule-evidence.pdf",
                b"%PDF-1.4\nSYNTHETIC RULE FIXTURE ONLY\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert legal.status_code == 201, legal.text
    bases, rules, _ = pf_fixture()
    for rule in rules:
        rule.update(
            source_evidence_version_id=legal.json()["id"], source_sha256=legal.json()["sha256"]
        )
    wage_source = await source(
        c, h, eid, bases, "Synthetic assessed component bases", "payroll-bases", {"INR": "60000"}
    )
    rule_source = await source(
        c, h, eid, rules, "Synthetic sourced payroll rules", "payroll-rules", {}
    )
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={
            "file": ("SYNTHETIC-rule-comparison-ecr.txt", ECR.splitlines()[0] + b"\n", "text/plain")
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    native = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "file_format": "india-epfo-ecr",
            "table_type": "obligations",
            "employer_registration": "EPFO-SYNTHETIC",
            "obligation_period": "2026-06",
            "expected_members": 1,
            "expected_rows": 3,
            "control_totals": {"INR": "3600"},
            "label": "Synthetic reported PF contributions",
        },
    )
    payload = {
        "workflow": "india-payroll-rules",
        "source_ids": {
            "bases": wage_source["id"],
            "rules": rule_source["id"],
            "reported": native["id"],
        },
        "as_of": "2026-06-30",
        "currency": "INR",
        "title": "Synthetic source-bound PF contribution review",
        "rationale": "Independent rule evidence, assessed bases and native reported contributions",
    }
    return h, eid, base, reviewer, document, legal.json(), rule_source, payload, rules


async def test_rule_review_retained_evidence_native_ecr_export_and_staleness(
    environment, monkeypatch
):
    c = environment
    h, eid, base, reviewer, document, legal, rule_source, payload, _ = await prepared(
        c, monkeypatch
    )
    await execute(c, h, eid, "country-workflow", payload, failed="Independently review")
    assert (await decision(c, h, eid, rule_source)).status_code == 403
    approved = await decision(c, reviewer[0], eid, rule_source)
    assert approved.status_code == 201, approved.text
    payload["source_ids"]["rules"] = approved.json()["id"]
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["expected_total"] == "3600"
    assert result["body"]["exception_count"] == 0 and not result["body"]["blocked"]
    assert any(
        dep["type"] == "evidence" and dep["id"] == legal["id"] for dep in result["dependencies"]
    )
    final_reviewer = await actor(h, "Firm Administrator", "payroll-final-reviewer")
    await grant(c, h, base, final_reviewer)
    premature = await decision(c, final_reviewer[0], eid, result)
    assert premature.status_code == 409, premature.text
    for role in ("bases", "reported"):
        current_source = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{payload['source_ids'][role]}",
            headers=h,
        )
        reviewed_source = await decision(c, reviewer[0], eid, current_source.json())
        assert reviewed_source.status_code == 201, reviewed_source.text
        payload["source_ids"][role] = reviewed_source.json()["id"]
    regenerated = await execute(c, h, eid, "country-workflow", payload)
    reviewed_result = await decision(c, final_reviewer[0], eid, regenerated)
    assert reviewed_result.status_code == 201, reviewed_result.text
    result = reviewed_result.json()
    assert result["body"]["review_status"] == "REVIEWED"
    export = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}/export?format=xlsx",
        headers=h,
    )
    assert export.status_code == 200 and export.content.startswith(b"PK")
    updated = await c.post(
        base + "/evidence-files/" + document["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-rule-evidence-v2.pdf",
                b"%PDF-1.4\nSYNTHETIC AMENDED RULE FIXTURE\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert updated.status_code == 201, updated.text
    for identifier in (approved.json()["id"], result["id"]):
        detail = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{identifier}", headers=h
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["freshness"] == "STALE"


async def test_rule_source_cannot_assert_a_hash_without_matching_retained_document(
    environment, monkeypatch
):
    c = environment
    h, eid, _, _, _, _, _, _, rules = await prepared(c, monkeypatch)
    rules[0]["source_sha256"] = "b" * 64
    await source(
        c,
        h,
        eid,
        rules,
        "Synthetic mismatched rule citation",
        "payroll-rules",
        {},
        failed="document hash differs",
    )


async def test_selected_retained_document_fills_missing_citation_fields_without_overriding_csv(
    environment, monkeypatch
):
    c = environment
    h, eid, _, _, _, legal, _, _, rules = await prepared(c, monkeypatch)
    bare = [
        {
            key: value
            for key, value in rule.items()
            if key not in {"source_evidence_version_id", "source_sha256"}
        }
        for rule in rules
    ]
    bound = await source(
        c,
        h,
        eid,
        bare,
        "Synthetic rules using selected retained document",
        "payroll-rules",
        {},
        rule_document_version_id=legal["id"],
    )
    assert bound["body"]["rule_document_binding"] == "SELECTED_RETAINED_DOCUMENT"
    assert all(
        row["source_evidence_version_id"] == legal["id"] and row["source_sha256"] == legal["sha256"]
        for row in bound["body"]["rows"]
    )
    rules[0]["source_sha256"] = "b" * 64
    await source(
        c,
        h,
        eid,
        rules,
        "Synthetic conflicting selected document",
        "payroll-rules",
        {},
        rule_document_version_id=legal["id"],
        failed="CSV rule document differs",
    )
