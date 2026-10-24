import uuid
from contextvars import ContextVar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import Text, cast, func, select

from app.db.models.platform import Engagement, LegalEntity, Membership, User
from app.modules.accounting.models import (
    Finding,
    ImportSnapshot,
    JournalLine,
    SamplingItem,
    SamplingRun,
)
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.catalogue import APPROVE, PREPARE, TRANSITIONS
from app.modules.audit_execution.models import (
    AuditAccess,
    AuditRecord,
    AuditRevision,
    EngagementPolicy,
    EvidenceVersion,
    ReviewDecision,
)
from app.modules.audit_execution.schemas import BODIES, Materiality
from app.modules.audit_log.service import record


def serialize(obj):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder({c.name: getattr(obj, c.name) for c in obj.__table__.columns})


async def engagement(db, ctx, identifier, permission="audit.read", mutable=False, *, lock=True):
    statement = select(Engagement).where(
        Engagement.tenant_id == ctx.tenant_id, Engagement.id == identifier
    )
    if lock or mutable:
        statement = statement.with_for_update()
    obj = await db.scalar(statement)
    if not obj:
        raise HTTPException(404, "Engagement not found")
    await engagement_permissions(db, ctx, identifier, permission)
    from app.modules.jurisdictions.service import require_capability

    if mutable:
        await require_capability(db, ctx, obj, permission)
    if mutable and obj.status.upper() in {"COMPLETED", "ARCHIVED", "CANCELLED"}:
        raise HTTPException(409, "Engagement is read-only")
    return obj


async def policy(db, ctx, eid):
    p = await db.scalar(
        select(EngagementPolicy).where(
            EngagementPolicy.tenant_id == ctx.tenant_id, EngagementPolicy.engagement_id == eid
        )
    )
    if p is None:
        p = EngagementPolicy(tenant_id=ctx.tenant_id, created_by=ctx.user_id, engagement_id=eid)
        db.add(p)
        await db.flush()
    return p


async def _get_record(db, ctx, eid, rid, permission="audit.read", mutable=False, *, lock=True):
    if permission == "audit.read" and "audit.read" not in ctx.permissions:
        scoped_kind = await db.scalar(
            select(AuditRecord.kind).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.id == rid,
            )
        )
        if scoped_kind and scoped_kind.startswith("grc-"):
            permission = "grc.read"
    await engagement(db, ctx, eid, permission, mutable, lock=lock)
    statement = select(AuditRecord).where(
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.id == rid,
    )
    obj = await db.scalar(statement.with_for_update() if lock or mutable else statement)
    if not obj:
        raise HTTPException(404, "Audit record not found")
    if obj.kind.startswith("ifrs-"):
        await engagement_permissions(db, ctx, eid, "ifrs.read")
    if obj.kind.startswith("tax-"):
        await engagement_permissions(db, ctx, eid, "tax.profile.read")
    if obj.kind.startswith("vat-"):
        await engagement_permissions(db, ctx, eid, "vat.read")
    if obj.kind.startswith("tp-"):
        await engagement_permissions(db, ctx, eid, "tp.read")
    if obj.kind.startswith("dmtt-"):
        await engagement_permissions(db, ctx, eid, "dmtt.read")
    if obj.kind.startswith("grc-"):
        from app.modules.grc.service import authorize_record

        await authorize_record(db, ctx, obj)
    return obj


_source_access_path: ContextVar[frozenset] = ContextVar(
    "audit_source_access_path", default=frozenset()
)


async def get_record(db, ctx, eid, rid, permission="audit.read", mutable=False, *, lock=True):
    """Generated source-linked papers retain specialist permissions on every read."""
    key = (ctx.tenant_id, eid, rid)
    path = _source_access_path.get()
    if key in path or len(path) >= 100:
        raise HTTPException(409, "Source authorization cycle/depth limit")
    token = _source_access_path.set(path | {key})
    try:
        obj = await _get_record(db, ctx, eid, rid, permission, mutable, lock=lock)
        if obj.kind == "working-papers" and obj.body.get("advanced_input"):
            from app.modules.enterprise_ai.business import advanced_read_permissions
            from app.modules.jurisdictions.ae.use_cases import CASES
            await advanced_read_permissions(db, ctx, eid, CASES[obj.body["advanced_input"]["use_case_id"]])
        if obj.kind == "working-papers" and obj.body.get("inherit_source_permissions"):
            for reference in obj.body.get("sources", []):
                identifier = uuid.UUID(str(reference["id"]))
                if reference["kind"] in {"record", "finding"}:
                    await get_record(db, ctx, eid, identifier, lock=False)
                elif reference["kind"] == "intelligence":
                    from app.modules.intelligence.service import event

                    await event(db, ctx, eid, identifier)
                elif reference["kind"] in {"journal", "snapshot", "sample"}:
                    await engagement_permissions(db, ctx, eid, "accounting.read")
        return obj
    finally:
        _source_access_path.reset(token)


