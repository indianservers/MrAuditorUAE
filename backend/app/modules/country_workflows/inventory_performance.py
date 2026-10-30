"""Explicit account-scoped stock and gross-profit comparisons from committed balances."""

import uuid
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.modules.ifrs.schemas import Money, Nonnegative
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "committed-inventory-performance/1"
METRICS = ("inventory", "revenue", "cost_of_sales")


class MetricSelection(Strict):
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    expected_accounts: int = Field(ge=1, le=100, strict=True)
    expected_amount: Money
    assessment: str = Field(min_length=10, max_length=2000)
    nil_inventory_assessment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def explicit_selection(self):
        if len(set(self.account_ids)) != len(self.account_ids):
            raise ValueError("Account selection must be distinct")
        if len(self.account_ids) != self.expected_accounts:
            raise ValueError("Selected accounts differ from the independent account-count control")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the complete account selection and measurement basis")
        return self


class PeriodSelection(Strict):
    snapshot_id: uuid.UUID
    inventory: MetricSelection
    revenue: MetricSelection
    cost_of_sales: MetricSelection

    @model_validator(mode="after")
    def disjoint_accounts(self):
        accounts = [
            identifier for metric in METRICS for identifier in getattr(self, metric).account_ids
        ]
        if len(set(accounts)) != len(accounts):
            raise ValueError("Inventory, revenue and cost-of-sales selections cannot overlap")
        for metric in METRICS:
            selection = getattr(self, metric)
            if metric == "inventory" and selection.expected_amount == 0:
                if len(selection.nil_inventory_assessment.strip()) < 10:
                    raise ValueError(
                        "Zero inventory needs an explicit nil/netting assessment and a retained ledger account"
                    )
            elif selection.nil_inventory_assessment:
                raise ValueError(
                    "Nil inventory assessment applies only to an explicit zero inventory balance"
                )
        return self


class InventoryPerformanceInput(Strict):
    current: PeriodSelection
    prior: PeriodSelection
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    periods_comparable: bool = Field(strict=True)
    comparability_assessment: str = Field(min_length=10, max_length=2000)
    stock_change_threshold_percent: Nonnegative
    gp_change_threshold_pp: Nonnegative
    rounding_places: int = Field(ge=0, le=8, strict=True)
    rounding_method: Literal["HALF_UP", "HALF_EVEN"]
    label: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def distinct_periods(self):
        if self.current.snapshot_id == self.prior.snapshot_id:
            raise ValueError("Current and prior snapshots must be distinct")
        if len(self.comparability_assessment.strip()) < 10 or len(self.rationale.strip()) < 10:
            raise ValueError("Assess period comparability and source scope explicitly")
        return self


def selected_values(selection, balance, side):
    """Check independently entered totals against exact selected account values."""
    links, controls, totals = [], [], {}
    by_id = {str(row["id"]): row for row in balance["lines"]}
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for metric in METRICS:
            scope = getattr(selection, metric)
            total = Decimal(0)
            for identifier in scope.account_ids:
                row = by_id.get(str(identifier))
                if row is None:
                    raise ValueError("Selected account is absent from the committed snapshot")
                opening, debit, credit, closing = (
                    Decimal(row[key]) for key in ("opening", "debit", "credit", "closing")
                )
                if opening + debit - credit != closing:
                    raise ValueError(
                        "Committed account opening/movement/closing arithmetic differs"
                    )
                amount = (
                    closing
                    if metric == "inventory"
                    else credit - debit
                    if metric == "revenue"
                    else debit - credit
                )
                total += amount
                links.append(
                    {
                        "period_side": side,
                        "metric": metric,
                        "snapshot_id": str(selection.snapshot_id),
                        "account_id": str(identifier),
                        "account_code": row["code"],
                        "account_name": row["name"],
                        "opening": str(opening),
                        "debit": str(debit),
                        "credit": str(credit),
                        "closing": str(closing),
                        "measurement_basis": "DEBIT_NORMAL_CLOSING"
                        if metric == "inventory"
                        else "CREDIT_MINUS_DEBIT_MOVEMENT"
                        if metric == "revenue"
                        else "DEBIT_MINUS_CREDIT_MOVEMENT",
                        "normalized_amount": str(amount),
                    }
                )
            if total != scope.expected_amount:
                raise ValueError(
                    f"Independent {side} {metric} amount control differs from selected committed accounts"
                )
            totals[metric] = total
            controls.append(
                {
                    "period_side": side,
                    "metric": metric,
                    "snapshot_id": str(selection.snapshot_id),
                    "expected_accounts": scope.expected_accounts,
                    "selected_accounts": len(scope.account_ids),
                    "expected_amount": str(scope.expected_amount),
                    "calculated_amount": str(total),
                    "assessment": scope.assessment,
                    "nil_inventory_assessment": scope.nil_inventory_assessment,
                    "zero_inventory_basis": "EXPLICIT_ZERO_LEDGER_BALANCE_ASSESSED"
                    if metric == "inventory" and total == 0
                    else None,
                }
            )
    return totals, links, controls


