"""Real HTTP/DB/storage/processor with explicit scanner and dispatch doubles."""

import os
from copy import deepcopy

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.country_workflow_cases import obligation
from tests.unit.native_source_examples import SIF, SIF_FILENAME

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable migrated database required"
)


@pytest.mark.parametrize(
    "content,error",
    [
        (SIF.replace(b"1000.00,", b'"1000.00\n",'), "single-line fields"),
        (SIF.replace(b"AED,SYNTHETIC\n", b'AED,"SYNTHETIC\n'), "Invalid WPS SIF"),
    ],
)
async def test_malformed_retained_wps_never_becomes_a_completed_source(
    environment, monkeypatch, content, error
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": (SIF_FILENAME, content, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": upload.json()["id"],
            "file_format": "uae-wps-sif",
            "table_type": "obligations",
            "label": "SYNTHETIC malformed retained instructions",
            "expected_rows": 2,
            "control_totals": {"AED": "1500"},
        },
        failed=error,
    )
    downloaded = await c.get(
        base + f"/evidence-files/{record['id']}/{upload.json()['id']}/download", headers=h
    )
    assert downloaded.status_code == 200 and downloaded.content == content


@pytest.mark.parametrize("profile", ["uae-wps-sif", "uae-wps-sif-evp"])
async def test_wps_upgrade_stales_base_preserves_strict_evp_and_keeps_financial_bodies(
    environment, monkeypatch, profile
):
    from app.modules.country_workflows import native_sources
    from tests.unit.test_wps_variable_pay import SIF_EVP, options

    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "wps-record-independent-reviewer")
    await grant(c, h, base, reviewer)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": (SIF_FILENAME, SIF if profile == "uae-wps-sif" else SIF_EVP, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    data = options(evidence_version_id=upload.json()["id"]).model_dump(mode="json")
    if profile == "uae-wps-sif":
        data.update(file_format=profile, wps_variable_pay_count=None, wps_variable_pay_totals={})
    selected = {}
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
            for index, employee, amount in [
                (1, "12345678901234", "1100"),
                (2, "12345678901235", "400"),
            ]
        ]
        retained = await source(
            c, h, eid, rows, "SYNTHETIC independent " + role, "obligations", {"AED": "1500"}
        )
        approved = await decision(c, reviewer[0], eid, retained)
        assert approved.status_code == 201, approved.text
        selected[role] = approved.json()["id"]
    payload = {
        "workflow": "payroll-settlement",
        "as_of": "2026-06-30",
        "currency": "AED",
        "title": "SYNTHETIC WPS record boundary comparison",
        "rationale": "Independent original payroll instructions and separate bank observations",
    }
    # Synthetic historical contract state, not a real production upgrade. The
    # strict reader remains active; only the version stamp is temporarily old.
    with monkeypatch.context() as past:
        past.setattr(native_sources, "WPS_RECORD_CONTRACT", "wps-single-line-records/0")
        retained = await execute(c, h, eid, "workflow-source", data)
        approved = await decision(c, reviewer[0], eid, retained)
        assert approved.status_code == 201, approved.text
        reviewed = approved.json()
        selected["channel"] = reviewed["id"]
        result = await execute(c, h, eid, "country-workflow", {**payload, "source_ids": selected})
        assert result["freshness"] == "CURRENT" and result["body"]["exception_count"] == 0
    original_source, original_result = deepcopy(reviewed["body"]), deepcopy(result["body"])
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    for event, original in [(reviewed, original_source), (result, original_result)]:
        stale = await c.get(prefix + "/events/" + event["id"], headers=h)
        assert stale.status_code == 200, stale.text
        assert stale.json()["freshness"] == ("STALE" if profile == "uae-wps-sif" else "CURRENT")
        assert stale.json()["body"] == original
        if profile == "uae-wps-sif":
            assert (await decision(c, reviewer[0], eid, event)).status_code == 409
    if profile == "uae-wps-sif-evp":
        return  # This existing profile already checked strict raw records.
    await execute(
        c, h, eid, "country-workflow", {**payload, "source_ids": selected}, failed="stale"
    )
    # The unchanged original upload can be explicitly re-prepared under the new
    # contract; old financial bodies and old review decisions remain untouched.
    reparsed = await execute(c, h, eid, "workflow-source", data)
    assert reparsed["freshness"] == "CURRENT"
    assert (
        reparsed["body"]["native_metadata"]["record_boundary_contract"]
        == native_sources.WPS_RECORD_CONTRACT
    )
    assert reparsed["body"]["rows"] == original_source["rows"]
