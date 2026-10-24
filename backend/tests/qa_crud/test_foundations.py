"""Full synthetic foundation path, real DB/API/jobs/PDF extraction.

Scanner and broker dispatch are explicit doubles, not operational attestations.
"""

import io
import json
import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed, upload
from tests.phase4.test_workflows import action as paper_action
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute
from tests.unit.test_regulatory_evaluation import fixture

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database")


async def reviewed_context(c, h, reviewer, eid):
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    result = await c.post(
        path,
        headers=h,
        json={
            "country": "AE",
            "framework": "IFRS",
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic foundation reporting context",
        },
    )
    assert result.status_code == 201, result.text
    response = await c.post(
        path + "/decision",
        headers=reviewer,
        json={
            "request_id": result.json()["id"],
            "approve": True,
            "comments": "Synthetic independent context review",
        },
    )
    assert response.status_code == 201, response.text


async def reviewed_assessment(c, h, reviewer, eid):
    rule = fixture(
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed=date.today(),
    ).model_dump(mode="json")
    rule["citations"][0].update(
        retrieval_status="RETRIEVED",
        document_sha256="a" * 64,
        retrieved_on=date.today().isoformat(),
    )
    # Attestation is synthetic: this is never a verified real UAE legal rule.
    response = await c.post("/api/v1/regulatory/rules", headers=h, json=rule)
    assert response.status_code == 201, response.text
    rid = response.json()["id"]
    for action, who, sequence in [("approve", reviewer, 1), ("publish", h, 2)]:
        response = await c.post(
            f"/api/v1/regulatory/rules/{rid}/decisions",
            headers=who,
            json={
                "action": action,
                "expected_sequence": sequence,
                "comments": "Synthetic technical fixture attestation only",
            },
        )
        assert response.status_code == 201, response.text
    response = await c.post(
        f"/api/v1/regulatory/engagements/{eid}/assessments",
        headers=h,
        json={
            "rule_ids": [rid],
            "facts": {"entity_type": "company"},
            "rationale": "Synthetic foundation applicability fixture",
        },
    )
    assert response.status_code == 201, response.text
    reviewed = await decision(c, reviewer, eid, response.json())
    assert reviewed.status_code == 201, reviewed.text
    return reviewed.json()


async def reviewed_extraction(c, h, reviewer, eid, base):
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    output = io.BytesIO()
    pdf = Canvas(output)
    pdf.drawString(30, 800, "Invoice Number: SYNTHETIC-1")
    pdf.drawString(30, 780, "Invoice Date: 2026-01-31")
    pdf.drawString(30, 760, "Gross Amount: 100.20")
    pdf.drawString(30, 740, "Currency: AED")
    pdf.save()
    response = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("SYNTHETIC.pdf", output.getvalue(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    repeated = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("SYNTHETIC.pdf", output.getvalue(), "application/pdf")},
    )
    assert repeated.status_code == 201 and repeated.json()["id"] == response.json()["id"], (
        repeated.text
    )
    assert repeated.json()["duplicate_detected"]
    extraction = await execute(c, h, eid, "ocr", {"evidence_version_id": response.json()["id"]})
    assert extraction["body"]["fields"]["gross_amount"] == "100.20"
    reviewed = await decision(c, reviewer, eid, extraction)
    assert reviewed.status_code == 201, reviewed.text
    return reviewed.json()


