"""Reproducible decimal mathematics; economic and legal conclusions remain reviewed facts."""

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, localcontext
from decimal import Decimal as D
from typing import Any

from app.modules.ifrs.calculations import serial

ZERO = D(0)


def q(value):
    return D(value).quantize(D("0.00000001"), rounding=ROUND_HALF_UP)


def ratio(numerator, denominator):
    return q(numerator / denominator) if denominator else None


def indicators(revenue, cost_sales, opex, assets):
    gp = revenue - cost_sales
    costs = cost_sales + opex
    op = revenue - costs
    return {
        "revenue": revenue,
        "cost_sales": cost_sales,
        "gross_profit": gp,
        "opex": opex,
        "operating_profit": op,
        "ebit": op,
        "operating_margin": ratio(op, revenue),
        "op_oc": ratio(op, costs),
        "gross_margin": ratio(gp, revenue),
        "gross_cost_plus": ratio(gp, cost_sales),
        "net_cost_plus": ratio(op, costs),
        "roa": ratio(op, assets),
        "cost_base": costs,
        "assets": assets,
        "undefined_ratios": [
            k
            for k, v in {
                "operating_margin": revenue,
                "op_oc": costs,
                "gross_margin": revenue,
                "roa": assets,
            }.items()
            if not v
        ],
    }


def allocate(amount, allocations):
    if len({x.segment for x in allocations}) != len(allocations):
        raise ValueError("Duplicate allocation recipient")
    total = sum((x.weight for x in allocations), ZERO)
    if total <= 0:
        raise ValueError("Positive allocation driver total required")
    rows = []
    accumulated = ZERO
    for index, row in enumerate(allocations):
        value = (
            amount - accumulated
            if index == len(allocations) - 1
            else q(amount * row.weight / total)
        )
        rows.append(
            {"segment": row.segment, "weight": row.weight, "amount": value, "driver_total": total}
        )
        accumulated += value
    assert accumulated == amount
    return rows


def segmentation(data, financial):
    source = {str(x["line_code"]): x for x in financial["lines"]}
    if len({x.financial_line_code for x in data.lines}) != len(data.lines):
        raise ValueError("Source financial line allocated more than once")
    missing = sorted(set(source) - {x.financial_line_code for x in data.lines})
    if missing:
        raise ValueError("All approved statement lines must be accounted for: " + ",".join(missing))
    result: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"revenue": ZERO, "cost_sales": ZERO, "opex": ZERO, "assets": ZERO}
    )
    trace = []
    for row in data.lines:
        if row.financial_line_code not in source:
            raise ValueError("Unknown financial statement line")
        original = source[row.financial_line_code]
        expected = {
            "revenue": {"income"},
            "cost_sales": {"expenses"},
            "opex": {"expenses"},
            "assets": {"assets"},
            "non_operating": {"income", "expenses", "oci"},
            "other": {"assets", "liabilities", "equity", "income", "expenses", "oci"},
        }
        if original["section"] not in expected[row.metric]:
            raise ValueError("Financial line section conflicts with metric")
        value = D(original["current"])
        if original["section"] == "income":
            value = -value
        amounts = allocate(value, row.allocation)
        for x in amounts:
            if row.metric in result[x["segment"]]:
                result[x["segment"]][row.metric] += x["amount"]
        trace.append(
            {
                "line_code": row.financial_line_code,
                "source_amount": value,
                "metric": row.metric,
                "classification": row.classification,
                "driver": row.driver,
                "methodology": row.methodology,
                "allocations": amounts,
                "difference": value - sum((x["amount"] for x in amounts), ZERO),
            }
        )
    return serial(
        {
            "segments": [
                {"segment": name, **indicators(**values)} for name, values in sorted(result.items())
            ],
            "trace": trace,
            "reconciled": all(x["difference"] == 0 for x in trace),
            "source_profit": financial["totals"]["profit"],
            "scope": "Complete statement allocation; operating/non-operating classifications require reviewed methodology",
        }
    )


