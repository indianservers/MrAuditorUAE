"""Bounded, independently approved schedules for cases 51–100. No legal decision/post/send."""

import uuid
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Any

from pydantic import Field, StrictBool, create_model, model_validator

from app.modules.audit_execution.schemas import Strict

from .advanced_specs import RAW, spec


def contract_sha256():
    import hashlib
    from pathlib import Path

    here = Path(__file__).resolve()
    paths = [
        here,
        here.with_name("advanced_specs.py"),
        here.with_name("continuation.py"),
        here.with_name("continuation_specs.py"),
        here.with_name("continuation_controls.py"),
        here.with_name("assurance.py"),
        here.with_name("assurance_specs.py"),
        here.with_name("rule_impact.py"),
        here.with_name("provenance.py"),
        here.parents[2] / "ifrs/schedule_math.py",
        here.parents[2] / "audit_analytics/workbooks.py",
    ]
    return hashlib.sha256(b"\n".join(p.read_bytes() for p in paths)).hexdigest()


Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=8, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, max_length=2000)]


class CashFlow(Strict):
    period: int = Field(ge=1, le=1200)
    amount: Positive


TYPES = {
    "n": Positive,
    "d": Money,
    "b": StrictBool,
    "t": Text,
    "x": date,
    "y": date | None,
    "u": uuid.UUID,
    "v": Annotated[list[uuid.UUID], Field(max_length=50)],
    "l": Annotated[list[Text], Field(max_length=50)],
    "c": Annotated[list[CashFlow], Field(min_length=1, max_length=120)],
}


def row_model(i):
    definitions: dict[str, Any] = {
        "reference": (Text, ...),
        "evidence_id": (uuid.UUID, ...),
        **{f["name"]: (TYPES[f["type"]], ...) for f in spec(i)["fields"]},
    }
    return create_model(f"UAE{i}Row", __base__=Strict, **definitions)


ROW_MODELS = {i: row_model(i) for i in RAW}


class Policy(Strict):
    source_id: uuid.UUID
    source_locator: Text
    version: Text
    kind: str = Field(
        pattern="^(legislation|official_guidance|accounting_requirement|firm_policy|contract)$"
    )
    effective_from: date
    effective_to: date
    adoption_assessment: Text

    @model_validator(mode="after")
    def dates(self):
        if self.effective_from > self.effective_to:
            raise ValueError("Policy interval is reversed")
        return self


