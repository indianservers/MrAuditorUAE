import uuid
from decimal import Decimal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import RecordInput, Strict
from app.modules.tax import service as tax
from app.modules.tp import service


class TaxLink(Strict):
    judgment_id: uuid.UUID
    tax_profile_id: uuid.UUID
    tax_rule_id: uuid.UUID
    account_codes: list[str] = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=4000)


async def create_adjustment(db, ctx, eid, rid, raw, request_id):
    data = TaxLink.model_validate(raw)
    run = await service.get_run(db, ctx, eid, rid)
    if not await service.current(db, ctx, eid, run):
        raise HTTPException(409, "Current TP calculation required")
    judgment = await service.record(db, ctx, eid, data.judgment_id, "judgment", True)
    if judgment.body["run_id"] != str(run.id) or judgment.body["conclusion"] == "MORE_INFORMATION":
        raise HTTPException(409, "Independent approved final judgment for this run required")
    _, tp_profile, _, _, _ = await service.profile_inputs(
        db, ctx, eid, uuid.UUID(run.inputs["profile_id"])
    )
    _, tax_profile, financial, _, _, _ = await tax.profile_inputs(db, ctx, eid, data.tax_profile_id)
    if tax_profile.financial_run_id != tp_profile.financial_run_id:
        raise HTTPException(422, "TP and CT must use the same approved financial source")
    amount = Decimal(judgment.body["proposed_tax_adjustment"])
    if not amount:
        raise HTTPException(422, "No adjustment was independently approved")
    if amount < 0 and not judgment.body.get("fta_downward_approval_id"):
        raise HTTPException(409, "Downward adjustment needs reviewed FTA approval evidence")
    line_codes = set(data.account_codes)
    lines = [x for x in financial.results["lines"] if x["line_code"] in line_codes]
    if {x["line_code"] for x in lines} != line_codes:
        raise HTTPException(422, "Accounts not in approved financial statements")
    reference = "TP-BRIDGE-" + str(judgment.id)
    body = {
        "profile_id": str(data.tax_profile_id),
        "category": "connected_person" if run.kind == "remuneration" else "related_party",
        "rule_id": str(data.tax_rule_id),
        "account_codes": data.account_codes,
        "accounting_amount": str(sum((Decimal(x["current"]) for x in lines), Decimal(0))),
        "proposed_adjustment": str(amount),
        "treatment": "professional_adjustment",
        "rationale": data.rationale,
        "evidence_record_ids": [str(judgment.id)],
    }
    from app.modules.tax.schemas import Adjustment

    body = Adjustment.model_validate(body).model_dump(mode="json")
    prior = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.kind == "tax-adjustment",
            AuditRecord.reference == reference,
        )
    )
    if prior:
        if {k: v for k, v in prior.body.items() if not k.startswith("review_")} != body:
            raise HTTPException(409, "Bridge already exists with different parameters")
        return audit.serialize(prior)
    return await audit.create(
        db,
        ctx,
        eid,
        "tax-adjustment",
        RecordInput(
            reference=reference, title="TP reviewed adjustment pending CT review", body=body
        ),
        request_id,
    )
