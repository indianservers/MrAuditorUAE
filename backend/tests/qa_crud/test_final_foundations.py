"""Isolated synthetic filing, runtime and connector health; no external requests."""

import json
import os
import uuid
from pathlib import Path

import pytest

from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.accounting.models import Connection, SyncRun
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, grant, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated migrated database"
)


async def test_unknown_obligation_filing_controls_and_runtime_health(environment):
    c = environment
    h, opts, eid, audit_base = await setup(c)
    reviewer = await actor(h, "Compliance Officer", "final-compliance-reviewer")
    await grant(c, h, audit_base, reviewer)
    base = f"/api/v1/grc/engagements/{eid}"
    uid = str(decode_token(h["Authorization"].removeprefix("Bearer ")))
    body = {
        "owner_id": uid,
        "entity_id": opts["entity_id"],
        "module": "policy",
        "source_url": "https://synthetic.invalid/internal-policy",
        "jurisdiction": "SYNTHETIC",
        "effective_from": "2026-01-01",
        "required_evidence": "Independent source and computation review",
        "compliance_assessment": "not_assessed",
        "reviewer_id": reviewer[3],
    }
    r = await c.post(
        base + "/records/obligation",
        headers=h,
        json={
            "reference": "SYN-UNRESOLVED",
            "title": "Synthetic unresolved deadline",
            "body": body,
        },
    )
    assert r.status_code == 201, r.text
    obj = r.json()
    calendar = (await c.get(base + "/compliance-calendar", headers=h)).json()
    assert calendar["items"][0]["calendar_state"] == "UNRESOLVED"
    jumped = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "submitted"},
    )
    assert jumped.status_code == 422, jumped.text
    step = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "preparing"},
    )
    assert step.status_code == 200, step.text
    assert (
        await c.post(
            base + f"/obligations/{obj['id']}/filing-stage",
            headers=h,
            json={"version": obj["version"], "stage": "under_review"},
        )
    ).status_code == 409
    obj = step.json()
    step = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "under_review"},
    )
    assert step.status_code == 200, step.text
    obj = await action(c, h, base, step.json(), "submit")
    obj = await action(c, reviewer[0], base, obj, "approve")
    reminder = await c.post(base + "/compliance-reminders", headers=h)
    assert reminder.status_code == 200 and reminder.json()["recorded"] == 0
    runtime = await c.get(f"/api/v1/ai/engagements/{eid}/runtime-status", headers=h)
    assert runtime.status_code == 200, runtime.text
    assert runtime.json()["language"]["local_ml_requires_gateway"] is False
    serialized = json.dumps(runtime.json())
    assert "api_key" not in serialized and "base_url" not in serialized
    stranger = await actor(h, "Client Viewer", "final-runtime-denied")
    assert (
        await c.get(f"/api/v1/ai/engagements/{eid}/runtime-status", headers=stranger[0])
    ).status_code == 403
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        connection = Connection(
            tenant_id=uuid.UUID(h["X-Tenant-ID"]),
            created_by=uuid.UUID(uid),
            client_id=uuid.UUID(opts["client_id"]),
            entity_id=uuid.UUID(opts["entity_id"]),
            period_id=uuid.UUID(opts["period_id"]),
            provider="file",
            name="SYNTHETIC controlled import",
            encrypted_credentials=None,
        )
        db.add(connection)
        await db.flush()
        run = SyncRun(
            tenant_id=connection.tenant_id,
            created_by=connection.created_by,
            client_id=connection.client_id,
            entity_id=connection.entity_id,
            period_id=connection.period_id,
            connection_id=connection.id,
            status="failed",
            completeness="insufficient_evidence",
            error_category="partial_page_failure",
            manifest={
                "counts": {"gl": 12},
                "checkpoint": {"downloaded": 2},
                "execution_mode": "simulated",
            },
        )
        db.add(run)
        identifier = str(connection.id)
    health = await c.get(f"/api/v1/connectors/operations/{identifier}", headers=h)
    assert health.status_code == 200, health.text
    assert health.json()["operational_health"]["complete"] is False
    assert health.json()["operational_health"]["connection_type"] == "import_export_adapter"
    folder = Path(os.environ.get("OPERATIONS_ARTIFACT_DIR", "../docs/engine-strengthening/phase5"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "compliance-runtime-connector.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "calendar": calendar,
                "reviewed_obligation": obj,
                "runtime": runtime.json(),
                "connector": health.json(),
                "external_requests_performed": False,
            },
            indent=2,
        )
    )


