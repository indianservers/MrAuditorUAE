"""151–200 deterministic schedules and clearly labelled rules-based indicators."""

from collections import defaultdict
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.ifrs.schedule_math import relative_allocations

Z = Decimal(0)
ONE = Decimal(1)
RANKING = {175, 178, 183, 186, 187, 192, 195}


def dependency_state(rows):
    byid = {r["task_id"]: r for r in rows}
    if len(byid) != len(rows):
        raise ValueError("Duplicate close task ID")
    done: dict[str, bool] = {}
    visiting = set()

    def visit(key):
        if key in done:
            return done[key]
        if key in visiting:
            raise ValueError("Cyclic close dependencies")
        if key not in byid:
            raise ValueError("Missing close dependency")
        visiting.add(key)
        r = byid[key]
        upstream = all([visit(d) for d in r["dependencies"]])
        ready = (
            upstream and r["completed"] and r["owner_confirmed"] and r["reconciliation_supported"]
        )
        visiting.remove(key)
        done[key] = ready
        return ready

    for key in byid:
        visit(key)
    return done


def validate(i, rows):
    if len(rows) > 200:
        raise ValueError("151–200 schedules support at most 200 supplied rows")
    for r in rows:
        for key, value in r.items():
            if (
                isinstance(value, Decimal)
                and (key.endswith("fraction") or key == "approved_probability")
                and not Z <= value <= ONE
            ):
                raise ValueError(f"{key} requires a fraction between zero and one")
        for key in {
            "suspended_days",
            "life_months",
            "elapsed_months",
            "service_months",
            "consumed_months",
            "service_periods",
            "earned_periods",
            "required_procedures",
            "performed_procedures",
        } & r.keys():
            if r[key] != r[key].to_integral_value():
                raise ValueError("Day, month and procedure counts must be whole")
        if i == 151 and r["affected_period_start"] > r["affected_period_end"]:
            raise ValueError("Impact interval is reversed")
        if i == 151 and r["old_source_id"] == r["new_source_id"]:
            raise ValueError("Preserve distinct old and new rule records")
        if i == 154 and r["start_date"] > r["end_date"]:
            raise ValueError("Reporting interval is reversed")
        if i == 155 and r["status"] not in {
            "available",
            "submitted",
            "approved",
            "rejected",
            "revoked",
            "expired",
        }:
            raise ValueError("Unknown evidence-supported lifecycle status")
        if i == 155 and r["effective_from"] > r["effective_to"]:
            raise ValueError("Election interval reversed")
        if i == 161 and r["capitalization_start"] > r["capitalization_end"]:
            raise ValueError("Capitalization dates reversed")
        if i == 165 and r["asset_fraction"] + r["prepayment_fraction"] > ONE:
            raise ValueError("Cloud allocation fractions exceed one")
        if (
            i == 165
            and r["asset_fraction"] > Z
            and not (r["resource_control_supported"] and r["deliverables_reviewed"])
        ):
            raise ValueError("Asset allocation requires reviewed resource control and deliverables")
        if i == 168 and r["proceeds"] != r["fair_value"]:
            raise ValueError("Off-market sale-and-leaseback adjustments require a specialist model")
        if i == 163 and (r["residual"] > r["cost"] or r["life_months"] <= Z):
            raise ValueError("Component residual/life is invalid")
        if i == 165 and (r["service_months"] <= Z or r["consumed_months"] > r["service_months"]):
            raise ValueError("Cloud service periods are invalid")
        if i == 169 and (r["service_periods"] <= Z or r["earned_periods"] > r["service_periods"]):
            raise ValueError("Lessor earning periods are invalid")
        if i == 178 and (r["distance_km"] <= Z or r["reviewed_litres_per_100km"] <= Z):
            raise ValueError("Positive mileage and contextual baseline required")
        if i == 182 and (r["annual_sales"] <= Z or r["annual_cost"] <= Z or r["period_days"] <= Z):
            raise ValueError("Positive consistent turnover denominators required")
        if i == 187 and (r["conversion_rate"] <= Z or r["comparable_reference_price"] <= Z):
            raise ValueError("Positive approved FX/normalized comparator required")
        if i == 189 and (r["maturity_date"] < r["start_date"] or r["day_basis"] <= Z):
            raise ValueError("Invalid deposit dates/day-count basis")
        if i == 192:
            import re

            if not all(
                re.fullmatch(r"[0-9a-f]{64}", r[k]) for k in ["content_sha256", "observed_sha256"]
            ):
                raise ValueError("Expected lowercase SHA256 digests")
    if i == 154:
        ordered = sorted(rows, key=lambda r: r["start_date"])
        for prev, nxt in zip(ordered, ordered[1:]):
            if (nxt["start_date"] - prev["end_date"]).days != 1:
                raise ValueError("Supplied reporting periods contain a gap or overlap")
    if i == 167:
        groups = defaultdict(list)
        for r in rows:
            groups[r["contract_id"]].append(r)
        for group in groups.values():
            if len({r["consideration"] for r in group}) != 1 or any(
                r["standalone_price"] <= Z for r in group
            ):
                raise ValueError(
                    "One consideration and positive standalone prices required per contract"
                )
    if i == 186 and (
        sum((r["allocation_fraction"] for r in rows), Z) != ONE
        or sum((r["alternative_fraction"] for r in rows), Z) != ONE
        or len({r["shared_pool"] for r in rows}) != 1
    ):
        raise ValueError("Each allocation scenario must distribute one shared pool completely")
    if i == 190:
        dependency_state(rows)


