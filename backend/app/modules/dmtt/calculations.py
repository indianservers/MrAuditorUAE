from decimal import ROUND_HALF_UP, localcontext
from decimal import Decimal as D

MINIMUM = D(".15")
PAYROLL = {
    2025: D(".096"),
    2026: D(".094"),
    2027: D(".092"),
    2028: D(".09"),
    2029: D(".082"),
    2030: D(".074"),
    2031: D(".066"),
    2032: D(".058"),
}
ASSETS = {
    2025: D(".076"),
    2026: D(".074"),
    2027: D(".072"),
    2028: D(".07"),
    2029: D(".066"),
    2030: D(".062"),
    2031: D(".058"),
    2032: D(".054"),
}


def scope(group):
    expected = set(range(group.fiscal_start.year - 4, group.fiscal_start.year))
    if group.multinational is None or len(group.preceding_revenues) != 4 or {x.year for x in group.preceding_revenues} != expected:
        return {"in_scope": None, "qualifying_years": None, "rule": "CD142/1.1",
                "status": "INCOMPLETE_SCOPE", "missing_inputs": ["four distinct preceding revenue years"]}
    hits = sum(x.eur >= D(750000000) * D(x.months) / 12 for x in group.preceding_revenues)
    return {
        "in_scope": group.multinational and hits >= 2,
        "qualifying_years": hits,
        "rule": "CD142/1.1",
    }


def deferred(row, year):
    if row.recorded_rate == 0 and row.amount:
        raise ValueError("Nonzero deferred balance requires a recorded rate")
    if row.treatment == "excluded":
        amount = D(0)
    elif row.treatment == "globe_loss_recast":
        if not row.loss_attributable:
            raise ValueError("Article 4.4.3 GloBE loss attribution required")
        amount = row.amount / row.recorded_rate * MINIMUM
    else:
        if row.treatment == "transition" and not row.transition_exclusions_checked:
            raise ValueError("Article 9.1 transition/anti-avoidance assessment required")
        amount = (
            row.amount * min(MINIMUM, row.recorded_rate) / row.recorded_rate
            if row.recorded_rate
            else D(0)
        )
    if row.recapture_exception and not row.exception_evidence_id:
        raise ValueError("Recapture exception evidence required")
    recapture_due = bool(
        row.origin_year is not None
        and year - row.origin_year >= 5
        and row.remaining_dtl
        and not row.recapture_exception
    )
    return {"adjusted_deferred": amount, "recapture_assessment_required": recapture_due}


