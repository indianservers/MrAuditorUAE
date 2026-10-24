"""Bounded deterministic tax formulas. Legal judgments remain approved inputs."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from app.modules.ifrs.calculations import serial
from app.modules.tax.schemas import QFZP, SBR, Interest, RuleParameters

D = Decimal
ZERO = D(0)
QFZP_REQUIRED = {
    "free_zone_person",
    "qualifying_income",
    "substance",
    "audited_financials",
    "transfer_pricing",
    "no_standard_tax_election",
    "intellectual_property",
    "immovable_property",
    "permanent_establishments",
    "commodity_trading",
    "distribution",
    "treasury",
    "outsourcing",
    "cessation_history",
}
CORE_QFZP = {
    "free_zone_person",
    "qualifying_income",
    "substance",
    "audited_financials",
    "transfer_pricing",
    "no_standard_tax_election",
    "cessation_history",
}


def q(value):
    return value.quantize(D("0.00000001"), rounding=ROUND_HALF_UP)


def standard_tax(income, parameters: RuleParameters):
    with localcontext() as ctx:
        ctx.prec = 64
        return q(max(ZERO, D(income) - parameters.standard_threshold) * parameters.standard_rate)


def filing_deadline(period_end: date, months: int):
    index = period_end.year * 12 + period_end.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    day = (
        monthrange(year, month)[1]
        if period_end.day == monthrange(period_end.year, period_end.month)[1]
        else min(period_end.day, monthrange(year, month)[1])
    )
    return date(year, month, day)


def adjustment_amount(data, parameters):
    value = data.accounting_amount
    if data.category == "entertainment":
        if value < 0:
            raise ValueError("Entertainment expense cannot be negative")
        result = (
            ZERO
            if data.entertainment_scope == "employees_only"
            else data.proposed_adjustment
            if data.entertainment_scope == "other_review"
            else q(value * parameters.entertainment_disallowance)
        )
    elif (
        data.category in {"fine", "nondeductible", "nonbusiness"}
        and data.treatment == "statutory_disallowance"
    ):
        if value < 0:
            raise ValueError("Disallowed expense cannot be negative")
        result = value
    elif data.treatment == "no_adjustment":
        result = ZERO
    else:
        result = data.proposed_adjustment
    if result != data.proposed_adjustment:
        raise ValueError("Proposed adjustment differs from selected statutory treatment")
    return result


def small_business(data: SBR, profile, parameters: RuleParameters):
    checks = {
        "resident": profile.resident,
        "period_start": profile.tax_start >= date(2023, 6, 1),
        "period_end": profile.tax_end <= parameters.sbr_last_period_end,
        "revenue": profile.revenue <= parameters.revenue_threshold,
        "history_complete": data.prior_periods_complete,
        "prior_revenues": all(x <= parameters.revenue_threshold for x in data.prior_revenues),
        "not_qfzp": not data.is_qfzp and profile.classification != "qfzp",
        "not_excluded_mne": not data.excluded_multinational and not profile.pillar_two_in_scope,
        "anti_fragmentation": not data.artificial_separation,
        "election": data.election_made,
    }
    return {
        "eligible_and_elected": all(checks.values()),
        "checks": checks,
        "scope": "Human historical completeness/aggregation facts; no automatic election",
    }


def interest(data: Interest, parameters: RuleParameters):
    with localcontext() as ctx:
        ctx.prec = 64
        if data.period_months > 24:
            raise ValueError("Supported tax period length is at most24months")
        if (
            data.excluded_expense + data.permanent_disallowances
            > data.interest_expense + data.capitalised_amortisation
            or data.excluded_income > data.interest_income
        ):
            raise ValueError("Interest exclusions exceed reconciled interest")
        if data.excluded_taxpayer and not data.exclusion_basis.strip():
            raise ValueError("Taxpayer exclusion needs legal assessment")
        expense = (
            data.interest_expense
            + data.capitalised_amortisation
            - data.excluded_expense
            - data.permanent_disallowances
        )
        income = data.interest_income - data.excluded_income
        nie = max(ZERO, expense - income)
        ebidta = max(
            ZERO,
            data.taxable_before_gidlr_losses
            + nie
            + data.depreciation_tax_deductible
            + data.historical_net_interest_adjustment
            + data.infrastructure_net_interest_adjustment,
        )
        threshold = parameters.interest_threshold * data.period_months / 12
        cap = max(threshold, ebidta * parameters.interest_percentage)
        available: list[Any] = []
        expired: list[Any] = []
        for row in sorted(data.carryforwards, key=lambda x: x.origin_period_index):
            age = data.period_index - row.origin_period_index
            if age <= 0:
                raise ValueError("Carried interest must originate in an earlier period")
            (available if age <= parameters.interest_carry_periods else expired).append(row)
        if data.excluded_taxpayer:
            # No automatic deduction of old GIDLR carryforwards in excluded-taxpayer cases.
            return serial(
                {
                    "net_interest": nie,
                    "adjusted_ebitda": ebidta,
                    "threshold": threshold,
                    "limit": nie,
                    "current_deductible": nie,
                    "current_disallowed": ZERO,
                    "carryforward_used": ZERO,
                    "tax_adjustment": data.permanent_disallowances,
                    "carryforward": [x.model_dump() for x in data.carryforwards],
                    "scope": "Current interest exclusion assessed; old carryforwards require separate review",
                }
            )
        remaining = cap
        movements = []
        used = ZERO
        for row in available:
            deduction = min(row.balance, remaining)
            remaining -= deduction
            used += deduction
            movements.append(
                {
                    "origin_period_index": row.origin_period_index,
                    "opening": row.balance,
                    "used": deduction,
                    "closing": row.balance - deduction,
                    "expired": False,
                }
            )
        current_deductible = min(nie, remaining)
        disallowed = nie - current_deductible
        for row in expired:
            movements.append(
                {
                    "origin_period_index": row.origin_period_index,
                    "opening": row.balance,
                    "used": ZERO,
                    "closing": ZERO,
                    "expired": True,
                }
            )
        return serial(
            {
                "net_interest": nie,
                "adjusted_ebitda": ebidta,
                "threshold": q(threshold),
                "percentage_limit": q(ebidta * parameters.interest_percentage),
                "limit": q(cap),
                "current_deductible": q(current_deductible),
                "current_disallowed": q(disallowed),
                "carryforward_used": used,
                "tax_adjustment": q(data.permanent_disallowances + disallowed - used),
                "new_carryforward": q(disallowed),
                "carryforward": movements,
                "capitalised_incurred_not_currently_deducted": data.capitalised_incurred,
                "scope": "Statutory bridge supplied and professionally assessed; FIFO old interest precedes current; ten-period aging",
            }
        )


def qfzp(data: QFZP, profile, parameters: RuleParameters):
    with localcontext() as ctx:
        ctx.prec = 64
        if len({r.reference for r in data.segments}) != len(data.segments):
            raise ValueError("Duplicate income segment reference")
        conditions = {x.requirement: x for x in data.conditions}
        if len(conditions) != len(data.conditions):
            raise ValueError("Duplicate QFZP condition")
        required = QFZP_REQUIRED | (
            {"fta_2026_procedures"}
            if data.distribution_activity
            and getattr(profile, "tax_start", date(2026, 1, 1)) >= date(2026, 1, 1)
            and getattr(profile, "legal_as_of", date(2026, 10, 18)) >= date(2026, 6, 2)
            else set()
        )
        unresolved = sorted(required - set(conditions))
        if (
            data.distribution_activity
            and getattr(profile, "tax_start", date(2026, 1, 1)) >= date(2026, 1, 1)
            and getattr(profile, "legal_as_of", date(2026, 10, 18)) >= date(2026, 6, 2)
            and not data.procedures_2026_applicable
        ):
            unresolved.append("FTA6/2026 applicability contradicts distribution facts")
        failed = []
        for key, row in conditions.items():
            if row.assessment == "FAIL":
                failed.append(key)
            elif (
                row.assessment not in {"PASS", "NOT_APPLICABLE"}
                or row.assessment == "PASS"
                and not row.evidence_record_ids
                or key in CORE_QFZP
                and row.assessment == "NOT_APPLICABLE"
            ):
                unresolved.append(key)
        total = sum((x.revenue for x in data.segments), ZERO)
        if total != profile.revenue:
            unresolved.append("revenue_reconciliation")
        denominator = ZERO
        numerator = ZERO
        uncertain_revenue = ZERO
        confirmed_nonqualifying = ZERO
        qual_profit = ZERO
        special_profit = ZERO
        for segment in data.segments:
            if segment.classification == "unresolved" or segment.counterparty_type == "unknown":
                unresolved.append(segment.reference)
            if segment.classification == "qualifying_ip":
                unresolved.append("IP nexus calculation unsupported: " + segment.reference)
            if segment.denominator_excluded:
                if (
                    segment.classification
                    not in {
                        "domestic_pe",
                        "foreign_pe",
                        "immovable_property",
                        "qualifying_ip",
                        "other_ip",
                    }
                    or not segment.exclusion_legal_basis.strip()
                ):
                    raise ValueError(
                        "De minimis exclusion requires a legally assessed special income category"
                    )
            else:
                denominator += segment.revenue
                if segment.classification == "unresolved" or segment.counterparty_type == "unknown":
                    uncertain_revenue += segment.revenue
                if segment.classification in {"nonqualifying", "excluded", "other_ip"}:
                    numerator += segment.revenue
                    if segment.counterparty_type != "unknown":
                        confirmed_nonqualifying += segment.revenue
            if segment.classification in {"qualifying", "nonqualifying", "excluded"}:
                qual_profit += segment.taxable_profit
            else:
                special_profit += segment.taxable_profit
        limit = min(parameters.de_minimis_cap, denominator * parameters.de_minimis_rate)
        de_minimis = numerator <= limit
        if not de_minimis:
            failed.append("de_minimis")
        if not profile.free_zone:
            failed.append("free_zone_status")
        if data.earlier_disqualification_remaining:
            failed.append("historic_disqualification")
            if not data.earlier_disqualification_source.strip():
                unresolved.append("historic_disqualification_evidence")
        status = "FAIL" if failed else "INSUFFICIENT_DATA" if unresolved else "PASS"
        return serial(
            {
                "assessment": status,
                "aup_submission_due": str(
                    filing_deadline(profile.tax_end, parameters.filing_months) + timedelta(days=30)
                )
                if data.procedures_2026_applicable and hasattr(profile, "tax_end")
                else None,
                "total_revenue": total,
                "denominator": denominator,
                "nonqualifying_revenue": numerator,
                "threshold": q(limit),
                "de_minimis_passed": de_minimis,
                "classification_sensitivity": {
                    "confirmed_nonqualifying": confirmed_nonqualifying,
                    "unresolved_revenue": uncertain_revenue,
                    "maximum_nonqualifying": confirmed_nonqualifying + uncertain_revenue,
                    "all_unresolved_nonqualifying_passes": confirmed_nonqualifying + uncertain_revenue <= limit,
                    "all_unresolved_qualifying_passes": confirmed_nonqualifying <= limit,
                    "conclusion": "UNRESOLVED" if uncertain_revenue else "CLASSIFIED_INPUTS_ONLY",
                },
                "qualifying_profit_if_qualified": qual_profit,
                "special_nonqualifying_profit": special_profit,
                "qfzp_tax_if_qualified": q(max(ZERO, special_profit) * parameters.standard_rate)
                if status == "PASS"
                else None,
                "unresolved": sorted(set(unresolved)),
                "failed": failed,
                "disqualification_periods_including_current": parameters.disqualification_periods
                if failed and not data.earlier_disqualification_remaining
                else data.earlier_disqualification_remaining,
                "conditions": [x.model_dump() for x in data.conditions],
                "segments": [x.model_dump() for x in data.segments],
                "scope": "Explicit transaction classifications; incidental income treatment depends on passed de minimis; special categories separately assessed; no automatic QFZP declaration",
            }
        )


def loss_allocation(taxable, percentage, lots):
    with localcontext() as ctx:
        ctx.prec = 64
        if len({str(lot["id"]) for lot in lots}) != len(lots):
            raise ValueError("Duplicate loss lot would duplicate utilization")
        if not ZERO <= percentage <= 1 or any(D(lot["available"]) < 0 for lot in lots):
            raise ValueError("Invalid loss cap or carryforward balance")
        remaining = max(ZERO, D(taxable)) * percentage
        allocations = []
        for lot in lots:
            amount = min(max(ZERO, D(lot["available"])), remaining)
            allocations.append(
                {
                    "loss_id": str(lot["id"]),
                    "opening": str(lot["available"]),
                    "used": str(amount),
                    "closing": str(D(lot["available"]) - amount),
                }
            )
            remaining -= amount
        return allocations


def sample_size(population: int):
    if population < 0:
        raise ValueError("Invalid population")
    return int(
        (D(population) / (1 + D(population) * D("0.1") ** 2)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
