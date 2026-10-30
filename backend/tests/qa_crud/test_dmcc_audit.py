"""Original public rule bytes and synthetic entity facts; not client qualification."""

import os
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.audit_execution.models import EvidenceVersion
from app.modules.lineage.storage import ObjectStore
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_dmcc_audit import payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated test DB required"
)
ROOT = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/dmcc-audit-2026-10-30"
)


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_dmcc_original_rule_integrity_independent_review_filing_and_stale_guideline(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, audit_base = await setup(c)
    else:
        h, eid, audit_base = await india_context(c)
    entity_id = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()["entity_id"]
    reviewer = await actor(h, "Firm Administrator", "dmcc-rule-reviewer")
    await grant(c, h, audit_base, reviewer)
    originals = {}
    for role, name in (
        ("rule", "dmcc-company-regulations-amended.pdf"),
        ("guideline", "dmcc-afs-guidelines-2025-04-29.pdf"),
        ("facts", None),
        ("readiness", None),
    ):
        record = await create(
            c, h, audit_base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            audit_base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    name or f"SYNTHETIC-DMCC-{role}.txt",
                    (ROOT / name).read_bytes()
                    if name
                    else f"SYNTHETIC independently assessed DMCC {role}, not real client qualification".encode(),
                    "application/pdf" if name else "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        record = (await c.get(audit_base + "/records/" + record["id"], headers=h)).json()
        originals[role] = await approve(c, h, reviewer[0], audit_base, record)
    body = payload()
    body.update(
        owner_id=str(decode_token(h["Authorization"].split()[1])),
        entity_id=entity_id,
        rule_evidence_id=originals["rule"]["id"],
        dmcc_guideline_evidence_id=originals["guideline"]["id"],
        fact_evidence_ids=[originals["facts"]["id"]],
        readiness_evidence_ids=[originals["readiness"]["id"]],
        reviewer_id=reviewer[3],
        filing_stage="preparing",
    )
    if country == "IN":
        body["jurisdiction_scope"].update(entity_country="IN", relationship="foreign")
        body["dmcc_audit_scope"].update(
            procedure="portal_submission",
            legal_form="branch",
            dormant_whole_year="not_applicable",
            holding_company="not_applicable",
            branch_group_auditor="assessed_yes",
            auditor_status="group_auditor_exception",
        )
    base = f"/api/v1/grc/engagements/{eid}"

    async def post(value):
        return await c.post(
            base + "/records/obligation",
            headers=h,
            json={
                "reference": "SYN-DMCC-AUTHORITY",
                "title": "SYNTHETIC source-pinned DMCC procedure",
                "body": value,
            },
        )

    swapped = deepcopy(body)
    swapped["rule_evidence_id"], swapped["dmcc_guideline_evidence_id"] = (
        body["dmcc_guideline_evidence_id"],
        body["rule_evidence_id"],
    )
    wrong = await post(swapped)
    assert wrong.status_code == 409 and "exact retained original PDFs" in wrong.text
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        version = await db.scalar(
            select(EvidenceVersion)
            .where(EvidenceVersion.record_id == UUID(body["dmcc_guideline_evidence_id"]))
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        with ObjectStore().local(version.object_key, version.object_version) as private_fixture:
            original_bytes = private_fixture.read_bytes()
            try:
                private_fixture.write_bytes(b"SYNTHETIC corrupted private test copy")
                corrupt = await post(body)
                assert corrupt.status_code == 409 and "source bytes do not match" in corrupt.text
            finally:
                private_fixture.write_bytes(original_bytes)
    response = await post(body)
    assert response.status_code == 201, response.text
    obj = response.json()
    assert obj["body"]["deadline"] == "2026-06-30"
    checked = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert checked.status_code == 200, checked.text
    assessment = checked.json()["items"][0]["dmcc_audit_assessment"]
    assert assessment["procedure_required"] is True and assessment["issues"] == []
    incomplete = deepcopy(body)
    incomplete["dmcc_audit_scope"]["auditor_status"] = "unassessed"
    pending = await c.post(
        base + "/records/obligation",
        headers=h,
        json={
            "reference": "SYN-DMCC-UNRESOLVED",
            "title": "Synthetic unresolved auditor assessment",
            "body": incomplete,
        },
    )
    assert pending.status_code == 201, pending.text
    pending = await action(c, h, base, pending.json(), "submit")
    blocked_review = await c.post(
        base + f"/records/{pending['id']}/actions",
        headers=reviewer[0],
        json={
            "version": pending["version"],
            "action": "approve",
            "comments": "Synthetic unresolved auditor assessment cannot be approved",
        },
    )
    assert blocked_review.status_code == 409 and "Resolve DMCC" in blocked_review.text
    if country == "IN":
        assert assessment["approved_auditor_rule"] == "BRANCH_GROUP_AUDITOR_EXCEPTION_ASSESSED"
    staged = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "under_review"},
    )
    assert staged.status_code == 200, staged.text
    obj = await approve(c, h, reviewer[0], base, staged.json())
    advanced = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=reviewer[0],
        json={"version": obj["version"], "stage": "approved_for_submission"},
    )
    assert advanced.status_code == 200, advanced.text
    obj = advanced.json()
    retained = deepcopy(obj["body"])
    await action(c, reviewer[0], audit_base, originals["guideline"], "reopen")
    unchanged = (await c.get(audit_base + f"/records/{obj['id']}", headers=h)).json()
    assert unchanged["body"] == retained
    checked = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert checked.json()["items"][0]["freshness"] == "STALE"
    assert checked.json()["items"][0]["reassessment_required"] is True
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
    entity = (await c.get("/api/v1/entities/" + entity_id, headers=h)).json()
    assert entity["country"] == country
