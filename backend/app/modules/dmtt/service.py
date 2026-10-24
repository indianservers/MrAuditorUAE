from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord
from app.modules.dmtt import schemas as s
from app.modules.dmtt.calculations import calculate
from app.modules.ifrs.calculations import serial
from app.modules.ml.service import event
from app.modules.tax.service import financial_source

SOURCES = {
    "CD142": {
        "url": "https://tax.gov.ae/Datafolder/Files/Legislation/Cabinet-Decision-No-142-of-2024-on-Top-up-Tax-on-MNEs.pdf",
        "effective": "2025-01-01",
        "version": "UAE-CD142-MD96/v2",
    },
    "MD88": {
        "url": "https://mof.gov.ae/wp-content/uploads/2025/04/English-Ministerial-Decision-No.-88-of-2025-on-Commentary-and-Guidance-for-Top-Up-Tax.pdf",
        "effective": "2025-01-01",
        "adopted": "2024 Consolidated Commentary (2023); June 2024 guidance; January 2025 Central Record, Articles 8.1.4/8.1.5, Article 9.1 and GIR",
    },
}
TASKS = [
    "scope_explanation",
    "revenue_threshold",
    "entity_classification",
    "globe_adjustments",
    "covered_taxes",
    "deferred_tax_review",
    "transition_rules",
    "sbie_review",
    "safe_harbour_review",
    "election_impact",
    "topup_variance",
    "technical_memo",
    "missing_evidence",
    "group_information_request",
    "regulatory_comparison",
]

SOURCES["MD88"]["lifecycle"] = "REPEALED_BY_MD96_2026"
SOURCES["MD96"] = {
    "url": "https://mof.gov.ae/wp-content/uploads/2026/06/Ministerial-Decision-No.-96-of-2026-on-the-Commentary-and-Agreed-Administrative-Guidance-for-the-Purposes-of-Cabinet-Decision-No.-142-of-2024-on-the-Imposition-of-Top-Up-Tax-on-Multinational-Enterprises-en.pdf",
    "effective": "2026-06-22",
    "applies_fiscal_start": "2025-01-01",
    "adopted": "OECD Consolidated Commentary 2026; Central Record 2026; GIR January 2025",
    "lifecycle": "ACTIVE",
    "coverage": "Ordinary cases only; advanced adopted guidance requires technical schedules",
}
SOURCES["MD133"] = {
    "url": "https://mof.gov.ae/wp-content/uploads/2026/08/Ministerial-Decision-No133-of-2026-on-Pillar-Two-Information-Return-EN.pdf",
    "effective": "2026-08-03",
    "applies_fiscal_start": "2025-01-01",
    "coverage": "Reporting evidence and manual obligations assessment; no electronic filing",
}


def clean(body):
    return {k: v for k, v in body.items() if not k.startswith("review_")}


async def evidence(db, ctx, eid, rid):
    from app.modules.tax.service import evidence as checked

    return await checked(db, ctx, eid, rid)


async def record(db, ctx, eid, rid, kind, approved=True):
    obj = await audit.get_record(db, ctx, eid, rid, "dmtt.read")
    if obj.kind != "dmtt-" + kind:
        raise HTTPException(422, "DMTT source kind mismatch")
    if approved and obj.status not in {"APPROVED", "LOCKED"}:
        raise HTTPException(409, "Independently approved DMTT source required")
    if approved:
        from app.modules.lineage.working_papers import require_context_current

        await require_context_current(db, ctx, obj)
    return obj


