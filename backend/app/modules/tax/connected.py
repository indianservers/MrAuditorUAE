"""Connect authoritative calculations through immutable receipts, never shared tax bases."""

import uuid

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select

from app.modules.audit_execution.access import engagement_permissions
from app.modules.jurisdictions.profiles import Strict


class ConnectedInput(Strict):
    vat_run_id: uuid.UUID | None = None
    ct_run_id: uuid.UUID | None = None
    tp_run_id: uuid.UUID | None = None
    dmtt_event_id: uuid.UUID | None = None
    rationale: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def selected(self):
        if not any([self.vat_run_id, self.ct_run_id, self.tp_run_id, self.dmtt_event_id]):
            raise ValueError("Select at least one authoritative calculation")
        return self


async def assess(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service
    from app.modules.regulatory.reporting import engines

    rows, dependencies, issues = [], [], []
    for module, identifier in [
        ("vat", data.vat_run_id),
        ("tax", data.ct_run_id),
        ("tp", data.tp_run_id),
    ]:
        if not identifier:
            continue
        model, permission, check = engines()[module]
        await engagement_permissions(db, ctx, eng.id, permission)
        run = await db.scalar(
            select(model).where(
                model.tenant_id == ctx.tenant_id,
                model.engagement_id == eng.id,
                model.id == identifier,
            )
        )
        if not run:
            raise HTTPException(404, "Calculation not found in engagement")
        if not await check(db, ctx, eng.id, run):
            raise HTTPException(409, "Selected tax calculation is stale; regenerate and review")
        receipt = run.results.get("tax_execution")
        if not receipt:
            issues.append(f"{module}: legacy provenance incomplete; regenerate")
        elif receipt["input_completeness"] != "complete_for_supported_case":
            issues.extend(f"{module}: {question}" for question in receipt["unresolved_questions"])
        dependencies.append(
            {"type": "calculation", "module": module, "id": str(run.id), "sha256": run.sha256}
        )
        rows.append(
            {
                "engine": module,
                "run_id": str(run.id),
                "kind": run.kind,
                "accounting_profit": run.results.get("accounting_profit"),
                "calculated_liability": receipt.get("calculated_liability") if receipt else None,
                "filing_status": "NOT_SUBMITTED",
                "review": "REQUIRES_INDEPENDENT_REVIEW",
                "source_snapshots": receipt.get("source_snapshots") if receipt else None,
            }
        )
    if data.dmtt_event_id:
        from app.modules.dmtt import service as dmtt
        from app.modules.ml.models import MLEvent

        await engagement_permissions(db, ctx, eng.id, "dmtt.read")
        item = await db.scalar(
            select(MLEvent).where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == eng.id,
                MLEvent.id == data.dmtt_event_id,
                MLEvent.kind == "dmtt_calculation",
            )
        )
        if not item or not await dmtt.current(db, ctx, eng.id, item):
            raise HTTPException(409, "A current DMTT calculation is required")
        result = item.body["results"]
        if result.get("uae_dmtt") is None:
            issues.append("DMTT scope, special case or calculation remains unresolved")
        dependencies.append({"type": "dmtt", "id": str(item.id), "sha256": item.sha256})
        rows.append(
            {
                "engine": "dmtt",
                "run_id": str(item.id),
                "outcome": result.get("outcome", result.get("status")),
                "calculated_liability": result.get("uae_dmtt"),
                "filing_status": "NOT_SUBMITTED",
            }
        )
    return await service.append(
        db,
        ctx,
        eng,
        "tax-connected-assessment",
        {
            "title": "Connected tax reconciliation and review",
            "rows": rows,
            "issues": issues,
            "execution_mode": "deterministic",
            "completeness": "partial" if issues else "complete_for_selected_controls",
            "review_status": "UNVERIFIED",
            "contributors": [str(ctx.user_id)],
            "rationale": data.rationale,
            "filing_status": "NOT_SUBMITTED",
            "authority_assessment": "NOT_ESTABLISHED",
            "bridges": {
                "owner_of_vat": "vat",
                "owner_of_current_tax": "tax",
                "owner_of_pricing": "tp",
                "owner_of_uae_topup": "dmtt",
                "domestic_taxable_income_is_globe_income": False,
                "deferred_tax_owner": "E09 interface only; no deferred-tax computation in current CT",
                "tp_vat_effect": "Separate supply/change-in-consideration determination required; no automatic VAT rate",
            },
        },
        dependencies,
        request_id,
    )
