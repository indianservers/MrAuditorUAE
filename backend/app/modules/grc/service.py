import hashlib
import json
import uuid
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions, firm_roles, role_permissions
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.grc import schemas as s
from app.modules.grc.catalogue import FRAMEWORKS, MONITOR_RULES, OWNER_ROLES
from app.modules.grc.models import GRCRun, MonitorAlert
from app.modules.ifrs.calculations import serial

APPROVED = {"APPROVED", "LOCKED"}


def clean(body):
    return {
        k: v
        for k, v in body.items()
        if k not in {"review_stage", "review_cycle", "review_approvers"}
    }


def dependency(obj):
    return {
        "id": str(obj.id),
        "version": obj.version,
        "kind": obj.kind,
        "updated_at": obj.updated_at.isoformat(),
    }


async def owner_scoped(db, ctx, eid):
    _, granted_names = await engagement_permissions(db, ctx, eid, "grc.read")
    if not granted_names & OWNER_ROLES:
        return False
    roles = await firm_roles(db, ctx.tenant_id, ctx.user_id)
    professional = [r.id for r in roles if r.name in granted_names and r.name not in OWNER_ROLES]
    permissions = await role_permissions(db, ctx.tenant_id, professional)
    return "grc.read" not in permissions


async def authorize_record(db, ctx, obj):
    await engagement_permissions(db, ctx, obj.engagement_id, "grc.read")
    if (
        await owner_scoped(db, ctx, obj.engagement_id)
        and not (
            obj.kind in {"grc-framework", "grc-policy", "grc-scoring"} and obj.status in APPROVED
        )
        and obj.body.get("owner_id") != str(ctx.user_id)
        and obj.prepared_by != ctx.user_id
    ):
        raise HTTPException(403, "Assigned owner access required")


async def record(db, ctx, eid, rid, kind=None, approved=True):
    obj = await audit.get_record(db, ctx, eid, rid, "grc.read")
    if not obj.kind.startswith("grc-") or kind and obj.kind != "grc-" + kind:
        raise HTTPException(422, "Unexpected GRC source kind")
    if approved and obj.status not in APPROVED:
        raise HTTPException(409, "Approved GRC source required")
    return obj


async def evidence(db, ctx, eid, rid):
    obj = await audit.get_record(db, ctx, eid, rid, "grc.read")
    if obj.status not in APPROVED:
        raise HTTPException(409, "Independently approved evidence required")
    if obj.kind == "evidence":
        version = await db.scalar(
            select(EvidenceVersion)
            .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == rid)
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if not version or version.scan_status != "CLEAN":
            raise HTTPException(409, "Clean scanned evidence required")
    return obj


REFS = {
    "universe_id": "universe",
    "scoring_id": "scoring",
    "risk_id": "risk",
    "control_id": "control",
    "plan_id": "plan",
    "policy_id": "policy",
    "remediation_id": "remediation",
    "deficiency_id": "deficiency",
    "test_id": "test",
    "retest_id": "test",
    "retests_id": "test",
    "ia_engagement_id": "engagement",
    "framework_id": "framework",
}
LIST_REFS = {
    "framework_ids": "framework",
    "obligation_ids": "obligation",
    "deficiency_ids": "deficiency",
    "report_ids": "report",
}


async def snapshot(db, ctx, eng, rid):
    from app.modules.accounting.models import ImportBatch, ImportSnapshot

    obj = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.tenant_id == ctx.tenant_id,
            ImportSnapshot.id == rid,
            ImportSnapshot.entity_id == eng.entity_id,
            ImportSnapshot.period_id == eng.period_id,
        )
    )
    batch = await db.get(ImportBatch, obj.batch_id) if obj else None
    if (
        not obj
        or not batch
        or batch.status not in {"active", "superseded"}
        or batch.kind not in {"gl", "journals"}
    ):
        raise HTTPException(409, "Committed same-entity/period journal snapshot required")
    return obj


