import uuid
from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.jurisdictions.ae.advanced import Schedule, calculate
from app.modules.jurisdictions.ae.advanced_specs import spec

S = str(uuid.UUID(int=1))


def fixture(i):
    row = {"reference": f"SYN-{i}", "evidence_id": S}
    for f in spec(i)["fields"]:
        row[f["name"]] = {
            "n": "1",
            "d": "1",
            "b": True,
            "t": "SYNTHETIC",
            "u": S,
            "x": "2026-01-01",
            "y": None,
            "c": [{"period": 1, "amount": "110"}],
        }[f["type"]]
    if i == 101:
        row.update(verified_deadline="2026-02-01")
    if i == 104:
        row.update(verified_deadline="2026-02-01")
    if i == 106:
        row.update(revoked=False)
    if i == 110:
        row.update(deposit="3", refunded="1", applied="1")
    if i == 111:
        row.update(agent_approved=False)
    if i == 113:
        row.update(treatment="cumulative")
    if i == 118:
        row.update(
            start_date="2026-01-01",
            end_date="2026-01-31",
            review_date="2026-01-31",
            total_pause_days="0",
            elapsed_pause_days="0",
            contract_price="310",
            opening_deferred="0",
            billed="310",
            refunds="0",
            previously_recognized="0",
            ledger_deferred="0",
        )
    if i == 121:
        row.update(
            initial_advance="100",
            transaction_costs="0",
            rate_lower="0",
            rate_upper="0.5",
            solver_tolerance="0.00000001",
        )
    if i == 122:
        row.update(original_periodic_rate="0.1", quantitative_threshold="0.1", carrying="100")
    if i == 124:
        row.update(
            foreign_currency="USD",
            notional="1000",
            contract_forward="3.67",
            market_forward="3.70",
            discount_factor="1",
            bank_value="30",
            ledger_value="30",
        )
    if i == 130:
        row.update(
            discount_rate="0.1",
            future_cash="110",
            revised_future_cash="110",
            periods="1",
            opening_provision="100",
            settlements="0",
            recorded_closing="100",
        )
    if i == 133:
        row.update(loss_of_control=False)
    return dict(
        use_case_id=i,
        period_start="2026-01-01",
        period_end="2026-12-31",
        currency="AED",
        jurisdiction_framework="AE_MAINLAND",
        jurisdiction_name="SYNTHETIC Dubai mainland",
        rounding_precision=2,
        rounding_mode="HALF_EVEN",
        policy=dict(
            source_id=S,
            source_locator="SYNTHETIC adopted policy section",
            version="SYN1",
            kind="official_guidance"
            if i in {101, 103, 104, 107, 108, 110}
            else "accounting_requirement",
            effective_from="2026-01-01",
            effective_to="2026-12-31",
            adoption_assessment="SYNTHETIC independent review",
        ),
        assumptions=["SYNTHETIC supplied facts only"],
        rows=[row],
    )


@pytest.mark.parametrize("i", range(101, 151))
def test_every_new_contract_has_reproducible_source_linked_nonfinal_output(i):
    data = fixture(i)
    out = calculate(Schedule.model_validate(data))
    assert out == calculate(Schedule.model_validate(deepcopy(data)))
    assert out["use_case_id"] == i and out["rows"][0]["evidence_id"] == S
    assert (
        out["professional_conclusion"] is None
        and out["publication"] == "NOT_POSTED_NOT_SENT_NOT_SUBMITTED"
    )
    data["rows"][0]["send_to_authority"] = True
    with pytest.raises(ValidationError):
        Schedule.model_validate(data)


@pytest.mark.parametrize(
    "i,key,expected",
    [
        (102, "expected_statement", "4.00"),
        (105, "remaining_supported_cap", "0.00"),
        (109, "reviewed_landed_cost", "4.00"),
        (110, "outstanding_deposit", "1.00"),
        (111, "agent_revenue", "0.00"),
        (112, "allocated_price", "1.00"),
        (113, "unposted_catch_up", "1.00"),
        (114, "net_transaction_price", "-1.00"),
        (115, "expected_liability", "-1.00"),
        (117, "prior_estimate_less_actual", "0.00"),
        (118, "cumulative_revenue", "310.00"),
        (120, "budget_variance", "0.00"),
        (121, "initial_carrying", "100.00"),
        (122, "original_present_value", "100.00"),
        (123, "residual_equity", "0.00"),
        (124, "supplied_input_forward_value", "30.00"),
        (126, "supplier_finance_total_difference", "0.00"),
        (127, "factoring_settlement_difference", "-2.00"),
        (128, "current_award_expense", "0.00"),
        (129, "expected_deferred_grant", "-2.00"),
        (130, "initial_present_value", "100.00"),
        (132, "expected_equity_carrying", "1.00"),
        (133, "parent_equity_difference", "-1.00"),
        (134, "provisional_disposal_gain", "2.00"),
        (135, "indexed_nonmonetary_amount", "1.00"),
        (136, "remaining_policy_alignment", "-1.00"),
        (137, "expected_closing_cash", "7.00"),
        (138, "financial_candidate_capacity", "0.00"),
        (139, "capital_settlement_difference", "-1.00"),
        (140, "reviewed_winddown_net_assets", "-1.00"),
        (141, "client_money_difference", "0.00"),
        (146, "migration_balance_difference", "0.00"),
        (149, "uncorrected_actual", "0.00"),
    ],
)
def test_independent_monetary_expectations(i, key, expected):
    assert calculate(Schedule.model_validate(fixture(i)))["rows"][0]["calculations"][
        key
    ] == Decimal(expected)


