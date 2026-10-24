"""Deterministic Decimal engines; scope and formulas are explicit in every result."""

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any
from uuid import UUID

from app.modules.ifrs import schemas as s
from app.modules.ifrs.employee_benefits import employee_benefits
from app.modules.ifrs.inventory import inventory

D = Decimal
ZERO = D(0)
ONE = D(1)


def q(value):
    return value.quantize(D("0.00000001"), rounding=ROUND_HALF_UP)


def serial(value):
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def growth(rate, days):
    return (ONE + rate) ** (D(days) / D(365))


def lease(data: s.Lease):
    payments = sorted(data.payments, key=lambda p: p.date)
    future = [p for p in payments if p.date > data.commencement]
    upfront = sum((p.amount for p in payments if p.date == data.commencement), ZERO)
    liability = sum(
        (
            p.amount / growth(data.annual_discount_rate, (p.date - data.commencement).days)
            for p in future
        ),
        ZERO,
    )
    rou = (
        liability
        + upfront
        + data.initial_direct_costs
        - data.incentive_received
        + data.restoration_obligation
    )
    if rou < 0:
        raise ValueError("Incentive exceeds recognized right-of-use asset components")
    balance = liability
    previous = data.commencement
    rows: list[dict[str, Any]] = []
    current = ZERO
    for payment in future:
        opening = balance
        interest = balance * (growth(data.annual_discount_rate, (payment.date - previous).days) - 1)
        principal = payment.amount - interest
        balance = opening + interest - payment.amount
        if payment.date <= data.commencement + timedelta(days=365):
            current += principal
        rows.append(
            {
                "date": str(payment.date),
                "opening": q(opening),
                "interest": q(interest),
                "payment": payment.amount,
                "principal": q(principal),
                "closing": q(balance),
                "rou_depreciation": q(
                    rou
                    * D((payment.date - previous).days)
                    / D((data.end_date - data.commencement).days)
                ),
            }
        )
        previous = payment.date
    return {
        "initial_liability": q(liability),
        "upfront_payments": upfront,
        "initial_rou": q(rou),
        "current_liability": q(current),
        "noncurrent_liability": q(liability - current),
        "rou_daily_depreciation": q(rou / D((data.end_date - data.commencement).days)),
        "rou_depreciation_after_last_payment": q(
            rou * D((data.end_date - previous).days) / D((data.end_date - data.commencement).days)
        ),
        "rou_total_depreciation": q(rou),
        "schedule": rows,
        "interest_total": q(sum((r["interest"] for r in rows), ZERO)),
        "closing_liability": q(balance),
        "variable_payments_excluded": data.variable_payments_excluded,
        "method": "Dated contractual payments; annual effective rate; actual/365; straight-line ROU to end date",
        "journal_proposals": [
            {"debit": "ROU asset", "credit": "Lease liability", "amount": q(liability)},
            {
                "debit": "ROU asset",
                "credit": "Cash/prepayments/restoration allocation requires human accounts",
                "amount": q(rou - liability),
            },
        ],
    }