async def validate_body(db, ctx, eng, kind, data, record_id=None):
    key = kind.removeprefix("grc-")
    body = data.model_dump(mode="json")
    if await owner_scoped(db, ctx, eng.id):
        if body.get("owner_id") != str(ctx.user_id):
            raise HTTPException(403, "Owners may prepare only their own assigned workpapers")
    for field, expected in REFS.items():
        if body.get(field):
            await record(db, ctx, eng.id, uuid.UUID(body[field]), expected)
    for field, expected in LIST_REFS.items():
        for rid in body.get(field, []):
            await record(db, ctx, eng.id, uuid.UUID(rid), expected)
    evidences = set()
    for field, value in body.items():
        if field.endswith("evidence_id") and value:
            evidences.add(value)
    evidences.update(body.get("evidence_ids", []))
    for rid in evidences:
        await evidence(db, ctx, eng.id, uuid.UUID(rid))
    if hasattr(data, "entity_id") and data.entity_id != eng.entity_id:
        raise HTTPException(422, "Record entity must match engagement")
    if key == "framework":
        entry = FRAMEWORKS.get(data.identifier)
        if not entry and not data.custom_source_url:
            raise HTTPException(422, "Custom methodology requires its source")
        if (
            entry
            and cast(dict, entry)["effective"]
            and str(data.effective_from) != cast(dict, entry)["effective"]
        ):
            raise HTTPException(422, "Framework effective date differs from verified metadata")
        if (
            data.identifier == "ISO27001-2022"
            and data.requirement_mapping
            and not data.proprietary_text_authorized
        ):
            raise HTTPException(422, "Licensed ISO mapping authorization required")
        if data.supersedes_id:
            await record(db, ctx, eng.id, data.supersedes_id, "framework")
    if key == "universe":
        if data.parent_id:
            await record(db, ctx, eng.id, data.parent_id, "universe")
        await active_member(db, ctx, eng.id, data.assigned_auditor_id)
    if key == "plan":
        from app.modules.grc.calculations import plan_score

        scoring = await record(db, ctx, eng.id, data.scoring_id, "scoring")
        for item in data.items:
            await record(db, ctx, eng.id, item.universe_id, "universe")
            await active_member(db, ctx, eng.id, item.auditor_id)
            if item.starts.year != data.year or item.ends.year != data.year:
                raise HTTPException(422, "Plan items must be within plan year")
        result = plan_score(data, s.Scoring.model_validate(clean(scoring.body)))
        if result["overbooked"]:
            raise HTTPException(422, "Plan exceeds approved resource capacity")
    if key == "engagement":
        plan = await record(db, ctx, eng.id, data.plan_id, "plan")
        if not any(
            x["universe_id"] == str(data.universe_id) and not x.get("deferred")
            for x in plan.body["items"]
        ):
            raise HTTPException(422, "Engagement universe must be scheduled in the approved plan")
        if data.ends < data.starts:
            raise HTTPException(422, "Engagement dates invalid")
        for uid in data.team_ids:
            await active_member(db, ctx, eng.id, uid)
    if key == "assessment":
        from app.modules.grc.calculations import risk_score

        scoring = await record(db, ctx, eng.id, data.scoring_id, "scoring")
        risk_score(s.Scoring.model_validate(clean(scoring.body)), data)
    if key == "kri":
        dates = [x.observed_on for x in data.observations]
        if len(set(dates)) != len(dates):
            raise HTTPException(422, "KRI observations must have distinct dates")
        for obs in data.observations:
            await evidence(db, ctx, eng.id, obs.evidence_id)
    if key == "control":
        from app.modules.accounting.models import Account

        for rid in data.account_ids:
            if not await db.scalar(
                select(Account.id).where(
                    Account.tenant_id == ctx.tenant_id,
                    Account.id == rid,
                    Account.entity_id == eng.entity_id,
                )
            ):
                raise HTTPException(422, "Account belongs to a different entity")
    if key == "test":
        if data.period_end < data.period_start:
            raise HTTPException(422, "Test period invalid")
        if data.population_snapshot_id:
            await snapshot(db, ctx, eng, data.population_snapshot_id)
        if data.sample_run_id:
            await test_sample(db, ctx, eng, data)
        for item in data.results:
            for rid in item.evidence_ids:
                await evidence(db, ctx, eng.id, rid)
    if key == "sod-access":
        rule = await record(db, ctx, eng.id, data.rule_id, "sod-rule")
        if data.system != rule.body["system"]:
            raise HTTPException(422, "Access and SoD definition systems must match")
        for item in data.assignments:
            if item.valid_to and item.valid_to < item.valid_from:
                raise HTTPException(422, "Invalid access validity window")
    if key == "monitor-rule":
        if data.rule_code not in MONITOR_RULES:
            raise HTTPException(422, "Unknown monitoring rule")
        if data.input_kind == "ledger":
            if not data.snapshot_id:
                raise HTTPException(422, "Ledger monitoring needs a snapshot")
            await snapshot(db, ctx, eng, data.snapshot_id)
        if data.ml_deployment_id:
            from app.modules.ml.service import get

            deployment = await get(db, ctx, data.ml_deployment_id, "deployment", "ml.score")
            if (
                deployment.engagement_id != eng.id
                or deployment.body.get("family") != data.ml_family
            ):
                raise HTTPException(422, "Same-engagement model family deployment required")
        if data.criteria and data.input_kind == "ledger":
            if "snapshot_id" in data.criteria:
                raise HTTPException(422, "Snapshot cannot be overridden by rule parameters")
            from app.modules.audit_analytics.schemas import AnalyticsRequest

            AnalyticsRequest.model_validate(
                {"snapshot_id": str(data.snapshot_id or uuid.uuid4()), **data.criteria}
            )
        if data.input_kind == "workpapers":
            from datetime import date

            if set(data.criteria) - {"as_of", "access_id"}:
                raise HTTPException(422, "Unknown workpaper monitoring parameter")
            if data.criteria.get("as_of"):
                date.fromisoformat(data.criteria["as_of"])
            if data.criteria.get("access_id"):
                await record(db, ctx, eng.id, uuid.UUID(data.criteria["access_id"]), "sod-access")
    if key == "alert-decision":
        await alert(db, ctx, eng.id, data.alert_id)
    if key == "deficiency":
        test = await record(db, ctx, eng.id, data.test_id, "test")
        if test.body["control_id"] != str(data.control_id):
            raise HTTPException(422, "Deficiency test must reference its control")
        link = await db.scalar(
            select(AuditRecord.id).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind == "grc-link",
                AuditRecord.status.in_(APPROVED),
                AuditRecord.body["risk_id"].astext == str(data.risk_id),
                AuditRecord.body["control_id"].astext == str(data.control_id),
            )
        )
        if not link:
            raise HTTPException(409, "Approved risk-control mapping required")
        if data.alert_id:
            await alert(db, ctx, eng.id, data.alert_id)
    if key == "closure":
        action = await record(db, ctx, eng.id, data.remediation_id, "remediation")
        deficiency = await record(
            db, ctx, eng.id, uuid.UUID(action.body["deficiency_id"]), "deficiency"
        )
        test = await record(db, ctx, eng.id, data.retest_id, "test")
        if (
            test.body["test_type"] != "retest"
            or test.body["control_id"] != deficiency.body["control_id"]
            or test.body["conclusion"] != "effective"
            or test.body.get("retests_id") != deficiency.body["test_id"]
        ):
            raise HTTPException(
                409, "Effective approved retest of the original deficient control required"
            )
        if action.body["management_status"] != "reported_complete":
            raise HTTPException(
                409, "Management completion response required before verified closure"
            )
    if key == "obligation" and data.compliance_assessment == "supported" and not data.evidence_ids:
        raise HTTPException(422, "Calendar completion is not evidence of compliance")
    if key == "obligation" and data.statutory_record_id:
        await evidence(db, ctx, eng.id, data.statutory_record_id)
    if key == "policy" and data.supersedes_id:
        old = await record(db, ctx, eng.id, data.supersedes_id, "policy")
        if data.version_number <= old.body["version_number"]:
            raise HTTPException(422, "Policy version must increase")
    if key == "qaip":
        framework = await record(db, ctx, eng.id, data.framework_id, "framework")
        if framework.body["effective_from"] > str(data.scheduled_on):
            raise HTTPException(422, "Framework not effective on assessment date")
    return body