class Schedule(Strict):
    use_case_id: int = Field(ge=51, le=200)
    jurisdiction_framework: str | None = None
    jurisdiction_name: str | None = Field(default=None, max_length=200)
    rounding_precision: int | None = Field(default=None, ge=0, le=8)
    rounding_mode: str | None = None
    period_start: date
    period_end: date
    currency: str = Field(pattern="^[A-Z]{3}$")
    policy: Policy
    assumptions: list[Text] = Field(min_length=1, max_length=30)
    unresolved_questions: list[Text] = Field(default_factory=list, max_length=30)
    rows: list[dict] = Field(min_length=1, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def no_binary_money(cls, value):
        def walk(item):
            if isinstance(item, float):
                raise ValueError("Use decimal strings, not binary floating-point inputs")
            if isinstance(item, dict):
                for v in item.values():
                    walk(v)
            elif isinstance(item, list):
                for v in item:
                    walk(v)

        walk(value)
        return value

    @model_validator(mode="after")
    def validate_rows(self):
        import pycountry

        if not pycountry.currencies.get(alpha_3=self.currency):
            raise ValueError("Unknown ISO currency")
        if (
            51 <= self.use_case_id <= 61 or 63 <= self.use_case_id <= 70 or self.use_case_id == 80
        ) and self.policy.kind not in {"legislation", "official_guidance"}:
            raise ValueError(
                "Tax classifications require adopted legislative or official-guidance evidence, not a firm policy"
            )
        if self.period_start > self.period_end:
            raise ValueError("Reporting interval is reversed")
        if (
            self.policy.effective_from > self.period_start
            or self.policy.effective_to < self.period_end
        ):
            raise ValueError(
                "Adopted policy must cover the whole schedule period; split periods at rule changes"
            )
        if self.use_case_id >= 101:
            if (
                self.jurisdiction_framework
                not in {"AE_MAINLAND", "DIFC", "ADGM", "FREE_ZONE_SPECIFIC", "FOREIGN_FRAMEWORK"}
                or not self.jurisdiction_name
                or not self.jurisdiction_name.strip()
            ):
                raise ValueError(
                    "An explicit legal/accounting framework and named jurisdiction are required"
                )
            if self.rounding_precision is None or self.rounding_mode not in {
                "HALF_EVEN",
                "HALF_UP",
            }:
                raise ValueError("Explicit rounding precision and mode required")
        if self.use_case_id in {101, 103, 104, 107, 108, 110} and self.policy.kind not in {
            "legislation",
            "official_guidance",
        }:
            raise ValueError(
                "Tax procedure/treaty workflows require an adopted primary legal or official-guidance source"
            )
        parsed = [ROW_MODELS[self.use_case_id].model_validate(r) for r in self.rows]
        if len({r.reference for r in parsed}) != len(parsed):
            raise ValueError("Duplicate row reference")
        for row in parsed:
            values = row.model_dump()
            if (
                self.use_case_id in {101, 104, 106, 110, 155}
                and not self.policy.effective_from <= values["as_of"] <= self.policy.effective_to
            ):
                raise ValueError(
                    "Policy must cover the procedure assessment date as well as the reporting period"
                )
            if self.use_case_id == 161 and not (
                self.period_start <= values["capitalization_start"] <= values["capitalization_end"]
                <= self.period_end + timedelta(days=1)
            ):
                raise ValueError("Capitalization interval must fit the reporting period; end date is exclusive")

            if self.use_case_id == 124 and values["foreign_currency"] == self.currency:
                raise ValueError("Forward currency pair must contain distinct ISO currencies")
            if self.use_case_id in {64, 91}:
                key = "foreign_currency" if self.use_case_id == 64 else "order_currency"
                currency = values[key]
                if not pycountry.currencies.get(alpha_3=currency) or values["fx_rate"] <= 0:
                    raise ValueError("Known source currency and positive conversion rate required")
                if currency == self.currency and values["fx_rate"] != 1:
                    raise ValueError("Same-currency conversion must use rate one")
            if (
                self.use_case_id in {81, 83}
                and values.get("review_date", values["year_end"]) < values["year_end"]
            ):
                raise ValueError("Review date precedes year end")
            count_fields = {
                70: {"outstanding_returns"},
                97: {
                    "broken_links",
                    "formula_inconsistencies",
                    "hidden_overrides",
                    "circular_references",
                    "hardcodes",
                },
                99: {
                    "misstatements",
                    "evidence_limitations",
                    "disclosure_issues",
                    "going_concern_issues",
                },
                100: {
                    "required_papers",
                    "approved_current_papers",
                    "unresolved_notes",
                    "missing_signoffs",
                    "broken_links",
                    "report_inconsistencies",
                },
            }
            for key in count_fields.get(self.use_case_id, set()):
                if values[key] != values[key].to_integral_value():
                    raise ValueError("Counts must be whole numbers")

            for key, value in values.items():
                if isinstance(value, Decimal) and (
                    key.endswith("fraction")
                    or key
                    in {
                        "reviewed_probability",
                        "reviewed_rate",
                        "enacted_rate",
                        "rate",
                        "annual_rate",
                    }
                ):
                    if not 0 <= value <= 1:
                        raise ValueError(f"{key} must be a fraction between zero and one")
        if self.use_case_id>=151:
            from .assurance import validate
            validate(self.use_case_id,[r.model_dump() for r in parsed])
        if self.use_case_id >= 101:
            from .continuation import check_rows

            check_rows(self.use_case_id, [r.model_dump() for r in parsed])
        self.rows = [r.model_dump(mode="json") for r in parsed]
        return self


def row_result(i, r):
    # Model validation already guarantees closed keys/types. All arithmetic stays Decimal.
    z = Decimal(0)
    one = Decimal(1)
    flags = []
    out = {}

    def flag(condition, code):
        if condition:
            flags.append(code)

    def difference(name, value):
        out[name] = value
        flag(value != z, name)

    if i == 51:
        out["candidate_disbursement"] = all(
            r[k] for k in ("addressed_to_client", "client_liable", "agent", "exact_recharge")
        )
        out["reviewed_cost"] = r["amount"]
        flag(not out["candidate_disbursement"], "recharge_review")
        flag(r["vat"] > 0, "tax_evidence_review")
    elif i == 52:
        if r["denominator"] <= 0 or r["numerator"] > r["denominator"]:
            raise ValueError("Invalid approved allocation ratio")
        out["residual_ratio"] = r["numerator"] / r["denominator"]
        out["recoverable"] = r["direct_recoverable"] + r["residual"] * out["residual_ratio"]
        out["blocked"] = r["direct_blocked"] + r["residual"] * (one - out["residual_ratio"])
        out["period_adjustment"] = out["recoverable"] - r["previously_claimed"]
    elif i == 53:
        eligible = all(r[k] for k in ("written_off", "notified", "conditions_met"))
        if r["assessment_date"] < r["invoice_date"]:
            raise ValueError("Assessment precedes invoice")
        eligible = (
            eligible
            and r["assessment_date"] >= r["eligible_from"]
            and r["writeoff_date"] is not None
            and r["notification_date"] is not None
        )
        if r["writeoff_date"] is not None and r["writeoff_date"] > r["assessment_date"]:
            eligible = False
        if r["notification_date"] is not None and r["notification_date"] > r["assessment_date"]:
            eligible = False
        cap = r["invoice_tax"] * r["unpaid_fraction"]
        if r["prior_relief"] > r["invoice_tax"]:
            raise ValueError("Prior relief exceeds invoice tax")
        out.update(
            candidate_additional_relief=max(z, cap - r["prior_relief"]) if eligible else z,
            recovery_reversal=r["prior_relief"] * r["recovery_fraction"],
        )
        flag(not eligible, "relief_conditions_unresolved")
    elif i == 54:
        difference("cash_unexplained", r["received"] - r["refunded"] - r["retained"])
        out["retained_less_recorded_revenue"] = r["retained"] - r["recorded_revenue"]
        flag(r["refundable"] or not r["event_occurred"], "contractual_nature_review")
    elif i == 55:
        difference("customs_quantity_difference", r["quantity"] - r["customs_quantity"])
    elif i == 56:
        if r["member_from"] > r["member_to"]:
            raise ValueError("Membership interval reversed")
        out["within_membership"] = (
            r["same_group_verified"] and r["member_from"] <= r["transaction_date"] <= r["member_to"]
        )
        flag(out["within_membership"] and r["tax_charged"] != z, "intragroup_tax_review")
        flag(not out["within_membership"], "outside_verified_membership")
    elif i in {57, 58, 60}:
        out["reviewed_tax"] = r["net"] * r["reviewed_rate"]
        difference("tax_coding_difference", r["recorded_tax"] - out["reviewed_tax"])
        if i == 60:
            difference("inventory_quantity_difference", r["quantity"] - r["inventory_quantity"])
    elif i == 59:
        out["expected_net_settlement"] = (
            r["rooms"] + r["food"] + r["service"] + r["levy"] - r["refunds"] - r["commission"]
        )
        difference(
            "settlement_difference",
            out["expected_net_settlement"] - r["receipts"] - r["receivable"],
        )
    elif i == 61:
        difference(
            "movement_difference",
            r["opening"] + r["production"] + r["imports"] - r["removals"] - r["closing"],
        )
        out["reviewed_unit_tax"] = r["taxable_quantity"] * r["rate_per_unit"]
    elif i == 62:
        out["expected_net_settlement"] = (
            r["gross"] - r["refunds"] - r["commission"] - r["withheld_vat"] - r["chargebacks"]
        )
        difference(
            "settlement_difference",
            out["expected_net_settlement"] - r["settlement"] - r["unsettled"],
        )
    elif i == 63:
        out.update(
            branch_profit=r["profit"], foreign_tax_for_separate_credit_review=r["foreign_tax"]
        )
    elif i == 64:
        out["translated_foreign_tax"] = r["foreign_tax"] * r["fx_rate"]
        out["credit_cap"] = min(out["translated_foreign_tax"], r["domestic_attributable_tax"])
        flag(r["previously_credited"] > out["credit_cap"], "previous_credit_exceeds_cap")
        out["remaining_candidate_credit"] = max(z, out["credit_cap"] - r["previously_credited"])
    elif i == 65:
        out["reviewed_tax_base"] = r["opening_tax_base"] + r["reviewed_election_adjustment"]
        difference("tax_base_difference", out["reviewed_tax_base"] - r["recorded_tax_base"])
        out["historic_to_tax_difference"] = r["historic_carrying"] - out["reviewed_tax_base"]
    elif i == 66:
        out["expected_closing"] = (
            r["opening_deferred"] + r["unrealized_movement"] - r["realized_release"]
        )
        difference("election_bridge_difference", out["expected_closing"] - r["recorded_closing"])
    elif i == 67:
        pass
    elif i == 68:
        out["business_turnover"] = r["business_turnover"]
        out["excluded_income_separate"] = r["excluded_income"]
        out["above_reviewed_threshold"] = r["business_turnover"] > r["reviewed_threshold"]
    elif i == 69:
        difference("partner_allocation_difference", r["allocation_total"] - one)
    elif i == 70:
        flag(r["cessation_date"] > r["review_date"], "cessation_in_future")
        flag(r["outstanding_returns"] > z or r["liabilities"] > z, "outstanding_tax_obligations")
        out["days_since_cessation"] = (r["review_date"] - r["cessation_date"]).days
    elif i == 71:
        for k in ("computation_amount", "financial_statement_amount", "schedule_amount"):
            difference("return_less_" + k, r["return_amount"] - r[k])
    elif i == 72:
        out["temporary_difference"] = (
            (r["carrying"] - r["tax_base"]) if r["asset"] else (r["tax_base"] - r["carrying"])
        )
        out["closing_deferred_liability_positive"] = (
            out["temporary_difference"] * r["enacted_rate"] * r["recognition_fraction"]
        )
        out["deferred_expense"] = out["closing_deferred_liability_positive"] - r["opening_deferred"]
        out["expected_tax_expense"] = r["current_tax"] + out["deferred_expense"]
        difference(
            "expense_bridge_difference", r["recorded_tax_expense"] - out["expected_tax_expense"]
        )
        out["tax_at_reviewed_enacted_rate"] = r["accounting_profit"] * r["enacted_rate"]
        out["tax_expense_reconciling_amount"] = (
            r["recorded_tax_expense"] - out["tax_at_reviewed_enacted_rate"]
        )
        out["effective_rate"] = (
            r["recorded_tax_expense"] / r["accounting_profit"]
            if r["accounting_profit"] != z
            else None
        )
    elif i == 73:
        out["allocated_pool"] = r["total_pool"] * r["allocation_fraction"]
        difference("charge_difference", r["charge"] - out["allocated_pool"])
        flag(r["duplicate_service"], "duplication")
    elif i == 74:
        out["expected_royalty"] = r["base"] * r["rate"]
        difference("royalty_difference", r["recorded_royalty"] - out["expected_royalty"])
    elif i == 75:
        if r["day_basis"] <= z:
            raise ValueError("Positive day basis required")
        out["expected_charge"] = r["principal"] * r["annual_rate"] * r["days"] / r["day_basis"]
        out["transaction_type"] = "guarantee" if r["guarantee"] else "cash_pool_interest"
        difference("pricing_difference", r["recorded_charge"] - out["expected_charge"])
    elif i == 76:
        out["target_revenue"] = r["cost"] * (one + r["approved_cost_markup"])
        out["unposted_true_up"] = out["target_revenue"] - r["revenue"] - r["already_booked"]
        out["reviewed_vat_effect"] = r["vat_impact"]
        out["reviewed_tax_effect"] = r["tax_impact"]
    elif i == 77:
        flag(
            (r["registered_relationship"] or r["agreement_match"]) and not r["declared"],
            "potentially_omitted_related_transaction",
        )
        out["candidate_amount"] = r["amount"]
    elif i == 78:
        out["allocated_cost"] = r["direct_cost"] + r["shared_pool"] * r["allocation_fraction"]
        out["adjusted_profit"] = (
            r["revenue"] - out["allocated_cost"] + r["working_capital_adjustment"]
        )
        out["adjusted_margin"] = out["adjusted_profit"] / r["revenue"] if r["revenue"] else None
    elif i == 79:
        out["in_scope"] = r["entity_in_scope"]
    elif i == 80:
        out["expected_closing"] = (
            r["opening"] + r["transition_adjustment"] + r["current_movement"] - r["reversal"]
        )
        difference("transition_difference", out["expected_closing"] - r["recorded_closing"])
    elif i == 81:
        out["within_review_window"] = r["year_end"] < r["event_date"] <= r["review_date"]
        out["proposed_review"] = (
            "adjusting" if r["condition_at_year_end"] else "nonadjusting_disclosure"
        )
        flag(
            out["within_review_window"]
            and not (r["recorded"] if r["condition_at_year_end"] else r["disclosed"]),
            "event_not_addressed",
        )
    elif i == 82:
        out["dispatch_status"] = (
            "SUPPLIED_AUTHORIZED_DISPATCH" if r["authorized_dispatch"] else "DRAFT_NOT_SENT"
        )
        if r["response_received"]:
            difference("confirmation_difference", r["book_balance"] - r["confirmed_balance"])
        flag(
            not r["response_received"] and not r["alternative_procedures"],
            "confirmation_or_alternative_missing",
        )
        flag(
            r["response_received"] and not r["response_authenticated"], "response_not_authenticated"
        )
    elif i == 83:
        out["potential_unrecorded_liability"] = (
            max(z, r["payment"] - r["recorded_accrual"])
            if r["receipt_date"] <= r["year_end"] < r["payment_date"]
            else z
        )
        flag(out["potential_unrecorded_liability"] > z, "potential_unrecorded_liability")
    elif i == 84:
        if r["discount_factor"] > one:
            raise ValueError("Discount factor must not exceed one")
        out["reviewed_expected_value"] = (
            r["exposure"] * r["reviewed_probability"] * r["discount_factor"]
        )
        difference("provision_difference", r["recorded_provision"] - out["reviewed_expected_value"])
    elif i == 85:
        if r["denominator"] <= z:
            raise ValueError("Positive covenant denominator required")
        out["ratio"] = r["numerator"] / r["denominator"]
        out["breach"] = (
            out["ratio"] > r["contractual_limit"]
            if r["maximum_test"]
            else out["ratio"] < r["contractual_limit"]
        )
        flag(out["breach"], "covenant_breach_for_classification_review")
        flag(
            r["waiver_date"] is not None and r["waiver_date"] > r["measurement_date"],
            "waiver_after_measurement",
        )
    elif i == 86:
        out["net_identifiable_assets"] = r["identifiable_assets"] - r["liabilities"]
        out["provisional_goodwill"] = (
            r["consideration"] + r["nci"] + r["prior_interest"] - out["net_identifiable_assets"]
        )
        flag(out["provisional_goodwill"] < z, "bargain_purchase_reassessment")
    elif i == 87:
        out["book_value_equity_bridge"] = r["transferred_net_assets"] - r["consideration"]
        difference("equity_difference", r["recorded_equity"] - out["book_value_equity_bridge"])
    elif i == 88:
        if (
            r["periods"] != r["periods"].to_integral_value()
            or not 1 <= r["periods"] <= 100
            or r["discount_rate"] <= r["terminal_growth"]
        ):
            raise ValueError("Require 1–100 whole periods and discount rate above terminal growth")
        cash = r["cash_flow"]
        value = z
        if r["growth"] <= -one or r["terminal_growth"] <= -one:
            raise ValueError("Growth must exceed minus one")
        for year in range(1, int(r["periods"]) + 1):
            cash *= one + r["growth"]
            value += cash / (one + r["discount_rate"]) ** year
        terminal = cash * (one + r["terminal_growth"]) / (r["discount_rate"] - r["terminal_growth"])
        out["reviewed_model_value"] = value + terminal / (one + r["discount_rate"]) ** int(
            r["periods"]
        )
        difference("valuation_difference", r["recorded_value"] - out["reviewed_model_value"])
        out["terminal_value"] = terminal
        shift = r["sensitivity_shift"]
        if shift <= z or r["discount_rate"] - shift <= max(z, r["terminal_growth"]):
            raise ValueError(
                "Sensitivity shift must be positive and keep lower discount rate above zero and terminal growth"
            )
        sensitivity = []
        for rate in [r["discount_rate"] - shift, r["discount_rate"] + shift]:
            cash = r["cash_flow"]
            v = z
            for year in range(1, int(r["periods"]) + 1):
                cash *= one + r["growth"]
                v += cash / (one + rate) ** year
            v += (cash * (one + r["terminal_growth"]) / (rate - r["terminal_growth"])) / (
                (one + rate) ** int(r["periods"])
            )
            sensitivity.append({"discount_rate": rate, "value": v})
        out["discount_rate_sensitivity"] = sensitivity
    elif i == 89:
        difference(
            "property_rollforward_difference",
            r["opening"]
            + r["additions"]
            - r["disposals"]
            + r["fair_value_movement"]
            - r["depreciation"]
            - r["closing"],
        )
    elif i == 90:
        out["restated_opening"] = r["prior_balance"] + r["approved_adjustment"]
        difference("opening_difference", out["restated_opening"] - r["opening_balance"])
        out["reviewed_tax_effect"] = r["tax_effect"]
    elif i == 91:
        if r["returned_qty"] > r["received_qty"] or r["fx_rate"] <= z:
            raise ValueError("Invalid returns or FX rate")
        out["available_received_qty"] = r["received_qty"] - r["returned_qty"]
        out["expected_invoice_net"] = r["invoiced_qty"] * r["unit_price"] * r["fx_rate"]
        flag(
            r["invoiced_qty"] > min(r["ordered_qty"], out["available_received_qty"]),
            "quantity_exception",
        )
        out["price_difference"] = r["invoice_net"] - out["expected_invoice_net"]
        flag(abs(out["price_difference"]) > r["tolerance"], "price_tolerance_exception")
    elif i == 92:
        out["rolled_count"] = r["counted_qty"] + r["movements_in"] - r["movements_out"]
        out["quantity_difference"] = out["rolled_count"] - r["book_qty"]
        out["unposted_adjustment"] = out["quantity_difference"] * r["unit_cost"]
        flag(out["quantity_difference"] != z, "count_difference")
    elif i == 93:
        out["expected_balance"] = r["opening"] + r["drawings"] - r["settlements"] + r["charges"]
        difference("bank_difference", out["expected_balance"] - r["bank_balance"])
        flag(
            r["maturity"] <= r["review_date"] and out["expected_balance"] > z, "matured_outstanding"
        )
    elif i == 94:
        if r["restricted"] > r["ledger_cash"]:
            raise ValueError("Restricted cash exceeds supplied cash population")
        out["unrestricted_cash"] = r["ledger_cash"] - r["restricted"]
        difference("confirmation_difference", r["restricted"] - r["confirmed_restricted"])
        difference("disclosure_difference", r["restricted"] - r["disclosure_restricted"])
        out["guarantees_separate"] = r["guarantee"]
        out["commitments_separate"] = r["commitment"]
    elif i == 95:
        out["refund_and_dispute_total"] = r["refund"] + r["prior_refunds"] + r["chargeback"]
        flag(out["refund_and_dispute_total"] > r["original_sale"], "refund_dispute_exceeds_sale")
    elif i == 96:
        flag(r["create_supplier"] and r["approve_payment"], "supplier_payment_conflict")
        flag(r["post_journal"] and r["approve_journal"], "journal_approval_conflict")
        out["compensating_control_tested"] = r["compensating_control_tested"]
    elif i == 97:
        out["reported_integrity_issues"] = sum(
            (
                r[k]
                for k in (
                    "broken_links",
                    "formula_inconsistencies",
                    "hidden_overrides",
                    "circular_references",
                    "hardcodes",
                )
            ),
            z,
        )
        flag(out["reported_integrity_issues"] > z, "workbook_integrity_exceptions")
        out["automatic_scanner"] = "NOT_IMPLEMENTED"
    elif i == 98:
        flag(
            r["financial_interest"] or r["prohibited_service"] or r["relationship"],
            "potential_independence_conflict",
        )
        out["clearance"] = None
    elif i == 99:
        out["unresolved_reporting_issues"] = (
            r["misstatements"]
            + r["evidence_limitations"]
            + r["disclosure_issues"]
            + r["going_concern_issues"]
        )
        flag(out["unresolved_reporting_issues"] > z, "reporting_issues_require_qualified_review")
        out["audit_opinion"] = None
    elif i == 100:
        out["missing_current_approved_papers"] = max(
            z, r["required_papers"] - r["approved_current_papers"]
        )
        out["completion_blockers"] = (
            out["missing_current_approved_papers"]
            + r["unresolved_notes"]
            + r["missing_signoffs"]
            + r["broken_links"]
            + r["report_inconsistencies"]
        )
        flag(out["completion_blockers"] > z, "file_completion_blocked")
        out["file_sealed"] = False
    # Boolean facts are observations, not conclusions. Negative factual evidence is explicit.
    state_fields = {
        51: {"addressed_to_client", "client_liable", "agent", "exact_recharge"},
        54: {"refundable", "event_occurred"},
        56: {"same_group_verified"},
        73: {"duplicate_service"},
        75: {"guarantee"},
        77: {"registered_relationship", "declared", "agreement_match"},
        79: {"entity_in_scope"},
        81: {"condition_at_year_end", "recorded", "disclosed"},
        82: {
            "authorized_dispatch",
            "response_received",
            "response_authenticated",
            "alternative_procedures",
        },
        85: {"maximum_test"},
        96: {"create_supplier", "approve_payment", "post_journal", "approve_journal"},
        98: {
            "financial_interest",
            "prohibited_service",
            "relationship",
            "policy_exception_approved",
        },
    }
    for key, value in r.items():
        if isinstance(value, bool) and not value and key not in state_fields.get(i, set()):
            flag(True, "missing_" + key)
    return {
        "reference": r["reference"],
        "evidence_id": str(r["evidence_id"]),
        "calculations": out,
        "exceptions": sorted(set(flags)),
        "status": "REVIEW_REQUIRED",
    }


def calculate(data: Schedule):
    with localcontext() as ctx:
        ctx.prec = 64
        rows = [ROW_MODELS[data.use_case_id].model_validate(r).model_dump() for r in data.rows]
        if (
            data.use_case_id == 78
            and sum((r["allocation_fraction"] for r in rows), Decimal(0)) != 1
        ):
            raise ValueError("Segment allocation fractions must total one for a shared pool")
        summary = {}
        if data.use_case_id>=151:
            from .assurance import evaluate as evaluate_assurance
            results,summary=evaluate_assurance(data.use_case_id,rows,data.rounding_precision,data.rounding_mode)
        elif data.use_case_id >= 101:
            from .continuation import evaluate

            results, summary = evaluate(
                data.use_case_id, rows, data.rounding_precision, data.rounding_mode
            )
        else:
            results = [row_result(data.use_case_id, r) for r in rows]
        return {
            "engine_version": "uae-advanced-schedules/2"
            if data.use_case_id >= 101
            else "uae-advanced-schedules/1",
            "use_case_id": data.use_case_id,
            "period_start": data.period_start.isoformat(),
            "period_end": data.period_end.isoformat(),
            "currency": data.currency,
            "rows": results,
            "summary": summary,
            "jurisdiction_framework": data.jurisdiction_framework,
            "jurisdiction_name": data.jurisdiction_name,
            "rounding_precision": data.rounding_precision,
            "rounding_mode": data.rounding_mode,
            "exception_count": sum(len(r["exceptions"]) for r in results),
            "policy": data.policy.model_dump(mode="json"),
            "assumptions": data.assumptions,
            "unresolved_questions": data.unresolved_questions,
            "limitation": spec(data.use_case_id)["limitation"],
            "professional_conclusion": None,
            "publication": "NOT_POSTED_NOT_SENT_NOT_SUBMITTED",
            "review_status": "UNREVIEWED",
        }