def ecl(data: s.ECL):
    rows: list[dict[str, Any]] = []
    for exposure in data.exposures:
        scenarios = []
        for scenario in data.scenarios:
            if data.approach == "provision_matrix":
                loss = exposure.amount * min(
                    ONE, data.segment_loss_rates[exposure.segment] * scenario.forward_multiplier
                )
                # Matrix loss rates are assumed to incorporate timing; no silent extra discount.
            elif scenario.cash_shortfall is not None:
                if scenario.cash_shortfall > exposure.amount:
                    raise ValueError(
                        "Cash shortfall cannot exceed this exposure in the bounded model"
                    )
                loss = (
                    scenario.cash_shortfall
                    / (ONE + data.effective_interest_rate) ** exposure.years_to_shortfall
                )
            else:
                pd = (
                    ONE
                    if exposure.stage == 3
                    else scenario.pd_12_month
                    if exposure.stage == 1 and data.approach == "general"
                    else scenario.pd_lifetime
                )
                loss = (
                    exposure.amount
                    * min(ONE, pd * scenario.forward_multiplier)
                    * scenario.lgd
                    / (ONE + data.effective_interest_rate) ** exposure.years_to_shortfall
                )
            scenarios.append(
                {
                    "scenario": scenario.name,
                    "probability": scenario.probability,
                    "loss": q(loss),
                    "weighted_loss": q(loss * scenario.probability),
                }
            )
        rows.append(
            {
                "reference": exposure.reference,
                "exposure": exposure.amount,
                "stage": exposure.stage,
                "segment": exposure.segment,
                "ecl": q(sum((r["weighted_loss"] for r in scenarios), ZERO)),
                "scenarios": scenarios,
            }
        )
    return {
        "schedule": rows,
        "total_exposure": sum((e.amount for e in data.exposures), ZERO),
        "total_ecl": q(sum((r["ecl"] for r in rows), ZERO)),
        "method": "Probability-weighted discounted PD/LGD or explicit cash shortfall; provision matrix uses approved timing-inclusive loss rates",
        "limitations": [
            "Stage/SICR/default and scenario assumptions require human approval",
            "No aging-only inference",
            "12-month PD weights lifetime shortfalls arising from defaults in the next 12 months",
        ],
    }


def instrument(data: s.Instrument):
    if data.classification != "amortised_cost":
        raise ValueError(
            "FVOCI/FVTPL classification is recorded, but fair-value measurement requires a separate approved valuation"
        )
    if (
        any(p.date <= data.initial_date for p in data.cash_flows)
        or sum((p.amount for p in data.cash_flows), ZERO) < data.initial_amount
    ):
        raise ValueError(
            "Bounded EIR solver requires future nonnegative receipts and a nonnegative yield"
        )

    def npv(rate):
        return (
            sum(
                (
                    p.amount / growth(rate, (p.date - data.initial_date).days)
                    for p in data.cash_flows
                ),
                ZERO,
            )
            - data.initial_amount
        )

    lo, hi = ZERO, D(10)
    if npv(hi) > 0:
        raise ValueError("EIR is outside the supported nonnegative 0–1000% interval")
    for _ in range(180):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    rate = (lo + hi) / 2
    bal = data.initial_amount
    previous = data.initial_date
    rows: list[dict[str, Any]] = []
    for p in sorted(data.cash_flows, key=lambda p: p.date):
        interest = bal * (growth(rate, (p.date - previous).days) - 1)
        closing = bal + interest - p.amount
        rows.append(
            {
                "date": str(p.date),
                "opening": q(bal),
                "interest": q(interest),
                "receipt": p.amount,
                "closing": q(closing),
            }
        )
        bal, previous = closing, p.date
    return {
        "effective_annual_rate": rate,
        "schedule": rows,
        "closing": q(bal),
        "method": "Monotonic Decimal bisection; dated actual/365 effective-interest schedule",
    }


def revenue(data: s.Revenue):
    if len({o.reference for o in data.obligations}) != len(data.obligations):
        raise ValueError("Duplicate performance obligation")
    price = data.fixed_price + data.constrained_variable_consideration
    total_ssp = sum((o.standalone_price for o in data.obligations), ZERO)
    allocated = ZERO
    rows: list[dict[str, Any]] = []
    for index, o in enumerate(data.obligations):
        amount = (
            price - allocated
            if index == len(data.obligations) - 1
            else q(price * o.standalone_price / total_ssp)
        )
        allocated += amount
        if o.recognition == "over_time":
            if not o.over_time_justification.strip():
                raise ValueError("Over-time recognition requires human justification")
            progress = o.progress
        else:
            if o.satisfied_on is None:
                raise ValueError("Point-in-time satisfaction date required")
            progress = ONE if o.satisfied_on <= data.reporting_date else ZERO
        rows.append(
            {
                "reference": o.reference,
                "allocated_price": amount,
                "recognition": o.recognition,
                "progress": progress,
                "recognised": q(amount * progress),
                "remaining": q(amount * (1 - progress)),
            }
        )
    recognised = sum((r["recognised"] for r in rows), ZERO)
    return {
        "transaction_price": price,
        "schedule": rows,
        "recognised_to_date": recognised,
        "contract_asset": max(ZERO, recognised - data.billed_to_date),
        "contract_liability": max(ZERO, data.billed_to_date - recognised),
        "method": "Relative standalone-price allocation; human-validated cumulative satisfaction/progress",
        "modification_analysis": data.modification_analysis,
        "limitations": [
            "Modification classification is human-documented; no automatic legal interpretation or variable-consideration estimation"
        ],
    }


