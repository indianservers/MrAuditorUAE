"""Deterministic 101–150 schedules. No external dispatch, posting or professional opinion."""

from collections import defaultdict
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.ifrs.schedule_math import (
    periodic_present_value as pv,
)
from app.modules.ifrs.schedule_math import (
    relative_allocations,
    solve_monotonic_rate,
)

ZERO = Decimal(0)
ONE = Decimal(1)


def check_rows(i, rows):
    for r in rows:
        for key, value in r.items():
            if (
                isinstance(value, Decimal)
                and (
                    key.endswith("fraction")
                    or "fraction_before" in key
                    or "fraction_after" in key
                    or key == "quantitative_threshold"
                )
                and not ZERO <= value <= ONE
            ):
                raise ValueError(f"{key} must be a fraction")
        for key in ["periods", "total_pause_days", "elapsed_pause_days", "old_count", "new_count"]:
            if key in r and (r[key] != r[key].to_integral_value()):
                raise ValueError(f"{key} requires a whole count no greater than 1200")
        for key in ["cashflows", "original_cashflows", "revised_cashflows"]:
            if key in r:
                flows = r[key]
                if len({f["period"] for f in flows}) != len(flows):
                    raise ValueError("Duplicate cash-flow period")
        if (
            i in {121, 122}
            and sum(
                max(f["period"] for f in r[key])
                for key in ["cashflows", "original_cashflows", "revised_cashflows"]
                if key in r
            )
            > 2400
        ):
            raise ValueError("Cashflow schedule exceeds bounded population")
        if i == 106 and r["valid_from"] > r["valid_to"]:
            raise ValueError("Mandate dates reversed")
        if i == 118 and r["start_date"] > r["end_date"]:
            raise ValueError("Subscription dates reversed")
        if i == 124:
            import pycountry

            if not pycountry.currencies.get(alpha_3=r["foreign_currency"]):
                raise ValueError("Unknown foreign currency")
        if i == 149 and r["projected_error"] != ZERO and not r["projection_supported"]:
            raise ValueError("Unsupported statistical projection cannot enter the aggregation")
        if i == 149 and r["trivial_threshold"] > r["materiality"]:
            raise ValueError("Trivial threshold exceeds materiality")
    if i == 121 and sum(max(f["period"] for f in r["cashflows"]) for r in rows) > 2000:
        raise ValueError("Amortization population exceeds 2000 period rows")
    if i == 112:
        groups = defaultdict(list)
        for r in rows:
            groups[r["contract_id"]].append(r)
        for group in groups.values():
            if (
                len({r["consideration"] for r in group}) != 1
                or sum((r["standalone_price"] for r in group), ZERO) <= ZERO
            ):
                raise ValueError(
                    "Each contract needs a single consideration and positive aggregate SSP"
                )
    if i == 149 and (
        len({r["materiality"] for r in rows}) != 1
        or len({r["trivial_threshold"] for r in rows}) != 1
    ):
        raise ValueError("Use one approved materiality/trivial policy per aggregate")


