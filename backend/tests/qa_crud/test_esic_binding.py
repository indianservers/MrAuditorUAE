import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_esic_population import prepare as prepare_population
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_esic_binding import contribution_populations

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


async def prepare(c, h, eid, base, reviewer, population_sources=None):
    selected = population_sources
    if selected is None:
        selected, _ = await prepare_population(c, h, eid, reviewer)
    parent = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "india-esic-population",
            "source_ids": selected,
            "as_of": "2026-06-30",
            "currency": "INR",
            "title": "SYNTHETIC reviewed ESIC member evidence",
            "rationale": "Independent fictional member and wage evidence before contribution assessment",
        },
    )
    documented = await decision(c, h, eid, parent, "accept", item_id="esic-member:1")
    assert documented.status_code == 201, documented.text
    approved = await decision(c, reviewer[0], eid, documented.json())
    assert approved.status_code == 201, approved.text
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    legal = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-esic-rules.txt",
                b"SYNTHETIC rule fixtures: 1% employee and 2% employer, no legal validity",
                "text/plain",
            )
        },
    )
    assert legal.status_code == 201, legal.text
    rows = contribution_populations()
    for rule in rows["rules"]:
        rule.update(
            source_evidence_version_id=legal.json()["id"], source_sha256=legal.json()["sha256"]
        )
    sources = {}
    for role, table, total in (
        ("bases", "payroll-bases", {"INR": "20000"}),
        ("rules", "payroll-rules", {}),
        ("reported", "obligations", {"INR": "300"}),
    ):
        item = await source(c, h, eid, rows[role], "SYNTHETIC linked ESI " + role, table, total)
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()["id"]
    payload = {
        "workflow": "india-payroll-rules",
        "source_ids": sources,
        "as_of": "2026-06-30",
        "currency": "INR",
        "title": "SYNTHETIC population-bound ESI contribution review",
        "rationale": "Fictional source-bound rules and explicitly assessed ESI bases linked to reviewed member evidence",
        "esic_population_review_id": approved.json()["id"],
        "esic_components": ["ESI:EMPLOYEE", "ESI:EMPLOYER"],
        "esic_basis_scope_assessment": "Independently assessed component coverage, retained zero-wage member, eligibility and wage-to-basis differences; fictional rates only",
    }
    return {
        "population_sources": selected,
        "population_review": approved.json()["id"],
        "sources": sources,
        "payload": payload,
    }


async def test_reviewed_esic_population_binds_contributions_and_remittance_freshness(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "esic-link-source-reviewer")
    await grant(c, h, base, reviewer)
    fixture = await prepare(c, h, eid, base, reviewer)
    payload = fixture["payload"]
    result = await execute(c, h, eid, "country-workflow", payload)
    assert (
        result["body"]["exception_count"] == 0
        and result["body"]["esic_population_binding"]["status"] == "BOUND"
    )
    assert len(result["body"]["rows"]) == 4 and result["body"]["expected_total"] == "300.00"
    assert any(dep.get("id") == fixture["population_review"] for dep in result["dependencies"])
    final = await actor(h, "Firm Administrator", "esic-link-final-reviewer")
    await grant(c, h, base, final)
    reviewed = await decision(c, final[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    due_record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    due = await c.post(
        base + "/evidence-files/" + due_record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-esic-due.txt",
                b"SYNTHETIC independently assessed deadline: 2026-07-15",
                "text/plain",
            )
        },
    )
    assert due.status_code == 201, due.text
    request = {
        "result_id": result["id"],
        "due_date_evidence_version_id": due.json()["id"],
        "label": "SYNTHETIC linked ESI remittance",
        "assessment": "Fictional independent remittance scope and due-date assessment",
        "groups": [
            {
                "registration": "00123456789012345",
                "period": "2026-06",
                "component": component,
                "expected_rows": 2,
                "amount": amount,
                "due_date": "2026-07-15",
                "due_date_reference": "SYNTHETIC retained due-date reference",
            }
            for component, amount in (("ESI:EMPLOYEE", "100"), ("ESI:EMPLOYER", "200"))
        ],
    }
    derived = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/contribution-obligation-source",
        headers=h,
        json=request,
    )
    assert derived.status_code == 201, derived.text
    assert derived.json()["body"]["control_totals"] == {"INR": "300.00"}
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    exported = await c.get(prefix + result["id"] + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    values = [
        value
        for sheet in load_workbook(io.BytesIO(exported.content))
        for row in sheet.values
        for value in row
    ]
    assert "0012345679" in values and "10000" in values
    original = await c.get(prefix + fixture["population_sources"]["reported"], headers=h)
    withdrawn = await decision(c, reviewer[0], eid, original.json(), "reject")
    assert withdrawn.status_code == 201, withdrawn.text
    for identifier in (result["id"], derived.json()["id"]):
        assert (await c.get(prefix + identifier, headers=h)).json()["freshness"] == "STALE"
    await execute(c, h, eid, "country-workflow", payload, failed="source is stale")


async def test_unreviewed_contribution_source_cannot_claim_esic_binding(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "esic-unreviewed-source-reviewer")
    await grant(c, h, base, reviewer)
    fixture = await prepare(c, h, eid, base, reviewer)
    unreviewed = await source(
        c,
        h,
        eid,
        contribution_populations()["bases"],
        "SYNTHETIC unreviewed ESI bases",
        "payroll-bases",
        {"INR": "20000"},
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**fixture["payload"], "source_ids": {**fixture["sources"], "bases": unreviewed["id"]}},
        failed="Independently review every contribution source",
    )
    unreviewed_parent = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "india-esic-population",
            "source_ids": fixture["population_sources"],
            "as_of": "2026-06-30",
            "currency": "INR",
            "title": "SYNTHETIC unreviewed parent population",
            "rationale": "Fictional independently sourced member comparison awaiting review",
        },
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**fixture["payload"], "esic_population_review_id": unreviewed_parent["id"]},
        failed="current independently reviewed complete ESIC",
    )
