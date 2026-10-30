"""Filing readiness is independent of generated exports and calendar completion."""

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions

STAGES = [
    "not_started",
    "preparing",
    "under_review",
    "approved_for_submission",
    "submitted",
    "acknowledged",
]


async def transition(db, ctx, eid, rid, data, request_id):
    from app.modules.audit_execution.models import AuditRecord
    from app.modules.grc import schemas, service
    from app.modules.lineage.working_papers import require_current

    permission = (
        "compliance.approve" if data.stage == "approved_for_submission" else "compliance.manage"
    )
    eng = await audit.engagement(db, ctx, eid, permission, True)
    obj = await service.record(db, ctx, eid, rid, "obligation", approved=False)
    await db.scalar(
        select(AuditRecord)
        .where(AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.id == rid)
        .with_for_update()
    )
    await db.refresh(obj)
    if obj.version != data.version:
        raise HTTPException(409, "Filing version conflict; reload the concrete preview")
    if obj.status not in {"IN_PROGRESS", "REVISED", "APPROVED", "DRAFT", "REVIEW_NOTES"}:
        raise HTTPException(
            409, "Reopen or return the governed record before changing its filing stage"
        )
    await require_current(db, ctx, obj)
    payload = service.clean(obj.body)
    payload["filing_stage"] = data.stage
    if data.submission_evidence_id:
        payload["submission_evidence_id"] = str(data.submission_evidence_id)
    if data.acknowledgment_evidence_id:
        payload["acknowledgment_evidence_id"] = str(data.acknowledgment_evidence_id)
    if data.stage == obj.body.get("filing_stage", "not_started"):
        if payload != service.clean(obj.body):
            raise HTTPException(
                409,
                "Evidence changed without a filing-stage transition; prepare a reviewed revision",
            )
        return audit.serialize(obj)
    try:
        parsed = schemas.Obligation.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(
            422, "Filing prerequisites incomplete; review deadline, blockers and separate evidence"
        ) from exc
    body = await service.validate_body(db, ctx, eng, obj.kind, parsed, obj.id)
    obj.body = body
    # This endpoint records evidence and a human attestation; it never submits externally.
    obj.status = "APPROVED" if data.stage == "approved_for_submission" else "IN_PROGRESS"
    obj.version += 1
    await audit.revision(db, ctx, obj, request_id, "filing-stage-recorded")
    return audit.serialize(obj)


async def validate_transition(db, ctx, eng, data, record_id):
    previous = await audit.get_record(db, ctx, eng.id, record_id, "grc.read") if record_id else None
    old = previous.body.get("filing_stage", "not_started") if previous else "not_started"
    new = data.filing_stage
    for identifier in (data.submission_evidence_id, data.acknowledgment_evidence_id):
        if identifier:
            receipt = await audit.get_record(db, ctx, eng.id, identifier, "grc.read")
            if receipt.kind != "evidence":
                raise HTTPException(
                    422,
                    "Retained submission/acknowledgment documents required; generated workpapers are not receipts",
                )
    if data.reviewer_id:
        if data.reviewer_id == data.owner_id:
            raise HTTPException(422, "Filing owner and reviewer must be independent")
        from app.core.dependencies import Context

        await engagement_permissions(
            db, Context(data.reviewer_id, ctx.tenant_id, frozenset()), eng.id, "compliance.approve"
        )
    if data.deadline_rule:
        if not data.entity_facts or not data.fact_evidence_ids:
            raise HTTPException(
                422, "Verified entity facts and evidence required for a calculated obligation"
            )
        if data.deadline_rule.date_basis == "period_end":
            from app.db.models.platform import FinancialPeriod

            if data.obligation_period_end is not None:
                if data.deadline_rule.trigger != data.obligation_period_end:
                    raise HTTPException(
                        422, "Period-end rule trigger must equal the explicit obligation period end"
                    )
            else:
                # Historical unstructured obligations retain their original engagement basis.
                period = await db.get(FinancialPeriod, eng.period_id)
                if not period or data.deadline_rule.trigger != period.end_date:
                    raise HTTPException(
                        422, "Period-end rule trigger must equal engagement period end"
                    )
    if old != new:
        if STAGES.index(new) != STAGES.index(old) + 1 and new not in {"not_started", "preparing"}:
            raise HTTPException(409, "Filing stages must advance one step at a time")
        if new == "approved_for_submission":
            await engagement_permissions(db, ctx, eng.id, "compliance.approve")
            if (
                not previous
                or previous.status not in {"APPROVED", "LOCKED"}
                or previous.prepared_by == ctx.user_id
                or ctx.user_id != data.reviewer_id
            ):
                raise HTTPException(
                    409, "Independent designated reviewer must approve the reviewed filing version"
                )
            await audit.reviewer_separation(db, ctx, previous)
        if new in {"submitted", "acknowledged"} and (
            not previous or previous.status not in {"APPROVED", "LOCKED"}
        ):
            raise HTTPException(409, "Independently approved preceding filing stage required")
    if previous and old in {"approved_for_submission", "submitted", "acknowledged"}:
        protected = [
            # Jurisdiction and obligation criteria are part of the approved filing scope.
            # Reopening a record alone must not retain its approved submission stage.
            "owner_id",
            "entity_id",
            "module",
            "jurisdiction",
            "jurisdiction_scope",
            "obligation_period_start",
            "obligation_period_end",
            "source_url",
            "effective_from",
            "deadline_kind",
            "required_evidence",
            "compliance_assessment",
            "evidence_ids",
            "statutory_record_id",
            "deadline",
            "deadline_rule",
            "entity_facts",
            "readiness_evidence_ids",
            "rule_evidence_id",
            "calendar_evidence_id",
            "dmcc_audit_scope",
            "dmcc_guideline_evidence_id",
            "fact_evidence_ids",
            "extension_deadline",
            "extension_evidence_id",
            "reviewer_id",
        ]
        # First receipts may be added as the filing advances. Previously recorded
        # receipts cannot be replaced while preserving the approved filing stage.
        protected.extend(
            field
            for field in ("submission_evidence_id", "acknowledgment_evidence_id")
            if previous.body.get(field) is not None
        )
        payload = data.model_dump(mode="json")
        if any(previous.body.get(k) != payload.get(k) for k in protected) and new not in {
            "not_started",
            "preparing",
        }:
            raise HTTPException(
                409, "Approved filing inputs changed; return to preparing and require reassessment"
            )
