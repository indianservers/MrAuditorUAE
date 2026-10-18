"""Guarded, idempotent synthetic GRC workpapers through real HTTP validation/review.

All evidence references are conspicuous software fixtures, not control assurance.
Existing journal lines and Phase 1â€“9 runs are never replaced.
"""

# ruff: noqa: E402
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from sqlalchemy import func, select

from app.core.dependencies import Context
from app.core.security import access_token, hash_password
from app.db.models.platform import Membership, MembershipRole, Role, User
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import ImportBatch, ImportSnapshot, JournalLine
from app.modules.audit_execution.models import AuditAccess, AuditRecord
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.grc.catalogue import MONITOR_RULES
from app.modules.grc.models import GRCRun, MonitorAlert
from app.modules.grc.monitoring import execute
from app.modules.ml.models import MLEvent


async def main():
    password = os.getenv("PHASE7_DEMO_PASSWORD", "")
    if len(password) < 16:
        raise ValueError("Explicit existing isolated demo password required")
    manifest = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    entry = next(x for x in manifest["engagements"] if x["year"] == 2026)
    eid = uuid.UUID(entry["id"])
    users = []
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        before = await db.scalar(select(func.count()).select_from(JournalLine))
        for name in [
            "Internal Auditor",
            "Chief Audit Executive",
            "Risk Owner",
            "Control Owner",
            "Remediation Owner",
            "Process Owner",
            "Audit Committee Member",
            "Board Viewer",
            "Internal Audit Quality Reviewer",
        ]:
            uid = uuid.uuid5(DEMO_TENANT, "phase10/user/" + name)
            mid = uuid.uuid5(DEMO_TENANT, "phase10/member/" + name)
            role = await db.scalar(select(Role).where(Role.name == name))
            if not role:
                raise ValueError("Apply 0010 before synthetic provisioning")
            email = "synthetic.p10." + name.lower().replace(" ", ".") + "@auditos.test"
            if not await db.get(User, uid):
                db.add(User(id=uid, email=email, password_hash=hash_password(password)))
                await db.flush()
                db.add(Membership(id=mid, tenant_id=DEMO_TENANT, user_id=uid))
                await db.flush()
                db.add(MembershipRole(membership_id=mid, role_id=role.id))
                db.add(
                    AuditAccess(
                        tenant_id=DEMO_TENANT,
                        created_by=uuid.UUID(manifest["users"][1]["id"]),
                        engagement_id=eid,
                        membership_id=mid,
                        role_id=role.id,
                    )
                )
            if name == "Chief Audit Executive":
                source_role = await db.scalar(
                    select(Role).where(Role.name == "Financial Reporting Manager")
                )
                if not await db.scalar(
                    select(MembershipRole.membership_id).where(
                        MembershipRole.membership_id == mid,
                        MembershipRole.role_id == source_role.id,
                    )
                ):
                    db.add(MembershipRole(membership_id=mid, role_id=source_role.id))
                    db.add(
                        AuditAccess(
                            tenant_id=DEMO_TENANT,
                            created_by=uuid.UUID(manifest["users"][1]["id"]),
                            engagement_id=eid,
                            membership_id=mid,
                            role_id=source_role.id,
                        )
                    )
            users.append({"id": str(uid), "role": name, "email": email})
        evidence = await db.scalar(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == DEMO_TENANT,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "ifrs-note",
                AuditRecord.status.in_(["APPROVED", "LOCKED"]),
            )
            .order_by(AuditRecord.reference)
            .limit(1)
        )
        if not evidence:
            raise ValueError("Existing approved synthetic source required")
        evidence_id = str(evidence.id)
        snapshot = await db.scalar(
            select(ImportSnapshot)
            .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
            .where(
                ImportSnapshot.tenant_id == DEMO_TENANT,
                ImportSnapshot.entity_id == uuid.UUID(entry["entity_id"]),
                ImportSnapshot.period_id == uuid.UUID(entry["period_id"]),
                ImportBatch.kind.in_(["gl", "journals"]),
                ImportBatch.status == "active",
            )
            .order_by(ImportSnapshot.created_at.desc())
            .limit(1)
        )
        deployment = await db.scalar(
            select(MLEvent)
            .where(
                MLEvent.tenant_id == DEMO_TENANT,
                MLEvent.engagement_id == eid,
                MLEvent.kind == "deployment",
                MLEvent.body["family"].astext == "autoencoder",
            )
            .order_by(MLEvent.created_at.desc(), MLEvent.id.desc())
            .limit(1)
        )
        if not snapshot or not deployment:
            raise ValueError("Existing committed ledger and deployed Phase 9 model required")
        snapshot_id, deployment_id = str(snapshot.id), str(deployment.id)
    from app.main import app

    logging.getLogger("auditos").setLevel(logging.WARNING)
    base = f"/api/v1/grc/engagements/{eid}"
    admin = manifest["users"][1]
    owner = users[0]["id"]
    prepared = {}
    started = time.perf_counter()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=300
    ) as c:

        async def call(path, body=None, who=admin, method="POST"):
            r = await c.request(
                method,
                path,
                headers={
                    "Authorization": "Bearer " + access_token(uuid.UUID(who["id"])),
                    "X-Tenant-ID": str(DEMO_TENANT),
                },
                **({"json": body} if body is not None else {}),
            )
            if r.status_code >= 400:
                raise RuntimeError(path + " " + str(r.status_code) + " " + r.text)
            return r.json()

        async def paper(kind, key, body, approve=True):
            reference = "P10-" + key
            async with Session() as db, db.begin():
                await tenant_context(db, str(DEMO_TENANT))
                obj = await db.scalar(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == DEMO_TENANT,
                        AuditRecord.engagement_id == eid,
                        AuditRecord.kind == "grc-" + kind,
                        AuditRecord.reference == reference,
                    )
                )
                current = (
                    {
                        "id": str(obj.id),
                        "version": obj.version,
                        "status": obj.status,
                        "body": obj.body,
                    }
                    if obj
                    else None
                )
            if not current:
                current = await call(
                    base + "/records/" + kind,
                    {
                        "reference": reference,
                        "title": "SYNTHETIC " + key.replace("-", " "),
                        "body": {
                            "narrative": "SYNTHETIC SOFTWARE FIXTURE. Referenced synthetic financial note tests lineage only; it is not operational evidence.",
                            **body,
                        },
                    },
                )
            if kind == "link" and current["body"].get("risk_id") != body["risk_id"]:
                if current["status"] in {"APPROVED", "LOCKED"}:
                    current = await call(
                        base + "/records/" + current["id"] + "/actions",
                        {
                            "version": current["version"],
                            "action": "reopen",
                            "comments": "Synthetic fixture correction: ensure 300 distinct same-process risk-control pairs",
                        },
                        users[1],
                    )
                current = await call(
                    base + "/records/" + current["id"],
                    {
                        "reference": reference,
                        "title": "SYNTHETIC " + key.replace("-", " "),
                        "version": current["version"],
                        "body": {
                            **{
                                k: v
                                for k, v in current["body"].items()
                                if k not in {"review_stage", "review_cycle", "review_approvers"}
                            },
                            **body,
                        },
                    },
                    method="PATCH",
                )
            if approve and current["status"] not in {"APPROVED", "LOCKED"}:
                if current["status"] in {"IN_PROGRESS", "REVISED", "REVIEW_NOTES"}:
                    current = await call(
                        base + "/records/" + current["id"] + "/actions",
                        {
                            "version": current["version"],
                            "action": "submit",
                            "comments": "Synthetic preparer submits software fixture; no real assurance conclusion",
                        },
                    )
                current = await call(
                    base + "/records/" + current["id"] + "/actions",
                    {
                        "version": current["version"],
                        "action": "approve",
                        "comments": "Independent synthetic workflow approval; financial-note fixture is not real control evidence",
                    },
                    users[1],
                )
            if approve and kind in {"assessment", "plan", "kri", "test"}:
                await call(base + "/records/" + current["id"] + "/calculate")
            prepared[key] = current["id"]
            return current["id"]

        framework = await paper(
            "framework",
            "FRAMEWORK",
            {
                "identifier": "IIA-GIAS-2024",
                "version_number": 1,
                "effective_from": "2025-01-09",
                "applicability": "Synthetic internal audit mandate",
                "technical_review": "Public metadata only; licensed text not reproduced",
                "authority": "professional_standard",
            },
        )
        scoring = await paper(
            "scoring",
            "SCORING",
            {
                "version_number": 1,
                "appetite": "9",
                "criteria_weights": {"exposure": "0.6", "prior_audit": "0.4"},
            },
        )
        processes = []
        for i, name in enumerate(
            [
                "Procure to pay",
                "Order to cash",
                "Payroll",
                "Treasury",
                "Financial close",
                "Tax operations",
                "Cybersecurity",
                "Vendor onboarding",
                "Inventory",
                "Business continuity",
            ]
        ):
            processes.append(
                await paper(
                    "universe",
                    f"PROCESS-{i:02d}",
                    {
                        "owner_id": owner,
                        "entity_id": entry["entity_id"],
                        "unit_type": "process",
                        "objective": "SYNTHETIC " + name,
                        "exposure": str((i + 1) * 10000),
                        "inherent_rating": 12 + i % 10,
                        "maturity": 2 + i % 3,
                        "frequency_months": 12,
                        "assigned_auditor_id": owner,
                    },
                )
            )
        plan = await paper(
            "plan",
            "PLAN-2026",
            {
                "year": 2026,
                "scoring_id": scoring,
                "capacity_hours": {owner: "1600"},
                "committee_evidence_id": evidence_id,
                "items": [
                    {
                        "universe_id": p,
                        "auditor_id": owner,
                        "starts": f"2026-{i + 1:02d}-01",
                        "ends": f"2026-{i + 1:02d}-20",
                        "budget_hours": "80",
                        "actual_hours": str(i * 4),
                        "criteria": {"exposure": str(1 + i % 5), "prior_audit": "3"},
                    }
                    for i, p in enumerate(processes)
                ],
            },
        )
        engagements = []
        for i, p in enumerate(processes):
            engagements.append(
                await paper(
                    "engagement",
                    f"ENGAGEMENT-{i:02d}",
                    {
                        "owner_id": owner,
                        "universe_id": p,
                        "plan_id": plan,
                        "objective": "Synthetic independent process evaluation",
                        "scope": "Software workflow demonstration",
                        "criteria": "Approved original methodology and documented mandate",
                        "program": [
                            "Walkthrough",
                            "Inspect selected evidence",
                            "Test and review exceptions",
                        ],
                        "team_ids": [owner],
                        "starts": f"2026-{i + 1:02d}-01",
                        "ends": f"2026-{i + 1:02d}-20",
                    },
                )
            )
        risks, controls, tests, deficiencies, actions = [], [], [], [], []
        for i in range(100):
            risks.append(
                await paper(
                    "risk",
                    f"RISK-{i:03d}",
                    {
                        "owner_id": owner,
                        "universe_id": processes[i % 10],
                        "category": [
                            "financial",
                            "operational",
                            "compliance",
                            "cybersecurity",
                            "third_party",
                        ][i % 5],
                        "objective": "Preserve authorized and complete transactions",
                        "description": f"Synthetic scenario {i}: incompatible access or missed reconciliation",
                        "cause": "Synthetic gap in independent authorization",
                        "consequence": "Potential unreviewed financial exception",
                        "treatment": "reduce",
                        "review_date": "2026-12-31",
                        "evidence_ids": [evidence_id],
                    },
                )
            )
            await paper(
                "assessment",
                f"ASSESSMENT-{i:03d}",
                {
                    "owner_id": owner,
                    "risk_id": risks[-1],
                    "scoring_id": scoring,
                    "as_of": "2026-10-18",
                    "inherent_likelihood": 4,
                    "inherent_impact": 5,
                    "residual_likelihood": 1 + i % 5,
                    "residual_impact": 1 + (i // 5) % 5,
                    "velocity": "moderate",
                    "rationale": "Ordinal synthetic assessment, not a calibrated probability",
                    "evidence_ids": [evidence_id],
                },
            )
        for i in range(200):
            controls.append(
                await paper(
                    "control",
                    f"CONTROL-{i:03d}",
                    {
                        "owner_id": owner,
                        "universe_id": processes[i % 10],
                        "subprocess": "Authorization and reconciliation",
                        "description": f"Synthetic control {i}: independent reviewer verifies access and transaction reconciliation",
                        "control_type": "authorization" if i % 2 else "reconciliation",
                        "frequency": "monthly",
                        "approach": "preventive" if i % 2 else "detective",
                        "operation": "hybrid",
                        "key_control": i % 4 == 0,
                        "procedure": "Obtain source population, independently compare approvals and document exceptions",
                        "framework_ids": [framework],
                    },
                )
            )
        for i in range(300):
            await paper(
                "link",
                f"RCM-{i:03d}",
                {
                    "risk_id": risks[(i if i < 200 else i + 10) % 100],
                    "control_id": controls[i % 200],
                    "rationale": "Synthetic mapping: authorization and reconciliation address this specific process risk",
                },
            )
        for i in range(100):
            tests.append(
                await paper(
                    "test",
                    f"TEST-{i:03d}",
                    {
                        "owner_id": owner,
                        "control_id": controls[i],
                        "test_type": "design",
                        "procedure": "Inspect synthetic design fixture and compare defined authorization criteria",
                        "period_start": "2026-01-01",
                        "period_end": "2026-12-31",
                        "conclusion": "ineffective" if i < 50 else "inconclusive",
                        "rationale": "Synthetic design gap"
                        if i < 50
                        else "Fixture cannot establish real operating effectiveness",
                        "evidence_ids": [evidence_id],
                    },
                )
            )
        for i in range(50):
            deficiencies.append(
                await paper(
                    "deficiency",
                    f"DEFICIENCY-{i:03d}",
                    {
                        "owner_id": owner,
                        "control_id": controls[i],
                        "risk_id": risks[i],
                        "test_id": tests[i],
                        "description": f"Synthetic authorization design deficiency {i}",
                        "root_cause_method": "five_whys",
                        "root_cause": "No independently defined authorization owner in fixture",
                        "consequence": "Potential unauthorized transaction",
                        "severity": "high" if i % 4 == 0 else "moderate",
                        "severity_methodology": "Original synthetic severity matrix: impact and likelihood",
                        "affected_from": "2026-01-01",
                        "affected_to": "2026-10-18",
                        "evidence_ids": [evidence_id],
                    },
                )
            )
            for j in range(2):
                actions.append(
                    await paper(
                        "remediation",
                        f"ACTION-{i:03d}-{j}",
                        {
                            "owner_id": users[4]["id"],
                            "deficiency_id": deficiencies[-1],
                            "corrective_action": "Define independent authorization owner"
                            if j == 0
                            else "Introduce evidenced monthly exception review",
                            "management_response": "Synthetic management accepts the proposed improvement",
                            "target_date": "2026-09-30" if i % 3 == 0 else "2026-12-01",
                            "management_status": "reported_complete"
                            if i % 2 == 0
                            else "in_progress",
                            "evidence_ids": [evidence_id],
                        },
                    )
                )
        for i in range(20):
            await paper(
                "kri",
                f"KRI-{i:02d}",
                {
                    "owner_id": owner,
                    "risk_id": risks[i],
                    "unit": "exceptions",
                    "direction": "above",
                    "threshold": "5",
                    "observations": [
                        {
                            "observed_on": f"2026-{month:02d}-01",
                            "value": str((i + month) % 10),
                            "evidence_id": evidence_id,
                        }
                        for month in [8, 9, 10]
                    ],
                },
            )
        monitor = []
        for i, (code, definition) in enumerate(MONITOR_RULES.items()):
            ledger = definition[1] in {"gl", "prior_activity"}
            body = {
                "owner_id": owner,
                "rule_key": "P10-" + code,
                "version_number": 1,
                "input_kind": "ledger" if ledger else "workpapers",
                "rule_code": code,
                "decision_rationale": "Synthetic monitor; unavailable specialized inputs explicitly remain NOT_TESTABLE",
                "trigger_on_import": False,
            }
            if ledger:
                body["snapshot_id"] = snapshot_id
            if code == "duplicate_payments":
                body.update(ml_deployment_id=deployment_id, ml_family="autoencoder", ml_limit=1000)
            monitor.append((code, await paper("monitor-rule", f"MONITOR-{i:02d}", body)))
        for i in range(20):
            await paper(
                "obligation",
                f"OBLIGATION-{i:02d}",
                {
                    "owner_id": owner,
                    "entity_id": entry["entity_id"],
                    "module": "governance",
                    "source_url": "https://www.theiia.org/en/standards/2024-standards/",
                    "jurisdiction": "AE - synthetic internal governance mandate",
                    "effective_from": "2025-01-09",
                    "deadline": "2026-09-30" if i % 2 else "2026-12-31",
                    "required_evidence": "Documented professional review, not calendar completion",
                    "compliance_assessment": "pending",
                },
            )
        sod_rule = await paper(
            "sod-rule",
            "SOD-RULE",
            {
                "system": "SYNTHETIC-ERP",
                "version_number": 1,
                "pairs": [
                    {
                        "first": "AP-create",
                        "second": "AP-approve",
                        "rationale": "Independent authorization of payment setup and approval",
                    }
                ],
                "definition_evidence_id": evidence_id,
            },
        )
        access = await paper(
            "sod-access",
            "SOD-ACCESS",
            {
                "system": "SYNTHETIC-ERP",
                "rule_id": sod_rule,
                "as_of": "2026-10-18",
                "source_evidence_id": evidence_id,
                "assignments": [
                    {
                        "principal": "FICTIONAL-ERP-user-1",
                        "permission": p,
                        "scope": "AE-ENTITY-A",
                        "valid_from": "2026-01-01",
                    }
                    for p in ["AP-create", "AP-approve"]
                ]
                + [
                    {
                        "principal": "FICTIONAL-ERP-user-2",
                        "permission": "AP-create",
                        "scope": "AE-ENTITY-A",
                        "valid_from": "2026-01-01",
                    },
                    {
                        "principal": "FICTIONAL-ERP-user-2",
                        "permission": "AP-approve",
                        "scope": "AE-ENTITY-B",
                        "valid_from": "2026-01-01",
                    },
                ],
            },
        )
        monitor.append(
            (
                "access_conflicts_configured",
                await paper(
                    "monitor-rule",
                    "SOD-MONITOR",
                    {
                        "owner_id": owner,
                        "rule_key": "P10-SOD-PROOF",
                        "version_number": 1,
                        "input_kind": "workpapers",
                        "rule_code": "access_conflicts",
                        "criteria": {"access_id": access},
                        "decision_rationale": "Evaluate the explicitly configured synthetic ERP permission population",
                    },
                ),
            )
        )
        await paper(
            "policy",
            "POLICY-01",
            {
                "owner_id": users[1]["id"],
                "version_number": 1,
                "effective_from": "2026-01-01",
                "review_date": "2026-12-31",
                "policy_text": "SYNTHETIC SOFTWARE POLICY. Independent authorization and documented reconciliation are required. This is test data only.",
            },
        )
        for i in range(10):
            await paper(
                "third-party",
                f"VENDOR-{i:02d}",
                {
                    "owner_id": owner,
                    "name": f"Fictional Software Vendor {i} [SYNTHETIC]",
                    "services": "Fictional critical software support",
                    "criticality": "high" if i % 2 else "moderate",
                    "geography": "AE",
                    "dependency": str(i + 1),
                    "security_assessment": "Synthetic questionnaire requires original evidence",
                    "renewal_date": "2026-12-31",
                    "sla_exceptions": "No real operational SLA conclusion",
                    "evidence_ids": [evidence_id],
                },
            )
        report = await paper(
            "report",
            "REPORT-01",
            {
                "ia_engagement_id": engagements[0],
                "executive_summary": "SYNTHETIC internal audit workflow demonstration",
                "objective": "Verify software evidence lineage and review separation",
                "scope": "Synthetic procure-to-pay fixture only",
                "methodology": "Documented ordinal risk scoring and independent design review",
                "overall_assessment": "Software test only; no real assurance opinion",
                "deficiency_ids": deficiencies[:5],
                "recommendations": "Assign authorization ownership and inspect original evidence",
                "management_response": "Synthetic management accepts actions",
                "appendices": "All sources are software fixtures",
                "synthetic": True,
            },
        )
        board = await paper(
            "board",
            "BOARD-01",
            {
                "report_ids": [report],
                "executive_briefing": "SYNTHETIC committee briefing. Five reviewed fixture deficiencies require documented follow-up; no real assurance is provided.",
                "authorized_audience": "both",
                "valid_until": "2027-12-31",
                "synthetic": True,
            },
        )
        publication = await call(base + f"/board/{board}/publish")
        await paper(
            "qaip",
            "QUALITY-01",
            {
                "owner_id": owner,
                "framework_id": framework,
                "assessment_type": "ongoing",
                "scheduled_on": "2026-10-18",
                "conformance_assessment": "Synthetic self-assessment only; no full GIAS conformance claim",
                "findings": "Expand operating evidence and external quality validation",
                "improvement_actions": "Document coverage and strengthen source traceability",
                "training_needs": "Risk scoring and evidence evaluation",
                "evidence_ids": [evidence_id],
            },
        )
    from app.core.permissions import ROLE_PERMISSIONS

    ctx = Context(
        uuid.UUID(admin["id"]), DEMO_TENANT, frozenset(ROLE_PERMISSIONS["Firm Administrator"])
    )
    results = []
    for code, rid in monitor:
        async with Session() as db, db.begin():
            await tenant_context(db, str(DEMO_TENANT))
            obj = await db.get(AuditRecord, uuid.UUID(rid))
            tick = time.perf_counter()
            result = await execute(
                db,
                ctx,
                {
                    "engagement_id": str(eid),
                    "rule_id": rid,
                    "version": obj.version,
                    "synthetic": True,
                },
            )
            frozen = await db.get(GRCRun, uuid.UUID(result["id"]))
            results.append(
                {
                    "rule": code,
                    "seconds": round(time.perf_counter() - tick, 3),
                    **result,
                    "results": frozen.results,
                }
            )
        print("Monitor", code, results[-1]["created_alerts"], flush=True)
    async with Session() as db, db.begin():
        await tenant_context(db, str(DEMO_TENANT))
        after = await db.scalar(select(func.count()).select_from(JournalLine))
        counts = dict(
            (
                await db.execute(
                    select(AuditRecord.kind, func.count())
                    .where(
                        AuditRecord.tenant_id == DEMO_TENANT,
                        AuditRecord.engagement_id == eid,
                        AuditRecord.kind.like("grc-%"),
                    )
                    .group_by(AuditRecord.kind)
                )
            ).all()
        )
        alert_count = await db.scalar(
            select(func.count())
            .select_from(MonitorAlert)
            .where(MonitorAlert.tenant_id == DEMO_TENANT, MonitorAlert.engagement_id == eid)
        )
    assert before == after, "Existing financial facts must remain unchanged"
    output = {
        "synthetic": True,
        "seed": 20261018,
        "engagement_id": str(eid),
        "snapshot_id": snapshot_id,
        "users": users,
        "counts": counts,
        "alerts": alert_count,
        "journal_lines_before": before,
        "journal_lines_after": after,
        "prepared": prepared,
        "board_publication": publication["id"],
        "monitoring": results,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    (ROOT / "docs/phase-10/demo-verification.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "counts": counts,
                "alerts": alert_count,
                "journal_lines_preserved": before,
                "seconds": output["elapsed_seconds"],
            }
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
