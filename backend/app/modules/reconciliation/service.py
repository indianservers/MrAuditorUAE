import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.db.models.platform import FinancialPeriod, LegalEntity
from app.modules.accounting.calculations import movements, reconcile
from app.modules.accounting.models import (
    ImportBatch,
    ImportSnapshot,
    ReconciliationException,
    ReconciliationRun,
    TrialBalance,
    TrialBalanceLine,
)
from app.modules.accounting.service import scope_values, scoped


async def balance(db: AsyncSession, ctx: Context, snapshot_id: uuid.UUID) -> dict:
    snapshot = await scoped(db, ctx, ImportSnapshot, snapshot_id)
    batch = await scoped(db, ctx, ImportBatch, snapshot.batch_id)
    if batch.status not in {"active", "superseded"}:
        raise HTTPException(409, "Snapshot is not a committed financial population")
    entity = await scoped(db, ctx, LegalEntity, batch.entity_id)
    from babel.numbers import get_currency_precision

    from app.modules.accounting.models import Currency

    policy = await db.scalar(
        select(Currency).where(
            Currency.tenant_id == ctx.tenant_id, Currency.code == entity.functional_currency
        )
    )
    precision = policy.precision if policy else get_currency_precision(entity.functional_currency)
    rounding = policy.rounding if policy else "ROUND_HALF_EVEN"
    params = {"tenant": ctx.tenant_id, "batch": batch.id}
    if batch.kind in {"gl", "journals"}:
        query = """SELECT a.id,a.code,a.name,a.classification,a.statement_group,a.contra,a.parent_code,a.source_group,
        SUM(CASE WHEN l.opening THEN l.base_debit-l.base_credit ELSE 0 END) opening,
        SUM(CASE WHEN NOT l.opening THEN l.base_debit ELSE 0 END) debit,
        SUM(CASE WHEN NOT l.opening THEN l.base_credit ELSE 0 END) credit,
        SUM(l.base_debit-l.base_credit) closing
        FROM journal_lines l JOIN accounts a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
        WHERE l.tenant_id=:tenant AND l.batch_id=:batch GROUP BY a.id ORDER BY a.code"""
    elif batch.kind == "tb":
        query = """SELECT a.id,a.code,a.name,a.classification,a.statement_group,a.contra,a.parent_code,a.source_group,
        SUM((s.canonical->>'opening_balance')::numeric) opening,
        SUM((s.canonical->>'base_debit')::numeric) debit,SUM((s.canonical->>'base_credit')::numeric) credit,
        SUM((s.canonical->>'closing_balance')::numeric) closing
        FROM source_records s JOIN accounts a ON a.code=s.canonical->>'account_code' AND a.tenant_id=s.tenant_id AND a.entity_id=s.entity_id
        WHERE s.tenant_id=:tenant AND s.batch_id=:batch GROUP BY a.id ORDER BY a.code"""
    else:
        raise HTTPException(409, "Chart of accounts has no financial balances")
    lines = [dict(row) for row in (await db.execute(text(query), params)).mappings()]
    for row in lines:
        row["display_closing"] = str(
            row["closing"].quantize(Decimal(1).scaleb(-precision), rounding=rounding)
        )
    total = sum((r["closing"] for r in lines), Decimal(0))
    return {
        "snapshot_id": str(snapshot_id),
        "functional_currency": entity.functional_currency,
        "display_precision": precision,
        "display_rounding": rounding,
        "sign_convention": "debit_positive",
        "rounding": "unrounded NUMERIC(28,8); display precision configured by currency",
        "journal_level_testable": batch.kind in {"gl", "journals"},
        "balanced": total == 0,
        "debit_credit_difference": str(total),
        "total_debit": str(sum((r["debit"] for r in lines), Decimal(0))),
        "total_credit": str(sum((r["credit"] for r in lines), Decimal(0))),
        "mapped_accounts": sum(
            bool(r["classification"]) and r["classification"] != "Unclassified" for r in lines
        ),
        "unmapped_accounts": sum(
            not r["classification"] or r["classification"] == "Unclassified" for r in lines
        ),
        "lines": lines,
        "completeness": "independent_controls_required",
    }