async def validate_body(db, ctx, eng, kind, data, record_id=None):
    key = kind.removeprefix("dmtt-")
    if key == "group":
        refs = [x.evidence_id for x in data.preceding_revenues] + [data.technical_evidence_id]
        if data.currency_election_evidence_id:
            refs.append(data.currency_election_evidence_id)
        if len(set(data.constituent_entity_ids)) != len(data.constituent_entity_ids):
            raise HTTPException(422, "Duplicate constituent entity")
        from app.db.models.platform import LegalEntity

        for identifier in data.constituent_entity_ids:
            entity = await db.scalar(
                select(LegalEntity).where(
                    LegalEntity.tenant_id == ctx.tenant_id, LegalEntity.id == identifier
                )
            )
            if not entity:
                raise HTTPException(422, "Constituent entity outside tenant")
    else:
        group = await record(db, ctx, eng.id, data.group_id, "group")
        g = s.Group.model_validate(clean(group.body))
        if isinstance(data, s.Entity):
            if data.entity_id not in g.constituent_entity_ids:
                raise HTTPException(422, "Entity absent from approved group roster")
            source, deps = await financial_source(
                db, ctx, data.source_engagement_id, data.financial_run_id
            )
            from app.db.models.platform import Engagement

            source_eng = await db.get(Engagement, data.source_engagement_id)
            if not source_eng or source_eng.entity_id != data.entity_id:
                raise HTTPException(422, "Financial source entity mismatch")
            if source.results["period_start"] != str(g.fiscal_start) or source.results[
                "period_end"
            ] != str(g.fiscal_end):
                raise HTTPException(422, "Financial period mismatch")
            if g.accounting_basis != "standalone_ifrs":
                raise HTTPException(422, "UPE accounting package basis is not implemented")
            if source.results["currency"] == g.calculation_currency:
                if data.fx_to_calculation != 1:
                    raise HTTPException(422, "Same currency requires FX 1")
            elif not g.currency_election_evidence_id:
                raise HTTPException(422, "Reviewed Article 10 currency basis/election required")
            refs = (
                [
                    data.classification_evidence_id,
                    data.fx_evidence_id,
                    data.covered_tax_evidence_id,
                    data.substance_evidence_id,
                ]
                + [a.evidence_id for a in data.adjustments]
                + [d.evidence_id for d in data.deferred]
            )
            if data.additional_topup and not data.additional_topup_evidence_id:
                raise HTTPException(422, "Additional top-up evidence required")
            refs += [
                x
                for x in [
                    data.additional_topup_evidence_id,
                    *[d.exception_evidence_id for d in data.deferred],
                ]
                if x
            ]
        else:
            refs = [data.evidence_id] if key == "election" else [data.technical_evidence_id]
    for rid in refs:
        await evidence(db, ctx, eng.id, rid)
    return data.model_dump(mode="json")


async def validate_action(db, ctx, eid, obj, action):
    if action in {"submit", "approve", "lock"}:
        data = s.BODIES[obj.kind.removeprefix("dmtt-")].model_validate(clean(obj.body))
        eng = await audit.engagement(db, ctx, eid, "dmtt.read")
        await validate_body(db, ctx, eng, obj.kind, data, obj.id)


async def computation(db, ctx, eid, gid):
    group = await record(db, ctx, eid, gid, "group")
    g = s.Group.model_validate(clean(group.body))
    objects = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind.in_(["dmtt-entity", "dmtt-election"]),
                AuditRecord.body["group_id"].astext == str(gid),
                AuditRecord.status.in_(["APPROVED", "LOCKED"]),
            )
        )
    ).all()
    entities = []
    elections = []
    dependencies = [{"id": str(group.id), "version": group.version}]
    eng = await audit.engagement(db, ctx, eid, "dmtt.calculate", True)
    await validate_body(db, ctx, eng, "dmtt-group", g)
    for obj in objects:
        key = obj.kind.removeprefix("dmtt-")
        data = s.BODIES[key].model_validate(clean(obj.body))
        await validate_body(db, ctx, eng, obj.kind, data, obj.id)
        dependencies.append({"id": str(obj.id), "version": obj.version})
        if isinstance(data, s.Entity):
            financial, deps = await financial_source(
                db, ctx, data.source_engagement_id, data.financial_run_id
            )
            dependencies.extend(deps)
            entities.append(
                (data, __import__("decimal").Decimal(financial.results["totals"]["profit"]))
            )
        else:
            elections.append(data)
    if {e.entity_id for e, _ in entities} != set(g.constituent_entity_ids) or len(entities) != len(
        g.constituent_entity_ids
    ):
        raise HTTPException(409, "Exactly one approved schedule per constituent entity is required")
    try:
        results = serial(calculate(g, entities, elections))
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None
    return await event(
        db,
        ctx,
        eid,
        "dmtt_calculation",
        {
            "group_id": str(gid),
            "rules": SOURCES,
            "dependencies": dependencies,
            "results": results,
            "synthetic": g.synthetic,
        },
    )
