import os
import uuid

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.regulatory_validation_fixtures import cases as validation_cases
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.unit.test_regulatory_evaluation import fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database"
)


async def test_rule_review_publication_versions_and_tenant_boundary(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, _ = await setup(c)
    other = await actor(h, "Firm Administrator", "regulatory-independent-reviewer")
    payload = fixture().model_dump(mode="json")
    created = await c.post("/api/v1/regulatory/rules", headers=h, json=payload)
    assert created.status_code == 201, created.text
    path = "/api/v1/regulatory/rules/" + created.json()["id"]
    decision = {
        "action": "approve",
        "expected_sequence": 1,
        "comments": "Synthetic independent source validation review",
        "validation_cases": validation_cases(payload),
    }
    assert (await c.post(path + "/decisions", headers=h, json=decision)).status_code == 403
    assert (await c.post(path + "/decisions", headers=other[0], json=decision)).status_code == 409
    payload.update(
        expected_sequence=1,
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-24",
    )
    payload["citations"][0].update(
        retrieval_status="RETRIEVED", document_sha256="a" * 64, retrieved_on="2026-10-24"
    )
    await retain(c, h, payload)
    amended = await c.post("/api/v1/regulatory/rules", headers=h, json=payload)
    assert amended.status_code == 201, amended.text
    amended_path = "/api/v1/regulatory/rules/" + amended.json()["id"]
    decision["expected_sequence"] = 2
    approved = await c.post(amended_path + "/decisions", headers=other[0], json=decision)
    assert approved.status_code == 201, approved.text
    decision.update(action="publish", expected_sequence=3)
    decision.pop("validation_cases")
    published = await c.post(amended_path + "/decisions", headers=h, json=decision)
    assert published.status_code == 201, published.text
    assert published.json()["state"] == "PUBLISHED"
    context_path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    context = await c.post(
        context_path,
        headers=h,
        json={
            "country": "AE",
            "framework": "IFRS",
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic explicit framework and entity applicability selection",
        },
    )
    assert context.status_code == 201, context.text
    context_review = await c.post(
        context_path + "/decision",
        headers=other[0],
        json={
            "request_id": context.json()["id"],
            "approve": True,
            "comments": "Synthetic independent reporting context assessment",
        },
    )
    assert context_review.status_code == 201, context_review.text
    assessment = await c.post(
        f"/api/v1/regulatory/engagements/{eid}/assessments",
        headers=h,
        json={
            "rule_ids": [amended.json()["id"]],
            "facts": {"entity_type": "company"},
            "rationale": "Synthetic applicability from an explicitly reviewed source rule",
        },
    )
    assert assessment.status_code == 201, assessment.text
    receipt = assessment.json()
    result_path = f"/api/v1/intelligence/engagements/{eid}/events/{receipt['id']}"
    assert (await c.get(result_path, headers=h)).json()["freshness"] == "CURRENT"
    for start, end, expected_state in [
        ("2027-01-01", "2027-12-31", "CURRENT"),
        ("2026-01-01", "2026-12-31", "STALE"),
    ]:
        head = (await c.get(amended_path, headers=h)).json()["current_sequence"]
        payload.update(effective_from=start, effective_to=end, expected_sequence=head)
        next_version = await c.post("/api/v1/regulatory/rules", headers=h, json=payload)
        assert next_version.status_code == 201, next_version.text
        next_path = "/api/v1/regulatory/rules/" + next_version.json()["id"]
        for operation, who in [("approve", other[0]), ("publish", h)]:
            head = (await c.get(next_path, headers=h)).json()["current_sequence"]
            decided = await c.post(
                next_path + "/decisions",
                headers=who,
                json={
                    "action": operation,
                    "expected_sequence": head,
                    "comments": "Synthetic effective-dated rule version change assessment",
                    **(
                        {"validation_cases": validation_cases(payload)}
                        if operation == "approve"
                        else {}
                    ),
                },
            )
            assert decided.status_code == 201, decided.text
        historical = (await c.get(result_path, headers=h)).json()
        assert (
            historical["freshness"] == expected_state and historical["sha256"] == receipt["sha256"]
        )
    impact = await c.get(amended_path + "/impact", headers=h)
    assert impact.status_code == 200 and impact.json()["items"][0]["freshness"] == "STALE"
    graph = await c.get(f"/api/v1/engagements/{eid}/audit/graph", headers=h)
    assert graph.status_code == 200, graph.text
    assert any(n["kind"] == "regulatory-rule" for n in graph.json()["nodes"])
    assert (await c.post(amended_path + "/decisions", headers=h, json=decision)).status_code == 409
    old = (await c.get(path, headers=h)).json()
    assert old["sha256"] == created.json()["sha256"] and old["version"] == 1
    assert (await c.get(path, headers={**h, "X-Tenant-ID": str(uuid.uuid4())})).status_code == 403