def materiality(data: Materiality):
    overall = (data.benchmark_amount * data.selected_percentage / 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        "overall": str(overall),
        "performance": str(
            (overall * data.performance_percentage / 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        ),
        "clearly_trivial": str(
            (overall * data.trivial_percentage / 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        ),
        "formula": "overall = benchmark_amount * selected_percentage / 100; performance and trivial = overall * selected percentage / 100",
        "currency": "engagement functional currency",
        "percentages_prescribed_by_isa": False,
    }


async def source_record(db, ctx, eng, source):
    if source.kind == "ml":
        from app.modules.lineage.freshness import require_ml_current
        from app.modules.ml.service import get

        obj = await get(db, ctx, source.id)
        if obj.engagement_id != eng.id or obj.kind not in {"inference", "feedback"}:
            raise HTTPException(422, "Scoped ML prediction or reviewed feedback required")
        await require_ml_current(db, ctx, obj)
        return obj
    if source.kind == "intelligence":
        from app.modules.intelligence.service import event

        return await event(db, ctx, eng.id, source.id, True)
    models: dict[str, Any] = {
        "record": AuditRecord,
        "finding": Finding,
        "journal": JournalLine,
        "snapshot": ImportSnapshot,
        "sample": SamplingRun,
    }
    model = models[source.kind]
    obj = await db.scalar(
        select(model).where(model.tenant_id == ctx.tenant_id, model.id == source.id)
    )
    if not obj:
        raise HTTPException(422, "Source does not exist in tenant")
    if source.kind == "record":
        valid = obj.engagement_id == eng.id
    else:
        valid = obj.entity_id == eng.entity_id and obj.period_id == eng.period_id
    if not valid:
        raise HTTPException(422, "Source outside engagement scope")
    if source.kind == "record" and obj.kind.startswith("ifrs-"):
        await engagement_permissions(db, ctx, eng.id, "ifrs.read")
    if source.kind == "record" and obj.status == "ARCHIVED":
        raise HTTPException(409, "Archived draft cannot be linked as current evidence")
    if source.kind == "record" and obj.kind.startswith("tax-"):
        await engagement_permissions(db, ctx, eng.id, "tax.profile.read")
    if source.kind == "record" and obj.kind.startswith("vat-"):
        await engagement_permissions(db, ctx, eng.id, "vat.read")
    if source.kind == "record" and obj.kind.startswith("tp-"):
        await engagement_permissions(db, ctx, eng.id, "tp.read")
    if source.kind == "record" and obj.kind.startswith("grc-"):
        from app.modules.grc.service import authorize_record

        await authorize_record(db, ctx, obj)
    if source.kind == "record" and obj.kind.startswith("dmtt-"):
        await engagement_permissions(db, ctx, eng.id, "dmtt.read")
    return obj


async def validate_body(db, ctx, eng, kind, body, record_id=None):
    if kind not in BODIES or kind == "ai":
        raise HTTPException(422, "Unsupported editable audit kind")
    try:
        data: Any = BODIES[kind].model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            422,
            "Invalid audit fields: "
            + "; ".join(".".join(map(str, e["loc"])) for e in exc.errors()),
        ) from None
    if kind == "working-papers" and record_id:
        from app.modules.lineage.source_links import acyclic_paper_links
        await acyclic_paper_links(db, ctx, eng.id, record_id, data.sources)
    if data.owner_id:
        owner = await db.scalar(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == ctx.tenant_id,
                Membership.user_id == data.owner_id,
                Membership.status == "active",
                User.status == "active",
            )
        )
        if not owner:
            raise HTTPException(422, "Owner must be active firm member")
        from app.core.dependencies import Context

        await engagement_permissions(
            db,
            Context(data.owner_id, ctx.tenant_id, frozenset()),
            eng.id,
            "grc.read" if kind.startswith("grc-") else "audit.read",
        )
    for source in data.sources:
        await source_record(db, ctx, eng, source)
    if kind.startswith("grc-"):
        from app.modules.grc.service import validate_body as validate_grc

        try:
            return await validate_grc(db, ctx, eng, kind, data, record_id)
        except (ValueError, ArithmeticError) as exc:
            raise HTTPException(422, str(exc)) from None
    if kind.startswith("ifrs-"):
        from app.modules.ifrs.service import validate_body as validate_ifrs

        return await validate_ifrs(db, ctx, eng, kind, data)
    if kind.startswith("tax-"):
        from app.modules.tax.service import validate_body as validate_tax

        return await validate_tax(db, ctx, eng, kind, data, record_id)
    if kind.startswith("vat-"):
        from app.modules.vat.service import validate_body as validate_vat

        return await validate_vat(db, ctx, eng, kind, data, record_id)
    if kind.startswith("dmtt-"):
        from app.modules.dmtt.service import validate_body as validate_dmtt

        return await validate_dmtt(db, ctx, eng, kind, data, record_id)
    if kind.startswith("tp-"):
        from app.modules.tp.service import validate_body as validate_tp

        try:
            return await validate_tp(db, ctx, eng, kind, data, record_id)
        except (ValueError, ArithmeticError) as exc:
            raise HTTPException(422, str(exc)) from None
    if kind == "independence" and data.expires_on <= date.today():
        raise HTTPException(422, "Declaration expiry must be in the future")
    if kind == "testing":
        from app.modules.audit_execution.schemas import Source

        sample = await source_record(db, ctx, eng, Source(kind="sample", id=data.sample_id))
        if data.evaluation_basis == "statistical" or data.projected_misstatement is not None:
            raise HTTPException(
                422,
                "Statistical projection/evaluation is not implemented; do not project a targeted or unevaluated selection",
            )
        if data.procedure_id:
            procedure = await get_record(db, ctx, eng.id, data.procedure_id)
            if procedure.kind != "procedures" or procedure.status not in {"APPROVED", "LOCKED"}:
                raise HTTPException(409, "Approved scoped audit procedure required")
            if not data.steps_performed.strip():
                raise HTTPException(422, "Record the steps actually performed")
    if kind == "procedures":
        for identifier in data.risk_ids:
            risk = await get_record(db, ctx, eng.id, identifier)
            if risk.kind != "risks":
                raise HTTPException(422, "Procedure risk link must reference an engagement risk")
    if kind == "findings" and data.correction_status == "corrected":
        if not data.correction_evidence_id:
            raise HTTPException(422, "Corrected misstatement requires correction evidence")
        correction = await get_record(db, ctx, eng.id, data.correction_evidence_id)
        if correction.status not in {"APPROVED", "LOCKED"}:
            raise HTTPException(409, "Correction evidence must be independently reviewed")
    if kind == "testing":
        selected = {
            str(i)
            for i in (
                await db.scalars(
                    select(SamplingItem.line_id).where(
                        SamplingItem.tenant_id == ctx.tenant_id, SamplingItem.run_id == sample.id
                    )
                )
            ).all()
        }
        if any(str(i.line_id) not in selected for i in data.results):
            raise HTTPException(422, "Test result is outside the selected sample")
        if len({i.line_id for i in data.results}) != len(data.results):
            raise HTTPException(422, "Duplicate test item results")
        for item in data.results:
            for identifier in item.evidence_ids:
                evidence = await get_record(db, ctx, eng.id, identifier)
                if evidence.kind != "evidence":
                    raise HTTPException(422, "Test item evidence reference required")
    if kind == "review-notes":
        target = await get_record(db, ctx, eng.id, data.target_id)
        if target.status in {"LOCKED"}:
            raise HTTPException(409, "Reopen approved paper before raising a new note")
    if kind == "requests":
        entity = await db.get(LegalEntity, eng.entity_id)
        if data.client_id != entity.client_id:
            raise HTTPException(422, "Request client differs from engagement client")
        for identifier in data.evidence_ids:
            evidence = await get_record(db, ctx, eng.id, identifier)
            if evidence.kind != "evidence":
                raise HTTPException(422, "Evidence record required")
    result = data.model_dump(mode="json")
    if kind == "independence":
        result["assessment_flags"] = [
            name
            for name in ["financial_interests", "relationships", "other_services"]
            if getattr(data, name)
        ]
    if kind == "materiality":
        result["calculation"] = materiality(data)
    return result


