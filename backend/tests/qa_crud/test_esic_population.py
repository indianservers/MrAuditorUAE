import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_esic_population import parameters, population

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required")


async def prepare(c, h, eid, reviewer, period="2026-06"):
    selected, original = {}, {}
    for role in ("payroll", "reported"):
        rows = population()
        for row in rows:
            row["period"] = period
            if period != "2026-06" and row["last_working_day"]:
                row["last_working_day"] = period + "-02"
            row["id"] = role + "-" + row["id"]
            row["evidence_reference"] = "SYNTHETIC " + role + " original"
        if role == "reported":
            rows[0]["paid_days"] = 24
        controls = parameters(rows)
        imported = await source(c, h, eid, rows, "SYNTHETIC ESIC " + role, table_type="esic-members",
            totals={"INR": "10000"}, esic_paid_days_control=controls.esic_paid_days_control,
            esic_zero_wage_members_control=controls.esic_zero_wage_members_control)
        original[role] = imported
        response = await decision(c, reviewer[0], eid, imported)
        assert response.status_code == 201, response.text
        selected[role] = response.json()["id"]
    return selected, original


async def test_reviewed_esic_population_days_export_country_and_staleness(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "esic-reviewer")
    await grant(c, h, base, reviewer)
    selected, originals = await prepare(c, h, eid, reviewer)
    payload = {"workflow": "india-esic-population", "source_ids": selected, "currency": "INR",
        "as_of": "2026-06-30", "title": "SYNTHETIC ESIC wage and member review",
        "rationale": "Independent fictional membership, wage, reason and leaving-date evidence", "tolerance": "999999"}
    # Select an actual current unreviewed version, rather than a superseded original.
    unreviewed = await source(c, h, eid, population(), "SYNTHETIC unreviewed ESIC", table_type="esic-members",
        totals={"INR": "10000"}, esic_paid_days_control=25, esic_zero_wage_members_control=1)
    await execute(c, h, eid, "country-workflow", {**payload, "source_ids": {**selected, "payroll": unreviewed["id"]}}, failed="Independently review both ESIC")
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["exception_count"] == 1 and not result["body"]["blocked"]
    assert result["body"]["rows"][0]["paid_day_difference"] == -1
    assert result["body"]["rows"][0]["exceptions"] == ["PAID_DAY_VARIANCE"]
    assert (await decision(c, h, eid, result)).status_code == 403
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409
    documented = await decision(c, h, eid, result, "accept", item_id="esic-member:1")
    assert documented.status_code == 201, documented.text
    approved = await decision(c, reviewer[0], eid, documented.json())
    assert approved.status_code == 201, approved.text
    result = approved.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    page = await c.get(prefix + "?offset=1&limit=1", headers=h)
    assert page.status_code == 200 and page.json()["body"]["rows"][0]["subject"] == "0012345679"
    exported = await c.get(prefix + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    values = [value for sheet in load_workbook(io.BytesIO(exported.content)) for row in sheet.values for value in row]
    assert "0012345678" in values and "0012345679" in values and "SYN-ASSESSED-LEAVER" in values
    withdrawn = await decision(c, reviewer[0], eid, (await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{selected['reported']}", headers=h)).json(), "reject")
    assert withdrawn.status_code == 201, withdrawn.text
    assert (await c.get(prefix, headers=h)).json()["freshness"] == "STALE"


async def test_esic_source_cannot_be_enabled_in_uae(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, _ = await setup(c)
    await source(c, h, eid, population(), "SYNTHETIC wrong country ESIC", table_type="esic-members",
        totals={"INR": "10000"}, esic_paid_days_control=25, esic_zero_wage_members_control=1, failed="ESIC member sources require an India")


async def test_esic_wage_month_cannot_escape_engagement_reporting_scope(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "esic-period-reviewer")
    await grant(c, h, base, reviewer)
    selected, _ = await prepare(c, h, eid, reviewer, period="2025-06")
    await execute(c, h, eid, "country-workflow", {"workflow": "india-esic-population", "source_ids": selected,
        "currency": "INR", "as_of": "2026-06-30", "title": "SYNTHETIC out of period ESIC",
        "rationale": "Retained fictional wage month predates this engagement"}, failed="fully within the engagement")