def evaluate(i, rows, precision, rounding):
    validate(i, rows)
    q = ONE.scaleb(-precision)
    mode = ROUND_HALF_UP if rounding == "HALF_UP" else ROUND_HALF_EVEN

    def cash(x):
        return x.quantize(q, rounding=mode)

    results = []
    summary: dict[str, Any] = {}
    ready = dependency_state(rows) if i == 190 else {}
    for r in rows:
        a = {}
        m: dict[str, Any] = {}
        f = []

        def flag(condition, code):
            if condition:
                f.append(code)

        def diff(key, value):
            a[key] = value
            flag(value != Z, key)

        if i == 151:
            m.update(
                amendment_reference=r["amendment_reference"],
                period_intersects_change=r["affected_period_end"] >= r["effective_from"],
                automatic_rule_adoption=False,
            )
        elif i == 152:
            a["reviewed_expected_exposure"] = r["exposure"] * r["approved_probability"]
            diff(
                "tax_position_provision_difference",
                a["reviewed_expected_exposure"] - r["recorded_provision"],
            )
        elif i == 153:
            flag(
                r["activity_code"] not in r["licensed_activities"],
                "licence_activity_specialist_review",
            )
            a["activity_revenue"] = r["revenue"]
            m["unlawful_activity_conclusion"] = None
        elif i == 154:
            m.update(
                start_date=r["start_date"].isoformat(),
                end_date=r["end_date"].isoformat(),
                covered_days=(r["end_date"] - r["start_date"]).days + 1,
                calendar_changed=False,
            )
        elif i == 155:
            active = (
                r["status"] == "approved"
                and r["effective_from"] <= r["as_of"] <= r["effective_to"]
                and r["continuing_conditions"]
            )
            m.update(
                recorded_status=r["status"],
                active_supported_election=active,
                government_acceptance_verified=False,
            )
            flag(not active, "election_effect_or_conditions_require_review")
        elif i == 156:
            diff(
                "substance_cost_difference",
                r["staff_cost"]
                + r["premises_cost"]
                + r["asset_cost"]
                + r["outsourced_cost"]
                - r["ledger_cost"],
            )
            m["qfzp_conclusion"] = None
        elif i == 157:
            flag(
                r["evidence_date"] > r["transaction_date"], "status_evidence_postdates_transaction"
            )
            flag(
                r["expires_on"] is not None and r["expires_on"] < r["transaction_date"],
                "status_evidence_expired",
            )
            flag(r["contrary_evidence"], "contradictory_counterparty_evidence")
            m["qualifying_income_conclusion"] = None
        elif i == 158:
            if r["allocated"] + r["refund"] > r["payment"]:
                raise ValueError("Payment allocation/refund exceeds supplied payment")
            a.update(
                unallocated_payment=r["payment"] - r["allocated"] - r["refund"],
                remaining_liability=r["liability"] - r["allocated"] - r["credit_applied"],
            )
            diff(
                "authority_allocation_difference", a["remaining_liability"] - r["authority_balance"]
            )
        elif i == 159:
            m.update(
                index_entry=r["item_reference"],
                supplied_version=r["supplied_version"],
                disclosed=False,
            )
        elif i == 160:
            for key in ["vat_base", "ct_base", "tp_base", "customs_base"]:
                a[key + "_less_accounting"] = r[key] - r["accounting_base"]
            flag(
                any(a.values()) and not r["differences_explained"],
                "unexplained_cross_tax_differences",
            )
            m["treatments_must_equal"] = False
        elif i == 161:
            elapsed = Decimal((r["capitalization_end"] - r["capitalization_start"]).days)
            if r["suspended_days"] > elapsed or r["day_basis"] <= Z:
                raise ValueError("Capitalization suspension/day basis invalid")
            modeled = (
                r["qualifying_expenditure"]
                * r["annual_rate"]
                * (elapsed - r["suspended_days"])
                / r["day_basis"]
            )
            a["candidate_capitalization"] = (
                min(modeled, r["actual_finance_cost"]) if r["recognition_approved"] else Z
            )
            a["finance_cost_remaining"] = r["actual_finance_cost"] - a["candidate_capitalization"]
        elif i == 162:
            if r["commissioned_cost"] > r["cip_cost"]:
                raise ValueError("Commissioning allocation exceeds CIP")
            a["unposted_commissioning_transfer"] = r["commissioned_cost"] - r["transferred_cost"]
            flag(
                r["ready_for_use_supported"]
                and r["commissioning_date"] is not None
                and r["commissioning_date"] <= r["review_date"]
                and a["unposted_commissioning_transfer"] > Z,
                "completed_asset_remaining_in_CIP",
            )
        elif i == 163:
            a["cumulative_component_depreciation"] = (r["cost"] - r["residual"]) * min(
                ONE, r["elapsed_months"] / r["life_months"]
            )
            a["component_carrying"] = r["cost"] - a["cumulative_component_depreciation"]
            a["candidate_replacement_net_change"] = r["replacement_cost"] - (
                r["replaced_carrying"] if r["derecognition_approved"] else Z
            )
        elif i == 164:
            criteria = all(
                r[k]
                for k in [
                    "feasibility",
                    "intent_and_resources",
                    "future_benefits",
                    "measurement_supported",
                ]
            )
            a["approved_candidate_asset"] = (
                r["development"] * r["approved_eligible_fraction"] if criteria else Z
            )
            a["research_maintenance_and_other_expense"] = (
                r["research"] + r["development"] + r["maintenance"] - a["approved_candidate_asset"]
            )
            diff(
                "development_asset_difference", a["approved_candidate_asset"] - r["recorded_asset"]
            )
        elif i == 165:
            a["approved_asset_allocation"] = r["cost"] * r["asset_fraction"]
            a["initial_prepayment"] = r["cost"] * r["prepayment_fraction"]
            a["remaining_prepayment"] = a["initial_prepayment"] * (
                ONE - r["consumed_months"] / r["service_months"]
            )
            a["expense_to_date"] = (
                r["cost"] - a["approved_asset_allocation"] - a["remaining_prepayment"]
            )
        elif i == 166:
            m["lease_condition_indicators_supported"] = (
                r["identified_asset"]
                and not r["substitution_substantive"]
                and r["use_decisions"]
                and r["economic_benefits"]
            )
            m["automatic_lease_recognition"] = False
            flag(not m["lease_condition_indicators_supported"], "lease_identification_review")
        elif i == 167:
            group = [x for x in rows if x["contract_id"] == r["contract_id"]]
            allocated = relative_allocations(
                r["consideration"], [x["standalone_price"] for x in group], cash, round_total=True
            )
            a["allocated_consideration"] = allocated[
                next(n for n, x in enumerate(group) if x["reference"] == r["reference"])
            ]
            m["component_kind"] = "lease" if r["lease_component"] else "nonlease"
        elif i == 168:
            if r["fair_value"] <= Z or r["lease_liability"] > r["fair_value"]:
                raise ValueError(
                    "At-market leaseback model requires positive fair value and retained ratio <=1"
                )
            ratio = r["lease_liability"] / r["fair_value"]
            if r["sale_approved"] and r["market_terms_reviewed"]:
                a.update(
                    retained_right_asset=r["carrying"] * ratio,
                    recognized_transferred_gain=(r["fair_value"] - r["carrying"]) * (ONE - ratio),
                )
                diff("sale_price_market_difference", r["proceeds"] - r["fair_value"])
            else:
                flag(True, "sale_leaseback_accounting_not_approved")
        elif i == 169:
            if r["finance_lease_approved"]:
                a.update(
                    periodic_finance_income=r["opening_receivable"] * r["periodic_rate"],
                    expected_closing_receivable=r["opening_receivable"] * (ONE + r["periodic_rate"])
                    - r["cash_received"],
                )
                diff(
                    "lessor_receivable_difference",
                    a["expected_closing_receivable"] - r["recorded_closing"],
                )
            else:
                a["operating_rental_income"] = (
                    r["rental_consideration"] * r["earned_periods"] / r["service_periods"]
                )
        elif i == 170:
            net = max(Z, r["fair_value"] - r["costs_to_sell"])
            if all(
                r[k]
                for k in ["available_for_sale", "sale_highly_probable", "classification_approved"]
            ):
                a["candidate_held_for_sale_amount"] = min(r["carrying"], net)
                diff(
                    "held_for_sale_measurement_difference",
                    a["candidate_held_for_sale_amount"] - r["recorded_amount"],
                )
                flag(not r["depreciation_stopped"], "depreciation_after_approved_classification")
            else:
                flag(True, "held_for_sale_classification_unresolved")
        elif i == 171:
            a.update(
                shipment_margin=r["customer_charge"]
                - r["carrier_cost"]
                - r["other_cost"]
                - r["accrued_cost"],
                unbilled_amount=r["customer_charge"] - r["billed"],
                advances_separate=r["advances"],
            )
            flag(r["completed"] and a["unbilled_amount"] > Z, "completed_unbilled_shipment")
        elif i == 172:
            a["customer_balance"] = (
                r["gross_bookings"] - r["cancellations"] - r["collections"] + r["customer_refunds"]
            )
            a["supplier_balance"] = r["supplier_due"] - r["supplier_paid"]
            a["commission_separate"] = r["commission"]
        elif i == 173:
            a["expected_claim_receivable"] = (
                r["submitted"] - r["contractual_deductions"] - r["receipts"]
            )
            a["rejected_for_followup"] = r["rejected"]
            diff(
                "insurer_subledger_difference",
                a["expected_claim_receivable"] - r["ledger_receivable"],
            )
        elif i == 174:
            a["student_expected_balance"] = (
                r["fees"]
                - r["scholarships"]
                - r["discounts"]
                - r["withdrawal_credit"]
                - r["deposit_applied"]
                - r["collections"]
            )
            diff("student_ledger_difference", a["student_expected_balance"] - r["ledger_balance"])
        elif i == 175:
            m.update(
                recipe_consumption=r["units_sold"] * r["recipe_quantity"],
                observed_consumption=r["opening"] + r["purchases"] - r["closing"],
            )
            m["unexplained_quantity"] = (
                m["observed_consumption"] - m["recipe_consumption"] - r["recorded_waste"]
            )
            flag(m["unexplained_quantity"] != Z, "consumption_variance")
        elif i == 176:
            a["actual_batch_cost"] = (
                r["materials"] + r["labor"] + r["overhead"] - r["scrap_recovery"]
            )
            diff("standard_cost_variance", a["actual_batch_cost"] - r["standard_cost"])
            diff("finished_goods_difference", a["actual_batch_cost"] - r["finished_goods_recorded"])
        elif i == 177:
            m["quantity_difference"] = r["weighed_quantity"] - r["contracted_quantity"]
            a["expected_settlement"] = (
                r["weighed_quantity"] * r["unit_price"]
                - r["quality_deduction"]
                - r["other_deduction"]
            )
            diff("commodity_settlement_difference", a["expected_settlement"] - r["settlement"])
        elif i == 178:
            actual = r["fuel_litres"] * 100 / r["distance_km"]
            m.update(
                actual_litres_per_100km=actual,
                variance_fraction=(actual - r["reviewed_litres_per_100km"])
                / r["reviewed_litres_per_100km"],
            )
            a["fleet_operating_cost"] = r["fuel_cost"] + r["maintenance_cost"]
        elif i == 179:
            a["site_margin"] = (
                r["billing"]
                - r["labor"]
                - r["materials"]
                - r["subcontractors"]
                - r["mobilization_expense"]
                - r["deductions"]
            )
            m["current_margin_fraction"] = a["site_margin"] / r["billing"] if r["billing"] else None
            flag(
                m["current_margin_fraction"] is not None
                and m["current_margin_fraction"] < r["prior_margin_fraction"],
                "declining_site_margin",
            )
        elif i == 180:
            a.update(
                loss_and_repair_separate=r["repair_cost"] + r["loss_expense"],
                approved_recovery=r["approved_recognition"],
                recovery_receivable=r["approved_recognition"] - r["received"],
            )
            flag(r["approved_recognition"] > r["claimed"], "recovery_exceeds_claim")
            diff("recovery_ledger_difference", r["approved_recognition"] - r["ledger_recovery"])
        elif i == 181:
            a.update(
                forecast_closing=r["opening_cash"]
                + r["forecast_receipts"]
                - r["forecast_payments"]
                + r["financing"],
                actual_expected_closing=r["opening_cash"]
                + r["actual_receipts"]
                - r["actual_payments"]
                + r["financing"],
            )
            a["forecast_error"] = r["actual_closing"] - a["forecast_closing"]
            diff(
                "cash_actualization_difference", r["actual_closing"] - a["actual_expected_closing"]
            )
        elif i == 182:
            m.update(
                receivable_days=r["receivables"] / r["annual_sales"] * r["period_days"],
                inventory_days=r["inventory"] / r["annual_cost"] * r["period_days"],
                payable_days=r["payables"] / r["annual_cost"] * r["period_days"],
            )
            m["cash_cycle_days"] = m["receivable_days"] + m["inventory_days"] - m["payable_days"]
            a.update(
                gross_operating_working_capital=r["receivables"] + r["inventory"] - r["payables"],
                disputed_balances_separate=r["disputed_balances"],
            )
            m["guaranteed_cash_savings"] = None
        elif i == 183:
            a["net_credit_exposure"] = max(
                Z, r["exposure"] + r["proposed_order"] - r["enforceable_guarantee"]
            )
            m["credit_hold_recommended"] = (
                a["net_credit_exposure"] > r["approved_limit"]
                or r["overdue"] > Z
                or r["dispute"] > Z
            )
            m["order_released"] = False
            flag(
                m["credit_hold_recommended"] and not r["independent_release_approved"],
                "independent_credit_release_review",
            )
        elif i == 184:
            a.update(
                revenue_price_effect=(r["actual_price"] - r["budget_price"]) * r["actual_units"],
                revenue_volume_effect=(r["actual_units"] - r["budget_units"]) * r["budget_price"],
            )
            a["revenue_variance"] = (
                r["actual_price"] * r["actual_units"] - r["budget_price"] * r["budget_units"]
            )
            a["cost_variance"] = r["actual_cost"] - r["budget_cost"]
            a["margin_variance"] = a["revenue_variance"] - a["cost_variance"]
            diff(
                "unexplained_revenue_residual",
                a["revenue_variance"] - a["revenue_price_effect"] - a["revenue_volume_effect"],
            )
        elif i == 185:
            a["bridged_operating_cash"] = (
                r["profit"]
                + r["noncash"]
                - r["receivables_increase"]
                - r["inventory_increase"]
                + r["payables_increase"]
                + r["other_operating"]
            )
            diff("profit_cash_difference", a["bridged_operating_cash"] - r["operating_cash"])
        elif i == 186:
            position = next(n for n, row in enumerate(rows) if row["reference"] == r["reference"])
            approved = relative_allocations(
                r["shared_pool"],
                [row["allocation_fraction"] for row in rows],
                cash,
                round_total=True,
            )
            alternative = relative_allocations(
                r["shared_pool"],
                [row["alternative_fraction"] for row in rows],
                cash,
                round_total=True,
            )
            a.update(
                approved_shared_cost=approved[position],
                alternative_shared_cost=alternative[position],
                approved_segment_profit=r["revenue"] - r["attributable_cost"] - approved[position],
                alternative_segment_profit=r["revenue"]
                - r["attributable_cost"]
                - alternative[position],
            )
            a["allocation_sensitivity"] = (
                a["alternative_segment_profit"] - a["approved_segment_profit"]
            )
        elif i == 187:
            a["normalized_unit_price"] = r["unit_price"] * r["conversion_rate"]
            a["supplied_spend"] = a["normalized_unit_price"] * r["units"]
            m["price_difference_fraction"] = (
                a["normalized_unit_price"] - r["comparable_reference_price"]
            ) / r["comparable_reference_price"]
        elif i == 188:
            contribution = r["unit_price"] - r["unit_variable_cost"]
            a["unit_contribution"] = contribution
            m.update(
                break_even_units=r["fixed_cost"] / contribution if contribution > Z else None,
                target_profit_units=(r["fixed_cost"] + r["target_profit"]) / contribution
                if contribution > Z
                else None,
            )
            flag(contribution <= Z, "no_finite_break_even")
            flag(
                m["break_even_units"] is not None and m["break_even_units"] > r["capacity_units"],
                "break_even_exceeds_capacity",
            )
        elif i == 189:
            days = Decimal((r["maturity_date"] - r["start_date"]).days)
            a.update(
                simple_interest=r["principal"] * r["annual_rate"] * days / r["day_basis"],
                needed_liquidity_separate=r["needed_liquidity"],
            )
            a["maturity_value"] = r["principal"] + a["simple_interest"]
            m.update(
                days_to_maturity=(r["maturity_date"] - r["as_of"]).days, investment_executed=False
            )
        elif i == 190:
            m.update(
                task_id=r["task_id"],
                dependency_ready=ready[r["task_id"]],
                finalization_blocked=r["required"] and not ready[r["task_id"]],
            )
            flag(m["finalization_blocked"], "required_close_dependency_unresolved")
        elif i == 191:
            from app.modules.intelligence.documents import money

            arabic = Decimal(money(r["arabic_amount"]))
            english = Decimal(money(r["english_amount"]))
            diff("bilingual_amount_difference", arabic - english)
            flag(r["arabic_date"] != r["english_date"], "bilingual_date_difference")
            m.update(semantic_translation_verified=False, translation_review_required=True)
        elif i == 192:
            flag(r["content_sha256"] != r["observed_sha256"], "content_hash_difference")
            flag(
                sum(x["content_sha256"] == r["content_sha256"] for x in rows) > 1,
                "duplicate_content",
            )
            flag(
                any(
                    x["reference_text"] == r["reference_text"]
                    and x["content_sha256"] != r["content_sha256"]
                    for x in rows
                ),
                "same_reference_different_content",
            )
            m["forgery_conclusion"] = None
        elif i == 193:
            flag(not r["supporting_sources"], "unsupported_assertion")
            flag(
                bool(r["contrary_sources"]) and not r["contradiction_resolved"],
                "contrary_evidence_unresolved",
            )
            m.update(sufficiency_inferred_from_volume=False, professional_conclusion=None)
        elif i == 194:
            verified = all(
                r[k]
                for k in [
                    "retest_performed",
                    "evidence_supported",
                    "test_passed",
                    "reviewer_approved",
                ]
            )
            m.update(
                management_claim=r["management_claimed_complete"],
                verified_remediation=verified,
                original_finding_closed=False,
            )
            flag(r["management_claimed_complete"] and not verified, "management_claim_not_verified")
        elif i == 195:
            m["coverage_fraction"] = (
                min(ONE, r["performed_procedures"] / r["required_procedures"])
                if r["required_procedures"]
                else None
            )
            flag(
                r["performed_procedures"] < r["required_procedures"]
                and not r["exclusion_approved"],
                "location_coverage_gap",
            )
            m["risk_weight"] = r["risk_weight"]
        elif i == 196:
            m["group_completion_blocked"] = not all(
                r[k]
                for k in [
                    "instructions_approved",
                    "package_received",
                    "findings_resolved",
                    "completion_received",
                    "reliance_reviewed",
                ]
            )
            flag(m["group_completion_blocked"], "component_delivery_or_reliance_unresolved")
        elif i == 197:
            a["balance_affected"] = r["balance"]
        elif i == 198:
            m.update(
                factual_finding_draft={
                    "procedure": r["approved_procedure"],
                    "population": r["population"],
                    "observation": r["observation"],
                },
                audit_opinion=None,
                assurance_conclusion=None,
                report_label="AGREED_UPON_PROCEDURES_FACTUAL_FINDINGS_ONLY",
            )
        elif i == 199:
            a.update(
                adjusted_earnings=r["reported_earnings"] + r["approved_adjustments"],
                net_debt=r["debt"] + r["debt_like"] - r["cash"],
                defined_working_capital=r["receivables"]
                + r["inventory"]
                - r["payables"]
                + r["other_working_capital"],
            )
        elif i == 200:
            a["approved_fee_envelope"] = r["agreed_fee"] + (
                r["approved_variations"] if r["variation_approved"] else Z
            )
            a.update(
                unapproved_scope_candidate=max(
                    Z, r["delivered_work_value"] - a["approved_fee_envelope"]
                ),
                unbilled_approved=max(Z, a["approved_fee_envelope"] - r["billed"]),
                uncollected_billed=r["billed"] - r["collected"],
                requested_variation_separate=r["requested_change"],
            )
            flag(r["billed"] > a["approved_fee_envelope"], "billing_exceeds_approved_scope")
            m["client_message_sent"] = False
        state = {
            157: {"contrary_evidence"},
            158: {"cross_tax_transfer_approved"},
            166: {"substitution_substantive"},
            167: {"lease_component"},
            169: {"finance_lease_approved"},
            170: {"depreciation_stopped"},
            171: {"completed"},
            183: {"independent_release_approved"},
            190: {"required", "completed"},
            194: {"management_claimed_complete"},
            195: {"exclusion_approved"},
        }
        for key, value in r.items():
            if isinstance(value, bool) and not value and key not in state.get(i, set()):
                flag(True, "missing_" + key)
        results.append(
            dict(
                reference=r["reference"],
                evidence_id=str(r["evidence_id"]),
                calculations={k: cash(v) for k, v in a.items()},
                metrics=m,
                exceptions=sorted(set(f)),
                status="REVIEW_REQUIRED",
                analysis_mode="rules_baseline" if i in RANKING else "deterministic_calculation",
                local_ml_mode="unavailable",
                language_mode="unavailable",
            )
        )
    if i in {178, 186, 195}:
        metric = (
            "variance_fraction"
            if i == 178
            else "risk_weight"
            if i == 195
            else "approved_segment_profit"
        )
        ranked = sorted(
            results,
            key=lambda x: x["calculations"].get(metric, x["metrics"].get(metric, Z)),
            reverse=True,
        )
        summary["ranking"] = [r["reference"] for r in ranked]
        summary["ranking_mode"] = "rules_baseline"
    if i == 187:
        total = sum((r["calculations"]["supplied_spend"] for r in results), Z)
        suppliers: dict[str, Decimal] = defaultdict(lambda: Z)
        for row, result in zip(rows, results):
            suppliers[row["supplier_id"]] += result["calculations"]["supplied_spend"]
        summary["supplier_spend_fraction"] = {
            k: v / total if total else None for k, v in suppliers.items()
        }
        summary["ranking_mode"] = "rules_baseline"
    return results, summary