def percentile(values, p, convention):
    n = len(values)
    if not n:
        return None
    if convention == "inclusive":
        index = D(n - 1) * p
    else:
        # Excel PERCENTILE.EXC: undefined when interpolation lies outside the sample.
        index = D(n + 1) * p - 1
        if index < 0 or index > n - 1:
            return None
    lo = int(index.to_integral_value(rounding=ROUND_FLOOR))
    hi = min(lo + 1, n - 1)
    return q(values[lo] + (values[hi] - values[lo]) * (index - lo))


def statistics(values, convention="inclusive"):
    present = sorted(D(x) for x in values if x is not None)
    histogram = []
    if present:
        low, high = present[0], present[-1]
        bins = 10 if high != low else 1
        width = (high - low) / bins
        for index in range(bins):
            lower, upper = low + index * width, low + (index + 1) * width
            count = sum(lower <= x < upper or index == bins - 1 and x == high for x in present)
            histogram.append({"lower": lower, "upper": upper, "count": count})
    return {
        "histogram": histogram,
        "n": len(present),
        "missing": len(values) - len(present),
        "minimum": present[0] if present else None,
        "maximum": present[-1] if present else None,
        "mean": q(sum(present, ZERO) / len(present)) if present else None,
        "median": percentile(present, D(".5"), "inclusive"),
        "lower_quartile": percentile(present, D(".25"), convention),
        "upper_quartile": percentile(present, D(".75"), convention),
        "quantile": convention,
        "interpolation": "linear; inclusive h=(n-1)p; exclusive h=(n+1)p-1, undefined outside sample",
        "scope": "Statistical range only; no automatic arm's length conclusion or median adjustment",
    }


def benchmark(observations, study):
    groups = defaultdict(list)
    annual = defaultdict(list)
    missing = []
    eligible = 0
    valid_observations = 0
    for obs in observations:
        if obs["currency"] != study.currency:
            raise ValueError(
                "Mixed currency population requires an explicit approved conversion dataset"
            )
        if obs["fiscal_year"] not in study.fiscal_years:
            continue
        eligible += 1
        if study.pli == "value":
            value = obs["value"]
        elif any(
            obs.get(key) is None
            for key in (
                ["revenue", "cost_sales"]
                if study.pli in {"gross_margin", "gross_cost_plus"}
                else ["revenue", "cost_sales", "opex"] + (["assets"] if study.pli == "roa" else [])
            )
        ):
            value = None
        else:
            value = indicators(
                obs["revenue"],
                obs["cost_sales"],
                obs.get("opex") or ZERO,
                obs.get("assets") or ZERO,
            )[study.pli]
        if value is not None:
            value += D(obs.get("financial_adjustment", 0))
        if value is None:
            missing.append(str(obs["id"]))
        else:
            valid_observations += 1
        annual[obs["fiscal_year"]].append(value)
        groups[obs["company_key"]].append((obs, value))
    values = []
    company_results = []
    for name, rows in sorted(groups.items()):
        valid = [x for x in rows if x[1] is not None]
        if study.aggregation == "year_specific":
            values += [x[1] for x in rows]
            continue
        if not valid:
            value = None
        elif study.aggregation == "company_unweighted":
            value = q(sum((x[1] for x in valid), ZERO) / len(valid))
        elif study.pli == "value":
            raise ValueError(
                "Weighted value observations require a documented exposure denominator; unsupported"
            )
        else:
            if any(D(x[0].get("financial_adjustment", 0)) for x in valid):
                raise ValueError(
                    "Weighted pooling requires adjustments to source financial amounts; PLI-point adjustments cannot be silently pooled"
                )
            totals = {
                key: sum((x[0].get(key) or ZERO for x in valid), ZERO)
                for key in ["revenue", "cost_sales", "opex", "assets"]
            }
            value = indicators(**totals)[study.pli]
        company_results.append({"company_key": name, "years": len(valid), "value": value})
        values.append(value)
    if missing and study.missing_policy == "reject":
        raise ValueError(
            "Accepted observations have missing metrics or zero denominators; explicitly reject them in screening or approve an exclusion policy"
        )
    summary = statistics(values, study.quantile)
    return serial(
        {
            **summary,
            "annual": {str(y): statistics(v, study.quantile) for y, v in sorted(annual.items())},
            "company_results": company_results,
            "missing_observation_ids": missing,
            "selected_target": study.selected_target,
            "target_rationale": study.target_rationale,
            "population": values,
            "observations_used": valid_observations,
            "observations_in_selected_years": eligible,
            "observations_outside_selected_years": len(observations) - eligible,
            "human_review_required": True,
        }
    )


