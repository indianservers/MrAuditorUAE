import uuid
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.modules.tp import calculations as c
from app.modules.tp.schemas import Allocation, Loan, RuleParameters


def loan(**changes):
    data = dict(
        profile_id=uuid.uuid4(),
        evidence_record_ids=[uuid.uuid4()],
        rationale="Synthetic loan calculation fixture",
        relationship_id=uuid.uuid4(),
        lender_id=uuid.uuid4(),
        borrower_id=uuid.uuid4(),
        currency="AED",
        functional_currency="AED",
        exchange_rate_source="Synthetic reporting FX",
        principal="100000",
        drawdown_date="2026-01-01",
        maturity="2030-01-01",
        calculation_end="2027-01-01",
        annual_rate="0.1",
        interest_type="fixed",
        day_count="ACT/365",
        payment_frequency="Synthetic annual contract",
        security="Unsecured",
        guarantees="None",
        covenants="Synthetic covenant",
        seniority="Senior",
        credit_characteristics="Reviewed synthetic facts",
        prepayment_options="Allowed",
        subordination="None",
        purpose="Synthetic working capital",
    )
    return Loan.model_validate({**data, **changes})


def test_independent_segment_pli_distinguishes_revenue_and_cost_denominators():
    values = c.indicators(D(100000000), D(97500000), D(0), D(10000000))
    assert values["operating_profit"] == 2500000
    assert values["op_oc"] == D("0.02564103")
    assert values["operating_margin"] == D("0.02500000")
    assert values["roa"] == D("0.25000000")
    assert c.indicators(D(0), D(0), D(0), D(0))["op_oc"] is None


@pytest.mark.parametrize(
    "values,convention,q1,median,q3",
    [
        ([1, 2, 3, 4, 5], "inclusive", "2", "3", "4"),
        ([1, 2, 3, 4], "inclusive", "1.75", "2.5", "3.25"),
        ([1, 2, 3, 4], "exclusive", "1.25", "2.5", "3.75"),
        ([1, 2], "exclusive", None, "1.5", None),
        ([-4, -2, 0, 2, 4], "inclusive", "-2", "0", "2"),
        ([None, 1, 3], "inclusive", "1.5", "2", "2.5"),
        ([], "inclusive", None, None, None),
    ],
)
def test_independent_percentile_conventions(values, convention, q1, median, q3):
    result = c.statistics(values, convention)
    for key, expected in [("lower_quartile", q1), ("median", median), ("upper_quartile", q3)]:
        assert result[key] == (D(expected) if expected is not None else None)


def test_allocation_conserves_rounding_and_rejects_bad_drivers():
    rows = c.allocate(D("100"), [Allocation(segment=str(i), weight=1) for i in range(3)])
    assert [x["amount"] for x in rows] == [D("33.33333333"), D("33.33333333"), D("33.33333334")]
    assert sum(x["amount"] for x in rows) == 100
    with pytest.raises(ValueError, match="Positive"):
        c.allocate(D(100), [Allocation(segment="a", weight=0)])
    with pytest.raises(ValueError, match="Duplicate"):
        c.allocate(D(100), [Allocation(segment="a", weight=1)] * 2)


@pytest.mark.parametrize(
    "convention,expected",
    [("ACT/365", "10000"), ("ACT/360", "10138.88888889"), ("30E/360", "10000")],
)
def test_loan_day_counts_bullet_and_original_currency(convention, expected):
    result = c.loan_schedule(
        loan(
            day_count=convention,
            cashflows=[
                {
                    "date": "2027-01-01",
                    "kind": "repayment",
                    "amount": "100000",
                    "reference": "Bullet",
                }
            ],
            expected_outstanding=0,
        )
    )
    assert D(result["total_interest"]) == D(expected)
    assert D(result["principal_outstanding"]) == 0
    assert D(result["weighted_average_principal"]) == 100000
    assert D(result["outstanding_difference"]) == 0


def test_mid_period_repayment_and_early_settlement():
    result = c.loan_schedule(
        loan(
            principal=1000,
            calculation_end="2026-01-31",
            cashflows=[
                {"date": "2026-01-16", "kind": "repayment", "amount": "500", "reference": "Partial"}
            ],
        )
    )
    assert D(result["total_interest"]) == D("6.16438356")
    assert D(result["weighted_average_principal"]) == 750
    settled = c.loan_schedule(
        loan(
            principal=1000,
            calculation_end="2026-01-31",
            cashflows=[
                {
                    "date": "2026-01-16",
                    "kind": "repayment",
                    "amount": "1000",
                    "reference": "Early settlement",
                }
            ],
        )
    )
    assert D(settled["total_interest"]) == D("4.10958904")