async def revision(db, ctx, obj, request_id, action):
    await db.flush()
    await db.refresh(obj)
    p = await db.scalar(
        select(EngagementPolicy).where(
            EngagementPolicy.tenant_id == ctx.tenant_id,
            EngagementPolicy.engagement_id == obj.engagement_id,
        )
    )
    if p and p.methodology.get("quality_review_decision"):
        p.methodology = {k: v for k, v in p.methodology.items() if k != "quality_review_decision"}
        record(db, ctx, "audit.quality.invalidated", obj.engagement_id, request_id)
    from app.modules.lineage.working_papers import capture

    previous = await db.scalar(
        select(AuditRevision)
        .where(
            AuditRevision.tenant_id == ctx.tenant_id,
            AuditRevision.record_id == obj.id,
            AuditRevision.version < obj.version,
        )
        .order_by(AuditRevision.version.desc())
        .limit(1)
    )
    receipts = (
        await capture(db, ctx, obj)
        if action in {"created", "updated", "restored"} or previous is None
        else previous.snapshot.get("dependency_receipts")
    )
    snapshot = {**serialize(obj), "country_package": None}
    from app.modules.jurisdictions.service import binding

    eng = await db.get(Engagement, obj.engagement_id)
    country = await binding(db, ctx, eng)
    from app.modules.jurisdictions.workspace import resolved

    _, reporting_context = await resolved(db, ctx, eng)
    snapshot["reporting_context"] = {
        key: reporting_context[key]
        for key in ["version", "country", "framework", "as_of", "entity_type"]
    }
    snapshot["country_package"] = {
        "country": country.country,
        "version": country.package_version,
        "sha256": country.package_sha256,
    }
    if receipts is not None:
        snapshot["dependency_receipts"] = receipts
    from app.core.operations_contracts import receipt as execution_receipt

    snapshot["operations_execution"] = await execution_receipt(
        db,
        ctx,
        kind=obj.kind,
        eng=eng,
        dependencies=receipts or (),
        body={
            "parameters": {"record_id": str(obj.id), "record_version": obj.version},
            "review_status": obj.status,
        },
        mode="unavailable",
        metadata_only=True,
    )
    db.add(
        AuditRevision(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            record_id=obj.id,
            version=obj.version,
            snapshot=snapshot,
        )
    )
    record(
        db,
        ctx,
        "audit." + action,
        obj.id,
        request_id,
        {"engagement_id": str(obj.engagement_id), "kind": obj.kind, "version": obj.version},
    )
    await db.flush()
    from app.modules.jurisdictions.ae.continuation_preview import refresh_draft
    await refresh_draft(db, ctx, obj, request_id)
    if action != "created":
        from app.modules.jurisdictions.ae.advanced_lineage import source_changed
        await source_changed(db, ctx, obj, request_id)


