"""Bridge the existing VAT engine to source-controlled reconciliation, without recalculating law."""

from collections import defaultdict
from decimal import Decimal, localcontext

from fastapi import HTTPException

from app.db.models.platform import FinancialPeriod
from app.modules.country_workflows.schemas import ReturnBox
from app.modules.vat import service as vat
from app.modules.vat.catalogue import BOXES
from app.modules.vat.schemas import Adjustment


def source_rows(results, registration, period_start, period_end, adjustments):
    if (
        results.get("currency") != "AED"
        or results.get("validation", {}).get("ready") is not True
        or results.get("exceptions")
    ):
        raise ValueError("Select a reconciled VAT201 run with no unresolved validation exceptions")
    boxes = results.get("boxes", [])
    if len(boxes) != len(BOXES) or {r["box"] for r in boxes} != set(BOXES):
        raise ValueError("VAT201 calculation must contain every distinct supported box")
    if not results.get("mapping_version"):
        raise ValueError("A VAT201 mapping version is required")
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        adjustment_totals: defaultdict[str, Decimal] = defaultdict(Decimal)
        for adj in adjustments:
            if (
                adj.box not in {"1", "2", "3", "4", "5", "6", "7", "9", "10"}
                or not adj.statutory_conditions_confirmed
            ):
                raise ValueError("VAT adjustment mapping and statutory conditions must be reviewed")
            adjustment_totals[adj.box] += adj.tax_amount
        adjustment_totals["8"] = sum((adjustment_totals[str(i)] for i in range(1, 8)), Decimal(0))
        adjustment_totals["11"] = adjustment_totals["9"] + adjustment_totals["10"]
        adjustment_totals["12"] = adjustment_totals["8"]
        adjustment_totals["13"] = adjustment_totals["11"]
        adjustment_totals["14"] = adjustment_totals["12"] - adjustment_totals["13"]
        rows = []
        for box in boxes:
            tax = Decimal(str(box["vat"]))
            if not tax.is_finite():
                raise ValueError("Non-finite VAT calculation output is not a source")
            row = ReturnBox(
                id="vat-box:" + box["box"],
                registration=registration,
                period_start=period_start,
                period_end=period_end,
                box=box["box"],
                currency="AED",
                taxable_amount=box["net"],
                tax=tax - adjustment_totals[box["box"]],
                adjustment=adjustment_totals[box["box"]],
            )
            rows.append(row.model_dump(mode="json"))
        total = sum((Decimal(r["tax"]) for r in rows), Decimal(0))
    return rows, {"AED": str(total)}


async def compute(db, ctx, eng, data, package, dependencies):
    if package.country != "AE":
        raise HTTPException(422, "A UAE VAT calculation source requires a UAE engagement")
    run = await vat.run(db, ctx, eng.id, data.run_id)
    if run.kind != "vat201" or not await vat.current(db, ctx, eng.id, run):
        raise HTTPException(409, "Select a current VAT201 calculation run")
    period = await db.get(FinancialPeriod, eng.period_id)
    if not period or not period.start_date <= run.period_start <= run.period_end <= period.end_date:
        raise HTTPException(422, "VAT calculation is outside the engagement financial period")
    import uuid

    profile = await vat.record(
        db, ctx, eng.id, uuid.UUID(run.inputs["profile_id"]), "profile", True
    )
    adjustments = []
    for identifier in run.inputs.get("adjustment_ids", []):
        record = await vat.record(db, ctx, eng.id, uuid.UUID(identifier), "adjustment", True)
        adjustments.append(Adjustment.model_validate(vat.clean(record.body)))
    try:
        rows, totals = source_rows(
            run.results, profile.body["trn"], run.period_start, run.period_end, adjustments
        )
    except ValueError:
        raise HTTPException(
            422,
            "VAT calculation output or adjustment mapping is incomplete; review the VAT workbench",
        ) from None
    return {
        "table_type": "return-boxes",
        "rows": rows,
        "row_count": len(rows),
        "control_totals": totals,
        "title": data.label,
        "review_status": "UNVERIFIED",
        "source_identity": "vat-run:" + str(run.id),
        "source_sha256": run.sha256,
        "calculation_module": "vat",
        "source_calculation_id": str(run.id),
        "contributors": sorted({str(ctx.user_id), str(run.created_by)}),
        "parser_version": "vat201-calculation-bridge-1",
        "population_completeness": "CURRENT_RECONCILED_VAT_CALCULATION",
        "statutory_calculation_qualified": False,
        "native_metadata": {
            "registration": profile.body["trn"],
            "period_start": run.period_start.isoformat(),
            "period_end": run.period_end.isoformat(),
            "mapping_version": run.results["mapping_version"],
            "net_vat": run.results.get("net_vat"),
            "box1_emirate_detail": run.results.get("emirates", {}),
            "tax_field_basis": "VAT BEFORE SEPARATELY IDENTIFIED MANUAL TAX ADJUSTMENTS",
            "taxable_amount_basis": "FINAL COMPUTED BOX NET INCLUDING REVIEWED NET ADJUSTMENTS",
            "control_total_basis": "SUM OF CANONICAL TAX FIELDS INCLUDING SUMMARY BOXES; NOT TAX PAYABLE",
        },
        "limitations": [
            "Calculation source only; filed return evidence must be imported independently",
            "Reviewed VAT classifications and rules retain their existing professional scope limits",
            "Box1 is aggregated; emirate details are retained separately and require their own comparison",
        ],
    }, [
        *dependencies,
        {"type": "calculation", "module": "vat", "id": str(run.id), "sha256": run.sha256},
    ]