def deferred_tax(data: s.DeferredTax):
    rows: list[dict[str, Any]] = []
    allocations: dict[str, Decimal] = defaultdict(lambda: ZERO)
    if len({item.reference for item in data.differences}) != len(data.differences):
        raise ValueError("Duplicate deferred-tax difference reference")
    issues = []
    for item in data.differences:
        if item.item_type == "tax_loss" and item.tax_base < 0:
            raise ValueError("Tax loss basis must be a nonnegative eligible carryforward")
        if item.exception_applied and not item.exception_rationale.strip():
            raise ValueError("Tax exception requires a documented rationale")
        difference = (
            -abs(item.tax_base)
            if item.item_type == "tax_loss"
            else item.carrying_amount - item.tax_base
            if item.item_type == "asset"
            else item.tax_base - item.carrying_amount
        )
        potential = q(difference * item.tax_rate)
        recognised = (
            ZERO
            if item.exception_applied or potential < 0 and not item.recognise_dta
            else potential
        )
        if recognised < 0 and (
            not item.recoverability_evidence.strip()
            or not item.expected_recovery_or_settlement.strip()
        ):
            recognised = ZERO
            issues.append(
                {
                    "code": "DTA_RECOVERABILITY_UNEVIDENCED",
                    "reference": item.reference,
                    "blocking": True,
                    "remediation": "Supply assessed recovery timing and supporting taxable-profit forecasts/evidence",
                }
            )
        movement = recognised - item.previous_deferred_balance
        allocations[item.allocation] += movement
        rows.append(
            {
                "reference": item.reference,
                "jurisdiction": item.jurisdiction,
                "tax_rate": item.tax_rate,
                "temporary_difference": difference,
                "deferred_balance_dtl_positive": recognised,
                "unrecognised_dta": -potential if potential < 0 and recognised == 0 else ZERO,
                "movement": movement,
                "allocation": item.allocation,
                "rate_source": item.rate_source,
                "rate_effective_date": item.rate_effective_date,
                "expected_recovery_or_settlement": item.expected_recovery_or_settlement,
                "recoverability_evidence": item.recoverability_evidence,
            }
        )
    return {
        "schedule": rows,
        "dtl": sum((max(ZERO, r["deferred_balance_dtl_positive"]) for r in rows), ZERO),
        "dta": sum((max(ZERO, -r["deferred_balance_dtl_positive"]) for r in rows), ZERO),
        "movements": dict(allocations),
        "current_tax": data.current_tax,
        "issues": issues,
        "tax_basis": "Ordinary IAS 12 differences only; no E08 GloBE/Pillar Two deferred-tax measurement",
        "method": "Item-specific tax-base differences and approved rates; DTA recognition and exceptions are human assessments; no statutory tax computation",
    }