def add_month(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def fraction(start, end, convention):
    if convention == "30E/360":
        return (
            D(
                (end.year - start.year) * 360
                + (end.month - start.month) * 30
                + min(end.day, 30)
                - min(start.day, 30)
            )
            / 360
        )
    return D((end - start).days) / (365 if convention == "ACT/365" else 360)


def loan_schedule(data):
    with localcontext() as ctx:
        ctx.prec = 64
        start, end = data.drawdown_date, data.calculation_end
        events = defaultdict(list)
        for row in data.cashflows:
            if not start <= row.date <= end:
                raise ValueError("Cashflow outside calculated loan interval")
            events[row.date].append(row)
        resets = {}
        for row in data.resets:
            if row.date in resets or not start <= row.date <= end:
                raise ValueError("Duplicate or out-of-period reset")
            resets[row.date] = row
        if data.interest_type == "fixed" and resets:
            raise ValueError("Fixed-rate loan cannot contain floating resets")
        compound_dates = set()
        if data.compounding != "none":
            months = 1 if data.compounding == "monthly" else 12
            index = months
            while (d := add_month(start, index)) <= end:
                compound_dates.add(d)
                index += months
        report_start = data.accrual_start or start
        dates = sorted({start, report_start, end, *events, *resets, *compound_dates})
        principal = data.principal
        capitalized = ZERO
        accrued = ZERO
        total_interest = ZERO
        period_interest = ZERO
        paid_interest = ZERO
        period_paid_interest = ZERO
        weighted_principal = ZERO
        weighted_rate = ZERO
        intervals = []
        rate = data.annual_rate
        for i, d in enumerate(dates):
            if i:
                previous = dates[i - 1]
                days = (d - previous).days
                interest = (principal + capitalized) * rate * fraction(previous, d, data.day_count)
                accrued += interest
                total_interest += interest
                if previous >= report_start:
                    period_interest += interest
                    weighted_principal += principal * days
                    weighted_rate += rate * principal * days
                intervals.append(
                    {
                        "start": previous,
                        "end": d,
                        "days": days,
                        "principal": q(principal),
                        "capitalized_interest": q(capitalized),
                        "rate": rate,
                        "year_fraction": fraction(previous, d, data.day_count),
                        "interest": q(interest),
                        "translated_interest": q(interest * data.exchange_rate),
                    }
                )
            for event in events[d]:
                if event.kind == "drawdown":
                    principal += event.amount
                elif event.kind == "repayment":
                    if event.amount > principal:
                        raise ValueError("Repayment exceeds drawn principal")
                    principal -= event.amount
                else:
                    available = accrued + capitalized
                    if event.amount > available:
                        raise ValueError("Interest payment exceeds accrued/capitalized interest")
                    from_accrued = min(accrued, event.amount)
                    accrued -= from_accrued
                    capitalized -= event.amount - from_accrued
                    paid_interest += event.amount
                    if d >= report_start:
                        period_paid_interest += event.amount
            if d in compound_dates:
                capitalized += accrued
                accrued = ZERO
            if d in resets:
                rate = resets[d].annual_rate
        duration = (end - report_start).days
        expected = data.expected_outstanding
        return serial(
            {
                "intervals": [x for x in intervals if x["start"] >= report_start],
                "accrual_start": report_start,
                "accrual_end_exclusive": end,
                "principal_outstanding": q(principal),
                "capitalized_interest": q(capitalized),
                "unpaid_accrued_interest": q(accrued),
                "interest_paid": q(period_paid_interest),
                "lifetime_interest_paid": q(paid_interest),
                "total_interest": q(period_interest),
                "lifetime_interest": q(total_interest),
                "translated_interest": q(period_interest * data.exchange_rate),
                "original_currency": data.currency,
                "functional_currency": data.functional_currency,
                "fx_source": data.exchange_rate_source,
                "weighted_average_principal": q(weighted_principal / duration),
                "weighted_average_rate": ratio(weighted_rate, weighted_principal),
                "outstanding_difference": q(principal - expected) if expected is not None else None,
                "day_count": data.day_count,
                "compounding": data.compounding,
                "scope": "Accrual intervals exclude end date; events apply before next interval. FX uses one reviewed reporting conversion, not a remeasurement ledger. Principal reconciliation excludes capitalized interest.",
            }
        )


def disclosure(profile, revenue, transactions, parameters):
    rp_total = ZERO
    categories: dict[str, D] = defaultdict(lambda: ZERO)
    connected: dict[str, D] = defaultdict(lambda: ZERO)
    connected_transactions: dict[str, D] = defaultdict(lambda: ZERO)
    rows = []
    for t in transactions:
        if t["source_role"] != "original":
            continue
        amount = abs(D(t["base_amount"]))
        if t.get("disclosure_market_value") is not None:
            amount = D(t["disclosure_market_value"])
        amount *= -1 if t.get("is_reversal") else 1
        if t["relationship_decision"] == "CONNECTED":
            key = t["connected_group_key"]
            if not key:
                raise ValueError(
                    "Connected-person aggregation group including related parties required"
                )
            connected_transactions[key] += amount
            if t.get("connected_payment_or_benefit") is None:
                raise ValueError("Explicit connected payment/benefit classification required")
            if t["connected_payment_or_benefit"]:
                connected[key] += amount
        rp_applicable = (
            t.get("rp_applicable", t["relationship_decision"] == "RELATED")
            and t["category"] != "dividend"
        )
        if rp_applicable:
            rp_total += amount
            categories[t["category"]] += amount
        rows.append(
            {
                "id": t["id"],
                "counterparty_id": t["counterparty_id"],
                "category": t["category"],
                "side": t["side"],
                "amount": amount,
                "rp_applicable": rp_applicable,
                "cp_payment_or_benefit": t.get("connected_payment_or_benefit") is True
                and t["relationship_decision"] == "CONNECTED",
            }
        )
    files = (
        revenue >= parameters.own_revenue
        or profile.mne_member
        and profile.group_revenue >= parameters.group_revenue
    )
    return serial(
        {
            "masterfile_required": bool(files and not profile.uae_headquartered_non_mne_group),
            "localfile_required": bool(files),
            "domestic_non_mne_masterfile_exception": bool(
                files and profile.uae_headquartered_non_mne_group
            ),
            "rp_total": rp_total,
            "rp_schedule_required": rp_total > parameters.rp_total,
            "category_totals": dict(categories),
            "reportable_categories": [
                key
                for key, value in categories.items()
                if rp_total > parameters.rp_total and value > parameters.rp_category
            ],
            "connected_totals": dict(connected),
            "connected_transaction_totals": dict(connected_transactions),
            "connected_schedule_gate": any(
                x > parameters.connected_total for x in connected_transactions.values()
            ),
            "reportable_connected_groups": [
                key for key, value in connected.items() if value > parameters.connected_total
            ],
            "rows": rows,
            "threshold_operators": {"documentation": ">=", "disclosures": ">"},
            "substantive_arms_length_applies_below_threshold": True,
            "scope": "Disclosure preparation only; non-MNE Master File exception requires reviewed group facts; Local File counterparty exclusions require manual MD97 assessment. No FTA submission.",
        }
    )


def working_capital(data):
    tested = (
        data.tested_receivables + data.tested_inventory - data.tested_payables
    ) / data.tested_revenue
    comp = (
        data.comparable_receivables + data.comparable_inventory - data.comparable_payables
    ) / data.comparable_revenue
    return serial(
        {
            "tested_wc_ratio": q(tested),
            "comparable_wc_ratio": q(comp),
            "margin_adjustment": q((tested - comp) * data.financing_rate)
            if data.selected
            else ZERO,
            "formula": "(tested WC/revenue - comparable WC/revenue) * approved financing rate; explicitly selected only",
            "rate_source": data.rate_source,
        }
    )