async def active_member(db, ctx, eid, uid):
    from app.core.dependencies import Context

    await engagement_permissions(db, Context(uid, ctx.tenant_id, frozenset()), eid, "grc.read")


async def test_sample(db, ctx, eng, data):
    from app.modules.accounting.models import SamplingItem, SamplingRun

    sample = await db.scalar(
        select(SamplingRun).where(
            SamplingRun.tenant_id == ctx.tenant_id,
            SamplingRun.id == data.sample_run_id,
            SamplingRun.entity_id == eng.entity_id,
            SamplingRun.period_id == eng.period_id,
        )
    )
    if not sample or sample.snapshot_id != data.population_snapshot_id:
        raise HTTPException(422, "Sample must use the same source population")
    ids = set(
        (
            await db.scalars(
                select(SamplingItem.line_id).where(
                    SamplingItem.tenant_id == ctx.tenant_id, SamplingItem.run_id == sample.id
                )
            )
        ).all()
    )
    if len({i.line_id for i in data.results}) != len(data.results):
        raise HTTPException(422, "Duplicate sample test item")
    if any(i.line_id not in ids for i in data.results):
        raise HTTPException(422, "Tested line absent from frozen sample")
    return ids


async def validate_action(db, ctx, eid, obj, action):
    if action in {"submit", "approve", "lock"}:
        eng = await audit.engagement(db, ctx, eid, "grc.read")
        key = obj.kind.removeprefix("grc-")
        data: Any = s.BODIES[key].model_validate(clean(obj.body))
        await validate_body(db, ctx, eng, obj.kind, data, obj.id)
        if key == "test":
            if data.test_type in {"operating", "retest"}:
                if not data.sample_run_id or not data.population_snapshot_id:
                    raise HTTPException(409, "Frozen population and sample required")
                selected = await test_sample(db, ctx, eng, data)
                if selected != {x.line_id for x in data.results} or not selected:
                    raise HTTPException(409, "Every sampled item must be tested")
                if any(not x.evidence_ids or x.outcome == "not_provided" for x in data.results):
                    raise HTTPException(409, "Reviewed evidence and outcome required per sample")
            if not data.evidence_ids:
                raise HTTPException(409, "Control test evidence required")
            if data.conclusion == "effective" and any(x.outcome != "passed" for x in data.results):
                raise HTTPException(409, "Exceptions cannot be silently concluded effective")
        if key == "policy" and action in {"approve", "lock"} and ctx.user_id != data.owner_id:
            raise HTTPException(
                403, "Authorized policy owner must approve a separately prepared revision"
            )
        if key == "framework" and data.effective_to and data.effective_to < data.effective_from:
            raise HTTPException(422, "Framework validity window invalid")


async def run(db, ctx, eid, kind, inputs, results, deps=(), rid=None):
    payload = serial(
        {"kind": kind, "inputs": inputs, "results": results, "dependencies": list(deps)}
    )
    obj = GRCRun(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        record_id=rid,
        kind=kind,
        inputs=payload["inputs"],
        dependencies=payload["dependencies"],
        results=payload["results"],
        sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    db.add(obj)
    await db.flush()
    return obj


async def alert(db, ctx, eid, identifier):
    await audit.engagement(db, ctx, eid, "monitor.alert.review")
    obj = await db.scalar(
        select(MonitorAlert).where(
            MonitorAlert.tenant_id == ctx.tenant_id,
            MonitorAlert.engagement_id == eid,
            MonitorAlert.id == identifier,
        )
    )
    if not obj:
        raise HTTPException(404, "Monitoring alert not found")
    return obj