def test_bundle_rounding_conserves_contract_price_and_separates_contracts():
    data = fixture(112)
    data["rows"] = []
    for n in range(3):
        r = fixture(112)["rows"][0]
        r.update(
            reference=f"P{n}",
            consideration="100",
            standalone_price="1",
            recognition_fraction="0.5",
            previously_recognized="0",
        )
        data["rows"].append(r)
    out = calculate(Schedule.model_validate(data))
    assert [r["calculations"]["allocated_price"] for r in out["rows"]] == [
        Decimal("33.33"),
        Decimal("33.33"),
        Decimal("33.34"),
    ]
    assert sum(r["calculations"]["allocated_price"] for r in out["rows"]) == 100


def test_effective_rate_solver_and_rounded_schedule_close():
    out = calculate(Schedule.model_validate(fixture(121)))["rows"][0]
    assert abs(out["metrics"]["periodic_effective_rate"] - Decimal("0.1")) < Decimal("0.000000001")
    assert out["schedule"][0]["interest"] == Decimal("10.00") and out["schedule"][0]["closing"] == 0


def test_duplicate_receipts_and_payroll_tokens_are_explainable_indicators():
    for i, code in [
        (143, "common_bidder_owner"),
        (144, "duplicate_receipt"),
        (145, "shared_bank_token"),
    ]:
        data = fixture(i)
        other = deepcopy(data["rows"][0])
        other["reference"] = "OTHER"
        data["rows"].append(other)
        assert all(
            code in r["exceptions"] for r in calculate(Schedule.model_validate(data))["rows"]
        )


def test_framework_policy_dates_missing_inputs_and_unsupported_projections_fail_closed():
    for modify in [
        lambda d: d.pop("jurisdiction_framework"),
        lambda d: d.update(jurisdiction_name=""),
        lambda d: d.update(rounding_precision=None),
        lambda d: d["policy"].update(effective_to="2026-06-01"),
        lambda d: d["rows"][0].update(projected_error="5", projection_supported=False),
    ]:
        data = fixture(149)
        modify(data)
        with pytest.raises(ValidationError):
            Schedule.model_validate(data)


def test_netting_does_not_hide_gross_misstatements():
    data = fixture(149)
    r = data["rows"][0]
    r.update(
        actual_error="120",
        corrected_amount="0",
        projected_error="0",
        classification_error="0",
        materiality="100",
        trivial_threshold="5",
    )
    other = deepcopy(r)
    other.update(reference="REV", actual_error="-120")
    data["rows"].append(other)
    summary = calculate(Schedule.model_validate(data))["summary"]
    assert (
        summary["net_actual"] == 0
        and summary["gross_actual"] == 240
        and summary["gross_actual_above_materiality"]
    )


def test_tiny_allocations_cannot_create_negative_final_obligation():
    from decimal import ROUND_HALF_EVEN

    from app.modules.ifrs.schedule_math import relative_allocations

    def rounded(value):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    amounts = relative_allocations(Decimal("2.50"), [Decimal("1")] * 500, rounded, round_total=True)
    assert sum(amounts) == Decimal("2.50") and min(amounts) >= 0 and max(amounts) == Decimal("0.01")


def test_alternative_classifications_and_candidate_provisions_have_independent_amounts():
    data = fixture(111)
    data["rows"][0].update(
        gross_sales="1000",
        supplier_share="800",
        recorded_revenue="200",
        principal_approved=False,
        agent_approved=True,
    )
    assert (
        calculate(Schedule.model_validate(data))["rows"][0]["calculations"]["approved_alternative"]
        == 200
    )
    data = fixture(117)
    data["rows"][0].update(
        units="120",
        claim_fraction="0.05",
        unit_repair_cost="10",
        recorded_provision="60",
        service_warranty=False,
    )
    assert (
        calculate(Schedule.model_validate(data))["rows"][0]["calculations"][
            "modeled_assurance_provision"
        ]
        == 60
    )
    data = fixture(128)
    data["rows"][0].update(
        awards="100",
        expected_vesting_fraction="0.8",
        grant_value="10",
        current_value="15",
        service_fraction="0.5",
        prior_expense="100",
        cash_settled=False,
    )
    assert (
        calculate(Schedule.model_validate(data))["rows"][0]["calculations"]["current_award_expense"]
        == 300
    )
    data = fixture(124)
    data["rows"][0].update(buy_foreign=False, bank_value="-30", ledger_value="-30")
    assert (
        calculate(Schedule.model_validate(data))["rows"][0]["calculations"][
            "supplied_input_forward_value"
        ]
        == -30
    )


def test_deadlines_are_not_inferred_and_mandates_can_be_revoked():
    data = fixture(101)
    data["rows"][0].update(verified_deadline=None, deadline_verified=False)
    assert (
        "deadline_not_verified" in calculate(Schedule.model_validate(data))["rows"][0]["exceptions"]
    )
    data = fixture(106)
    data["rows"][0].update(revoked=True)
    out = calculate(Schedule.model_validate(data))["rows"][0]
    assert (
        out["metrics"]["within_recorded_mandate"] is False
        and out["metrics"]["external_action_enabled"] is False
    )
    data = fixture(133)
    data["rows"][0]["loss_of_control"] = True
    with pytest.raises(ValueError):
        calculate(Schedule.model_validate(data))


def test_midperiod_subscription_distinguishes_future_and_elapsed_pauses():
    data = fixture(118)
    data["rows"][0].update(
        review_date="2026-01-16", total_pause_days="5", elapsed_pause_days="3", contract_price="260"
    )
    assert (
        calculate(Schedule.model_validate(data))["rows"][0]["calculations"]["cumulative_revenue"]
        == 130
    )
