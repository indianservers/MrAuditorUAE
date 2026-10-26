import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text

from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.models import AuditRecord
from app.modules.grc import calculations as calc
from app.modules.grc import schemas as s
from app.modules.grc import service
from app.modules.grc.models import GRCRun


async def calculate(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "grc.calculate", True)
    obj = await service.record(db, ctx, eid, rid)
    key = obj.kind.removeprefix("grc-")
    data: Any = s.BODIES[key].model_validate(service.clean(obj.body))
    deps = [service.dependency(obj)]
    for field, expected in service.REFS.items():
        identifier = obj.body.get(field)
        if identifier:
            dependency = await service.record(db, ctx, eid, uuid.UUID(identifier), expected)
            if not any(x["id"] == str(dependency.id) for x in deps):
                deps.append(service.dependency(dependency))
    sod_metadata = None
    sod_rule = None
    if key == "sod-access":
        from app.modules.grc.sod_sources import bind

        source = await service.record(db, ctx, eid, data.rule_id, "sod-rule")
        sod_rule = s.SoDRule.model_validate(service.clean(source.body))
        sod_metadata, sod_dependencies = await bind(db, ctx, eid, obj, source, data, sod_rule)
        deps = list({dep["id"]: dep for dep in [*deps, *sod_dependencies]}.values())
    previous = await db.scalar(
        select(GRCRun)
        .where(GRCRun.tenant_id == ctx.tenant_id, GRCRun.record_id == obj.id, GRCRun.kind == key)
        .order_by(GRCRun.created_at.desc(), GRCRun.id.desc())
        .limit(1)
    )
    compatible = key != "sod-access" or (
        previous is not None
        and previous.results.get("sod_contract") == "permission-overlap-intervals/1"
        and sod_metadata is not None
        and previous.results.get("sod_implementation_sha256")
        == sod_metadata["sod_implementation_sha256"]
    )
    if (
        previous
        and compatible
        and any(
            d["id"] == str(obj.id) and d["version"] == obj.version for d in previous.dependencies
        )
    ):
        for dep in previous.dependencies:
            source = await db.scalar(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    AuditRecord.id == uuid.UUID(dep["id"]),
                )
            )
            if (
                not source
                or source.version != dep["version"]
                or source.status not in service.APPROVED
            ):
                raise HTTPException(
                    409,
                    "Calculation source changed; reopen and independently review this workpaper",
                )
        return previous
    if key in {"assessment", "plan"}:
        source = await service.record(db, ctx, eid, data.scoring_id, "scoring")
        if not any(x["id"] == str(source.id) for x in deps):
            deps.append(service.dependency(source))
        scoring = s.Scoring.model_validate(service.clean(source.body))
        results = (
            calc.risk_score(scoring, data)
            if key == "assessment"
            else calc.plan_score(data, scoring)
        )
    elif key == "sod-access":
        try:
            results = calc.sod(sod_rule, data)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        results.update(sod_metadata or {})
    elif key == "kri":
        rows = sorted(data.observations, key=lambda x: x.observed_on)
        results = {
            "observations": [
                {
                    "date": str(x.observed_on),
                    "value": x.value,
                    "breach": x.value > data.threshold
                    if data.direction == "above"
                    else x.value < data.threshold,
                    "evidence_id": str(x.evidence_id),
                }
                for x in rows
            ],
            "unit": data.unit,
            "threshold": data.threshold,
            "direction": data.direction,
        }
    elif key == "test":
        results = {
            "proposed_human_conclusion": data.conclusion,
            "tested": len(data.results),
            "passed": sum(x.outcome == "passed" for x in data.results),
            "exceptions": sum(x.outcome == "exception" for x in data.results),
            "effectiveness_inferred_from_document_presence": False,
            "population_snapshot": str(data.population_snapshot_id),
            "sample_id": str(data.sample_run_id),
        }
    else:
        raise HTTPException(422, "This workpaper is governed by review, not arithmetic")
    return await service.run(db, ctx, eid, key, service.clean(obj.body), results, deps, obj.id)


