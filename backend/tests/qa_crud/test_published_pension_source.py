"""Synthetic pension profiles through actual API/storage and job processing."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_regulatory_sources import propose
from tests.unit.test_pension_profiles import profile, vector
from tests.unit.test_pension_workflow import pension_fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


async def publish(
    c,
    h,
    reviewer,
    component="EMPLOYEE",
    *,
    sequence=0,
    start="2026-01-01",
    end="2026-12-31",
    pension_overrides=None,
    validation_fixtures=None,
):
    payload = profile(
        component,
        expected_sequence=sequence,
        effective_from=start,
        effective_to=end,
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-25",
    ).model_dump(mode="json")
    payload["pension_parameters"].update(pension_overrides or {})
    payload["citations"][0]["url"] = "https://gpssa.gov.ae/"
    document = await retain(c, h, payload)
    identifier = await propose(c, h, payload)
    expected = {"EMPLOYEE": "700.00", "EMPLOYER": "1500.00", "GOVERNMENT": "300.00"}[component]
    changes = dict(reported_amount=expected, expected_amount=expected)
    if component == "EMPLOYER":
        changes["government_amount"] = "300.00"
    if start == "2026-06-10":
        changes.update(expected_state="RULE_MISSING_OR_SPLIT_PERIOD", expected_amount=None)
    fixtures = validation_fixtures or [vector(component, **changes).model_dump(mode="json")]
    approved = await c.post(
        f"/api/v1/regulatory/rules/{identifier}/decisions",
        headers=reviewer,
        json=dict(
            action="approve",
            expected_sequence=sequence + 1,
            comments="Independent synthetic pension source and fixture assessment",
            validation_cases=fixtures,
        ),
    )
    assert approved.status_code == 201, approved.text
    published = await c.post(
        f"/api/v1/regulatory/rules/{identifier}/decisions",
        headers=h,
        json=dict(
            action="publish",
            expected_sequence=sequence + 2,
            comments="Publish independently reviewed synthetic pension fixtures",
        ),
    )
    assert published.status_code == 201, published.text
    return identifier, document


async def prepared(c, monkeypatch):
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "published-pension-reviewer")
    final = await actor(h, "Firm Administrator", "published-pension-final")
    for participant in (reviewer, final):
        await grant(c, h, base, participant)
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    context = await c.post(
        path,
        headers=h,
        json=dict(
            country="AE",
            framework="IFRS",
            entity_type="company",
            as_of="2026-12-31",
            base_version=0,
            reason="Synthetic pension profile reporting context",
        ),
    )
    assert context.status_code == 201, context.text
    reviewed = await c.post(
        path + "/decision",
        headers=reviewer[0],
        json=dict(
            request_id=context.json()["id"],
            approve=True,
            comments="Independent synthetic pension reporting context review",
        ),
    )
    assert reviewed.status_code == 201, reviewed.text
    identifiers, documents = [], []
    for component in ("EMPLOYEE", "EMPLOYER", "GOVERNMENT"):
        identifier, document = await publish(c, h, reviewer[0], component)
        identifiers.append(identifier)
        documents.append(document)
    bases, _, reported = pension_fixture()
    raw = await source(
        c,
        h,
        eid,
        bases,
        "Synthetic pension bases for published profiles",
        "pension-bases",
        {"AED": "30000.03"},
    )
    actual = await source(
        c,
        h,
        eid,
        reported,
        "Synthetic published pension observations",
        "pension-reported",
        {"AED": "2500"},
    )
    request = dict(
        basis_source_id=raw["id"],
        rule_version_ids=identifiers,
        expected_basis_rows=3,
        label="Synthetic published pension rules",
        assessment="Explicit authority, scheme, cohort, salary basis and full wage month reviewed",
    )
    return h, eid, base, reviewer, final, identifiers, documents, raw, actual, request


async def test_published_pension_source_binding_export_and_controlled_withdrawal(
    environment, monkeypatch
):
    c = environment
    h, eid, _, reviewer, final, identifiers, documents, raw, actual, request = await prepared(
        c, monkeypatch
    )
    endpoint = f"/api/v1/intelligence/engagements/{eid}/pension-rule-source"
    assert (await c.post(endpoint, headers=h, json=request)).status_code == 409
    basis = await decision(c, reviewer[0], eid, raw)
    observed = await decision(c, reviewer[0], eid, actual)
    assert basis.status_code == 201 and observed.status_code == 201
    request["basis_source_id"] = basis.json()["id"]
    assert (
        await c.post(endpoint, headers=h, json={**request, "rule_version_ids": identifiers[:1]})
    ).status_code == 409
    assert (
        await c.post(endpoint, headers=h, json={**request, "expected_basis_rows": 4})
    ).status_code == 422
    created = await c.post(endpoint, headers=h, json=request)
    assert created.status_code == 201, created.text
    derived = created.json()
    assert derived["body"]["parser_version"] == "published-pension-profiles/1"
    assert {row["source_document_id"] for row in derived["body"]["rows"]} == {
        item["id"] for item in documents
    }
    assert all(row["source_evidence_version_id"] is None for row in derived["body"]["rows"])
    assert (await decision(c, h, eid, derived)).status_code == 403
    approved = await decision(c, reviewer[0], eid, derived)
    assert approved.status_code == 201, approved.text
    payload = dict(
        workflow="uae-pension-review",
        currency="AED",
        as_of="2026-06-30",
        title="Synthetic published pension review",
        rationale="Independent reviewed pension basis and contribution observations",
        source_ids=dict(
            bases=basis.json()["id"], rules=approved.json()["id"], reported=observed.json()["id"]
        ),
    )
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["expected_total"] == "2500.00" and not result["body"]["blocked"]
    assert {row["published_rule_version_id"] for row in result["body"]["rows"]} == set(identifiers)
    assert (
        next(row for row in result["body"]["rows"] if row["component"] == "PENSION:EMPLOYER")[
            "government_support"
        ]
        == "300.00"
    )
    reviewed = await decision(c, final[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    saved = reviewed.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    # A separately reviewed clone must not replace the exact bound basis event.
    clone = await source(
        c,
        h,
        eid,
        pension_fixture()[0],
        "Synthetic alternate pension basis event",
        "pension-bases",
        {"AED": "30000.03"},
    )
    clone_review = await decision(c, reviewer[0], eid, clone)
    assert clone_review.status_code == 201
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "source_ids": {**payload["source_ids"], "bases": clone_review.json()["id"]}},
        failed="original reviewed wage bases",
    )
    withdrawn = await c.post(
        f"/api/v1/regulatory/rules/{identifiers[0]}/decisions",
        headers=h,
        json=dict(
            action="withdraw",
            expected_sequence=3,
            comments="Synthetic controlled withdrawal pending source qualification",
        ),
    )
    assert withdrawn.status_code == 201, withdrawn.text
    stale = await c.get(path, headers=h)
    assert stale.json()["freshness"] == "STALE" and stale.json()["sha256"] == saved["sha256"]
    assert (await c.post(endpoint, headers=h, json=request)).status_code == 409


async def test_interior_pension_amendment_invalidates_whole_month_selection(
    environment, monkeypatch
):
    c = environment
    h, eid, _, reviewer, _, identifiers, _, raw, _, request = await prepared(c, monkeypatch)
    basis = await decision(c, reviewer[0], eid, raw)
    assert basis.status_code == 201
    request["basis_source_id"] = basis.json()["id"]
    endpoint = f"/api/v1/intelligence/engagements/{eid}/pension-rule-source"
    response = await c.post(endpoint, headers=h, json=request)
    assert response.status_code == 201, response.text
    original = response.json()
    amendment, _ = await publish(
        c, h, reviewer[0], sequence=3, start="2026-06-10", end="2026-06-20"
    )
    detail = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{original['id']}", headers=h
    )
    assert detail.json()["freshness"] == "STALE" and detail.json()["sha256"] == original["sha256"]
    refusal = await c.post(
        endpoint, headers=h, json={**request, "rule_version_ids": [*identifiers, amendment]}
    )
    assert refusal.status_code == 409 and "entire wage month" in refusal.text