async def test_complete_foundation_path_and_blocked_release(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "foundation-reviewer")
    await grant(c, h, base, reviewer)
    await reviewed_context(c, h, reviewer[0], eid)
    _, snapshot = await committed(c, h, options)
    blocked = await execute(
        c,
        h,
        eid,
        "foundation-validation",
        {
            "snapshot_id": snapshot,
            "rationale": "Synthetic missing evidence and rule blocked workflow",
        },
    )
    assert blocked["body"]["execution_status"] == "succeeded"
    assert blocked["body"]["completeness"] == "partial"
    submitted = await decision(c, h, eid, blocked, action="submit")
    assert submitted.status_code == 201, submitted.text
    assert (await decision(c, reviewer[0], eid, submitted.json())).status_code == 409
    mapped = await c.post(
        "/api/v1/accounting/mappings",
        headers=h,
        json={
            **{key: options[key] for key in ["client_id", "entity_id", "period_id"]},
            "name": "SYNTHETIC alternative foundation mapping",
            "approved": True,
            "mapping": {
                "accounts": {
                    "100": {"classification": "Assets"},
                    "300": {"classification": "Equity"},
                    "500": {"classification": "Expenses"},
                }
            },
        },
    )
    assert mapped.status_code == 201, mapped.text
    extraction = await reviewed_extraction(c, h, reviewer[0], eid, base)
    assessment = await reviewed_assessment(c, h, reviewer[0], eid)
    lines = (
        await c.get("/api/v1/accounting/ledger", headers=h, params={"snapshot_id": snapshot})
    ).json()["items"]
    line = next(line for line in lines if str(line["debit"]).startswith("100.2"))
    payload = {
        "snapshot_id": snapshot,
        "extraction_ids": [extraction["id"]],
        "document_links": [{"extraction_id": extraction["id"], "journal_line_id": line["id"]}],
        "assessment_ids": [assessment["id"]],
        "rationale": "Synthetic full foundation control assessment",
    }
    validated = await execute(c, h, eid, "foundation-validation", payload)
    assert validated["body"]["completeness"] == "complete", validated["body"]
    assert (await decision(c, reviewer[0], eid, validated)).status_code == 409  # submit required
    prepared = (await decision(c, h, eid, validated, action="submit")).json()
    assert (await decision(c, h, eid, prepared)).status_code == 403
    approved = await decision(c, reviewer[0], eid, prepared)
    assert approved.status_code == 201, approved.text
    original = approved.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    paper = await c.post(
        prefix + f"/events/{original['id']}/working-paper",
        headers=h,
        json={
            "reference": "FOUNDATION-SYNTHETIC-1",
            "title": "Synthetic foundation validation",
            "objective": "Document foundation controls and reviewer conclusions",
        },
    )
    assert paper.status_code == 201, paper.text
    manager = await actor(h, "Audit Manager", "foundation-paper-manager")
    partner = await actor(h, "Audit Partner", "foundation-paper-partner")
    await grant(c, h, base, manager)
    await grant(c, h, base, partner)
    paper_prepared = await paper_action(c, h, base, paper.json(), "submit")
    paper_stage1 = await paper_action(c, manager[0], base, paper_prepared, "approve")
    paper_approved = await paper_action(c, partner[0], base, paper_stage1, "approve")
    assert paper_approved["status"] == "APPROVED"
    corrected = await c.post(
        prefix + f"/events/{extraction['id']}/corrections",
        headers=h,
        json={
            "expected_version": extraction["version"],
            "fields": {"gross_amount": "105.20"},
            "reason": "Synthetic material source correction for invalidation test",
        },
    )
    assert corrected.status_code == 201, corrected.text
    old = (await c.get(prefix + f"/events/{original['id']}", headers=h)).json()
    assert old["freshness"] == "STALE" and old["sha256"] == original["sha256"]
    assert (
        await c.post(
            base + f"/records/{paper_approved['id']}/actions",
            headers=partner[0],
            json={
                "version": paper_approved["version"],
                "action": "lock",
                "comments": "Synthetic stale release must be blocked",
            },
        )
    ).status_code == 409
    assert (await decision(c, reviewer[0], eid, original)).status_code == 409
    reviewed = await decision(c, reviewer[0], eid, corrected.json())
    assert reviewed.status_code == 201, reviewed.text
    payload["extraction_ids"] = [reviewed.json()["id"]]
    payload["document_links"][0]["extraction_id"] = reviewed.json()["id"]
    recalculated = await execute(c, h, eid, "foundation-validation", payload)
    prepared = await decision(c, h, eid, recalculated, action="submit")
    reapproved = await decision(c, reviewer[0], eid, prepared.json())
    assert reapproved.status_code == 201, reapproved.text
    replacement = await c.post(
        prefix + f"/events/{reapproved.json()['id']}/working-paper",
        headers=h,
        json={
            "reference": "FOUNDATION-SYNTHETIC-2",
            "title": "Synthetic revised foundation validation",
            "objective": "Document recalculated foundation controls and reviewed sources",
        },
    )
    assert replacement.status_code == 201, replacement.text
    new_prepared = await paper_action(c, h, base, replacement.json(), "submit")
    new_reviewed = await paper_action(c, manager[0], base, new_prepared, "approve")
    new_approved = await paper_action(c, partner[0], base, new_reviewed, "approve")
    assert new_approved["status"] == "APPROVED"
    assert (await c.get(prefix + f"/events/{reapproved.json()['id']}", headers=h)).json()[
        "freshness"
    ] == "CURRENT"
    # An account mapping change also invalidates approved results, without editing them.
    changed = await c.post(
        "/api/v1/accounting/mappings",
        headers=h,
        json={
            **{key: options[key] for key in ["client_id", "entity_id", "period_id"]},
            "name": "SYNTHETIC foundation mapping",
            "approved": True,
            "mapping": {
                "accounts": {
                    "100": {
                        "classification": "Assets",
                        "statement_group": "Revised cash presentation",
                    }
                }
            },
        },
    )
    assert changed.status_code == 201, changed.text
    assert (await c.get(prefix + f"/events/{reapproved.json()['id']}", headers=h)).json()[
        "freshness"
    ] == "STALE"
    assert (
        await c.get(
            prefix + f"/events/{original['id']}", headers={**h, "X-Tenant-ID": str(uuid.uuid4())}
        )
    ).status_code == 403
    other = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": options["entity_id"],
            "period_id": options["period_id"],
            "name": "SYNTHETIC other engagement",
            "engagement_type": "External Audit",
        },
    )
    assert other.status_code == 201, other.text
    assert (
        await c.get(
            f"/api/v1/intelligence/engagements/{other.json()['id']}/events/{original['id']}",
            headers=h,
        )
    ).status_code == 404
    report = {
        "fixture": "SYNTHETIC technical workflow; no real legal verification",
        "scanner": "test double CLEAN",
        "broker_dispatch": "test double; real job processor invoked",
        "blocked_approval": 409,
        "source_correction_stales_approved_result": True,
        "approved_version_preserved": True,
        "recalculated_and_reapproved": True,
        "mapping_change_stales_result": True,
        "foundation_event": original["id"],
        "reapproved_event": reapproved.json()["id"],
        "working_paper": paper.json()["id"],
        "working_paper_approved": paper_approved["status"],
        "replacement_working_paper_approved": new_approved["status"],
        "stale_working_paper_release_blocked": True,
    }
    path = (
        Path(__file__).resolve().parents[3]
        / "docs/engine-strengthening/phase1/workflow-evidence.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


async def test_period_lock_blocks_activation_reopening_is_versioned(environment):
    c = environment
    h, options, eid, base = await setup(c)
    identifier = await upload(c, h, options)
    assert (
        await c.post(f"/api/v1/accounting/imports/{identifier}/validate", headers=h)
    ).status_code == 200
    path = f"/api/v1/intelligence/engagements/{eid}"
    action = {
        "expected_version": 1,
        "action": "lock",
        "reason": "Synthetic reporting period closed by reviewer",
    }
    associate = await actor(h, "Audit Trainee", "foundation-associate")
    await grant(c, h, base, associate)
    assert (
        await c.post(path + "/period-actions", headers=associate[0], json=action)
    ).status_code == 403
    locked = await c.post(path + "/period-actions", headers=h, json=action)
    assert locked.status_code == 200, locked.text
    mapping = await c.post(
        "/api/v1/accounting/mappings",
        headers=h,
        json={
            **{key: options[key] for key in ["client_id", "entity_id", "period_id"]},
            "name": "Synthetic locked mapping",
            "approved": True,
            "mapping": {},
        },
    )
    assert mapping.status_code == 409, mapping.text
    assert (
        await c.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=h)
    ).status_code == 409
    assert (
        await c.post(path + "/period-actions", headers=h, json={**action, "action": "reopen"})
    ).status_code == 409
    reopened = await c.post(
        path + "/period-actions",
        headers=h,
        json={**action, "expected_version": 2, "action": "reopen"},
    )
    assert reopened.status_code == 200, reopened.text
    assert (
        await c.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=h)
    ).status_code == 200


