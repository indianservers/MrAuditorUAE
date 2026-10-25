"""Real retained WPS instructions, review, separate bank evidence and source staleness."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import obligation
from tests.unit.native_source_examples import SIF_FILENAME
from tests.unit.test_wps_variable_pay import SIF_EVP, options

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def retain(c, h, eid, base):
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": (SIF_FILENAME, SIF_EVP, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    data = options(
        evidence_version_id=upload.json()["id"], employer_registration="1234567890123"
    ).model_dump(mode="json")
    return data, record, upload.json()


async def test_wps_evp_original_review_payroll_comparison_export_and_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "wps-evp-independent-reviewer")
    await grant(c, h, base, reviewer)
    data, record, original = await retain(c, h, eid, base)
    prepared = await execute(c, h, eid, "workflow-source", data)
    assert prepared["body"]["row_count"] == 2 and prepared["body"]["control_totals"] == {
        "AED": "1500.00"
    }
    assert prepared["body"]["rows"][0]["variable_pay_components"]["housing_allowance"] == "40.00"
    assert prepared["body"]["allowed_source_roles"] == ["channel", "return", "reported"]
    assert (await decision(c, h, eid, prepared)).status_code == 403
    approved = await decision(c, reviewer[0], eid, prepared)
    assert approved.status_code == 201, approved.text
    selected = {"channel": approved.json()["id"]}
    for role in ("payroll", "bank"):
        rows = [
            obligation(
                id=role + str(index),
                registration="1234567890123",
                subject=employee,
                period="2026-06",
                amount=amount,
                due_date="2026-06-30",
                payment_date="2026-06-30" if role == "bank" else None,
            )
            for index, employee, amount in (
                (1, "12345678901234", "1100"),
                (2, "12345678901235", "400"),
            )
        ]
        item = await source(
            c,
            h,
            eid,
            rows,
            "Synthetic independent " + role + " amounts",
            "obligations",
            {"AED": "1500"},
        )
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        selected[role] = reviewed.json()["id"]
    payload = {
        "workflow": "payroll-settlement",
        "source_ids": selected,
        "as_of": "2026-06-30",
        "currency": "AED",
        "title": "Synthetic EVP payroll settlement",
        "rationale": "Independent payroll accrual, original salary instructions and separate employee bank settlement observations",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    assert len(result["body"]["rows"]) == 2 and result["body"]["exception_count"] == 0
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **payload,
            "source_ids": {**selected, "bank": approved.json()["id"], "channel": selected["bank"]},
        },
        failed="return/channel role",
    )
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    exported = await c.get(prefix + f"/events/{prepared['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content[:2] == b"PK"
    downloaded = await c.get(
        base + f"/evidence-files/{record['id']}/{original['id']}/download", headers=h
    )
    assert downloaded.status_code == 200 and downloaded.content == SIF_EVP
    replaced = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (SIF_FILENAME, SIF_EVP.replace(b",40.00,10.00", b",41.00,9.00"), "text/csv")
        },
    )
    assert replaced.status_code == 201
    for identifier in (prepared["id"], result["id"]):
        stale = await c.get(prefix + "/events/" + identifier, headers=h)
        assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"


async def test_wps_evp_profile_cannot_run_for_india(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    data, _, _ = await retain(c, h, eid, base)
    await execute(
        c, h, eid, "workflow-source", data, failed="unavailable for this engagement country"
    )
