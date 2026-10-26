import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_esic_population import population
from tests.unit.test_esic_xls import parameters, workbook

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required")


async def retain(c, h, eid, base):
    original_record = await create(c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"})
    original = await c.post(base + "/evidence-files/" + original_record["id"], headers=h,
        files={"file": ("SYNTHETIC-esic-members.xls", workbook(), "application/vnd.ms-excel")})
    assert original.status_code == 201, original.text
    context_record = await create(c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"})
    context = await c.post(base + "/evidence-files/" + context_record["id"], headers=h,
        files={"file": ("SYNTHETIC-esic-context.txt", b"SYNTHETIC employer 00123456789012345, wage month 2026-06, monthly member workbook, independent original context", "text/plain")})
    assert context.status_code == 201, context.text
    payload = parameters().model_dump(mode="json")
    payload.update(evidence_version_id=original.json()["id"], esic_context_evidence_version_id=context.json()["id"])
    return payload, original.json(), context.json(), context_record


async def prepare(c, h, eid, base, reviewer):
    payload, original, context, _ = await retain(c, h, eid, base)
    native = await execute(c, h, eid, "workflow-source", payload)
    native_review = await decision(c, reviewer[0], eid, native)
    assert native_review.status_code == 201, native_review.text
    rows = population()
    rows[1].update(zero_wage_reason="6", zero_day_reason="6")
    payroll = await source(c, h, eid, rows, "SYNTHETIC independent payroll for native ESIC", "esic-members", {"INR": "10000"},
        esic_paid_days_control=25, esic_zero_wage_members_control=1)
    reviewed = await decision(c, reviewer[0], eid, payroll)
    assert reviewed.status_code == 201, reviewed.text
    return {"engagement": eid, "original": original["id"], "context": context["id"], "payload": payload,
        "source_ids": {"payroll": reviewed.json()["id"], "reported": native_review.json()["id"]}}


async def test_original_esic_xls_review_compare_export_and_context_staleness(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "esic-native-reviewer")
    await grant(c, h, base, reviewer)
    payload, original, context, context_record = await retain(c, h, eid, base)
    native = await execute(c, h, eid, "workflow-source", payload)
    assert native["body"]["native_metadata"]["context_sha256"] == context["sha256"]
    assert native["body"]["evidence_sha256"] == original["sha256"]
    assert native["body"]["rows"][1]["source_text_cells"]["F3"] == "02/06/2026"
    reviewed = await decision(c, reviewer[0], eid, native)
    assert reviewed.status_code == 201, reviewed.text
    native = reviewed.json()
    rows = population()
    rows[1].update(zero_wage_reason="6", zero_day_reason="6")
    expected = await source(c, h, eid, rows, "SYNTHETIC independent ESIC payroll", "esic-members", {"INR": "10000"}, esic_paid_days_control=25, esic_zero_wage_members_control=1)
    approved = await decision(c, reviewer[0], eid, expected)
    assert approved.status_code == 201, approved.text
    inputs = {"workflow": "india-esic-population", "source_ids": {"payroll": approved.json()["id"], "reported": native["id"]},
        "as_of": "2026-06-30", "currency": "INR", "title": "SYNTHETIC native ESIC population", "rationale": "Native retained XLS compared with independently assessed payroll and separate employer/month context"}
    result = await execute(c, h, eid, "country-workflow", inputs)
    assert result["body"]["exception_count"] == 0
    await execute(c, h, eid, "country-workflow", {**inputs, "source_ids": {"payroll": native["id"], "reported": approved.json()["id"]}}, failed="restricted to its assessed source role")
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    exported = await c.get(prefix + native["id"] + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    values = [value for sheet in load_workbook(io.BytesIO(exported.content)) for row in sheet.values for value in row]
    assert "0012345679" in values and "02/06/2026" in " ".join(str(value) for value in values)
    replacement = await c.post(base + "/evidence-files/" + context_record["id"], headers=h,
        files={"file": ("SYNTHETIC-esic-context-updated.txt", b"SYNTHETIC changed context awaiting a new source assessment", "text/plain")})
    assert replacement.status_code == 201, replacement.text
    for identifier in (native["id"], result["id"]):
        assert (await c.get(prefix + identifier, headers=h)).json()["freshness"] == "STALE"


async def test_esic_native_requires_clean_evidence(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch, scan="QUARANTINED")
    h, eid, base = await india_context(c)
    payload, _, _, _ = await retain(c, h, eid, base)
    await execute(c, h, eid, "workflow-source", payload, failed="Evidence is quarantined")


async def test_esic_native_is_country_scoped(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    payload, _, _, _ = await retain(c, h, eid, base)
    await execute(c, h, eid, "workflow-source", payload, failed="ESIC member sources require an India")
