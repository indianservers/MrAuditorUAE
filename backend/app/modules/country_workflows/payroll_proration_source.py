"""Reviewed dated PF calculations become purpose-bound monthly wage sources."""

from decimal import Decimal, localcontext
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.modules.country_workflows.payroll_basis_proration import CONTRACT
from app.modules.country_workflows.payroll_schemas import Money, PayrollBasis
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict

SOURCE_CONTRACT = "prorated-payroll-bases/1"


class ProratedBasisInput(Strict):
    result_id: UUID
    expected_rows: int = Field(strict=True, ge=3, le=5000)
    control_total: Money = Field(ge=0)
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def assessed(self):
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the original monthly controls and post-ceiling wage basis")
        return self


def source_rows(body, data):
    if (
        body.get("workflow") != "india-payroll-basis-proration"
        or body.get("payroll_proration_contract") != CONTRACT
        or body.get("blocked") is not False
        or body.get("monthly_basis_complete") is not True
        or len(body.get("rows", [])) != data.expected_rows
    ):
        raise ValueError(
            "Select a complete current dated PF basis calculation and exact row control"
        )
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        total = Decimal(0)
        for row in body["rows"]:
            if row.get("state") != "MATCHED" or row.get("computed_monthly_basis") is None:
                raise ValueError(
                    "Every monthly basis must agree with independent original controls"
                )
            canonical = PayrollBasis(
                id="prorated:"
                + fingerprint({"result_row": row["id"], "control_row": row["basis_source_id"]})[
                    :32
                ],
                registration=row["registration"],
                subject=row["subject"],
                period=row["period"],
                component=row["component"],
                currency=row["currency"],
                amount=row["computed_monthly_basis"],
                rule_group=row["rule_group"],
                jurisdiction=row["jurisdiction"],
                eligible=row["eligible"],
                eligibility_reference="Dated reviewed result " + row["id"],
                assessment=data.assessment,
            ).model_dump(mode="json")
            rows.append(
                {
                    **canonical,
                    "post_cap_basis_contract": CONTRACT,
                    "proration_result_row_id": row["id"],
                    "monthly_control_source_id": row["basis_source_id"],
                    "proration_segments": row["segment_trace"],
                }
            )
            total += Decimal(canonical["amount"])
        if total != data.control_total:
            raise ValueError("Independent post-ceiling component-basis total does not agree")
    return rows, {"INR": str(total)}


async def derive(db, ctx, eng, data):
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved

    parent = await intelligence.event(db, ctx, eng.id, data.result_id, True)
    binding, _ = await resolved(db, ctx, eng)
    if binding.country != "IN":
        raise HTTPException(422, "Dated PF wage sources require an India engagement")
    if parent.kind != "country-workflow" or parent.body.get("review_status") != "REVIEWED":
        raise HTTPException(409, "Select a current independently reviewed dated PF basis result")
    try:
        rows, totals = await run_in_threadpool(source_rows, parent.body, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    authors = {str(ctx.user_id), *parent.body.get("contributors", [str(parent.created_by)])}
    return parent, rows, totals, [intelligence.event_receipt(parent)], sorted(authors)


async def prepare(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service as intelligence

    parent, rows, totals, dependencies, authors = await derive(db, ctx, eng, data)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "payroll-bases",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": SOURCE_CONTRACT,
            "allowed_workflows": ["india-payroll-rules"],
            "allowed_source_roles": ["bases"],
            "source_identity": "prorated-basis:" + str(parent.root_id),
            "source_sha256": fingerprint(rows),
            "contributors": authors,
            "native_metadata": data.model_dump(mode="json"),
            "population_completeness": "REVIEWED_MONTHLY_PF_COMPONENT_BASES_ONLY",
            "limitations": [
                "Ceilings and eligibility are already assessed upstream; contribution profiles must not cap or select wage slabs again"
            ],
        },
        dependencies,
        request_id,
    )


async def verify(db, ctx, eng, source, contributors):
    data = ProratedBasisInput.model_validate(source["native_metadata"])
    _, rows, totals, dependencies, authors = await derive(db, ctx, eng, data)
    if (
        rows != source["rows"]
        or totals != source["control_totals"]
        or fingerprint(rows) != source["source_sha256"]
    ):
        raise HTTPException(
            409, "Monthly wage source no longer agrees with its reviewed dated result"
        )
    contributors.update(authors)
    return dependencies
