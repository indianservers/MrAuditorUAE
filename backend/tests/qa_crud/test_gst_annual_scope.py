import io
import json
import os
from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.turnover import ROLES
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_gst_annual_scope import annual_rows, scope

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


async def test_annual_candidates_review_export_and_withdrawal_preserve_original(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, original_eid, _ = await india_context(c)
    original = await c.get(f"/api/v1/engagements/{original_eid}", headers=h)
    assert original.status_code == 200, original.text
    entity_id = original.json()["entity_id"]
    period = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={"entity_id": entity_id, "start_date": "2025-04-01", "end_date": "2026-03-31"},
    )
    assert period.status_code == 201, period.text
    engagement = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": entity_id,
            "period_id": period.json()["id"],
            "name": "SYNTHETIC annual GST assessment",
            "engagement_type": "External Audit",
        },
    )
    assert engagement.status_code == 201, engagement.text
    eid = engagement.json()["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    reviewer = await actor(h, "Firm Administrator", "annual-gst-reviewer")
    await grant(c, h, base, reviewer)
    source_ids = {}
    first_source = None
    pending_id = None
    for role, records in annual_rows("30000000").items():
        totals = (
            {}
            if role == "scope"
            else {"INR": str(sum((Decimal(r["amount"]) for r in records), Decimal(0)))}
        )
        prepared = await source(
            c, h, eid, records, "SYNTHETIC annual GST " + role, ROLES[role], totals
        )
        if role == "scope":
            pending_id = prepared["id"]
        checked = await decision(c, reviewer[0], eid, prepared)
        assert checked.status_code == 201, checked.text
        source_ids[role] = checked.json()["id"]
        if role == "scope":
            first_source = checked.json()
    pending_source = await source(
        c,
        h,
        eid,
        annual_rows("30000000")["scope"],
        "SYNTHETIC unreviewed annual scope",
        ROLES["scope"],
        {},
    )
    pending_id = pending_source["id"]
    facts = scope()
    facts["aggregate_turnover"] = "30000000"
    data = dict(
        workflow="tax-turnover-bridge",
        source_ids=source_ids,
        currency="INR",
        as_of="2026-03-31",
        title="SYNTHETIC annual GST candidates",
        rationale="Synthetic independently reviewed source populations and PAN facts",
        gst_annual_scope=facts,
    )
    wrong = deepcopy(data)
    wrong["source_ids"]["scope"] = pending_id
    await execute(
        c, h, eid, "country-workflow", wrong, failed="Independently review every turnover"
    )
    wrong_year = deepcopy(data)
    wrong_year["gst_annual_scope"].update(
        financial_year_start="2024-04-01", financial_year_end="2025-03-31"
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        wrong_year,
        failed="match the India engagement financial year",
    )
    result = await execute(c, h, eid, "country-workflow", data)
    assert result["body"]["annual_gst_assessment"]["gstr9"] == "CANDIDATE_REQUIRED"
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    endpoint = f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}"
    export = await c.get(endpoint + "/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    book = load_workbook(io.BytesIO(export.content), read_only=True)
    metadata = dict(book["Source and review"].values)
    assert (
        json.loads(metadata["annual_gst_assessment"])["scope"]["aggregate_turnover"] == "30000000"
    )
    book.close()
    saved = (await c.get(endpoint, headers=h)).json()
    historical = deepcopy(saved["body"])
    assert saved["freshness"] == "CURRENT"
    pending = deepcopy(data)
    pending["gst_annual_scope"]["aggregate_turnover"] = None
    blocked = await execute(c, h, eid, "country-workflow", pending)
    assert (
        blocked["body"]["blocked"]
        and blocked["body"]["annual_gst_assessment"]["gstr9"] == "PENDING_REVIEW"
    )
    rejected = await decision(c, reviewer[0], eid, blocked)
    assert rejected.status_code == 409, rejected.text
    withdrawn = await decision(c, reviewer[0], eid, first_source, action="reject")
    assert withdrawn.status_code == 201, withdrawn.text
    stale = (await c.get(endpoint, headers=h)).json()
    assert stale["freshness"] == "STALE" and stale["body"] == historical