async def test_failed_foundation_job_recovers_without_duplicate_result(environment, monkeypatch):
    from app.modules.intelligence import service
    from app.modules.intelligence.jobs import process

    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, _ = await setup(c)
    _, snapshot = await committed(c, h, options)
    compute = service.compute
    attempts = 0

    async def transient(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("Synthetic dependency unavailable")
        return await compute(*args, **kwargs)

    monkeypatch.setattr(service, "compute", transient)
    payload = {"snapshot_id": snapshot, "rationale": "Synthetic retry recovery control test"}
    job = await execute(
        c,
        h,
        eid,
        "foundation-validation",
        payload,
        key="synthetic-recovery",
        failed="Synthetic dependency unavailable",
    )
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    retry = await c.post(
        prefix + f"/jobs/{job['id']}/actions",
        headers=h,
        json={"version": job["version"], "action": "retry"},
    )
    assert retry.status_code == 200, retry.text
    await process(job["id"], h["X-Tenant-ID"])
    await process(job["id"], h["X-Tenant-ID"])
    recovered = (await c.get(prefix + f"/jobs/{job['id']}", headers=h)).json()
    assert recovered["status"] == "completed" and recovered["attempts"] == 2
    duplicate = await c.post(
        prefix + "/jobs",
        headers={**h, "Idempotency-Key": "synthetic-recovery"},
        json={"operation": "foundation-validation", "payload": payload},
    )
    assert duplicate.status_code == 202 and duplicate.json()["result_id"] == recovered["result_id"]


async def test_partial_extract_imbalance_is_blocked_without_asserting_ledger_error(environment):
    c = environment
    h, options, _, _ = await setup(c)
    data = b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID\n500,Expense,PARTIAL,2026-01-31,100.20,0,SYNTHETIC-PARTIAL\n"
    identifier = await upload(
        c,
        h,
        {
            **options,
            "source_complete": False,
            "expected_rows": 1,
            "expected_debit": "100.20",
            "expected_credit": "0",
        },
        data,
    )
    response = await c.post(f"/api/v1/accounting/imports/{identifier}/validate", headers=h)
    assert response.status_code == 200 and response.json()["status"] == "blocked"
    rows = (await c.get(f"/api/v1/accounting/imports/{identifier}/validations", headers=h)).json()
    assert "items" in rows, rows
    balance = next(row for row in rows["items"] if row["rule"] == "journal_balance")
    assert "Incomplete extract" in balance["message"]
    assert balance["evidence"]["accounting_error_conclusion"] is False