def calculate(group, entities, elections=()):
    with localcontext() as ctx:
        ctx.prec = 50
        assessed = scope(group)
        if assessed["in_scope"] is None:
            return {**assessed, "uae_dmtt": None}
        if group.special_cases:
            raise ValueError(
                "Special group entry/exit, initial international phase and restructuring require a separate technical calculation"
            )
        if not assessed["in_scope"]:
            return {**assessed, "uae_dmtt": D(0), "status": "OUT_OF_SCOPE"}
        rows = []
        for e, profit in entities:
            if e.jurisdiction != "AE" or e.classification == "excluded":
                continue
            if e.classification != "ordinary":
                raise ValueError(
                    "Separate investment/PE/JV/minority/stateless blending is not implemented; computation blocked"
                )
            ds = [deferred(x, group.fiscal_start.year) for x in e.deferred]
            if any(x["recapture_assessment_required"] for x in ds):
                raise ValueError("DTL recapture requires a reviewed prior-year ETR recalculation")
            income = (profit + sum((a.amount for a in e.adjustments), D(0))) * e.fx_to_calculation
            covered = (
                e.current_tax
                + e.covered_tax_adjustments
                + sum((x["adjusted_deferred"] for x in ds), D(0))
            ) * e.fx_to_calculation
            rows.append(
                {
                    "entity_id": str(e.entity_id),
                    "income": income,
                    "covered": covered,
                    "payroll": e.eligible_payroll * e.fx_to_calculation,
                    "assets": e.eligible_tangible_assets * e.fx_to_calculation,
                    "additional": e.additional_topup * e.fx_to_calculation,
                    "deferred": ds,
                }
            )
        if not rows:
            raise ValueError("At least one ordinary UAE constituent entity required")
        income = sum((r["income"] for r in rows), D(0))
        tax = sum((r["covered"] for r in rows), D(0))
        year = group.fiscal_start.year
        sbie = sum(
            (
                r["payroll"] * PAYROLL.get(year, D(".05"))
                + r["assets"] * ASSETS.get(year, D(".05"))
                for r in rows
            ),
            D(0),
        )
        if income <= 0 or tax < 0:
            return {
                **assessed,
                "status": "LOSS_OR_NEGATIVE_TAX_TECHNICAL_REVIEW",
                "net_globe_income": income,
                "covered_taxes": tax,
                "sbie": sbie,
                "uae_dmtt": None,
                "loss_dta_candidate": max(-income, D(0)) * MINIMUM,
                "entity_rows": rows,
            }
        etr = tax / income
        rate = max(MINIMUM - etr, D(0))
        excess = max(income - sbie, D(0))
        core = rate * excess
        additional = sum((r["additional"] for r in rows), D(0))
        safe = []
        for election in elections:
            if not (election.qualified_sources and election.all_conditions_reviewed):
                raise ValueError(
                    "Safe harbour requires qualified sources and full conditions review"
                )
            if election.type == "transitional_cbcr":
                if not (
                    year in {2025, 2026}
                    and group.fiscal_end.isoformat() < "2028-07-01"
                    and election.once_out_history_clear
                ):
                    raise ValueError("Transitional CbCR period or continuing eligibility failed")
                transition = D(".16") if year == 2025 else D(".17")
                tests = {
                    "de_minimis": election.cbcr_revenue_eur < D(10000000)
                    and election.cbcr_profit_eur < D(1000000),
                    "simplified_etr": election.cbcr_profit_eur > 0
                    and election.simplified_taxes_eur / election.cbcr_profit_eur >= transition,
                    "routine_profits": election.cbcr_profit_eur <= election.cbcr_sbie_eur,
                }
                safe.append(
                    {"type": election.type, "tests": tests, "qualifies": any(tests.values())}
                )
            elif election.type == "de_minimis":
                if (
                    len(election.three_year_revenues_eur) != 3
                    or len(election.three_year_incomes_eur) != 3
                ):
                    raise ValueError("De minimis needs three reviewed annual values")
                safe.append(
                    {
                        "type": election.type,
                        "qualifies": sum(election.three_year_revenues_eur) / 3 < D(10000000)
                        and sum(election.three_year_incomes_eur) / 3 < D(1000000),
                    }
                )
            else:
                raise ValueError(
                    "Election requires a separate technical schedule; not applied automatically"
                )
        relief = any(s["qualifies"] for s in safe)
        cbcr_relief = any(s["type"] == "transitional_cbcr" and s["qualifies"] for s in safe)
        payable = D(0) if cbcr_relief else additional if relief else core + additional
        positives = sum((max(r["income"], D(0)) for r in rows), D(0))
        alloc = [
            {
                "entity_id": r["entity_id"],
                "tax": (payable * max(r["income"], D(0)) / positives).quantize(
                    D(".01"), rounding=ROUND_HALF_UP
                ),
            }
            for r in rows
        ]
        rounded = payable.quantize(D(".01"), rounding=ROUND_HALF_UP)
        residual_index = max(range(len(rows)), key=lambda i: rows[i]["income"])
        alloc[residual_index]["tax"] += rounded - sum((r["tax"] for r in alloc), D(0))
        return {
            **assessed,
            "status": "DRAFT_TECHNICAL_REVIEW",
            "outcome": "SAFE_HARBOUR_APPLIED" if relief else "NO_TOPUP_CALCULATED" if rounded == 0 else "TOPUP_CALCULATED",
            "currency": group.calculation_currency,
            "net_globe_income": income,
            "covered_taxes": tax,
            "etr": etr,
            "topup_percentage": rate,
            "sbie": sbie,
            "payroll_rate": PAYROLL.get(year, D(".05")),
            "asset_rate": ASSETS.get(year, D(".05")),
            "excess_profit": excess,
            "core_topup": core,
            "additional_topup": additional,
            "safe_harbours": safe,
            "uae_dmtt": rounded,
            "allocation": alloc,
            "entity_rows": rows,
            "iir_utpr_included": False,
        }