async def create(db, ctx, eid, kind, data, request_id):
    if kind not in PREPARE:
        raise HTTPException(404, "Audit area not found")
    eng = await engagement(db, ctx, eid, PREPARE[kind], True)
    body = await validate_body(db, ctx, eng, kind, data.body)
    obj = AuditRecord(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        kind=kind,
        reference=data.reference,
        title=data.title,
        body=body,
        prepared_by=ctx.user_id,
        status="OPEN" if kind == "findings" else "DRAFT" if kind == "requests" else "IN_PROGRESS",
    )
    db.add(obj)
    await revision(db, ctx, obj, request_id, "created")
    return serialize(obj)


async def update(db, ctx, eid, rid, data, request_id):
    obj = await get_record(db, ctx, eid, rid, mutable=True)
    if obj.kind == "working-papers" and obj.body.get("factual_findings_only"):
        data.body["factual_findings_only"] = True
    if obj.kind == "working-papers" and obj.body.get("advanced_input"):
        proposed_case = (data.body.get("advanced_input") or {}).get("use_case_id")
        if proposed_case != obj.body["advanced_input"]["use_case_id"]:
            raise HTTPException(409, "Structured schedule classification cannot be removed or reassigned; prepare a new reviewed paper")
    if obj.kind == "working-papers" and obj.body.get("inherit_source_permissions"):
        previous = {(s["kind"], str(s["id"])) for s in obj.body.get("sources", [])}
        proposed = {(s["kind"], str(s["id"])) for s in data.body.get("sources", [])}
        if not previous <= proposed:
            raise HTTPException(
                409,
                "Generated workpaper source links cannot be removed through a generic edit; prepare a separately reviewed replacement",
            )
        data.body["inherit_source_permissions"] = True
    if obj.kind == "tp-ai":
        raise HTTPException(409, "TP AI suggestions are immutable; use the TP decision workflow")
    eng = await engagement(db, ctx, eid, PREPARE[obj.kind], True)
    if obj.version != data.version:
        raise HTTPException(409, "Record version conflict; reload before saving")
    if obj.status not in {
        "IN_PROGRESS",
        "REVISED",
        "REVIEW_NOTES",
        "OPEN",
        "DRAFT",
        "MORE_INFORMATION_REQUIRED",
        "UNDER_REVIEW",
        "MANAGEMENT_RESPONSE_PENDING",
        "REMEDIATION_PENDING",
    }:
        raise HTTPException(409, "Record must be returned or reopened before editing")
    if obj.kind == "independence" and obj.prepared_by != ctx.user_id:
        raise HTTPException(403, "Only the declarant can revise their declaration")
    obj.body = await validate_body(db, ctx, eng, obj.kind, data.body, obj.id)
    obj.title, obj.reference = data.title, data.reference
    # Anyone materially editing a paper becomes a preparer; immutable versions retain all editors.
    obj.prepared_by = ctx.user_id
    if obj.status == "REVIEW_NOTES":
        obj.status = "REVISED"
    obj.version += 1
    await revision(db, ctx, obj, request_id, "updated")
    return serialize(obj)


