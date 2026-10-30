"""Retain withholding identity while reusing the existing many-to-many bank allocator."""

from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, field_validator

from app.db.models.platform import FinancialPeriod
from app.modules.country_workflows.schemas import Obligation
from app.modules.country_workflows.withholding_calculations import (
    KEY_FIELDS,
    assessment_issues,
    select_records,
)
from app.modules.country_workflows.withholding_provisions import withdrawn_expectation
from app.modules.country_workflows.withholding_scope import WithholdingSettlementScope
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "withholding-obligations/1"
Amount = Annotated[Decimal, Field(ge=0, max_digits=36, decimal_places=8, allow_inf_nan=False)]


class WithholdingObligationInput(Strict):
    purpose: Literal["expected", "reported"]
    legal_role: Literal["deductor", "collector"]
    cutoff_date: date
    expected_current_rows: int = Field(ge=1, le=5000)
    amount: Amount
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)

    @field_validator("assessment")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10:
            raise ValueError(
                "Assess the liability, source purpose and bank-allocation scope explicitly"
            )
        return value.strip()


def source_rows(body, data):
    if body.get("table_type") != "withholding-records":
        raise ValueError(
            "Select retained withholding records, not beneficiary credit or bank evidence"
        )
    selected, inactive = select_records(
        body["rows"], data.legal_role, data.cutoff_date, data.purpose
    )
    if len(selected) != data.expected_current_rows or inactive.keys() - selected.keys():
        raise ValueError(
            "Every withholding identity needs one current record and agreeing independent row control; cancelled history is not zero"
        )
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        total = sum((Decimal(row["amount"]) for row in selected.values()), Decimal(0))
        if total != data.amount:
            raise ValueError("Independent current withholding amount control does not agree")
        for key, record in sorted(selected.items()):
            if record.get("payment_date"):
                raise ValueError(
                    "Payment dates cannot establish expected/reported obligations; retain independent allocated bank evidence"
                )
            if data.purpose == "expected" and (
                not record.get("due_date") or assessment_issues(record, "rule", {})
            ):
                raise ValueError(
                    "Expected withholding needs a retained rule assessment, transaction coverage and explicit due date"
                )
            scope = WithholdingSettlementScope.model_validate(
                {field: record[field] for field in WithholdingSettlementScope.model_fields}
            )
            if data.purpose == "expected" and withdrawn_expectation(record):
                raise ValueError(
                    "Positive section206C(1H) expectations are withdrawn for this transaction/reporting period"
                )
            identifier = fingerprint(dict(zip(KEY_FIELDS, key, strict=True)))[:32]
            canonical = Obligation(
                id="wh-" + data.purpose + "-" + identifier,
                registration=record["registration"],
                subject=record["counterparty"],
                period=record["period"],
                component=record["tax_kind"],
                currency="INR",
                amount=record["amount"],
                due_date=record.get("due_date"),
                withholding_scope=scope,
            ).model_dump(mode="json")
            rows.append(
                {
                    **canonical,
                    "source_withholding_row_id": record["id"],
                    "source_withholding_reference": record["source_reference"],
                    "source_withholding_version": record["source_version"],
                    "excluded_withholding_row_ids": inactive.get(key, []),
                }
            )
    return rows, {"INR": str(total)}, list(selected.values())


async def derive(db, ctx, eng, parent, data, contributors):
    from app.modules.country_workflows.service import withholding_documents
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    package, _ = await resolved(db, ctx, eng)
    if package.country != "IN":
        raise HTTPException(422, "Withholding obligations require an India engagement")
    if parent.kind != "workflow-source" or parent.body.get("review_status") != "REVIEWED":
        raise HTTPException(409, "Select a current independently reviewed withholding source")
    period = await db.get(FinancialPeriod, eng.period_id)
    if period is None or not period.start_date <= data.cutoff_date <= period.end_date:
        raise HTTPException(422, "Withholding cutoff must fall within the engagement period")
    try:
        rows, totals, selected = source_rows(parent.body, data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    receipts = [service.event_receipt(parent)]
    contributors.update(parent.body.get("contributors", [str(parent.created_by)]))
    if data.purpose == "expected":
        receipts.extend(
            await withholding_documents(db, ctx, eng, selected, contributors=contributors)
        )
    return rows, totals, receipts


async def prepare(db, ctx, eng, parent, data, request_id):
    from app.modules.intelligence import service

    contributors = {str(ctx.user_id)}
    rows, totals, receipts = await derive(db, ctx, eng, parent, data, contributors)
    return await service.append(
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
            "source_identity": "withholding-obligations:" + str(parent.root_id),
            "source_sha256": parent.body["evidence_sha256"],
            "derived_rows_sha256": fingerprint(rows),
            "contributors": sorted(contributors),
            "allowed_source_roles": [data.purpose],
            "allowed_workflows": ["obligation-bank-allocations"],
            "population_completeness": "CURRENT_REVIEWED_WITHHOLDING_IDENTITIES_ONLY",
            "statutory_calculation_qualified": False,
            "native_metadata": {
                "source_id": str(parent.id),
                "controls": data.model_dump(mode="json"),
            },
            "limitations": [
                "Tax amounts, legal roles, sections, tax years and due dates are assessed inputs, not statutory calculations",
                "Original current and excluded source observations remain linked; cancelled-only identities never become zero",
                "Bank cash allocations do not establish challan posting, return filing or beneficiary tax credit",
                "Each transaction, tax year and section stays separate; advance challans need a separate assessment",
            ],
        },
        receipts,
        request_id,
    )


async def verify(db, ctx, eng, source, data, role, contributors):
    from app.modules.intelligence import service

    metadata = source["native_metadata"]
    controls = WithholdingObligationInput.model_validate(metadata["controls"])
    if controls.purpose != role or controls.cutoff_date != data.as_of:
        raise HTTPException(
            422, "Withholding obligation purpose and cutoff must match the allocation review"
        )
    parent = await service.event(db, ctx, eng.id, UUID(metadata["source_id"]), True)
    rows, totals, receipts = await derive(db, ctx, eng, parent, controls, contributors)
    if (
        rows != source["rows"]
        or totals != source["control_totals"]
        or fingerprint(rows) != source["derived_rows_sha256"]
        or source["source_sha256"] != parent.body["evidence_sha256"]
    ):
        raise HTTPException(409, "Withholding obligations no longer agree to their retained source")
    return receipts