async def financial_workspace(db, ctx, snapshot_id, comparison_id=None):
    """Read-only view over committed populations, including historical sources."""
    from decimal import localcontext

    with localcontext() as precision:
        precision.prec = 48
        return await _financial_workspace(db, ctx, snapshot_id, comparison_id)


async def _financial_workspace(db, ctx, snapshot_id, comparison_id):
    snapshot = await scoped(db, ctx, ImportSnapshot, snapshot_id)
    result = await balance(db, ctx, snapshot_id)
    result["current_accounts"] = len(result["lines"])
    batch = await scoped(db, ctx, ImportBatch, snapshot.batch_id)
    period = await scoped(db, ctx, FinancialPeriod, snapshot.period_id)
    result["source_status"] = batch.status
    result["period"] = {"start": str(period.start_date), "end": str(period.end_date)}
    candidates = (
        await db.execute(
            select(
                ImportSnapshot.id,
                FinancialPeriod.start_date,
                FinancialPeriod.end_date,
                ImportBatch.status,
            )
            .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
            .join(FinancialPeriod, FinancialPeriod.id == ImportSnapshot.period_id)
            .where(
                ImportSnapshot.tenant_id == ctx.tenant_id,
                ImportBatch.tenant_id == ctx.tenant_id,
                FinancialPeriod.tenant_id == ctx.tenant_id,
                ImportSnapshot.entity_id == snapshot.entity_id,
                ImportSnapshot.client_id == snapshot.client_id,
                FinancialPeriod.end_date < period.start_date,
                ImportBatch.status.in_(["active", "superseded"]),
                ImportBatch.kind.in_(["gl", "journals", "tb"]),
            )
            .order_by(FinancialPeriod.end_date.desc(), ImportSnapshot.created_at.desc())
            .limit(100)
        )
    ).all()
    result["comparison_candidates"] = [
        {"id": str(r.id), "label": f"{r.start_date} – {r.end_date} · {r.status} · {str(r.id)[:8]}"}
        for r in candidates
    ]
    result["comparison_snapshot_id"] = None
    if comparison_id:
        prior = await scoped(db, ctx, ImportSnapshot, comparison_id)
        prior_period = await scoped(db, ctx, FinancialPeriod, prior.period_id)
        if (prior.entity_id, prior.client_id) != (snapshot.entity_id, snapshot.client_id):
            raise HTTPException(422, "Comparison client/entity mismatch")
        if prior_period.end_date >= period.start_date:
            raise HTTPException(422, "Comparison period must precede current period")
        previous = await balance(db, ctx, comparison_id)
        if previous["functional_currency"] != result["functional_currency"]:
            raise HTTPException(422, "Comparative functional currencies differ")
        movement = {
            r["account_code"]: r
            for r in movements(
                {r["code"]: r["closing"] for r in result["lines"]},
                {r["code"]: r["closing"] for r in previous["lines"]},
            )
        }
        current_codes = {r["code"] for r in result["lines"]}
        result["lines"] += [
            {
                **r,
                "opening": Decimal(0),
                "debit": Decimal(0),
                "credit": Decimal(0),
                "closing": Decimal(0),
                "display_closing": "0",
                "comparison_only": True,
            }
            for r in previous["lines"]
            if r["code"] not in current_codes
        ]
        for row in result["lines"]:
            values = movement[row["code"]]
            row.update(
                previous=values["previous"],
                variance=values["variance"],
                percentage=values["percentage"],
            )
        result["comparison_snapshot_id"] = str(comparison_id)
    controls = (
        (
            await db.execute(
                text(
                    "SELECT rule,status,evidence FROM import_validation_results WHERE tenant_id=:tenant AND batch_id=:batch AND rule IN ('source_count','source_total_debit','source_total_credit')"
                ),
                {"tenant": ctx.tenant_id, "batch": batch.id},
            )
        )
        .mappings()
        .all()
    )
    required = {"source_count", "source_total_debit", "source_total_credit"}
    passed = {r["rule"] for r in controls if r["status"] == "passed"}
    result["source_controls"] = [dict(r) for r in controls]
    result["completeness"] = (
        "failed"
        if any(r["status"] == "failed" for r in controls)
        else "controls_reconciled"
        if required <= passed
        else "independent_controls_required"
    )
    result["monthly_movements"] = []
    if batch.kind in {"gl", "journals"}:
        monthly = (
            (
                await db.execute(
                    text(
                        "SELECT to_char(posting_date,'YYYY-MM') AS month_label, SUM(base_debit) debit, SUM(base_credit) credit FROM journal_lines WHERE tenant_id=:tenant AND batch_id=:batch AND NOT opening GROUP BY 1 ORDER BY 1"
                    ),
                    {"tenant": ctx.tenant_id, "batch": batch.id},
                )
            )
            .mappings()
            .all()
        )
        result["monthly_movements"] = [
            {
                "id": r["month_label"],
                "month": r["month_label"],
                "debit": str(r["debit"]),
                "credit": str(r["credit"]),
            }
            for r in monthly
        ]
    result["monthly_testable"] = batch.kind in {"gl", "journals"}
    return result