async def reviewer_separation(db, ctx, obj):
    preparers = set(
        (
            await db.scalars(
                select(AuditRevision.created_by).where(
                    AuditRevision.record_id == obj.id, AuditRevision.tenant_id == ctx.tenant_id
                )
            )
        ).all()
    )
    # Submission/note actions also produce revisions; actual body editors are preserved in snapshots.
    versions = (
        await db.scalars(
            select(AuditRevision).where(
                AuditRevision.record_id == obj.id, AuditRevision.tenant_id == ctx.tenant_id
            )
        )
    ).all()
    preparers = {uuid.UUID(v.snapshot["prepared_by"]) for v in versions}
    if ctx.user_id == obj.prepared_by or ctx.user_id in preparers:
        raise HTTPException(403, "Preparers cannot approve or review their own work")


async def draft_lifecycle(db, ctx, obj, data, request_id):
    if len(data.comments.strip()) < 10:
        raise HTTPException(422, "A lifecycle reason of at least ten characters is required")
    if obj.kind not in {
        "working-papers",
        "risks",
        "vat-invoice",
        "requests",
        "planning",
        "programs",
        "procedures",
    }:
        raise HTTPException(409, "This record requires its governed workflow, not draft archival")
    await engagement_permissions(db, ctx, obj.engagement_id, PREPARE[obj.kind])
    if data.action == "archive":
        if obj.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(409, "Only unused unapproved drafts may be archived")
        reviewed = await db.scalar(
            select(AuditRevision.id)
            .where(
                AuditRevision.record_id == obj.id,
                AuditRevision.snapshot["status"].astext.in_(["APPROVED", "LOCKED"]),
            )
            .limit(1)
        )
        referenced = await db.scalar(
            select(AuditRecord.id)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == obj.engagement_id,
                AuditRecord.id != obj.id,
                AuditRecord.status != "ARCHIVED",
                cast(AuditRecord.body, Text).contains(str(obj.id), autoescape=True),
            )
            .limit(1)
        )
        if reviewed or referenced:
            raise HTTPException(
                409, "Reviewed or referenced records must be retained; supersede through review"
            )
        obj.status = "ARCHIVED"
    else:
        if obj.status != "ARCHIVED":
            raise HTTPException(409, "Only archived drafts can be restored")
        prior = await db.scalar(
            select(AuditRevision)
            .where(
                AuditRevision.record_id == obj.id,
                AuditRevision.snapshot["status"].astext != "ARCHIVED",
            )
            .order_by(AuditRevision.version.desc())
            .limit(1)
        )
        if not prior or prior.snapshot["status"] not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(409, "Restoration requires an original editable draft")
        eng = await engagement(db, ctx, obj.engagement_id, PREPARE[obj.kind], True)
        await validate_body(
            db,
            ctx,
            eng,
            obj.kind,
            {k: v for k, v in obj.body.items() if k in BODIES[obj.kind].model_fields},
            obj.id,
        )
        obj.status = prior.snapshot["status"]
    obj.version += 1
    await revision(db, ctx, obj, request_id, data.action + "d")
    record(
        db,
        ctx,
        "audit.lifecycle",
        obj.id,
        request_id,
        {"action": data.action, "reason": data.comments, "version": obj.version},
    )
    return serialize(obj)


