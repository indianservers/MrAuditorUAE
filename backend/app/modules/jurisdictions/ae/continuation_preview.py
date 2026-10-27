"""Recalculate eligible new draft inputs, never approved facts or source classifications."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.intelligence.models import IntelligenceEvent


async def refresh_draft(db, ctx, paper, request_id):
    body = paper.body.get("advanced_input") or {}
    identifier = body.get("use_case_id", 0)
    if identifier < 101 or paper.status not in {"IN_PROGRESS", "REVISED", "REVIEW_NOTES"}:
        return
    from app.modules.audit_execution.access import engagement_permissions
    from app.modules.enterprise_ai.business import case_scope
    from app.modules.enterprise_ai.security import digest, serial, source
    from app.modules.intelligence.service import append
    from app.modules.jurisdictions.ae.advanced import Schedule, calculate, contract_sha256
    from app.modules.jurisdictions.ae.use_cases import MANIFEST
    from app.modules.lineage.working_papers import require_current

    try:
        eng, case, _ = await case_scope(db, ctx, paper.engagement_id, identifier, "ai.workflow.run")
        await engagement_permissions(db, ctx, eng.id, "audit.testing.execute")
        await engagement_permissions(db, ctx, eng.id, "accounting.read")
        for engine, permission in {
            "E04": "vat.calculate",
            "E05": "tax.computation.prepare",
            "E06": "tax.computation.prepare",
            "E07": "tp.calculate",
            "E08": "dmtt.calculate",
            "E09": "ifrs.calculation.execute",
        }.items():
            if engine in case.engines:
                await engagement_permissions(db, ctx, eng.id, permission)
        await require_current(db, ctx, paper)
        data = Schedule.model_validate(body)
        from app.db.models.platform import FinancialPeriod

        period = await db.get(FinancialPeriod, eng.period_id) if eng.period_id else None
        if (
            not period
            or not period.start_date <= data.period_start <= data.period_end <= period.end_date
        ):
            return
        refs = {
            str(data.policy.source_id),
            *(r["evidence_id"] for r in data.rows),
            *(str(v) for r in data.rows for k, v in r.items() if k.endswith("_source_id")),
        }
        refs.update(
            str(v)
            for row in data.rows
            for key in ("supporting_sources", "contrary_sources")
            for v in row.get(key, [])
        )
        dependencies = [{"type": "record", "id": str(paper.id), "version": paper.version}]
        for rid in refs:
            proof = await source(db, ctx, eng.id, uuid.UUID(rid))
            dependencies.append({"type": "record", "id": str(proof.id), "version": proof.version})
        from app.modules.jurisdictions.ae.continuation_controls import validate_parameters

        await validate_parameters(db, ctx, eng.id, data)
        output = calculate(data)
    except (ValueError, ArithmeticError):
        return
    except HTTPException as exc:
        if exc.status_code in {403, 404, 409, 422}:
            return
        raise
    key = f"draft-preview:{paper.id}:{paper.version}"
    if await db.scalar(
        select(IntelligenceEvent.id).where(
            IntelligenceEvent.tenant_id == ctx.tenant_id,
            IntelligenceEvent.engagement_id == eng.id,
            IntelligenceEvent.kind == "business-action",
            IntelligenceEvent.body["idempotency_key"].astext == key,
        )
    ):
        return
    await append(
        db,
        ctx,
        eng,
        "business-action",
        {
            "use_case_id": identifier,
            "action": "draft-auto-recalculation",
            "idempotency_key": key,
            "request_sha256": digest(body),
            "case_catalogue_sha256": digest(MANIFEST),
            "advanced_contract_sha256": contract_sha256(),
            "output": {
                "results": serial(output),
                "input_record_id": str(paper.id),
                "input_version": paper.version,
                "input_title": paper.title,
                "provisional": True,
                "review_status": "UNVERIFIED",
                "publication": "DRAFT_NOT_APPROVED_NOT_POSTED_NOT_SENT",
            },
            "execution_mode": "deterministic_draft_preview",
            "review_status": "UNVERIFIED",
            "contributors": sorted({str(ctx.user_id), str(paper.prepared_by)}),
            "professional_conclusion": None,
        },
        dependencies,
        request_id,
    )
