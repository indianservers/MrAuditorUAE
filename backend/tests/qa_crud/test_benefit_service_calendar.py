"""Real service-calendar API/storage/DB/processor; scanner and dispatch are doubled."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.benefit_settlement_workflow import verify_settlement
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_benefit_service_calendar import TABLE, record, zero
from tests.unit.test_practice_audit_workflows import (
    benefit_employee,
    benefit_rule,
    part_time_employee,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated disposable database required"
)


@pytest.mark.parametrize("excluded,withdrawal", [(0, "review"), (5, "original-file")])
async def test_reviewed_calendar_calculation_export_settlement_and_recursive_staleness(
    environment, monkeypatch, excluded, withdrawal
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "calendar-source-reviewer")
    final_reviewer = await actor(h, "Firm Administrator", "calendar-result-reviewer")
    for participant in (reviewer, final_reviewer):
        await grant(c, h, base, participant)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    legal = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + legal["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-calendar-rule.txt",
                b"SYNTHETIC supplied parameters only",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    rules = [benefit_rule(), benefit_rule(id="PART", work_model="part-time")]
    for row in rules:
        row.pop("source_sha256")
        row.pop("source_evidence_version_id")
    employees = [
        benefit_employee(excluded_service_days=excluded, amount="0" if excluded else "2100"),
        part_time_employee(id="E2"),
    ]
    total = "1050" if excluded else "3150"
    calendar_records = [
        record(employees[0]) if excluded else zero(employees[0]),
        zero(employees[1]),
    ]
    retained = {
        "employees": await source(
            c,
            h,
            eid,
            employees,
            "Synthetic service-day employees",
            "benefit-employees",
            {"AED": total},
        ),
        "rules": await source(
            c,
            h,
            eid,
            rules,
            "Synthetic service-day parameters",
            "benefit-rules",
            {},
            rule_document_version_id=uploaded.json()["id"],
        ),
        "service_calendar": await source(
            c,
            h,
            eid,
            calendar_records,
            "Synthetic dated HR absences",
            TABLE,
            {},
            benefit_service_controls={"employee_count": 2, "excluded_days": excluded},
        ),
    }
    params = {
        "workflow": "uae-benefit-review",
        "source_ids": {role: obj["id"] for role, obj in retained.items()},
        "as_of": "2026-06-30",
        "currency": "AED",
        "title": "Synthetic dated benefit service review",
        "rationale": "Independent original calendar and declared employee-day comparison",
    }
    await execute(c, h, eid, "country-workflow", params, failed="Independently review employees")
    for role, obj in retained.items():
        approved = await decision(c, reviewer[0], eid, obj)
        assert approved.status_code == 201, approved.text
        retained[role] = approved.json()
    params["source_ids"] = {role: obj["id"] for role, obj in retained.items()}
    result = await execute(c, h, eid, "country-workflow", params)
    assert not result["body"]["blocked"]
    assert result["body"]["rows"][0]["eligible_service_days"] == 365 - excluded
    assert result["body"]["rows"][0]["expected_benefit"] == ("0.00" if excluded else "2100.00")
    assert result["body"]["rows"][1]["calendar_excluded_service_days"] == 0
    assert (await decision(c, h, eid, result)).status_code == 403
    reviewed = await decision(c, final_reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    response = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert response.status_code == 200
    rows = list(load_workbook(io.BytesIO(response.content))["Benefit service exclusions"].values)
    assert len(rows) == 3 and rows[1][rows[0].index("days")] == str(excluded)
    descendants = []
    if not excluded:
        _, bridge, settlement, _ = await verify_settlement(c, h, eid, base, result, final_reviewer)
        descendants = [bridge, settlement]
    before = {obj["id"]: deepcopy(obj["body"]) for obj in [result, *descendants]}
    calendar = retained["service_calendar"]
    if withdrawal == "review":
        rejected = await decision(c, reviewer[0], eid, calendar, "reject")
        assert rejected.status_code == 201, rejected.text
    else:
        original = next(dep for dep in calendar["dependencies"] if dep["type"] == "evidence")
        replaced = await c.post(
            base + "/evidence-files/" + original["record_id"],
            headers=h,
            files={
                "file": (
                    "SYNTHETIC-calendar-replacement.txt",
                    b"SYNTHETIC changed original HR calendar",
                    "text/plain",
                )
            },
        )
        assert replaced.status_code == 201, replaced.text
    for identifier, body in before.items():
        stale = (await c.get(prefix + f"/events/{identifier}", headers=h)).json()
        assert stale["freshness"] == "STALE" and stale["body"] == body
    assert (await decision(c, final_reviewer[0], eid, result)).status_code == 409