def fixed_assets(data: s.FixedAssets):
    if data.period_end < data.period_start:
        raise ValueError("Invalid asset period")
    rows: list[dict[str, Any]] = []
    if len({a.reference for a in data.assets}) != len(data.assets):
        raise ValueError("Duplicate fixed asset reference")
    for a in data.assets:
        if a.asset_class != "ppe":
            raise ValueError(
                "IAS 40, IFRS 5 and IAS 38 require separate specialist measurement; PPE depreciation is blocked"
            )
        if a.disposal_date and a.disposal_date < data.period_start:
            raise ValueError("Previously disposed assets must be excluded from the active register")
        if a.capitalisation_date > data.period_end:
            raise ValueError(
                "Future acquisitions must be excluded from the reporting-period register"
            )
        if a.opening_accumulated + a.impairment > a.cost + a.revaluation_increment:
            raise ValueError("Invalid asset residual/accumulated depreciation/impairment")
        if a.revaluation_increment and not a.revaluation_assessment.strip():
            raise ValueError("Revaluation requires approved rationale")
        # Derecognition ends depreciation; its date is excluded from the charge.
        end = (
            min(data.period_end, a.disposal_date - timedelta(days=1))
            if a.disposal_date
            else data.period_end
        )
        commencement = a.available_for_use_date or a.capitalisation_date
        start = max(data.period_start, commencement)
        days = max(0, (end - start).days + 1)
        opening = a.cost + a.revaluation_increment - a.opening_accumulated - a.impairment
        capacity = max(ZERO, opening - a.residual)
        annual = (
            (a.cost + a.revaluation_increment - a.residual) / a.useful_life_years
            if a.method == "straight_line"
            else opening * a.diminishing_rate
        )
        depreciation = (
            ZERO if a.construction_in_progress else min(capacity, max(ZERO, annual) * D(days) / 365)
        )
        estimate_bridge = None
        if a.estimate_change_date:
            if a.revised_residual is None or a.revised_remaining_life_years is None:
                raise ValueError(
                    "A dated estimate change requires revised residual and remaining life"
                )
            if not data.period_start <= a.estimate_change_date <= data.period_end:
                raise ValueError(
                    "Estimate change must fall in this period; revise opening estimates for earlier changes"
                )
            before_days = max(
                0, (min(end + timedelta(days=1), a.estimate_change_date) - start).days
            )
            prior_charge = (
                ZERO
                if a.construction_in_progress
                else min(capacity, max(ZERO, annual) * D(before_days) / 365)
            )
            carrying_at_change = opening - prior_charge
            if a.revised_residual > carrying_at_change:
                # IAS 16: residual above carrying gives a zero charge, not a negative expense.
                new_capacity = ZERO
            else:
                new_capacity = carrying_at_change - a.revised_residual
            after_days = max(0, (end - max(start, a.estimate_change_date)).days + 1)
            revised_charge = (
                ZERO
                if a.construction_in_progress
                else min(
                    new_capacity,
                    new_capacity / a.revised_remaining_life_years * D(after_days) / 365,
                )
            )
            depreciation = prior_charge + revised_charge
            estimate_bridge = {
                "effective_date": a.estimate_change_date,
                "prior_charge": q(prior_charge),
                "carrying_at_change": q(carrying_at_change),
                "revised_charge": q(revised_charge),
                "treatment": "Prospective; no restatement of prior depreciation",
            }
        before_disposal = opening - depreciation
        disposed = bool(a.disposal_date and data.period_start <= a.disposal_date <= data.period_end)
        rows.append(
            {
                "reference": a.reference,
                "component_of": a.component_of,
                "available_for_use_date": a.available_for_use_date,
                "commencement_verified": bool(
                    a.available_for_use_date and a.available_for_use_evidence
                ),
                "construction_in_progress": a.construction_in_progress,
                "estimate_change": estimate_bridge,
                "cost": a.cost,
                "cost_rollforward": {
                    "opening": a.cost if a.capitalisation_date < data.period_start else ZERO,
                    "additions": a.cost if a.capitalisation_date >= data.period_start else ZERO,
                    "revaluation": a.revaluation_increment,
                    "disposals": a.cost + a.revaluation_increment if disposed else ZERO,
                    "closing": ZERO if disposed else a.cost + a.revaluation_increment,
                },
                "accumulated_depreciation_rollforward": {
                    "opening": a.opening_accumulated,
                    "charge": q(depreciation),
                    "derecognised": q(a.opening_accumulated + depreciation) if disposed else ZERO,
                    "closing": ZERO if disposed else q(a.opening_accumulated + depreciation),
                },
                "opening_carrying": q(opening),
                "days": days,
                "depreciation": q(depreciation),
                "impairment": a.impairment,
                "disposal_carrying": q(before_disposal) if disposed else ZERO,
                "disposal_gain_loss": q(a.proceeds - before_disposal) if disposed else ZERO,
                "closing_carrying": ZERO if disposed else q(before_disposal),
            }
        )
    return {
        "schedule": rows,
        "total_depreciation": sum((r["depreciation"] for r in rows), ZERO),
        "closing_carrying": sum((r["closing_carrying"] for r in rows), ZERO),
        "method": "Daily actual/365 straight-line or stated annual diminishing rate; residual floor; separately documented components",
        "issues": [
            {
                "code": "AVAILABLE_FOR_USE_UNVERIFIED",
                "reference": a.reference,
                "blocking": True,
                "remediation": "Supply approved available-for-use date and evidence; legacy capitalisation-date calculation is provisional",
            }
            for a in data.assets
            if not a.construction_in_progress and not a.available_for_use_date
        ],
    }