async def persist_balance(db: AsyncSession, ctx: Context, snapshot_id: uuid.UUID):
    snapshot = await scoped(db, ctx, ImportSnapshot, snapshot_id)
    result = await balance(db, ctx, snapshot_id)
    run = TrialBalance(
        **scope_values(snapshot),
        snapshot_id=snapshot.id,
        currency=result["functional_currency"],
        status="balanced" if result["balanced"] else "unbalanced",
        evidence={k: v for k, v in result.items() if k != "lines"},
    )
    db.add(run)
    await db.flush()
    records = [
        dict(
            id=uuid.uuid4(),
            **scope_values(snapshot),
            trial_balance_id=run.id,
            account_id=r["id"],
            opening=r["opening"],
            debit=r["debit"],
            credit=r["credit"],
            closing=r["closing"],
        )
        for r in result["lines"]
    ]
    for offset in range(0, len(records), 1000):
        await db.execute(insert(TrialBalanceLine), records[offset : offset + 1000])
    return {"id": run.id, "status": run.status, "result": result}


async def run_reconciliation(
    db: AsyncSession,
    ctx: Context,
    snapshot_id: uuid.UUID,
    comparison_id: uuid.UUID | None,
    tolerance: Decimal,
):
    snapshot = await scoped(db, ctx, ImportSnapshot, snapshot_id)
    batch = await scoped(db, ctx, ImportBatch, snapshot.batch_id)
    current = await balance(db, ctx, snapshot_id)
    checks = []
    differences = []
    rows = (
        await db.execute(
            text("SELECT count(*) FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch"),
            {"tenant": ctx.tenant_id, "batch": batch.id},
        )
    ).scalar_one()
    checks.append(
        {
            "test": "source_records_to_manifest_count",
            "status": "passed" if rows == batch.row_count == batch.valid_count else "failed",
            "source": batch.row_count,
            "calculated": rows,
        }
    )
    checks.append(
        {
            "test": "roll_forward",
            "status": "passed"
            if all(
                r["closing"] == r["opening"] + r["debit"] - r["credit"] for r in current["lines"]
            )
            else "failed",
        }
    )
    checks.append(
        {
            "test": "ledger_balance",
            "status": "passed" if current["balanced"] else "failed",
            "difference": current["debit_credit_difference"],
        }
    )
    controls = (
        (
            await db.execute(
                text(
                    "SELECT rule,status,evidence FROM import_validation_results WHERE tenant_id=:tenant AND batch_id=:batch AND rule IN ('source_count','source_total_debit','source_total_credit')"
                ),
                {"tenant": ctx.tenant_id, "batch": batch.id},
            )
        )
        .mappings()
        .all()
    )
    checks.extend(
        {"test": r["rule"], "status": r["status"], "evidence": r["evidence"]} for r in controls
    )
    missing = sum(r["classification"] is None for r in current["lines"])
    checks.append(
        {
            "test": "unmapped_accounts",
            "status": "warning" if missing else "passed",
            "count": missing,
        }
    )
    if batch.kind in {"gl", "journals"}:
        ledger_count = await db.scalar(
            text("SELECT count(*) FROM journal_lines WHERE tenant_id=:tenant AND batch_id=:batch"),
            {"tenant": ctx.tenant_id, "batch": batch.id},
        )
        checks.append(
            {
                "test": "journal_to_ledger_count",
                "status": "passed" if ledger_count == rows else "failed",
                "source": rows,
                "calculated": ledger_count,
            }
        )
        totals = (
            await db.execute(
                text(
                    "SELECT (SELECT COALESCE(SUM((canonical->>'base_debit')::numeric),0) FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch) source_debit,(SELECT COALESCE(SUM((canonical->>'base_credit')::numeric),0) FROM source_records WHERE tenant_id=:tenant AND batch_id=:batch) source_credit,COALESCE(SUM(base_debit),0) ledger_debit,COALESCE(SUM(base_credit),0) ledger_credit FROM journal_lines WHERE tenant_id=:tenant AND batch_id=:batch"
                ),
                {"tenant": ctx.tenant_id, "batch": batch.id},
            )
        ).one()
        checks.append(
            {
                "test": "source_to_normalized_totals",
                "status": "passed"
                if abs(totals[0] - totals[2]) <= tolerance
                and abs(totals[1] - totals[3]) <= tolerance
                else "failed",
                "source_debit": str(totals[0]),
                "source_credit": str(totals[1]),
                "calculated_debit": str(totals[2]),
                "calculated_credit": str(totals[3]),
            }
        )

    else:
        checks.append({"test": "journal_to_ledger", "status": "not_testable"})
    if comparison_id == snapshot_id:
        raise HTTPException(422, "An independent comparison snapshot must be distinct")
    if comparison_id:
        previous_snapshot = await scoped(db, ctx, ImportSnapshot, comparison_id)
        if (
            previous_snapshot.entity_id != snapshot.entity_id
            or previous_snapshot.client_id != snapshot.client_id
        ):
            raise HTTPException(422, "Comparison client/entity mismatch")
        previous = await balance(db, ctx, comparison_id)
        if previous["functional_currency"] != current["functional_currency"]:
            raise HTTPException(422, "Comparative functional currencies differ")
        source = {r["code"]: r["closing"] for r in previous["lines"]}
        computed = {r["code"]: r["closing"] for r in current["lines"]}
        if previous_snapshot.period_id == snapshot.period_id:
            match = reconcile(source, computed, tolerance)
            checks.append({"test": "gl_to_source_tb", **match})
            differences = match["differences"]
            for component in ["opening", "debit", "credit"]:
                component_match = reconcile(
                    {r["code"]: r[component] for r in previous["lines"]},
                    {r["code"]: r[component] for r in current["lines"]},
                    tolerance,
                )
                checks.append({"test": "gl_to_source_tb_" + component, **component_match})
                differences.extend(
                    {**d, "component": component} for d in component_match["differences"]
                )

        else:
            checks.append(
                {
                    "test": "comparative_movements",
                    "status": "information",
                    "movements": movements(computed, source),
                }
            )
            prior_closing = source
            opening = {r["code"]: r["opening"] for r in current["lines"]}
            match = reconcile(prior_closing, opening, tolerance)
            checks.append({"test": "opening_to_prior_closing", **match})
            differences = match["differences"]
    else:
        checks.append({"test": "independent_gl_to_tb", "status": "not_testable"})
    checks.append(
        {
            "test": "source_system_completeness",
            "status": "passed"
            if batch.options.get("source_complete")
            and len(controls) == 3
            and all(c["status"] == "passed" for c in controls)
            else "insufficient_evidence",
        }
    )
    statuses = {c["status"] for c in checks}
    status = (
        "failed"
        if "failed" in statuses
        else "insufficient_evidence"
        if statuses & {"not_testable", "insufficient_evidence"}
        else "warning"
        if "warning" in statuses
        else "passed"
    )
    result = {
        "status": status,
        "tolerance": str(tolerance),
        "snapshot_id": str(snapshot_id),
        "comparison_snapshot_id": str(comparison_id) if comparison_id else None,
        "checks": checks,
        "note": "Balanced totals alone do not establish completeness",
    }
    run = ReconciliationRun(
        **scope_values(snapshot),
        snapshot_id=snapshot.id,
        comparison_snapshot_id=comparison_id,
        status=status,
        result=result,
    )
    db.add(run)
    await db.flush()
    for exception in differences:
        db.add(
            ReconciliationException(
                **scope_values(snapshot),
                run_id=run.id,
                account_code=exception["account_code"],
                details=exception,
            )
        )
    return {"id": run.id, "status": status, "result": result}