async def action(db, ctx, eid, rid, data, request_id):
    obj = await get_record(db, ctx, eid, rid, mutable=True)
    if obj.kind == "tp-ai":
        raise HTTPException(409, "Use the independently grounded TP AI decision workflow")
    if obj.version != data.version:
        raise HTTPException(409, "Record version conflict")
    if data.action in {"archive", "restore"}:
        return await draft_lifecycle(db, ctx, obj, data, request_id)
    prior = obj.status
    if obj.kind.startswith("ifrs-"):
        from app.modules.ifrs.service import validate_action

        await validate_action(db, ctx, eid, obj, data.action)
    if obj.kind.startswith("tax-"):
        from app.modules.tax.service import validate_action as tax_validate_action

        await tax_validate_action(db, ctx, eid, obj, data.action)
    if obj.kind.startswith("vat-"):
        from app.modules.vat.service import validate_action as vat_validate_action

        await vat_validate_action(db, ctx, eid, obj, data.action)
    if obj.kind.startswith("tp-"):
        from app.modules.tp.service import validate_action as tp_validate_action

        await tp_validate_action(db, ctx, eid, obj, data.action)
    if obj.kind.startswith("dmtt-"):
        from app.modules.dmtt.service import validate_action as dmtt_validate_action

        await dmtt_validate_action(db, ctx, eid, obj, data.action)
    if obj.kind.startswith("grc-"):
        from app.modules.grc.service import validate_action as grc_validate_action

        await grc_validate_action(db, ctx, eid, obj, data.action)
    p = await policy(db, ctx, eid)
    review = data.action in {"approve", "return", "reopen", "lock"}
    needed = (
        APPROVE.get(obj.kind, "workingpaper.review")
        if review
        else "workingpaper.create"
        if obj.kind == "review-notes" and data.action == "resolve"
        else PREPARE[obj.kind]
    )
    _, roles = await engagement_permissions(db, ctx, eid, needed)
    if review:
        await reviewer_separation(db, ctx, obj)
    if data.action in {"approve", "lock"}:
        from app.modules.lineage.working_papers import require_current

        await require_current(db, ctx, obj)
        if obj.kind == "procedures":
            for identifier in obj.body.get("risk_ids", []):
                risk = await get_record(db, ctx, eid, uuid.UUID(identifier))
                if risk.status not in {"APPROVED", "LOCKED"}:
                    raise HTTPException(
                        409, "Approve linked risks before approving their response procedure"
                    )
        if obj.kind == "testing" and obj.body.get("procedure_id"):
            procedure = await get_record(db, ctx, eid, uuid.UUID(obj.body["procedure_id"]))
            if procedure.status not in {"APPROVED", "LOCKED"}:
                raise HTTPException(409, "Linked procedure is no longer approved")
    if data.action == "submit":
        if obj.status not in {"IN_PROGRESS", "REVISED", "REVIEW_NOTES"}:
            raise HTTPException(409, "Only prepared work can be submitted")
        if obj.kind == "evidence":
            version = await db.scalar(
                select(EvidenceVersion)
                .where(EvidenceVersion.record_id == obj.id)
                .order_by(EvidenceVersion.number.desc())
                .limit(1)
            )
            if not version or version.scan_status != "CLEAN":
                raise HTTPException(409, "Clean scanned evidence version required")
        obj.status = "REVIEW_REQUIRED"
        obj.body = {
            **obj.body,
            "review_stage": 0,
            "review_cycle": obj.version,
            "review_approvers": [],
        }
    elif data.action == "return" and obj.status in {"REVIEW_REQUIRED", "APPROVED"}:
        obj.status = "REVIEW_NOTES"
    elif data.action == "approve" and obj.status == "REVIEW_REQUIRED":
        if obj.kind == "testing":
            selected = {
                str(i)
                for i in (
                    await db.scalars(
                        select(SamplingItem.line_id).where(
                            SamplingItem.tenant_id == ctx.tenant_id,
                            SamplingItem.run_id == uuid.UUID(obj.body["sample_id"]),
                        )
                    )
                ).all()
            }
            tested = {
                i["line_id"]
                for i in obj.body.get("results", [])
                if i["outcome"] in {"passed", "exception"} and i["evidence_ids"]
            }
            if not selected or selected != tested:
                raise HTTPException(
                    409, "Every selected item requires a documented outcome and supporting evidence"
                )
            for item in obj.body["results"]:
                for identifier in item["evidence_ids"]:
                    evidence = await get_record(db, ctx, eid, uuid.UUID(identifier))
                    if evidence.kind != "evidence" or evidence.status not in {"APPROVED", "LOCKED"}:
                        raise HTTPException(409, "Test item evidence must be reviewed")
        stage = obj.body.get("review_stage", 0)
        chain = (
            p.review_chain
            if obj.kind in {"working-papers", "planning", "programs", "testing", "ifrs-financials"}
            else []
        )
        review_roles = set(roles)
        if obj.kind in {"tp-study", "tp-judgment", "tp-localfile", "tp-masterfile", "tp-release"}:
            chain = ["TP Manager", "Tax Partner"]
            if "Tax Manager" in roles or "Transfer Pricing Director" in roles:
                review_roles.add("TP Manager")
            if "Chartered Accountant" in roles or "Transfer Pricing Director" in roles:
                review_roles.add("Tax Partner")
        if obj.kind in {"tax-computation", "tax-return", "vat-return"}:
            chain = ["Tax Manager", "Tax Partner"]
            if "VAT Manager" in roles:
                review_roles.add("Tax Manager")
            if "Tax Director" in roles:
                review_roles.update({"Tax Manager", "Tax Partner"})
            if "Chartered Accountant" in roles:
                review_roles.add("Tax Partner")
        if obj.kind == "ifrs-financials":
            if "Financial Reporting Manager" in roles:
                review_roles.add("Audit Manager")
            if "Chartered Accountant" in roles:
                review_roles.add("Audit Partner")
        if chain and chain[stage] not in review_roles:
            raise HTTPException(403, "Current review stage requires " + chain[stage])
        if str(ctx.user_id) in obj.body.get("review_approvers", []):
            raise HTTPException(403, "Each review stage requires a different reviewer")
        if obj.kind == "independence":
            if date.fromisoformat(obj.body["expires_on"]) <= date.today():
                raise HTTPException(409, "Independence declaration expired")
        notes = await db.scalar(
            select(func.count())
            .select_from(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "review-notes",
                AuditRecord.body["target_id"].astext == str(obj.id),
                AuditRecord.status != "CLOSED",
            )
        )
        if notes:
            raise HTTPException(409, "Open review notes must be cleared by reviewer")
        obj.body = {
            **obj.body,
            "review_stage": stage + 1,
            "review_approvers": [*obj.body.get("review_approvers", []), str(ctx.user_id)],
        }
        obj.status = "APPROVED" if not chain or stage + 1 >= len(chain) else "REVIEW_REQUIRED"
    elif data.action == "lock" and obj.status == "APPROVED":
        obj.status = "LOCKED"
    elif data.action == "reopen" and obj.status in {"APPROVED", "LOCKED"}:
        obj.status = "REVIEW_NOTES"
        obj.body = {**obj.body, "review_stage": 0}
    elif obj.kind == "review-notes" and data.action == "resolve" and obj.status != "CLOSED":
        obj.status = "RESOLVED"
    elif obj.kind == "review-notes" and data.action == "clear" and obj.status == "RESOLVED":
        if ctx.user_id != uuid.UUID(obj.body["assigned_reviewer"]):
            raise HTTPException(403, "Assigned reviewer must clear the note")
        obj.status = "CLOSED"
    elif obj.kind in {"findings", "requests"}:
        flows = (
            {
                "OPEN": {"UNDER_REVIEW"},
                "UNDER_REVIEW": {
                    "MANAGEMENT_RESPONSE_PENDING",
                    "REMEDIATION_PENDING",
                    "RESOLVED",
                    "ACCEPTED_UNRESOLVED",
                },
                "MANAGEMENT_RESPONSE_PENDING": {"UNDER_REVIEW"},
                "REMEDIATION_PENDING": {"UNDER_REVIEW"},
                "RESOLVED": {"CLOSED"},
                "ACCEPTED_UNRESOLVED": {"CLOSED"},
            }
            if obj.kind == "findings"
            else {
                "DRAFT": {"SENT"},
                "SENT": {"VIEWED"},
                "VIEWED": {"RESPONDED"},
                "RESPONDED": {"ACCEPTED", "MORE_INFORMATION_REQUIRED"},
                "MORE_INFORMATION_REQUIRED": {"RESPONDED"},
                "ACCEPTED": {"CLOSED"},
            }
        )
        if data.action not in flows.get(obj.status, set()):
            raise HTTPException(409, "Invalid workflow transition")
        if data.action in {"RESOLVED", "ACCEPTED_UNRESOLVED", "CLOSED", "ACCEPTED"}:
            await engagement_permissions(db, ctx, eid, APPROVE[obj.kind])
            await reviewer_separation(db, ctx, obj)
        obj.status = data.action
    else:
        raise HTTPException(409, "Invalid record action for current state")
    if obj.kind == "tp-release" and obj.status == "APPROVED":
        from app.modules.tp.publication import publish

        await publish(db, ctx, eid, obj)
    db.add(
        ReviewDecision(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            record_id=obj.id,
            version=obj.version,
            stage=obj.body.get("review_stage", 0),
            decision=data.action,
            comments=data.comments,
            prior_status=prior,
        )
    )
    obj.version += 1
    await revision(db, ctx, obj, request_id, data.action)
    if obj.kind.startswith("tax-"):
        from app.modules.tax.service import after_action

        await after_action(db, ctx, eid, obj, data.action)
    return serialize(obj)