async def transition(db, ctx, eid, rid, data):
    obj = await service.record(db, ctx, eid, rid, "engagement", False)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"ia-stage:{ctx.tenant_id}:{rid}"},
    )
    last = await db.scalar(
        select(GRCRun)
        .where(
            GRCRun.tenant_id == ctx.tenant_id,
            GRCRun.record_id == rid,
            GRCRun.kind == "ia-transition",
        )
        .order_by(GRCRun.created_at.desc(), GRCRun.id.desc())
        .limit(1)
    )
    current = last.results["stage"] if last else "DRAFT"
    if data.expected_stage != current:
        raise HTTPException(409, "Internal audit stage changed; reload")
    allowed = {
        "DRAFT": {"PLANNED"},
        "PLANNED": {"APPROVED", "DRAFT"},
        "APPROVED": {"FIELDWORK"},
        "FIELDWORK": {"REVIEW"},
        "REVIEW": {"REPORTING", "FIELDWORK"},
        "REPORTING": {"ISSUED", "FIELDWORK"},
        "ISSUED": {"FOLLOW_UP"},
        "FOLLOW_UP": {"CLOSED", "FIELDWORK"},
        "CLOSED": {"FOLLOW_UP"},
    }
    if data.next_stage not in allowed[current]:
        raise HTTPException(409, "Invalid internal audit stage transition")
    permission = (
        "ia.engagement.review"
        if data.next_stage in {"APPROVED", "REPORTING", "CLOSED"}
        else "ia.report.approve"
        if data.next_stage == "ISSUED"
        else "ia.engagement.execute"
    )
    await engagement_permissions(db, ctx, eid, permission)
    if data.next_stage in {"APPROVED", "REPORTING", "ISSUED", "CLOSED"}:
        await audit.reviewer_separation(db, ctx, obj)
    if data.next_stage == "APPROVED" and obj.status not in service.APPROVED:
        raise HTTPException(409, "Engagement scope must be independently approved")
    deps = [service.dependency(obj)]
    if data.next_stage == "ISSUED":
        if not data.report_id:
            raise HTTPException(422, "Approved report required")
        report = await service.record(db, ctx, eid, data.report_id, "report")
        if report.body["ia_engagement_id"] != str(obj.id):
            raise HTTPException(422, "Report belongs to a different internal audit")
        deps.append(service.dependency(report))
    if data.next_stage == "CLOSED":
        deficiencies = (
            await db.scalars(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    AuditRecord.kind == "grc-deficiency",
                    AuditRecord.status.in_(service.APPROVED),
                )
            )
        ).all()
        actions = (
            await db.scalars(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    AuditRecord.kind == "grc-remediation",
                    AuditRecord.status.in_(service.APPROVED),
                )
            )
        ).all()
        closed = set(
            (
                await db.scalars(
                    select(AuditRecord.body["remediation_id"].astext).where(
                        AuditRecord.tenant_id == ctx.tenant_id,
                        AuditRecord.engagement_id == eid,
                        AuditRecord.kind == "grc-closure",
                        AuditRecord.status.in_(service.APPROVED),
                    )
                )
            ).all()
        )
        if deficiencies and (
            not actions
            or any(str(x.id) not in closed for x in actions)
            or any(
                not any(a.body["deficiency_id"] == str(d.id) for a in actions) for d in deficiencies
            )
        ):
            raise HTTPException(
                409, "Approved independent remediation closure required for all findings/actions"
            )
    return await service.run(
        db,
        ctx,
        eid,
        "ia-transition",
        data.model_dump(mode="json"),
        {"stage": data.next_stage, "rationale": data.rationale, "previous": current},
        deps,
        obj.id,
    )


async def dashboard(db, ctx, eid):
    await audit.engagement(db, ctx, eid, "grc.read")
    rows = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind.like("grc-%"),
            )
        )
    ).all()
    if await service.owner_scoped(db, ctx, eid):
        rows = [
            r
            for r in rows
            if r.body.get("owner_id") == str(ctx.user_id)
            or r.prepared_by == ctx.user_id
            or r.kind in {"grc-framework", "grc-policy", "grc-scoring"}
            and r.status in service.APPROVED
        ]
    approved = [x for x in rows if x.status in service.APPROVED]
    count: dict[str, int] = {}
    heat = []
    closed = {x.body["remediation_id"] for x in approved if x.kind == "grc-closure"}
    for row in rows:
        key = row.kind.removeprefix("grc-")
        count[key] = count.get(key, 0) + 1
    assessments = {}
    for row in sorted(approved, key=lambda x: (x.body.get("as_of", ""), x.updated_at, str(x.id))):
        if row.kind == "grc-assessment":
            assessments[row.body["risk_id"]] = row
    frozen_runs = (
        await db.scalars(
            select(GRCRun)
            .where(
                GRCRun.tenant_id == ctx.tenant_id,
                GRCRun.engagement_id == eid,
                GRCRun.kind == "assessment",
            )
            .order_by(GRCRun.created_at, GRCRun.id)
        )
    ).all()
    frozen_by_record = {str(x.record_id): x for x in frozen_runs}
    missing_calculations = 0
    for row in assessments.values():
        frozen = frozen_by_record.get(str(row.id))
        if not frozen or not any(
            d["id"] == str(row.id) and d["version"] == row.version for d in frozen.dependencies
        ):
            missing_calculations += 1
            continue
        scoring = next((x for x in approved if str(x.id) == row.body["scoring_id"]), None)
        if scoring:
            data = s.Assessment.model_validate(service.clean(row.body))
            result = frozen.results
            stale = any(
                not any(str(x.id) == dep["id"] and x.version == dep["version"] for x in approved)
                for dep in frozen.dependencies
            )
            heat.append(
                {
                    "id": str(row.id),
                    "risk_id": row.body["risk_id"],
                    "assessment_reference": row.reference,
                    "stale_source": stale,
                    "calculation_id": str(frozen.id),
                    "scoring_id": str(scoring.id),
                    "scoring_reference": scoring.reference,
                    "risk_reference": next(
                        (x.reference for x in approved if str(x.id) == row.body["risk_id"]),
                        row.body["risk_id"],
                    ),
                    "owner_id": row.body["owner_id"],
                    "inherent_likelihood": data.inherent_likelihood,
                    "inherent_impact": data.inherent_impact,
                    "residual_likelihood": data.residual_likelihood,
                    "residual_impact": data.residual_impact,
                    **result,
                }
            )
    overdue = [
        {
            "id": str(r.id),
            "reference": r.reference,
            "owner_id": r.body["owner_id"],
            "target_date": r.body["target_date"],
            "days_overdue": (date.today() - date.fromisoformat(r.body["target_date"])).days,
        }
        for r in approved
        if r.kind == "grc-remediation"
        and str(r.id) not in closed
        and r.body["target_date"] < str(date.today())
    ]
    return {
        "missing_assessment_calculations": missing_calculations,
        "counts": count,
        "heatmap": heat,
        "overdue_actions": overdue,
        "closed_actions": len(closed),
        "approved_workpapers": len(approved),
        "qualitative_risk_scores": True,
    }
