"""Original authority bytes, synthetic company/calendar facts, real filing controls."""

import os
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.lineage.storage import ObjectStore
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.unit.test_adgm_accounts import first_long
from tests.unit.test_adgm_filing_duty import dormant
from tests.unit.test_adgm_filing_duty import payload as duty_payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated test DB required"
)
ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/adgm-accounts-2026-10-31"
)


@pytest.mark.parametrize(
    ("procedure", "withdraw"),
    [
        (None, "guidance"),
        (None, "calendar"),
        ("individual_accounts", "duty"),
        ("dormant_subsidiary_supporting_documents", "duty"),
    ],
)
async def test_adgm_original_sources_independent_review_and_unchanged_stale_filing(
    environment, monkeypatch, procedure, withdraw
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await setup(c)
    entity = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()["entity_id"]
    reviewer = await actor(h, "Firm Administrator", "adgm-independent-reviewer")
    await grant(c, h, audit, reviewer)
    originals = {}
    for role, name in [
        ("rule", "adgm-companies-consolidated-ver20260626.pdf"),
        ("guidance", "adgm-annual-accounts-v2-20261014.pdf"),
        ("facts", None),
        ("calendar", None),
        ("readiness", None),
        *([("duty", None)] if procedure else []),
    ]:
        record = await create(
            c, h, audit, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            audit + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    name or f"SYNTHETIC-ADGM-{role}.txt",
                    (ROOT / name).read_bytes()
                    if name
                    else f"SYNTHETIC independently assessed ADGM {role}; explicitly zero holidays in test calendar only, no client or national calendar qualification".encode(),
                    "application/pdf" if name else "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        record = (await c.get(audit + "/records/" + record["id"], headers=h)).json()
        originals[role] = await approve(c, h, reviewer[0], audit, record)
    body = duty_payload(first_long()) if procedure else first_long()
    if procedure == "dormant_subsidiary_supporting_documents":
        body = dormant(body, delivered=None)
        body["adgm_accounts_scope"]["filing_procedure"] = procedure
    body.update(
        owner_id=str(decode_token(h["Authorization"].split()[1])),
        entity_id=entity,
        rule_evidence_id=originals["rule"]["id"],
        adgm_guidance_evidence_id=originals["guidance"]["id"],
        calendar_evidence_id=originals["calendar"]["id"],
        fact_evidence_ids=[originals["facts"]["id"]],
        readiness_evidence_ids=[originals["readiness"]["id"]],
        reviewer_id=reviewer[3],
        filing_stage="preparing",
    )
    if procedure:
        body["fact_evidence_ids"].append(originals["duty"]["id"])
        for fact in body["adgm_accounts_scope"]["filing_duty_checks"]["facts"]:
            fact["evidence_ids"] = (
                [originals["duty"]["id"]] if fact["answer"] != "unassessed" else []
            )
    base = f"/api/v1/grc/engagements/{eid}"

    async def post(value, reference="SYN-ADGM-TIMETABLE"):
        return await c.post(
            base + "/records/obligation",
            headers=h,
            json={
                "reference": reference,
                "title": "SYNTHETIC source-pinned ADGM accounts timetable",
                "body": value,
            },
        )

    swapped = deepcopy(body)
    swapped["rule_evidence_id"], swapped["adgm_guidance_evidence_id"] = (
        body["adgm_guidance_evidence_id"],
        body["rule_evidence_id"],
    )
    wrong = await post(swapped)
    assert wrong.status_code == 409 and "exact retained original PDFs" in wrong.text
    if procedure:
        unbound = deepcopy(body)
        unbound["adgm_accounts_scope"]["filing_duty_checks"]["facts"][0]["evidence_ids"] = [
            originals["calendar"]["id"]
        ]
        rejected = await post(unbound)
        assert rejected.status_code == 422, rejected.text
        wrong_year = deepcopy(body)
        wrong_year["adgm_accounts_scope"]["filing_duty_checks"]["accounts_period_end"] = (
            "2027-12-30"
        )
        rejected = await post(wrong_year)
        assert rejected.status_code == 422, rejected.text
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        version = await db.scalar(
            select(EvidenceVersion)
            .where(EvidenceVersion.record_id == UUID(body["adgm_guidance_evidence_id"]))
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        with ObjectStore().local(version.object_key, version.object_version) as private_fixture:
            original = private_fixture.read_bytes()
            try:
                private_fixture.write_bytes(b"SYNTHETIC corrupted private test copy")
                corrupt = await post(body)
                assert corrupt.status_code == 409 and "source bytes do not match" in corrupt.text
            finally:
                private_fixture.write_bytes(original)
    response = await post(body)
    assert response.status_code == 201, response.text
    obj = response.json()
    assert obj["body"]["deadline"] == "2028-06-30"
    calendar = (
        await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    ).json()["items"][0]
    assert calendar["adgm_accounts_assessment"]["issues"] == []
    assert calendar["adgm_accounts_assessment"]["accounting_reference_end"] == "2027-12-31"
    assert calendar["deadline_comparison"]["selected_before_rolling"] == "2028-06-30"
    exemption = None
    if procedure:
        duty = calendar["adgm_accounts_assessment"]["filing_duty_assessment"]
        assert duty["procedure"] == procedure and duty["filing_required"] is True
        assert any(originals["duty"]["id"] in fact["evidence_ids"] for fact in duty["checks"])
        if procedure == "dormant_subsidiary_supporting_documents":
            assert duty["supporting_documents_required"] is True
            assert duty["dormant_individual_accounts_exemption"] is None
            assert len(duty["supporting_documents"]) == 5
            completed = deepcopy(body)
            completed.pop("deadline_rule")
            completed.pop("calendar_evidence_id")
            completed["jurisdiction_scope"]["applicability"] = "assessed_not_applicable"
            completed["adgm_accounts_scope"].update(
                filing_procedure="individual_accounts", filing_duty="assessed_exempt"
            )
            for fact in completed["adgm_accounts_scope"]["filing_duty_checks"]["facts"]:
                if (
                    fact["key"].endswith("_delivered")
                    or fact["key"] == "support_delivery_within_filing_period_assessed"
                ):
                    fact.update(
                        answer="assessed_yes",
                        evidence_ids=[originals["duty"]["id"]],
                        assessment="SYNTHETIC completed-delivery alternative over the exact financial year; not real delivery evidence",
                    )
            response = await post(completed, "SYN-ADGM-INDIVIDUAL-EXEMPT")
            assert response.status_code == 201, response.text
            exemption = await approve(c, h, reviewer[0], base, response.json())
            reviewed = (
                await c.get(base + f"/compliance-calendar?record_id={exemption['id']}", headers=h)
            ).json()["items"][0]
            assert (
                reviewed["deadline"] is None
                and reviewed["calendar_state"] == "ASSESSED_NOT_APPLICABLE"
            )
            checked = reviewed["adgm_accounts_assessment"]["filing_duty_assessment"]
            assert (
                checked["filing_required"] is False
                and checked["supporting_documents_required"] is True
            )
            impossible = await c.post(
                base + f"/obligations/{exemption['id']}/filing-stage",
                headers=reviewer[0],
                json={"version": exemption["version"], "stage": "approved_for_submission"},
            )
            assert impossible.status_code == 422, impossible.text

    pending_body = deepcopy(body)
    pending_body["adgm_accounts_scope"]["period_validity"] = "unresolved"
    if procedure:
        key = (
            "restricted_scope_company"
            if procedure == "individual_accounts"
            else "guarantee_authenticated"
        )
        checks = pending_body["adgm_accounts_scope"]["filing_duty_checks"]
        checks["facts"] = [fact for fact in checks["facts"] if fact["key"] != key]
        pending_body["adgm_accounts_scope"]["filing_duty"] = "unassessed"
        pending_body["jurisdiction_scope"]["applicability"] = "potential"
    pending = await post(pending_body, "SYN-ADGM-UNRESOLVED")
    assert pending.status_code == 201, pending.text
    pending = await action(c, h, base, pending.json(), "submit")
    rejected = await c.post(
        base + f"/records/{pending['id']}/actions",
        headers=reviewer[0],
        json={
            "version": pending["version"],
            "action": "approve",
            "comments": "SYNTHETIC unresolved period must not be approved",
        },
    )
    assert rejected.status_code == 409 and "Resolve ADGM" in rejected.text

    advanced = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "under_review"},
    )
    assert advanced.status_code == 200, advanced.text
    obj = await approve(c, h, reviewer[0], base, advanced.json())
    approved = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=reviewer[0],
        json={"version": obj["version"], "stage": "approved_for_submission"},
    )
    assert approved.status_code == 200, approved.text
    obj = approved.json()
    retained = deepcopy(obj["body"])
    await action(c, reviewer[0], audit, originals[withdraw], "reopen")
    unchanged = (await c.get(audit + f"/records/{obj['id']}", headers=h)).json()
    assert unchanged["body"] == retained
    stale = (await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)).json()[
        "items"
    ][0]
    assert stale["freshness"] == "STALE" and stale["reassessment_required"] is True
    if exemption:
        companion = (
            await c.get(base + f"/compliance-calendar?record_id={exemption['id']}", headers=h)
        ).json()["items"][0]
        assert companion["freshness"] == "STALE" and companion["reassessment_required"] is True
    blocked = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={
            "version": obj["version"],
            "stage": "submitted",
            "submission_evidence_id": originals["readiness"]["id"],
        },
    )
    assert blocked.status_code == 409, blocked.text
    # A damaged historical rule must project reassessment, not crash timezone/date handling.
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        damaged = await db.get(AuditRecord, UUID(pending["id"]))
        broken = deepcopy(damaged.body)
        broken["deadline_rule"].pop("later_of", None)
        broken["deadline_rule"]["timezone"] = "SYNTHETIC/invalid-zone"
        damaged.body = broken
    projection = await c.get(base + f"/compliance-calendar?record_id={pending['id']}", headers=h)
    assert projection.status_code == 200, projection.text
    item = projection.json()["items"][0]
    assert item["calendar_state"] == "AUTHORITY_REASSESSMENT_REQUIRED"
    assert item["reassessment_required"] is True
