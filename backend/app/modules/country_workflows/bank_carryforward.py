"""Carry reviewed residuals, never rewrite the original reporting-date BRS."""

from decimal import Decimal, localcontext
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, field_validator

from app.modules.country_workflows.bank_clearance import clearances
from app.modules.country_workflows.operations_schemas import BankOutstanding
from app.modules.country_workflows.schemas import Money, WorkflowInput
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "bank-clearance-carryforward/1"


class CarryforwardInput(Strict):
    label: str = Field(min_length=3, max_length=200)
    assessment: str = Field(min_length=10, max_length=2000)
    expected_rows: int = Field(ge=0, le=5000)
    positive_total: Money = Field(ge=0)
    negative_total: Money = Field(le=0)

    @field_validator("assessment")
    @classmethod
    def assess_window(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Assess retained review-window completeness and unresolved reversals")
        return value.strip()


def source_rows(body, sources, data):
    if body.get("workflow") != "bank-subsequent-clearance":
        raise ValueError("Select a subsequent bank clearance")
    params = WorkflowInput.model_validate(body["parameters"])
    recalculated = clearances(params, {role: source["rows"] for role, source in sources.items()})
    review_fields = {"auditor_status", "auditor_comments", "auditor", "auditor_at"}
    saved_rows = [
        {key: value for key, value in row.items() if key not in review_fields}
        for row in body["rows"]
    ]
    if recalculated["rows"] != saved_rows:
        raise ValueError(
            "Clearance rows differ from retained source calculation; recalculate first"
        )
    originals = {row["id"]: row for row in sources["outstanding"]["rows"]}
    rows = []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for item in recalculated["rows"]:
            if item["kind"] != "outstanding" or not Decimal(item["remaining_after_review"]):
                continue
            original = originals[item["source_id"]]
            row = BankOutstanding(
                id=original["id"],
                account=original["account"],
                currency=original["currency"],
                balance_date=params.review_through,
                date=original["date"],
                reference=original["reference"],
                amount=item["remaining_after_review"],
                evidence_reference=original["evidence_reference"],
            ).model_dump(mode="json")
            rows.append(
                {
                    **row,
                    "previous_balance_date": original["balance_date"],
                    "previous_outstanding_amount": original["amount"],
                    "cleared_in_previous_window": item["subsequently_cleared"],
                    "original_outstanding_date": original.get(
                        "original_outstanding_date", original["date"]
                    ),
                    "original_outstanding_amount": original.get(
                        "original_outstanding_amount", original["amount"]
                    ),
                    "original_outstanding_id": original.get(
                        "original_outstanding_id", original["id"]
                    ),
                    "source_clearance_row_id": item["id"],
                }
            )
        positive = sum(
            (Decimal(row["amount"]) for row in rows if Decimal(row["amount"]) > 0), Decimal(0)
        )
        negative = sum(
            (Decimal(row["amount"]) for row in rows if Decimal(row["amount"]) < 0), Decimal(0)
        )
        if (len(rows), positive, negative) != (
            data.expected_rows,
            data.positive_total,
            data.negative_total,
        ):
            raise ValueError(
                "Independent carry-forward row count or directional amount controls do not agree"
            )
        return rows, {params.currency: str(positive + negative)}


async def prepare(db, ctx, eng, parent, data, request_id):
    from app.modules.intelligence import service

    if (
        parent.kind != "country-workflow"
        or parent.body.get("workflow") != "bank-subsequent-clearance"
    ):
        raise HTTPException(422, "Select a subsequent bank clearance")
    if parent.body.get("review_status") != "REVIEWED" or parent.body.get("blocked"):
        raise HTTPException(
            409, "Independently review the clearance before carrying its residuals forward"
        )
    source_ids = parent.body.get("parameters", {}).get("source_ids", {})
    if set(source_ids) != {"outstanding", "statement", "allocations"}:
        raise HTTPException(409, "Clearance source roles are incomplete")
    sources = {}
    for role, identifier in source_ids.items():
        original = await service.event(db, ctx, eng.id, UUID(identifier), True)
        if original.kind != "workflow-source" or original.body.get("review_status") != "REVIEWED":
            raise HTTPException(409, "Independently review every retained clearance source")
        sources[role] = original.body
    try:
        rows, totals = source_rows(parent.body, sources, data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return await service.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "bank-outstanding",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": CONTRACT,
            "source_identity": "bank-carryforward:" + str(parent.root_id),
            "source_sha256": parent.sha256,
            "contributors": sorted(
                {*parent.body.get("contributors", [str(parent.created_by)]), str(ctx.user_id)}
            ),
            "population_completeness": "ALL_RESIDUALS_OF_RETAINED_CLEARANCE_ONLY_NOT_NEW_PERIOD_BRS",
            "nil_reason": data.assessment if not rows else None,
            "native_metadata": {
                "source_clearance_id": str(parent.id),
                "previous_reporting_date": parent.body["as_of"],
                "balance_date": parent.body["parameters"]["review_through"],
                "controls": data.model_dump(mode="json"),
                "new_period_items_included": False,
            },
            "limitations": [
                "All retained residuals only; new-period outstanding items and unbooked statement movements are not a complete BRS",
                "Original item dates and amounts remain in lineage; this carry-forward never posts a journal or rewrites a prior result",
                "Review-window completeness, reversal pairing and continued validity require independent assessment",
                "Independently review the carried population before using it in the next clearance window",
            ],
        },
        [service.event_receipt(parent)],
        request_id,
    )