async def completion(db, ctx, eid):
    await engagement(db, ctx, eid)
    rows = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.engagement_id == eid
            )
        )
    ).all()
    approved = {r.kind for r in rows if r.status in {"APPROVED", "LOCKED"}}
    checks = []
    # Approved consultation inputs can still contain unresolved release blockers.
    for paper in rows:
        if (paper.body.get("advanced_input") or {}).get("use_case_id") not in {150,190} or paper.status == "ARCHIVED":
            continue
        from app.modules.jurisdictions.ae.advanced import Schedule, calculate
        from app.modules.lineage.working_papers import freshness
        current_input = await freshness(db, ctx, paper) == "CURRENT"
        try:
            assessment = calculate(Schedule.model_validate(paper.body["advanced_input"]))
            blocked = any(row["metrics"]["release_blocked" if assessment["use_case_id"]==150 else "finalization_blocked"] for row in assessment["rows"])
        except (ValueError, ArithmeticError):
            blocked = True
        checks.append({"code":"quality_consultation_"+str(paper.id),"passed":current_input and paper.status in {"APPROVED","LOCKED"} and not blocked,"description":"Current independently approved consultation with no outstanding required quality release blockers","record_ids":[str(paper.id)]})
    for kind in [
        "acceptance",
        "planning",
        "materiality",
        "risks",
        "programs",
        "procedures",
        "testing",
        "working-papers",
        "completion",
    ]:
        checks.append(
            {
                "code": kind,
                "passed": kind in approved,
                "description": "Reviewed " + kind,
                "record_ids": [str(r.id) for r in rows if r.kind == kind],
            }
        )
    for kind in [
        "acceptance",
        "planning",
        "materiality",
        "risks",
        "programs",
        "procedures",
        "testing",
        "working-papers",
        "evidence",
        "review-notes",
        "findings",
        "completion",
    ]:
        outstanding = [
            r for r in rows if r.kind == kind and r.status not in {"APPROVED", "LOCKED", "CLOSED"}
        ]
        checks.append(
            {
                "code": "outstanding_" + kind,
                "passed": not outstanding,
                "record_ids": [str(r.id) for r in outstanding],
            }
        )
    members = (
        await db.scalars(
            select(AuditAccess).where(
                AuditAccess.tenant_id == ctx.tenant_id,
                AuditAccess.engagement_id == eid,
                AuditAccess.active.is_(True),
            )
        )
    ).all()
    member_users = set(
        (
            await db.scalars(
                select(Membership.user_id).where(
                    Membership.id.in_([m.membership_id for m in members])
                )
            )
        ).all()
    )
    declared = {
        r.prepared_by
        for r in rows
        if r.kind == "independence"
        and r.status in {"APPROVED", "LOCKED"}
        and date.fromisoformat(r.body["expires_on"]) > date.today()
    }
    checks.append(
        {
            "code": "independence",
            "passed": bool(member_users) and member_users <= declared,
            "description": "Current human-reviewed declarations for every assigned team member",
        }
    )
    p = await policy(db, ctx, eid)
    checks.append(
        {
            "code": "quality_review",
            "passed": not p.quality_review_required
            or bool(p.methodology.get("quality_review_decision")),
            "description": "Independent quality review where required",
        }
    )
    return {
        "checks": checks,
        "ready": all(c["passed"] for c in checks),
        "misstatement_register": {
            "corrected_gross": str(
                sum(
                    (
                        abs(Decimal(str(r.body["financial_impact"])))
                        for r in rows
                        if r.kind == "findings"
                        and r.body.get("finding_type") == "misstatement"
                        and r.body.get("correction_status") == "corrected"
                        and r.body.get("financial_impact") is not None
                    ),
                    Decimal(0),
                )
            ),
            "uncorrected_gross": str(
                sum(
                    (
                        abs(Decimal(str(r.body["financial_impact"])))
                        for r in rows
                        if r.kind == "findings"
                        and r.body.get("finding_type") == "misstatement"
                        and r.body.get("correction_status") != "corrected"
                        and r.body.get("financial_impact") is not None
                    ),
                    Decimal(0),
                )
            ),
            "unquantified_ids": [
                str(r.id)
                for r in rows
                if r.kind == "findings"
                and r.body.get("finding_type") == "misstatement"
                and r.body.get("financial_impact") is None
            ],
            "qualitative_review": "Amounts do not determine reporting implications; qualified assessment required",
        },
        "audit_opinion": "Human professional judgment required; no opinion generated",
    }


