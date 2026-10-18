"""Guarded real monitoring -> ML feedback -> test -> remediation -> retest -> closure."""

# ruff: noqa: E402
import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from sqlalchemy import select

from app.core.security import access_token
from app.db.models.platform import BackgroundJob
from app.db.session import Session, engine, tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.grc.models import GRCRun, MonitorAlert
from app.modules.ml.models import MLEvent
from app.modules.ml.service import read_object
from app.workers.grc import dispatch


async def main():
    demo = json.loads((ROOT / "docs/phase-10/demo-verification.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text(encoding="utf-8"))
    admin = manifest["users"][1]
    reviewer = demo["users"][1]
    eid = demo["engagement_id"]
    base = f"/api/v1/grc/engagements/{eid}"
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
    from app.main import app

    logging.getLogger("auditos").setLevel(logging.WARNING)
    output = {"synthetic": True, "engagement_id": eid, "steps": []}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=120
    ) as c:

        async def call(path, body=None, who=admin, method="POST", expected=None):
            started = time.perf_counter()
            r = await c.request(
                method,
                path,
                headers={
                    "Authorization": "Bearer " + access_token(uuid.UUID(who["id"])),
                    "X-Tenant-ID": str(DEMO_TENANT),
                },
                **({"json": body} if body is not None else {}),
            )
            output["steps"].append(
                {
                    "path": path,
                    "role": who["role"],
                    "status": r.status_code,
                    "seconds": round(time.perf_counter() - started, 4),
                }
            )
            if expected is not None:
                assert r.status_code == expected, r.text
            elif r.status_code >= 400:
                raise RuntimeError(path + " " + r.text)
            return r.json()

        async def paper(kind, key, body):
            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                old = await db.scalar(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == DEMO_TENANT,
                        AuditRecord.engagement_id == uuid.UUID(eid),
                        AuditRecord.reference == "P10-PROOF-" + key,
                    )
                )
                obj = (
                    {"id": str(old.id), "version": old.version, "status": old.status}
                    if old
                    else None
                )
            if not obj:
                obj = await call(
                    base + "/records/" + kind,
                    {
                        "reference": "P10-PROOF-" + key,
                        "title": "SYNTHETIC " + key,
                        "body": {
                            "narrative": "SYNTHETIC software fixture. Evidence demonstrates workflow lineage only, not real control effectiveness.",
                            **body,
                        },
                    },
                )
            if obj["status"] in {"IN_PROGRESS", "REVISED", "REVIEW_NOTES"}:
                obj = await call(
                    base + "/records/" + obj["id"] + "/actions",
                    {
                        "version": obj["version"],
                        "action": "submit",
                        "comments": "Synthetic software test submitted for independent review",
                    },
                )
            if obj["status"] == "REVIEW_REQUIRED":
                obj = await call(
                    base + "/records/" + obj["id"] + "/actions",
                    {
                        "version": obj["version"],
                        "action": "approve",
                        "comments": "Independent software fixture review; no real assurance provided",
                    },
                    reviewer,
                )
            return obj

        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            source = await db.get(AuditRecord, uuid.UUID(demo["prepared"]["MONITOR-00"]))
            config = {
                k: v
                for k, v in source.body.items()
                if k not in {"review_stage", "review_cycle", "review_approvers"}
            }
        config.update(
            rule_key="P10-PROOF-WEEKEND-ML",
            rule_code="weekend_postings",
            ml_limit=100,
            trigger_on_import=True,
        )
        rule = await paper("monitor-rule", "RULE", config)
        queued = await call(base + f"/monitoring/{rule['id']}/execute", {})

        async def completed(identifier):
            for _ in range(60):
                async with Session() as db, db.begin():
                    await tenant_context(db, str(DEMO_TENANT))
                    job = await db.get(BackgroundJob, uuid.UUID(identifier))
                    if job.status in {"completed", "failed", "cancelled"}:
                        assert job.status == "completed", job.error_category
                        return {"id": str(job.id), "status": job.status, "result": job.result}
                await asyncio.sleep(1)
            raise RuntimeError("Real Celery job did not complete within 60 seconds")

        output["worker_job"] = await completed(queued["id"])
        replay = await call(base + f"/monitoring/{rule['id']}/execute", {})
        output["dedup_replay_job"] = await completed(replay["id"])
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            alert = await db.scalar(
                select(MonitorAlert)
                .where(
                    MonitorAlert.tenant_id == DEMO_TENANT,
                    MonitorAlert.engagement_id == uuid.UUID(eid),
                    MonitorAlert.rule_key == "P10-PROOF-WEEKEND-ML",
                    MonitorAlert.signals["ml"].is_not(None),
                    MonitorAlert.signals["ml"]["inference_id"].astext.is_not(None),
                    MonitorAlert.signals["deterministic"]["rule"].astext == "J01",
                )
                .order_by(MonitorAlert.id)
                .limit(1)
            )
            if not alert:
                raise RuntimeError("Actual rule and model overlap required for demonstration")
            alert_id, line_id, prediction = str(alert.id), str(alert.source_id), alert.signals["ml"]
            evidence = await db.scalar(
                select(AuditRecord)
                .where(
                    AuditRecord.tenant_id == DEMO_TENANT,
                    AuditRecord.engagement_id == uuid.UUID(eid),
                    AuditRecord.kind == "ifrs-note",
                    AuditRecord.status.in_(["APPROVED", "LOCKED"]),
                )
                .limit(1)
            )
            evidence_id = str(evidence.id)
        output["alert_id"] = alert_id
        source = await call(base + f"/alerts/{alert_id}/source", method="GET")
        assert source["record"]["id"] == line_id
        await paper(
            "alert-decision",
            "DECISION",
            {
                "owner_id": demo["users"][0]["id"],
                "alert_id": alert_id,
                "decision": "investigate",
                "rationale": "Rule and ML are independent signals; original synthetic journal inspected, no fraud conclusion",
                "evidence_ids": [evidence_id],
            },
        )
        feedback = await call(
            "/api/v1/ml/predictions/" + prediction["inference_id"] + "/feedback",
            {
                "transaction_id": line_id,
                "label": "valid_exception",
                "evidence_id": evidence_id,
                "rationale": "Synthetic professional fixture label only; no claim of real-world misstatement",
            },
            reviewer,
        )
        output["ml_feedback_id"] = feedback["id"]
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            inference = await db.get(MLEvent, uuid.UUID(prediction["inference_id"]))
            dataset_id = inference.body["dataset_id"]
        curated = await call(
            "/api/v1/ml/datasets/" + dataset_id + "/curation",
            {
                "feedback_ids": [feedback["id"]],
                "rationale": "Independent synthetic feedback curation; original test holdout split must be preserved",
            },
        )
        curated_data = json.loads(read_object(curated["body"]["object"]))
        assert set(curated_data["split"]) == {"test"}
        output["curated_dataset_id"] = curated["id"]
        output["training_rows_after_curation"] = curated_data["split"].count("train")

        sample = await call(
            base + "/samples",
            {
                "snapshot_id": demo["snapshot_id"],
                "method": "judgmental",
                "size": 1,
                "seed": 20261018,
                "selected_line_ids": [line_id],
                "selection_rationale": "Explicit synthetic weekend candidate selected for workflow verification",
            },
        )
        test_body = {
            "owner_id": demo["users"][0]["id"],
            "control_id": demo["prepared"]["CONTROL-000"],
            "test_type": "operating",
            "procedure": "Inspect selected synthetic authorization support",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "sample_run_id": sample["id"],
            "population_snapshot_id": demo["snapshot_id"],
            "results": [
                {
                    "line_id": line_id,
                    "outcome": "exception",
                    "evidence_ids": [evidence_id],
                    "comments": "Synthetic authorization exception",
                }
            ],
            "evidence_ids": [evidence_id],
            "conclusion": "ineffective",
            "rationale": "Synthetic evidence fixture tests linkage only",
        }
        test = await paper("test", "OPERATING-TEST", test_body)
        finding = await paper(
            "deficiency",
            "DEFICIENCY",
            {
                "owner_id": demo["users"][0]["id"],
                "control_id": demo["prepared"]["CONTROL-000"],
                "risk_id": demo["prepared"]["RISK-000"],
                "test_id": test["id"],
                "alert_id": alert_id,
                "description": "Synthetic missed authorization detected through source investigation",
                "root_cause_method": "five_whys",
                "root_cause": "Synthetic missing independent review assignment",
                "consequence": "Potential unreviewed transaction",
                "severity": "moderate",
                "severity_methodology": "Synthetic ordinal likelihood-impact rubric",
                "affected_from": "2026-01-01",
                "affected_to": "2026-10-18",
                "evidence_ids": [evidence_id],
            },
        )
        remediation = await paper(
            "remediation",
            "MANAGEMENT-ACTION",
            {
                "owner_id": demo["users"][4]["id"],
                "deficiency_id": finding["id"],
                "corrective_action": "Assign independent reviewer and evidence recurring checks",
                "management_response": "Synthetic management records implementation for software verification",
                "target_date": "2026-10-31",
                "management_status": "reported_complete",
                "evidence_ids": [evidence_id],
            },
        )
        retest = await paper(
            "test",
            "RETEST",
            {
                **test_body,
                "test_type": "retest",
                "results": [
                    {
                        "line_id": line_id,
                        "outcome": "passed",
                        "evidence_ids": [evidence_id],
                        "comments": "Synthetic retest fixture only",
                    }
                ],
                "retests_id": test["id"],
                "conclusion": "effective",
                "rationale": "Synthetic fixture retest; no operational assurance claim",
            },
        )
        closure = await paper(
            "closure",
            "CLOSURE",
            {
                "remediation_id": remediation["id"],
                "retest_id": retest["id"],
                "conclusion": "Independently reviewed synthetic closure linked to approved retest",
                "evidence_ids": [evidence_id],
            },
        )
        output["chain"] = {
            "rule": rule["id"],
            "alert": alert_id,
            "sample": sample["id"],
            "test": test["id"],
            "deficiency": finding["id"],
            "remediation": remediation["id"],
            "retest": retest["id"],
            "closure": closure["id"],
        }
        await call(
            base + f"/records/{closure['id']}/actions",
            {
                "version": closure["version"],
                "action": "reopen",
                "comments": "Unauthorized synthetic owner reopening attempt",
            },
            demo["users"][4],
            expected=403,
        )
        await call(base + "/records/risk", method="GET", who=demo["users"][7], expected=403)
        package = await call(
            base + "/board/packages/" + demo["board_publication"],
            method="GET",
            who=demo["users"][7],
        )
        assert "owner_id" not in json.dumps(package)
        for format in ["pdf", "docx"]:
            r = await c.get(
                base + f"/board/packages/{demo['board_publication']}/export/{format}",
                headers={
                    "Authorization": "Bearer " + access_token(uuid.UUID(demo["users"][7]["id"])),
                    "X-Tenant-ID": str(DEMO_TENANT),
                },
            )
            assert r.status_code == 200 and len(r.content) > 1000
            output[format + "_bytes"] = len(r.content)
        schedule = await call(
            base + "/schedules",
            {
                "rule_id": rule["id"],
                "frequency": "daily",
                "next_due": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
            },
        )
        output["scheduler_dispatch"] = await dispatch()
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            job = await db.scalar(
                select(BackgroundJob)
                .where(
                    BackgroundJob.tenant_id == DEMO_TENANT,
                    BackgroundJob.payload["schedule_id"].astext == schedule["id"],
                )
                .order_by(BackgroundJob.created_at.desc())
                .limit(1)
            )
            scheduled_id = str(job.id)
        output["scheduled_job"] = await completed(scheduled_id)
        await call(
            base + "/schedules/" + schedule["id"], {"version": 2, "active": False}, method="PATCH"
        )
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            output["monitoring_receipts"] = {}
            for key in ["worker_job", "dedup_replay_job", "scheduled_job"]:
                receipt = await db.scalar(
                    select(GRCRun).where(
                        GRCRun.tenant_id == DEMO_TENANT,
                        GRCRun.kind == "monitoring-receipt",
                        GRCRun.inputs["run_id"].astext == output[key]["result"]["resource_id"],
                    )
                )
                output["monitoring_receipts"][key] = receipt.results
            report = await db.get(AuditRecord, uuid.UUID(demo["prepared"]["REPORT-01"]))
            report_body = {
                k: v
                for k, v in report.body.items()
                if k not in {"review_stage", "review_cycle", "review_approvers"}
            }
        revocable_report = await paper("report", "REVOCATION-REPORT", report_body)
        restricted = await paper(
            "board",
            "AUDIT-COMMITTEE-PACKAGE",
            {
                "report_ids": [revocable_report["id"]],
                "executive_briefing": "SYNTHETIC audience and revocation proof package only",
                "authorized_audience": "audit_committee",
                "valid_until": "2027-12-31",
                "synthetic": True,
            },
        )
        frozen_package = await call(base + f"/board/{restricted['id']}/publish")
        await call(
            base + "/board/packages/" + frozen_package["id"],
            who=demo["users"][7],
            method="GET",
            expected=403,
        )
        await call(
            base + "/board/packages/" + frozen_package["id"],
            who=demo["users"][6],
            method="GET",
            expected=200,
        )
        await call(
            base + f"/records/{revocable_report['id']}/actions",
            {
                "version": revocable_report["version"],
                "action": "reopen",
                "comments": "Synthetic deliberate source reopening to verify publication revocation",
            },
            reviewer,
        )
        await call(
            base + "/board/packages/" + frozen_package["id"],
            who=demo["users"][6],
            method="GET",
            expected=409,
        )
        output["board_audience_and_revocation_verified"] = True

    (ROOT / "docs/phase-10/end-to-end-verification.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "worker": output["worker_job"]["status"],
                "scheduled": output["scheduled_job"]["status"],
                "closure": closure["status"],
                "steps": len(output["steps"]),
            }
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