def calculate(data, balances, periods):
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        return _calculate(data, balances, periods)


def _calculate(data, balances, periods):
    values, links, controls = {}, [], []
    for side in ("current", "prior"):
        if balances[side]["functional_currency"] != data.currency:
            raise ValueError(
                "Both source snapshots must use the explicitly selected functional currency"
            )
        values[side], account_links, control_rows = selected_values(
            getattr(data, side), balances[side], side
        )
        links.extend(account_links)
        controls.extend(control_rows)
        values[side]["gross_profit"] = values[side]["revenue"] - values[side]["cost_of_sales"]
        revenue = values[side]["revenue"]
        values[side]["gp_margin_percent"] = (
            values[side]["gross_profit"] / revenue * 100 if revenue > 0 else None
        )
    quantum = Decimal(1).scaleb(-data.rounding_places)
    rounding = ROUND_HALF_UP if data.rounding_method == "HALF_UP" else ROUND_HALF_EVEN

    def displayed(value):
        return str(value.quantize(quantum, rounding=rounding)) if value is not None else None

    rows = []
    for metric in (*METRICS, "gross_profit", "gp_margin_percent"):
        current, prior = values["current"][metric], values["prior"][metric]
        difference = current - prior if current is not None and prior is not None else None
        change = None
        basis = (
            "PERCENTAGE_POINTS" if metric == "gp_margin_percent" else "PERCENT_OF_POSITIVE_PRIOR"
        )
        issues = []
        if not data.periods_comparable:
            issues.append("PERIODS_NOT_ASSESSED_COMPARABLE")
        elif difference is not None:
            if metric == "gp_margin_percent":
                change = difference
                if abs(change) > data.gp_change_threshold_pp:
                    issues.append("GP_MARGIN_CHANGE_EXCEEDS_ASSESSED_THRESHOLD")
            elif prior > 0:
                change = difference / prior * 100
                if metric == "inventory" and abs(change) > data.stock_change_threshold_percent:
                    issues.append("STOCK_CHANGE_EXCEEDS_ASSESSED_THRESHOLD")
        if metric == "gp_margin_percent" and (current is None or prior is None):
            issues.append("GP_MARGIN_UNDEFINED_WITHOUT_POSITIVE_REVENUE")
        if metric != "gp_margin_percent" and (current < 0 or prior < 0):
            issues.append("NEGATIVE_BALANCE_REQUIRES_ASSESSMENT")
        if metric != "gp_margin_percent" and prior <= 0:
            issues.append("PERCENT_CHANGE_UNDEFINED_WITHOUT_POSITIVE_PRIOR")
        rows.append(
            {
                "id": "performance:" + metric,
                "metric": metric,
                "currency": data.currency if metric != "gp_margin_percent" else None,
                "current_raw": str(current) if current is not None else None,
                "prior_raw": str(prior) if prior is not None else None,
                "current_display": displayed(current),
                "prior_display": displayed(prior),
                "amount_difference_raw": str(difference) if difference is not None else None,
                "change_raw": str(change) if change is not None else None,
                "change_display": displayed(change),
                "change_basis": basis,
                "exceptions": issues,
                "state": "EXCEPTIONS" if issues else "SUPPORTED",
            }
        )
    gp = rows[-1]
    gp_conclusion = (
        "Gross-profit margin comparison is not assessed comparable or lacks a positive revenue denominator; no trend conclusion is inferred."
        if gp["change_raw"] is None
        else f"Gross-profit margin moved from {gp['prior_display']}% to {gp['current_display']}%, a change of {gp['change_display']} percentage points. "
        + (
            "The absolute change exceeds the explicitly assessed threshold. "
            if gp["exceptions"]
            else "The absolute change does not exceed the explicitly assessed threshold. "
        )
        + "Causes and any audit conclusion require source-supported professional assessment."
    )
    return {
        "workflow": "inventory-performance",
        "title": data.label,
        "rationale": data.rationale,
        "rows": rows,
        "review_status": "UNVERIFIED",
        "blocked": not data.periods_comparable
        or any(not balance["balanced"] for balance in balances.values()),
        "exception_count": sum(bool(row["exceptions"]) for row in rows),
        "inventory_performance_contract": CONTRACT,
        "inventory_performance_binding": "COMMITTED_SNAPSHOT_ACCOUNT_CONTROLS_VERIFIED",
        "inventory_performance_scope": {
            "currency": data.currency,
            "periods": periods,
            "periods_comparable": data.periods_comparable,
            "comparability_assessment": data.comparability_assessment,
            "source_balance_status": {
                side: {
                    "balanced": balance["balanced"],
                    "debit_credit_difference": balance["debit_credit_difference"],
                }
                for side, balance in balances.items()
            },
            "stock_change_threshold_percent": str(data.stock_change_threshold_percent),
            "gp_change_threshold_pp": str(data.gp_change_threshold_pp),
            "rounding_places": data.rounding_places,
            "rounding_method": data.rounding_method,
        },
        "inventory_performance_links": links,
        "inventory_performance_controls": controls,
        "gp_arithmetic_observation": gp_conclusion,
        "population_completeness": "EXPLICIT_SNAPSHOT_ACCOUNT_SELECTION_ONLY",
        "statutory_calculation_qualified": False,
        "limitations": [
            "Account classifications, cost-of-sales scope, completeness and period comparability require explicit assessment; account names do not determine metrics",
            "Inventory uses debit-normal closing balances; revenue and cost of sales use signed period movements, excluding openings and preserving reversals",
            "Selected closing stock ties to selected committed account balances; this does not establish complete inventory population, physical existence, title or NRV",
            "Percentage change requires a positive prior denominator; gross-profit margin requires positive net revenue; unavailable percentages remain null",
            "Thresholds are engagement-assessed signals, not country legal rules; observations do not explain causes or issue an audit opinion",
            "No country framework, FX conversion, stock adjustment, tax filing, bank drawing power or lender eligibility is inferred",
        ],
    }