async def transition(db, ctx, eid, data, request_id):
    permission = (
        "engagement.archive"
        if data.action == "ARCHIVED"
        else "engagement.accept"
        if data.action == "ACCEPTED"
        else "engagement.finalize"
        if data.action in {"COMPLETED", "REPORTING", "QUALITY_REVIEW"}
        else "audit.plan"
    )
    eng = await engagement(db, ctx, eid, permission)
    if eng.version != data.version:
        raise HTTPException(409, "Engagement version conflict")
    current = eng.status.upper()
    if data.action not in TRANSITIONS.get(current, set()):
        raise HTTPException(409, "Invalid engagement status transition")
    rows = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.engagement_id == eid
            )
        )
    ).all()
    approved = {r.kind for r in rows if r.status in {"APPROVED", "LOCKED"}}
    required = {
        "ACCEPTED": {"acceptance"},
        "PLANNING": {"independence"},
        "RISK_ASSESSMENT": {"planning", "materiality"},
        "FIELDWORK": {"risks", "programs"},
    }
    if not required.get(data.action, set()) <= approved:
        raise HTTPException(409, "Required approved audit records are missing")
    if data.action == "PLANNING":
        checks = await completion(db, ctx, eid)
        if not next(c["passed"] for c in checks["checks"] if c["code"] == "independence"):
            raise HTTPException(
                409, "Every assigned member requires a current reviewed independence declaration"
            )
    if data.action in {"REVIEW", "QUALITY_REVIEW", "REPORTING", "COMPLETED"}:
        checks = await completion(db, ctx, eid)
        ignored = (
            {"completion", "quality_review"}
            if data.action in {"REVIEW", "QUALITY_REVIEW"}
            else set()
        )
        if any(not c["passed"] and c["code"] not in ignored for c in checks["checks"]):
            raise HTTPException(409, "Outstanding engagement completion controls")
    eng.status = data.action
    record(
        db,
        ctx,
        "audit.engagement.transition",
        eid,
        request_id,
        {"from": current, "to": data.action, "reason": data.comments, "version": eng.version},
    )
    await db.flush()
    await db.refresh(eng)
    return serialize(eng)