def impairment(data: s.Impairment):
    if data.goodwill_included > data.carrying_amount:
        raise ValueError("Goodwill cannot exceed CGU carrying amount")
    viu = sum(
        (flow / (1 + data.discount_rate) ** i for i, flow in enumerate(data.cash_flows, 1)), ZERO
    )
    recoverable = max(viu, data.fair_value_less_disposal_costs)
    loss = max(ZERO, data.carrying_amount - recoverable)
    goodwill_loss = min(loss, data.goodwill_included)
    reversal = min(
        data.reversal_requested,
        data.reversal_cap_excluding_goodwill,
        max(ZERO, recoverable - data.carrying_amount),
    )
    sensitivities = [
        {
            "rate": max(ZERO, data.discount_rate + delta),
            "value_in_use": q(
                sum(
                    (
                        flow / (1 + max(ZERO, data.discount_rate + delta)) ** i
                        for i, flow in enumerate(data.cash_flows, 1)
                    ),
                    ZERO,
                )
            ),
        }
        for delta in [D("-.01"), ZERO, D(".01")]
    ]
    return {
        "value_in_use": q(viu),
        "recoverable_amount": q(recoverable),
        "impairment_loss": q(loss),
        "goodwill_loss": q(goodwill_loss),
        "other_asset_loss": q(loss - goodwill_loss),
        "permitted_reversal_excluding_goodwill": q(reversal),
        "sensitivity": sensitivities,
        "method": "Explicit period-end annual forecast present values; higher of VIU/FVLCD; goodwill first; no goodwill reversal",
    }


def provision(data: s.Provision):
    pv = (
        data.best_estimate / (1 + data.discount_rate) ** data.settlement_years
        if data.recognition == "provision"
        else ZERO
    )
    if data.utilisation + data.reversals > pv:
        raise ValueError("Provision movements exceed available obligation")
    return {
        "recognition": data.recognition,
        "present_value": q(pv),
        "opening": data.opening,
        "remeasurement": q(pv - data.opening),
        "utilisation": data.utilisation,
        "reversals": data.reversals,
        "closing": q(max(ZERO, pv - data.utilisation - data.reversals)),
        "method": "Human recognition assessment; discounted best estimate; no automatic legal-probability determination",
    }


ENGINES: dict[str, Callable[[Any], dict]] = {
    "lease": lease,
    "ecl": ecl,
    "instrument": instrument,
    "revenue": revenue,
    "deferred-tax": deferred_tax,
    "fixed-assets": fixed_assets,
    "impairment": impairment,
    "provision": provision,
    "inventory": inventory,
    "employee-benefits": employee_benefits,
}


def calculate(kind, body):
    with localcontext() as context:
        context.prec = 48
        data: Any = s.BODIES[kind].model_validate(body)
        return serial(ENGINES[kind](data))
