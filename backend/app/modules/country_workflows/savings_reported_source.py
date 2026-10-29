"""Preserve reviewed fund observations as reported remittances, never expectations."""

from decimal import Decimal, localcontext
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.modules.country_workflows.savings_scheme import SCOPE, SavingsObservation
from app.modules.country_workflows.schemas import Obligation
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.pension_profiles import Money

CONTRACT = "savings-fund-observations/1"


class SavingsReportedInput(Strict):
    source_id: UUID
    expected_rows: int = Field(strict=True, ge=0, le=5000)
    control_total: Money = Field(ge=0)
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed(self):
        if len(self.assessment.strip()) < 10:
            raise ValueError(
                "Assess the original fund observation population and independent totals"
            )
        return self


def source_rows(source, data):
    if (
        source.get("table_type") != "savings-reported"
        or len(source.get("rows", [])) != data.expected_rows
    ):
        raise ValueError(
            "Select the exact reviewed fund observation population and independent count"
        )
    if not source["rows"] and not source.get("nil_reason"):
        raise ValueError(
            "An empty fund population requires its original independently reviewed nil declaration"
        )
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        total = Decimal(0)
        for raw in source["rows"]:
            observation = SavingsObservation.model_validate(raw).model_dump(mode="json")
            row = Obligation(
                **{
                    key: observation[key]
                    for key in (
                        "registration",
                        "subject",
                        "period",
                        "component",
                        "currency",
                        "amount",
                    )
                },
                id="fund:" + observation["id"],
                savings_scope={key: observation[key] for key in SCOPE},
            ).model_dump(mode="json")
            rows.append(
                {
                    **row,
                    "fund_source_row_id": observation["id"],
                    "fund_evidence_reference": observation["evidence_reference"],
                }
            )
            total += Decimal(row["amount"])
        if total != data.control_total:
            raise ValueError("Independent reported fund amount control does not agree")
    return rows, {"AED": str(total)}


async def derive(db, ctx, eng, data):
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved

    original = await intelligence.event(db, ctx, eng.id, data.source_id, True)
    binding, _ = await resolved(db, ctx, eng)
    if binding.country != "AE":
        raise HTTPException(422, "MOHRE savings fund observations require a UAE engagement")
    if original.kind != "workflow-source" or original.body.get("review_status") != "REVIEWED":
        raise HTTPException(
            409, "Select a current independently reviewed original fund observation source"
        )
    try:
        rows, totals = await run_in_threadpool(source_rows, original.body, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    authors = {str(ctx.user_id), *original.body.get("contributors", [str(original.created_by)])}
    return original, rows, totals, [intelligence.event_receipt(original)], sorted(authors)


async def prepare(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service as intelligence

    original, rows, totals, dependencies, authors = await derive(db, ctx, eng, data)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "obligations",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": CONTRACT,
            "allowed_workflows": ["obligation-bank-allocations"],
            "allowed_source_roles": ["reported"],
            "source_identity": "savings-fund:" + str(original.root_id),
            "source_sha256": fingerprint(rows),
            "contributors": authors,
            "native_metadata": data.model_dump(mode="json"),
            "nil_reason": original.body.get("nil_reason"),
            "population_completeness": "ORIGINAL_REVIEWED_FUND_OBSERVATIONS_ONLY",
            "limitations": [
                "Fund-reported basic contributions only; neither independently calculated expectations nor authenticated bank payments; no NAV or benefit entitlement"
            ],
        },
        dependencies,
        request_id,
    )


async def verify(db, ctx, eng, source, contributors):
    data = SavingsReportedInput.model_validate(source["native_metadata"])
    original, rows, totals, dependencies, authors = await derive(db, ctx, eng, data)
    if (
        rows != source["rows"]
        or totals != source["control_totals"]
        or fingerprint(rows) != source["source_sha256"]
        or source.get("nil_reason") != original.body.get("nil_reason")
    ):
        raise HTTPException(
            409, "Reported remittances no longer agree with the reviewed original fund source"
        )
    contributors.update(authors)
    return dependencies