def evaluate(i, rows, precision, rounding):
    check_rows(i, rows)
    mode = ROUND_HALF_UP if rounding == "HALF_UP" else ROUND_HALF_EVEN
    quantum = ONE.scaleb(-precision)

    def money(x):
        return x.quantize(quantum, rounding=mode)

    results = []
    for r in rows:
        a = {}
        m: dict[str, Any] = {}
        flags = []
        schedule = []

        def flag(condition, code):
            if condition:
                flags.append(code)

        def diff(key, value):
            a[key] = value
            flag(value != ZERO, key)

        if i == 101:
            flag(
                not r["deadline_verified"] or r["verified_deadline"] is None,
                "deadline_not_verified",
            )
            flag(
                r["verified_deadline"] is not None and r["as_of"] > r["verified_deadline"],
                "verified_deadline_passed",
            )
            m.update(
                response_draft=f"Notice {r['notice_reference']} ({r['notice_type']}): respond to {r['request_text']}. Supporting facts and reviewer approval outstanding.",
                dispatch_status="NOT_SENT",
            )
        elif i == 102:
            a["expected_statement"] = (
                r["opening"]
                + r["assessments"]
                + r["penalties"]
                + r["interest"]
                - r["payments"]
                + r["refunds"]
            )
            diff("statement_difference", a["expected_statement"] - r["statement_closing"])
            diff("unposted_ledger_adjustment", r["statement_closing"] - r["ledger_closing"])
        elif i == 103:
            m.update(
                clarification_draft={
                    "facts": r["facts"],
                    "issue": r["unresolved_issue"],
                    "questions": r["questions"],
                    "reviewed_analysis": r["reviewed_analysis"],
                },
                submission_status="NOT_SUBMITTED",
            )
        elif i == 104:
            if r["notification_date"] < r["decision_date"]:
                raise ValueError("Notification precedes decision")
            m.update(
                chronology_event=r["event_text"],
                decision_reference=r["decision_reference"],
                days_since_notification=(r["as_of"] - r["notification_date"]).days,
            )
            flag(r["verified_deadline"] is None, "deadline_not_verified")
            flag(
                r["verified_deadline"] is not None and r["as_of"] > r["verified_deadline"],
                "verified_deadline_passed",
            )
        elif i == 105:
            a["remaining_supported_cap"] = max(
                ZERO,
                min(
                    r["return_credit"],
                    r["ledger_credit"],
                    r["invoice_support"],
                    r["payment_support"],
                )
                - r["previously_claimed"],
            )
            diff(
                "unsupported_requested_amount",
                max(ZERO, r["requested"] - a["remaining_supported_cap"]),
            )
        elif i == 106:
            m["within_recorded_mandate"] = (
                r["valid_from"] <= r["as_of"] <= r["valid_to"]
                and r["activity_permitted"]
                and not r["revoked"]
                and r["authorization_verified"]
            )
            flag(not m["within_recorded_mandate"], "activity_outside_verified_mandate")
            m["external_action_enabled"] = False
        elif i == 107:
            m.update(applicant_type=r["applicant_type"], authority_acceptance=None)
        elif i == 108:
            m.update(
                treaty_locator=r["treaty_locator"],
                income_type=r["income_type"],
                treaty_relief_conclusion=None,
            )
        elif i == 109:
            a["reviewed_customs_value"] = r["purchase"] + r["freight"] + r["insurance"]
            a["reviewed_landed_cost"] = (
                a["reviewed_customs_value"] + r["duty"] + r["other_cost"] - r["noncapital_cost"]
            )
            if a["reviewed_landed_cost"] < ZERO:
                raise ValueError("Noncapital allocation exceeds supplied landed cost")
            diff("customs_difference", a["reviewed_customs_value"] - r["customs_declared"])
            diff("inventory_difference", a["reviewed_landed_cost"] - r["inventory_recorded"])
        elif i == 110:
            if r["refunded"] + r["applied"] > r["deposit"]:
                raise ValueError("Deposit utilization exceeds original deposit")
            a["outstanding_deposit"] = r["deposit"] - r["refunded"] - r["applied"]
            flag(r["exit_date"] is None or not r["exit_evidence"], "exit_evidence_missing")
            flag(r["verified_exit_deadline"] is None, "exit_deadline_unverified")
            flag(
                r["verified_exit_deadline"] is not None
                and r["as_of"] > r["verified_exit_deadline"]
                and not r["exit_evidence"],
                "unresolved_after_verified_exit_deadline",
            )
        elif i == 111:
            a.update(
                principal_revenue=r["gross_sales"],
                agent_revenue=r["gross_sales"] - r["supplier_share"],
            )
            if r["principal_approved"] and r["agent_approved"]:
                raise ValueError("Conflicting approved principal/agent judgments")
            if r["principal_approved"] or r["agent_approved"]:
                a["approved_alternative"] = (
                    a["principal_revenue"] if r["principal_approved"] else a["agent_revenue"]
                )
                diff(
                    "recorded_revenue_difference", r["recorded_revenue"] - a["approved_alternative"]
                )
            else:
                flag(True, "gross_net_judgment_unresolved")
        elif i == 112:
            group = [x for x in rows if x["contract_id"] == r["contract_id"]]
            amounts = relative_allocations(
                r["consideration"], [x["standalone_price"] for x in group], money, round_total=True
            )
            allocation = amounts[
                next(n for n, x in enumerate(group) if x["reference"] == r["reference"])
            ]
            a.update(
                allocated_price=allocation,
                cumulative_recognized=allocation * r["recognition_fraction"],
            )
            a["current_recognition"] = a["cumulative_recognized"] - r["previously_recognized"]
        elif i == 113:
            if r["treatment"] not in {"separate", "prospective", "cumulative"}:
                raise ValueError("Select separate, prospective or cumulative approved treatment")
            revised = r["original_price"] + r["added_price"]
            if revised < ZERO:
                raise ValueError("Modified contract consideration is negative")
            if r["treatment"] == "separate":
                a.update(
                    new_separate_contract=r["added_price"],
                    original_schedule_preserved=r["original_price"],
                )
            elif r["treatment"] == "prospective":
                a["remaining_pool"] = revised - r["previously_recognized"]
            else:
                a["unposted_catch_up"] = (
                    revised * r["revised_progress_fraction"] - r["previously_recognized"]
                )
            m["approved_treatment"] = r["treatment"]
        elif i == 114:
            a["rebate"] = r["base_revenue"] * r["rebate_fraction"]
            a["net_transaction_price"] = (
                r["base_revenue"] - a["rebate"] + r["bonus"] - r["penalty"] - r["expected_returns"]
            )
        elif i == 115:
            a["expected_liability"] = (
                r["opening_liability"]
                + r["issued"]
                - r["redeemed"]
                - r["refunded"]
                - r["approved_breakage"]
            )
            flag(a["expected_liability"] < ZERO, "voucher_utilization_exceeds_available")
            diff("voucher_ledger_difference", a["expected_liability"] - r["closing_ledger"])
        elif i == 116:
            flag(
                r["recorded_sale"] > ZERO
                and (
                    r["consignment"]
                    or not all(
                        r[k]
                        for k in [
                            "control_transferred",
                            "goods_identified",
                            "ready_for_delivery",
                            "customer_request",
                        ]
                    )
                ),
                "unsupported_early_recognition",
            )
            a["sales_for_review"] = r["recorded_sale"]
        elif i == 117:
            if r["service_warranty"]:
                flag(True, "service_obligation_requires_revenue_allocation")
            else:
                a["modeled_assurance_provision"] = (
                    r["units"] * r["claim_fraction"] * r["unit_repair_cost"]
                )
                diff(
                    "warranty_provision_difference",
                    a["modeled_assurance_provision"] - r["recorded_provision"],
                )
            a["prior_estimate_less_actual"] = r["prior_estimate"] - r["actual_claims"]
        elif i == 118:
            total = (r["end_date"] - r["start_date"]).days + 1
            elapsed = max(0, min(total, (r["review_date"] - r["start_date"]).days + 1))
            if r["elapsed_pause_days"] > min(r["total_pause_days"], Decimal(elapsed)):
                raise ValueError("Elapsed pauses exceed documented total pauses or elapsed days")
            active = Decimal(elapsed) - r["elapsed_pause_days"]
            if r["total_pause_days"] >= total:
                raise ValueError("Pause days leave no service days")
            denominator = Decimal(total) - r["total_pause_days"]
            a["cumulative_revenue"] = r["contract_price"] * min(ONE, active / denominator)
            a["current_revenue"] = a["cumulative_revenue"] - r["previously_recognized"]
            a["expected_deferred"] = (
                r["opening_deferred"] + r["billed"] - r["refunds"] - a["current_revenue"]
            )
            diff("deferred_ledger_difference", a["expected_deferred"] - r["ledger_deferred"])
            m.update(total_service_days=total, elapsed_active_days=active)
        elif i == 119:
            a["expected_escrow"] = (
                r["opening"] + r["collections"] - r["authorized_releases"] + r["other_movements"]
            )
            diff("escrow_statement_difference", a["expected_escrow"] - r["statement_closing"])
            diff("escrow_project_difference", a["expected_escrow"] - r["project_ledger"])
        elif i == 120:
            a.update(
                budget_variance=r["budget"] - r["expenditure"],
                owner_allocation=r["billings"] * r["allocation_fraction"],
                uncollected=r["billings"] - r["collections"],
            )
            diff(
                "reserve_difference",
                r["opening_reserve"] + r["collections"] - r["expenditure"] - r["closing_reserve"],
            )
        elif i == 121:
            carrying = (
                r["initial_advance"] + r["transaction_costs"]
                if r["asset"]
                else r["initial_advance"] - r["transaction_costs"]
            )
            low = r["rate_lower"]
            high = r["rate_upper"]
            tol = r["solver_tolerance"]
            if carrying <= ZERO or high <= low or not ZERO < tol <= Decimal("0.00000001"):
                raise ValueError(
                    "Positive carrying value, ordered rate bracket and solver tolerance <=1e-8 required"
                )
            rate, residual = solve_monotonic_rate(
                lambda value: pv(r["cashflows"], value) - carrying, low, high, 512, tol
            )
            m.update(periodic_effective_rate=rate, present_value_residual=residual)
            flows = {f["period"]: f["amount"] for f in r["cashflows"]}
            balance = money(carrying)
            for period in range(1, max(flows) + 1):
                opening = balance
                interest = money(opening * rate)
                payment = money(flows.get(period, ZERO))
                balance = opening + interest - payment
                schedule.append(
                    dict(
                        period=period,
                        opening=opening,
                        interest=interest,
                        payment=payment,
                        closing=balance,
                    )
                )
            a.update(initial_carrying=carrying, rounding_residual=balance)
        elif i == 122:
            original = pv(r["original_cashflows"], r["original_periodic_rate"])
            revised = pv(r["revised_cashflows"], r["original_periodic_rate"])
            if original <= ZERO:
                raise ValueError("Original discounted cashflows must be positive")
            ratio = abs(revised + r["fees_paid"] - original) / original
            a.update(
                original_present_value=original,
                revised_present_value=revised,
                unposted_modification_difference=revised - r["carrying"],
            )
            m.update(
                quantitative_difference_ratio=ratio,
                above_reviewed_threshold=ratio >= r["quantitative_threshold"],
                derecognition_conclusion=None,
            )
            flag(r["qualitative_changes"], "qualitative_derecognition_review")
        elif i == 123:
            if r["liability_component"] > r["proceeds"]:
                raise ValueError("Liability component exceeds proceeds")
            a.update(
                supplied_liability_component=r["liability_component"],
                residual_equity=r["proceeds"] - r["liability_component"],
            )
            flag(
                r["mandatory_redemption"] or r["cash_obligation"],
                "contractual_liability_features_review",
            )
        elif i == 124:
            if (
                not ZERO < r["discount_factor"] <= ONE
                or min(r["contract_forward"], r["market_forward"]) <= ZERO
            ):
                raise ValueError("Positive FX quotes and discount factor in (0,1] required")
            value = (
                r["notional"]
                * (r["market_forward"] - r["contract_forward"])
                * r["discount_factor"]
                * (ONE if r["buy_foreign"] else -ONE)
            )
            a["supplied_input_forward_value"] = value
            diff("bank_valuation_difference", value - r["bank_value"])
            diff("ledger_valuation_difference", value - r["ledger_value"])
        elif i == 125:
            flag(r["designation_date"] > r["inception_date"], "designation_after_inception_review")
        elif i == 126:
            diff(
                "supplier_finance_total_difference",
                r["supplier_balance"]
                + r["facility_balance"]
                - r["ledger_trade"]
                - r["ledger_borrowings"],
            )
            flag(r["extended_terms"] or r["bank_paid_supplier"], "presentation_and_cashflow_review")
        elif i == 127:
            diff(
                "factoring_settlement_difference",
                r["receivables"] - r["proceeds"] - r["fees"] - r["retained_reserve"],
            )
            a["approved_retained_asset"] = (
                r["retained_reserve"] if r["derecognition_approved"] else r["receivables"]
            )
            diff("factoring_asset_difference", a["approved_retained_asset"] - r["recorded_asset"])
            flag(r["recourse"], "retained_risk_review")
        elif i == 128:
            value = r["current_value"] if r["cash_settled"] else r["grant_value"]
            a["cumulative_award_expense"] = (
                r["awards"] * r["expected_vesting_fraction"] * value * r["service_fraction"]
            )
            a["current_award_expense"] = a["cumulative_award_expense"] - r["prior_expense"]
        elif i == 129:
            a["modeled_current_recognition"] = r["current_eligible_cost"] * r["eligible_fraction"]
            a["expected_deferred_grant"] = (
                r["grant_received"]
                - r["recognized_to_date"]
                - a["modeled_current_recognition"]
                - r["repayment"]
            )
            flag(a["expected_deferred_grant"] < ZERO, "grant_use_exceeds_available")
            diff("grant_deferred_difference", a["expected_deferred_grant"] - r["recorded_deferred"])
        elif i == 130:
            if r["periods"] <= ZERO:
                raise ValueError("Positive restoration periods required")
            a["initial_present_value"] = r["future_cash"] / (ONE + r["discount_rate"]) ** int(
                r["periods"]
            )
            a["unwind"] = r["opening_provision"] * r["discount_rate"]
            a["reviewed_revised_present_value"] = r["revised_future_cash"] / (
                ONE + r["discount_rate"]
            ) ** int(r["periods"])
            a["estimate_movement"] = a["reviewed_revised_present_value"] - (
                r["opening_provision"] + a["unwind"] - r["settlements"]
            )
            diff(
                "restoration_closing_difference",
                a["reviewed_revised_present_value"] - r["recorded_closing"],
            )
        elif i == 131:
            m.update(
                voting_fraction=r["voting_fraction"],
                approved_control_input=r["control_approved"],
                automatic_control_conclusion=None,
            )
        elif i == 132:
            a["expected_equity_carrying"] = (
                r["opening"]
                + (r["profit"] + r["oci"] - r["dividends"]) * r["ownership_fraction"]
                - r["impairment"]
            )
            diff("equity_method_difference", a["expected_equity_carrying"] - r["recorded_closing"])
        elif i == 133:
            if r["loss_of_control"]:
                raise ValueError(
                    "Loss-of-control accounting requires case134, not an equity-only ownership adjustment"
                )
            a["nci_carrying_transfer"] = r["net_assets"] * (
                r["nci_fraction_before"] - r["nci_fraction_after"]
            )
            a["parent_equity_difference"] = a["nci_carrying_transfer"] - r["consideration"]
            a["expected_nci_closing"] = (
                r["nci_opening"]
                + (r["profit"] + r["oci"] - r["dividends"]) * r["nci_fraction_before"]
                - a["nci_carrying_transfer"]
            )
        elif i == 134:
            if not r["loss_of_control_approved"]:
                flag(True, "loss_of_control_not_approved")
            a["provisional_disposal_gain"] = (
                r["consideration"]
                + r["retained_interest_value"]
                + r["nci"]
                - r["net_assets"]
                - r["disposal_costs"]
                + r["recycled_oci"]
            )
        elif i == 135:
            if min(r["acquisition_index"], r["closing_index"]) <= ZERO:
                raise ValueError("Positive approved indices required")
            if r["nonmonetary"] and r["applicability_approved"] and r["index_source_verified"]:
                a["indexed_nonmonetary_amount"] = (
                    r["historic_amount"] * r["closing_index"] / r["acquisition_index"]
                )
                diff(
                    "index_restatement_difference",
                    a["indexed_nonmonetary_amount"] - r["recorded_restated"],
                )
            else:
                flag(True, "index_restater_not_applicable_or_unverified")
        elif i == 136:
            diff(
                "remaining_policy_alignment",
                r["group_policy_amount"] - r["subsidiary_amount"] - r["posted_alignment"],
            )
        elif i == 137:
            a["expected_closing_cash"] = (
                r["opening_cash"]
                + r["operating"]
                + r["investing"]
                + r["financing"]
                + r["fx_effect"]
                + r["acquisition_cash"]
                + r["disposal_cash"]
            )
            diff("cashflow_bridge_difference", a["expected_closing_cash"] - r["closing_cash"])
        elif i == 138:
            a["financial_candidate_capacity"] = max(
                ZERO,
                min(r["approved_reserves"] - r["restricted_reserves"], r["liquidity_available"]),
            )
            flag(
                r["proposed_distribution"] > a["financial_candidate_capacity"],
                "distribution_exceeds_financial_candidate_cap",
            )
            m["legal_distribution_conclusion"] = None
        elif i == 139:
            diff(
                "capital_document_to_equity_difference",
                r["approved_capital_change"] - r["equity_recorded"],
            )
            diff(
                "capital_settlement_difference",
                r["approved_capital_change"] - r["bank_movement"] - r["shareholder_settlement"],
            )
        elif i == 140:
            a["reviewed_winddown_net_assets"] = (
                r["asset_recoveries"] - r["liability_settlements"] - r["closure_costs"]
            )
            a["basis_movement"] = a["reviewed_winddown_net_assets"] - r["opening_net_assets"]
        elif i == 141:
            diff("client_money_difference", r["designated_bank"] - r["client_liability"])
            flag(
                r["operating_funds_mixed"] > ZERO or r["unauthorized_transfers"] > ZERO,
                "client_money_segregation_exception",
            )
        elif i == 142:
            changed = r["approved_beneficiary"] != r["instructed_beneficiary"]
            m.update(
                beneficiary_changed=changed,
                payment_hold_recommended=changed and not r["independent_verification"],
                payment_released=False,
            )
            flag(m["payment_hold_recommended"], "independent_beneficiary_verification_required")
        elif i == 143:
            same = [x for x in rows if x["tender_id"] == r["tender_id"]]
            flag(
                any(x is not r and x["owner_id"] == r["owner_id"] for x in same),
                "common_bidder_owner",
            )
            flag(r["owner_id"] == r["approver_id"], "owner_approver_identity_overlap")
            flag(
                r["awarded"] and r["bid_amount"] > min(x["bid_amount"] for x in same),
                "award_above_lowest_supplied_bid",
            )
        elif i == 144:
            flag(sum(x["receipt_id"] == r["receipt_id"] for x in rows) > 1, "duplicate_receipt")
            flag(r["amount"] > r["approved_limit"], "claim_exceeds_approved_limit")
            flag(r["receipt_date"] > r["claim_date"], "receipt_after_claim")
        elif i == 145:
            flag(sum(x["employee_id"] == r["employee_id"] for x in rows) > 1, "duplicate_employee")
            flag(sum(x["bank_token"] == r["bank_token"] for x in rows) > 1, "shared_bank_token")
            flag(
                (not r["active_hr"] or r["access_revoked"]) and r["amount"] > ZERO,
                "payroll_identity_requires_HR_review",
            )
        elif i == 146:
            diff("migration_balance_difference", r["new_balance"] - r["old_balance"])
            m["transaction_count_difference"] = r["new_count"] - r["old_count"]
            flag(m["transaction_count_difference"] != ZERO, "migration_count_difference")
            flag(r["old_tax_code"] != r["new_tax_code"], "migration_tax_code_difference")
        elif i == 147:
            if r["report_start"] > r["report_end"] or r["reliance_start"] > r["reliance_end"]:
                raise ValueError("Assurance intervals reversed")
            m["period_covered"] = (
                r["report_start"] <= r["reliance_start"] and r["report_end"] >= r["reliance_end"]
            )
            flag(not m["period_covered"], "assurance_period_gap")
        elif i == 148:
            m.update(
                representation_draft=r["wording"],
                matter=r["matter"],
                sending_status="DRAFT_NOT_SENT",
            )
        elif i == 149:
            if abs(r["corrected_amount"]) > abs(r["actual_error"]) or (
                r["corrected_amount"] * r["actual_error"] < ZERO
            ):
                raise ValueError("Correction must share sign and not exceed actual error")
            a["uncorrected_actual"] = r["actual_error"] - r["corrected_amount"]
            a["projected_separate"] = r["projected_error"]
            a["classification_separate"] = r["classification_error"]
            m["below_trivial_amount_only"] = abs(a["uncorrected_actual"]) < r["trivial_threshold"]
        elif i == 150:
            m["release_blocked"] = r["review_required"] and not all(
                r[k]
                for k in [
                    "reviewer_independent",
                    "consultation_complete",
                    "conclusion_approved",
                    "release_authorized",
                ]
            )
            flag(m["release_blocked"], "quality_release_blocker")
            m["report_released"] = False
        state_fields = {
            106: {"revoked", "activity_permitted"},
            111: {
                "principal_approved",
                "agent_approved",
                "pricing_discretion",
                "fulfillment_responsibility",
            },
            113: {"distinct_addition"},
            116: {"consignment"},
            117: {"service_warranty"},
            121: {"asset"},
            122: {"qualitative_changes", "derecognition_approved"},
            123: {"mandatory_redemption", "cash_obligation"},
            124: {"buy_foreign"},
            126: {"extended_terms", "bank_paid_supplier"},
            127: {"recourse", "risks_transferred", "control_transferred", "derecognition_approved"},
            128: {"cash_settled"},
            131: {"control_approved"},
            133: {"loss_of_control"},
            135: {"nonmonetary"},
            142: {"independent_verification"},
            143: {"awarded"},
            145: {"access_revoked"},
            150: {"review_required"},
        }
        for key, value in r.items():
            if isinstance(value, bool) and not value and key not in state_fields.get(i, set()):
                flag(True, "missing_" + key)
        results.append(
            dict(
                reference=r["reference"],
                evidence_id=str(r["evidence_id"]),
                calculations={k: money(v) for k, v in a.items()},
                metrics=m,
                schedule=schedule,
                exceptions=sorted(set(flags)),
                status="REVIEW_REQUIRED",
            )
        )
    summary = {}
    if i == 149:
        actual = sum((x["calculations"]["uncorrected_actual"] for x in results), ZERO)
        gross = sum((abs(x["calculations"]["uncorrected_actual"]) for x in results), ZERO)
        projected = sum((abs(x["projected_error"]) for x in rows), ZERO)
        classification = sum((abs(x["classification_error"]) for x in rows), ZERO)
        summary = dict(
            net_actual=money(actual),
            gross_actual=money(gross),
            gross_projected_separate=money(projected),
            gross_classification_separate=money(classification),
            gross_actual_above_materiality=gross >= rows[0]["materiality"],
            audit_opinion=None,
        )
    return results, summary