async def prepare(db, ctx, eng, data, request_id):
    from app.db.models.platform import FinancialPeriod, LegalEntity
    from app.modules.accounting.models import ImportBatch
    from app.modules.intelligence import service
    from app.modules.reconciliation.service import balance

    entity = await db.get(LegalEntity, eng.entity_id)
    if not entity or entity.functional_currency != data.currency:
        raise HTTPException(
            422, "Inventory performance uses entity functional currency without inferred FX"
        )
    balances, periods, dependencies = {}, {}, []
    contributors = {str(ctx.user_id)}
    for side in ("current", "prior"):
        source, receipt = await service.snapshot(
            db, ctx, eng, getattr(data, side).snapshot_id, side == "prior"
        )
        batch = await db.get(ImportBatch, source.batch_id)
        period = await db.get(FinancialPeriod, source.period_id)
        if batch.kind not in {"gl", "journals", "tb"} or not period:
            raise HTTPException(
                422,
                "Committed GL/journal or trial-balance sources and retained financial periods are required",
            )
        balances[side] = await balance(db, ctx, source.id)
        periods[side] = {
            "start": period.start_date.isoformat(),
            "end": period.end_date.isoformat(),
            "days": (period.end_date - period.start_date).days + 1,
            "snapshot_id": str(source.id),
            "sha256": source.sha256,
            "source_kind": batch.kind,
        }
        dependencies.append(receipt)
        for original in (source, batch):
            if original.created_by is not None:
                contributors.add(str(original.created_by))
    try:
        result = calculate(data, balances, periods)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    result["contributors"] = sorted(contributors)
    return await service.append(db, ctx, eng, "country-workflow", result, dependencies, request_id)
