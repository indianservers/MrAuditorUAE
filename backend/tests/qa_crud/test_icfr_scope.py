"""Real HTTP/storage/job ICFR scope controls; scanner and dispatch are explicit doubles."""

import io
import os

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.icfr_scope import BINDING, CONTRACT, ROLES
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_icfr_scope import population

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


async def original(c, h, base, label, content):
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    response = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": (label + ".txt", content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return record, response.json()


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("reviewer_contributed", [False, True])
async def test_icfr_sources_review_originals_export_and_replacement(
    environment, monkeypatch, country, reviewer_contributed
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "icfr-duty-reviewer")
    await grant(c, h, base, reviewer)
    independent = reviewer
    if reviewer_contributed:
        independent = await actor(h, "Firm Administrator", "icfr-uninvolved-reviewer")
        await grant(c, h, base, independent)
    _, authority = await original(
        c,
        h,
        base,
        "SYNTHETIC-ICFR-authority",
        b"SYNTHETIC authority context; not an actual legal source",
    )
    assessment_record, assessment = await original(
        c,
        reviewer[0] if reviewer_contributed else h,
        base,
        "SYNTHETIC-ICFR-company",
        b"SYNTHETIC independently assessed issuer/component and duty facts",
    )
    p = population(country)
    for row in p["scopes"]:
        for role, document in (("authority", authority), ("assessment", assessment)):
            row[role + "_evidence_version_id"] = document["id"]
            row[role + "_sha256"] = document["sha256"]
    selected, initial = {}, {}
    for role, rows in p.items():
        imported = await source(
            c, h, eid, rows, "SYNTHETIC ICFR " + role, table_type=ROLES[role], totals={}
        )
        initial[role] = imported
        if role == "scopes":
            assert imported["body"]["icfr_scope_document_binding"] == BINDING
            assert len(imported["body"]["retained_icfr_documents"]) == 2
        assert (await decision(c, h, eid, imported)).status_code == 403
        if reviewer_contributed and role == "scopes":
            assert (await decision(c, reviewer[0], eid, imported)).status_code == 403
        approved = await decision(c, independent[0], eid, imported)
        assert approved.status_code == 201, approved.text
        selected[role] = approved.json()["id"]
    payload = {
        "workflow": "icfr-duty-coverage",
        "source_ids": selected,
        "period_start": "2026-06-01",
        "as_of": "2026-06-30",
        "subjects": ["SYN-COMPONENT"],
        "required_checks": ["404a:CTRL"],
        "title": "SYNTHETIC separately assessed ICFR duties",
        "rationale": "SYNTHETIC independently assessed authority, group facts and declared control evidence",
    }
    raw = await source(
        c, h, eid, p["scopes"], "SYNTHETIC unreviewed ICFR", table_type=ROLES["scopes"], totals={}
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "source_ids": {**selected, "scopes": raw["id"]}},
        failed="Independently review ICFR",
    )
    result = await execute(c, h, eid, "country-workflow", payload)
    body = result["body"]
    assert (
        body["icfr_scope_contract"] == CONTRACT and body["icfr_scope_document_binding"] == BINDING
    )
    assert len(body["rows"]) == 3 and body["exception_count"] == 0 and not body["blocked"]
    assert body["effectiveness_conclusion"] == body["professional_conclusion"] == "NOT_DETERMINED"
    assert body["statutory_calculation_qualified"] is False
    assert (await decision(c, h, eid, result)).status_code == 403
    if reviewer_contributed:
        assert (await decision(c, reviewer[0], eid, result)).status_code == 403
    approved = await decision(c, independent[0], eid, result)
    assert approved.status_code == 201, approved.text
    result = approved.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    page = await c.get(prefix + "?limit=1&offset=2", headers=h)
    assert page.status_code == 200 and page.json()["collection_totals"]["rows"] == 3
    assert page.json()["body"]["rows"][0]["duty"] == "404b"
    exported = await c.get(prefix + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    book = load_workbook(io.BytesIO(exported.content))
    values = list(book["Rows"].values)
    records = [dict(zip(values[0], row)) for row in values[1:]]
    assert len(records) == 3
    scopes = {r["duty"]: r for r in records if r["kind"] == "scope-decision"}
    assert scopes["404a"]["state"] == "SUPPORTED" and scopes["404b"]["state"] == "NOT-APPLICABLE"
    assert scopes["404a"]["assessment_evidence_version_id"] == assessment["id"]
    restricted = await actor(h, "Senior Auditor", "icfr-restricted-preparer")
    await grant(c, h, base, restricted)
    for path in (
        prefix,
        prefix + "/export?format=xlsx",
        f"/api/v1/intelligence/engagements/{eid}/events/{selected['scopes']}",
    ):
        assert (await c.get(path, headers=restricted[0])).status_code == 403
    tampered = [dict(row, authority_sha256="f" * 64) for row in p["scopes"]]
    await source(
        c,
        h,
        eid,
        tampered,
        "SYNTHETIC wrong authority hash",
        table_type=ROLES["scopes"],
        totals={},
        failed="document hash differs",
    )
    wrong_context = [
        dict(row, engagement_country="IN" if country == "AE" else "AE") for row in p["scopes"]
    ]
    await source(
        c,
        h,
        eid,
        wrong_context,
        "SYNTHETIC wrong review-country",
        table_type=ROLES["scopes"],
        totals={},
        failed="ICFR source review-country",
    )
    changed = await c.post(
        base + "/evidence-files/" + assessment_record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-replaced-ICFR.txt",
                b"SYNTHETIC changed company/group duty facts",
                "text/plain",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    stale = await c.get(prefix, headers=h)
    assert stale.json()["freshness"] == "STALE" and stale.json()["body"] == result["body"]
    source_state = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{selected['scopes']}", headers=h
    )
    assert source_state.json()["freshness"] == "STALE"
    await execute(
        c, h, eid, "country-workflow", payload, failed="select the reviewed current version"
    )


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_reference_catalogue_evidence_is_synthetic_in_both_api_views(environment, country):
    c = environment
    if country == "IN":
        h, eid, _ = await india_context(c)
    else:
        h, _, eid, _ = await setup(c)
    capabilities = await c.get("/api/v1/intelligence/capabilities", headers=h)
    config = await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    assert capabilities.status_code == config.status_code == 200
    global_body, country_body = capabilities.json(), config.json()
    evidence = global_body["reference_scenario_evidence"]
    assert evidence == country_body["reference_scenario_evidence"]
    assert country_body["country"] == country
    assert evidence["dataset_kind"] == "SYNTHETIC_ENGINE_FIXTURES"
    assert evidence["count_basis"] == "AUTHORED_REFERENCE_SCENARIOS"
    assert evidence["scenario_count"] == global_body["real_world_scenario_count"] == 164
    assert evidence["counts_by_country"] == {"AE": 106, "IN": 58}
    assert evidence["scenario_count"] == len(country_body["scenarios"])
    assert evidence["client_validation"] == "NOT_ESTABLISHED_BY_CATALOGUE"
    assert evidence["execution_status"] == "CONSULT_SOURCE_SPECIFIC_TEST_RECEIPTS"
    assert evidence["statutory_qualification"] is False
    assert global_body["statutory_qualification"] is False
    assert evidence["legacy_count_field"] == "real_world_scenario_count"