async def test_evidenced_filing_lifecycle_reminders_and_stale_receipt(environment, monkeypatch):
    from datetime import date

    from tests.phase4.test_workflows import approve, create
    from tests.qa_crud.test_country_workflows import double_boundaries

    double_boundaries(
        monkeypatch
    )  # Controlled scanner/broker doubles, not live-provider qualification.
    c = environment
    h, opts, eid, audit_base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "final-filing-independent")
    await grant(c, h, audit_base, reviewer)
    evidences = []
    for name in ["readiness", "submission", "acknowledgment"]:
        paper = await create(
            c, h, audit_base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        upload = await c.post(
            audit_base + "/evidence-files/" + paper["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-{name}.txt",
                    f"SYNTHETIC {name} fixture; no authority contact".encode(),
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 201, upload.text
        paper = (await c.get(audit_base + "/records/" + paper["id"], headers=h)).json()
        paper = await approve(c, h, reviewer[0], audit_base, paper)
        evidences.append(paper)
    base = f"/api/v1/grc/engagements/{eid}"
    body = {
        "owner_id": str(decode_token(h["Authorization"].split()[1])),
        "entity_id": opts["entity_id"],
        "module": "policy",
        "source_url": "https://synthetic.invalid/policy",
        "jurisdiction": "SYNTHETIC",
        "effective_from": "2026-01-01",
        "deadline": str(date.today()),
        "deadline_kind": "firm_internal",
        "required_evidence": "Synthetic readiness and authorization documents",
        "compliance_assessment": "pending",
        "reviewer_id": reviewer[3],
        "readiness_evidence_ids": [evidences[0]["id"]],
        "notifications_enabled": True,
        "reminder_days": [0],
    }
    response = await c.post(
        base + "/records/obligation",
        headers=h,
        json={"reference": "SYN-FILING", "title": "Synthetic filing lifecycle", "body": body},
    )
    assert response.status_code == 201, response.text
    obj = response.json()

    async def step(headers, stage, **evidence):
        response = await c.post(
            base + f"/obligations/{obj['id']}/filing-stage",
            headers=headers,
            json={"version": obj["version"], "stage": stage, **evidence},
        )
        assert response.status_code == 200, response.text
        return response.json()

    obj = await step(h, "preparing")
    obj = await step(h, "under_review")
    obj = await approve(c, h, reviewer[0], base, obj)
    one = await c.post(base + "/compliance-reminders", headers=h)
    two = await c.post(base + "/compliance-reminders", headers=h)
    assert one.json()["recorded"] == 1 and two.json()["recorded"] == 0
    obj = await step(reviewer[0], "approved_for_submission")
    assert obj["status"] == "APPROVED"
    same = await step(h, "approved_for_submission")
    assert same["version"] == obj["version"]
    obj = await step(h, "submitted", submission_evidence_id=evidences[1]["id"])
    obj = await approve(c, h, reviewer[0], base, obj)
    obj = await step(h, "acknowledged", acknowledgment_evidence_id=evidences[2]["id"])
    obj = await approve(c, h, reviewer[0], base, obj)
    calendar = (await c.get(base + "/compliance-calendar", headers=h)).json()
    assert calendar["items"][0]["calendar_state"] == "ACKNOWLEDGED"
    obj = await action(c, reviewer[0], base, obj, "lock")
    locked = await c.post(
        base + f"/obligations/{obj['id']}/filing-stage",
        headers=h,
        json={"version": obj["version"], "stage": "preparing"},
    )
    assert locked.status_code == 409
    await action(c, reviewer[0], audit_base, evidences[0], "reopen")
    calendar = (await c.get(base + "/compliance-calendar", headers=h)).json()
    assert calendar["items"][0]["reassessment_required"] is True
    folder = Path(os.environ["OPERATIONS_ARTIFACT_DIR"])
    (folder / "filing-lifecycle.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "acknowledged_record": obj,
                "source_correction": calendar,
                "duplicate_reminders_suppressed": True,
                "external_submission_performed": False,
            },
            indent=2,
        )
    )


async def test_expired_worker_claim_is_not_blindly_reexecuted(environment, monkeypatch):
    """Controlled crash condition: persisted expired claim, not a killed live worker."""
    from datetime import UTC, datetime, timedelta

    from app.modules.intelligence.jobs import recover_due
    from app.modules.intelligence.models import IntelligenceJob
    from app.workers.intelligence import run

    c = environment
    h, _, eid, _ = await setup(c)
    uid = decode_token(h["Authorization"].split()[1])
    calls = []
    monkeypatch.setattr(run, "apply_async", lambda **kwargs: calls.append(kwargs))
    ids = []
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        for status in ["running", "pending"]:
            job = IntelligenceJob(
                tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                created_by=uid,
                engagement_id=uuid.UUID(eid),
                idempotency_key="SYN-EXPIRED-" + status,
                operation="foundation-validation",
                payload={},
                payload_sha256="a" * 64,
                status=status,
                updated_at=datetime.now(UTC) - timedelta(minutes=6),
            )
            db.add(job)
            await db.flush()
            ids.append(job.id)
    assert await recover_due() == 1
    assert calls[0]["args"][0] == str(ids[1])
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        abandoned = await db.get(IntelligenceJob, ids[0])
        assert abandoned.status == "failed" and abandoned.error_category == "abandoned_claim"
        assert abandoned.result_id is None
    folder = Path(os.environ["OPERATIONS_ARTIFACT_DIR"])
    (folder / "worker-recovery.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "failure_injection": "persisted expired worker claim",
                "abandoned_claim": "failed_requires_manual_retry",
                "pending_outbox_dispatched": len(calls),
                "abandoned_job_automatically_reexecuted": False,
            },
            indent=2,
        )
    )