def test_floating_reset_and_multiple_disbursements():
    result = c.loan_schedule(
        loan(
            principal=1000,
            interest_type="floating",
            calculation_end="2026-01-31",
            annual_rate="0.1",
            resets=[
                {
                    "date": "2026-01-16",
                    "annual_rate": "0.2",
                    "reference_source": "Synthetic authorized rate observation",
                }
            ],
            cashflows=[
                {
                    "date": "2026-01-16",
                    "kind": "drawdown",
                    "amount": "1000",
                    "reference": "Second draw",
                }
            ],
        )
    )
    assert D(result["total_interest"]) == D("20.54794521")
    assert D(result["weighted_average_principal"]) == 1500
    assert D(result["weighted_average_rate"]) == D("0.16666667")


def test_monthly_repayment_schedule_and_compounding():
    result = c.loan_schedule(
        loan(
            principal=12000,
            cashflows=[
                {
                    "date": str(c.add_month(date(2026, 1, 1), i)),
                    "kind": "repayment",
                    "amount": "1000",
                    "reference": "Monthly principal",
                }
                for i in range(1, 13)
            ],
        )
    )
    # Independent monthly day-count exposure: principal 12k..1k at each month's start.
    expected = (
        sum(
            D(p) * D(days)
            for p, days in zip(
                range(12000, 0, -1000),
                [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
                strict=True,
            )
        )
        * D(".1")
        / 365
    )
    assert D(result["total_interest"]) == c.q(expected)
    assert D(result["principal_outstanding"]) == 0
    compound = c.loan_schedule(
        loan(principal=1000, compounding="annual", calculation_end="2028-01-01")
    )
    assert D(compound["total_interest"]) == 210
    assert D(compound["capitalized_interest"]) == 210
    historical = c.loan_schedule(
        loan(
            principal=1000,
            drawdown_date="2025-01-01",
            accrual_start="2026-01-01",
            compounding="annual",
            calculation_end="2027-01-01",
        )
    )
    assert D(historical["total_interest"]) == 110 and D(historical["lifetime_interest"]) == 210


def test_fx_translation_and_invalid_cashflows():
    result = c.loan_schedule(loan(currency="USD", exchange_rate="3.6725"))
    assert D(result["total_interest"]) == 10000
    assert D(result["translated_interest"]) == 36725
    for flow in [
        [{"date": "2026-01-02", "kind": "repayment", "amount": "100001", "reference": "Invalid"}],
        [{"date": "2025-01-01", "kind": "drawdown", "amount": "1", "reference": "Invalid"}],
        [{"date": "2026-01-01", "kind": "interest_payment", "amount": "1", "reference": "Invalid"}],
    ]:
        with pytest.raises(ValueError):
            c.loan_schedule(loan(cashflows=flow))


def transaction(amount, category="goods", relationship="RELATED", key="RP", source_role="original"):
    return {
        "id": str(uuid.uuid4()),
        "counterparty_id": key,
        "category": category,
        "side": "expense",
        "base_amount": str(amount),
        "source_role": source_role,
        "relationship_decision": relationship,
        "connected_group_key": key,
        "connected_payment_or_benefit": True if relationship == "CONNECTED" else None,
        "disclosure_market_value": None,
    }


@pytest.mark.parametrize(
    "amount,required", [(39999999, False), (40000000, False), (40000001, True)]
)
def test_disclosure_total_strictly_exceeds_threshold(amount, required):
    p = SimpleNamespace(mne_member=True, group_revenue=D(0), uae_headquartered_non_mne_group=False)
    result = c.disclosure(p, D(1), [transaction(amount)], RuleParameters())
    assert result["rp_schedule_required"] is required
    assert result["substantive_arms_length_applies_below_threshold"]


@pytest.mark.parametrize(
    "revenue,required", [(199999999, False), (200000000, True), (200000001, True)]
)
def test_documentation_inclusive_threshold(revenue, required):
    p = SimpleNamespace(mne_member=False, group_revenue=D(0), uae_headquartered_non_mne_group=False)
    result = c.disclosure(p, D(revenue), [], RuleParameters())
    assert result["localfile_required"] is required and result["masterfile_required"] is required


def test_category_cp_group_dividend_and_settlement_controls():
    p = SimpleNamespace(
        mne_member=True, group_revenue=D(3150000000), uae_headquartered_non_mne_group=False
    )
    rows = [
        transaction(36000001, "services"),
        transaction(4000000),
        transaction(250000, "other", "CONNECTED", "Director family"),
        transaction(250001, "other", "CONNECTED", "Director family"),
        transaction(999999999, "dividend"),
        transaction(999999999, source_role="settlement"),
    ]
    result = c.disclosure(p, D(0), rows, RuleParameters())
    assert result["localfile_required"]
    assert result["reportable_categories"] == ["services"]
    assert result["reportable_connected_groups"] == ["Director family"]
    assert result["rp_total"] == "40000001"
    rows[1]["base_amount"] = "4000001"
    assert set(c.disclosure(p, D(0), rows, RuleParameters())["reportable_categories"]) == {
        "services",
        "goods",
    }


def test_benchmark_weighted_and_unweighted_missing_currency_explicitness():
    observations = [
        {
            "id": 1,
            "company_key": "SYNTHETIC A",
            "currency": "AED",
            "fiscal_year": 2025,
            "revenue": D(100),
            "cost_sales": D(80),
            "opex": D(10),
            "assets": None,
        },
        {
            "id": 2,
            "company_key": "SYNTHETIC A",
            "currency": "AED",
            "fiscal_year": 2026,
            "revenue": D(900),
            "cost_sales": D(600),
            "opex": D(120),
            "assets": None,
        },
    ]
    study = SimpleNamespace(
        currency="AED",
        fiscal_years=[2025, 2026],
        pli="operating_margin",
        aggregation="company_unweighted",
        quantile="inclusive",
        selected_target=None,
        target_rationale="No automatic target",
        missing_policy="reject",
    )
    assert c.benchmark(observations, study)["median"] == "0.15000000"
    study.aggregation = "company_weighted"
    assert c.benchmark(observations, study)["median"] == "0.19000000"
    study.fiscal_years = [2026]
    selected_year = c.benchmark(observations, study)
    assert selected_year["observations_used"] == 1
    assert selected_year["observations_outside_selected_years"] == 1
    study.fiscal_years = [2025, 2026]
    observations[0]["financial_adjustment"] = D(".01")
    with pytest.raises(ValueError, match="Weighted pooling"):
        c.benchmark(observations, study)
    observations[0].pop("financial_adjustment")
    observations[0]["currency"] = "USD"
    with pytest.raises(ValueError, match="Mixed currency"):
        c.benchmark(observations, study)
    observations[0]["currency"] = "AED"
    observations[0]["revenue"] = D(0)
    with pytest.raises(ValueError, match="missing metrics"):
        c.benchmark(observations, study)


def test_histogram_accounts_for_negative_constant_and_missing_values():
    for values in [[D(-1), D(0), D(1), None], [D(5)] * 20, []]:
        stats = c.statistics(values)
        assert sum(x["count"] for x in stats["histogram"]) == stats["n"]


def test_connected_receipts_are_separate_from_benefits_and_overlap_is_explicit():
    p = SimpleNamespace(mne_member=False, group_revenue=D(0), uae_headquartered_non_mne_group=False)
    receipt = transaction(900000, relationship="CONNECTED", key="Director")
    receipt.update(connected_payment_or_benefit=False, rp_applicable=True, side="revenue")
    payment = transaction(500000, relationship="CONNECTED", key="Director")
    result = c.disclosure(p, D(0), [receipt, payment], RuleParameters())
    assert result["connected_schedule_gate"]
    assert result["connected_totals"]["Director"] == "500000"
    assert result["reportable_connected_groups"] == []
    assert result["rp_total"] == "900000"
    payment.update(base_amount="500001", rp_applicable=True)
    result = c.disclosure(p, D(0), [receipt, payment], RuleParameters())
    assert result["reportable_connected_groups"] == ["Director"]
    assert result["rp_total"] == "1400001"


def test_disclosure_reversal_applies_to_reviewed_market_value():
    p = SimpleNamespace(mne_member=False, group_revenue=D(0), uae_headquartered_non_mne_group=False)
    row = transaction(100)
    row.update(is_reversal=True, disclosure_market_value="120")
    assert c.disclosure(p, D(0), [row], RuleParameters())["rp_total"] == "-120"
