from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.enterprise_ai.business import Execute
from app.modules.enterprise_ai.catalogue import TOOLS, plan
from app.modules.ifrs.fx import MonetaryBalance, closing_revaluation
from app.modules.jurisdictions.ae.registration import Exposure, RegistrationPolicy, calculate
from app.modules.jurisdictions.ae.use_cases import CASES


def test_fifty_distinct_cases_have_bounded_approved_engine_graphs():
    assert set(CASES) == set(range(1, 201))
    assert len({c.title for c in CASES.values()}) == 200
    assert set().union(*(set(c.engines) for c in CASES.values())) == {
        f"E{i:02}" for i in range(1, 23)
    }
    for case in CASES.values():
        task, tools = plan(case.key, case.prompt)
        assert task == case.key
        assert len(tools) <= 12 and len(tools) == len(set(tools))
        assert set(tools) <= set(TOOLS)
        assert tools[0] == "uae.get_case_inputs"
        assert case.required_information


def test_registration_arithmetic_is_policy_driven_decimal_and_not_a_legal_determination():
    policy = RegistrationPolicy(
        threshold_aed=Decimal("100.10"), historical_months=12, forecast_days=30
    )
    population = Exposure(
        as_of=date(2026, 12, 31),
        historical=[
            {
                "id": "ledger-1",
                "date": "2026-01-01",
                "amount_aed": "100.10",
                "taxable_classification_confirmed": True,
            }
        ],
        forecast=[
            {
                "id": "approved-forecast",
                "date": "2027-01-01",
                "amount_aed": "101",
                "taxable_classification_confirmed": True,
            }
        ],
    )
    result = calculate(population, policy)
    assert result["historical_exposure_signal"] is False
    assert result["forecast_exposure_signal"] is True
    assert result["registration_required"] is None and result["filing_due_date"] is None
    unknown = population.model_copy(
        update={
            "historical": [
                population.historical[0].model_copy(
                    update={"taxable_classification_confirmed": False}
                )
            ]
        }
    )
    assert calculate(unknown, policy)["unresolved_observation_ids"] == ["ledger-1"]


def test_duplicate_and_out_of_window_observations_fail():
    with pytest.raises(ValidationError, match="Duplicated"):
        Exposure(
            as_of=date(2026, 1, 1),
            historical=[{"id": "x", "date": "2025-12-31", "amount_aed": "1"}] * 2,
        )
    data = Exposure(
        as_of=date(2026, 1, 1), historical=[{"id": "x", "date": "2020-01-01", "amount_aed": "1"}]
    )
    with pytest.raises(ValueError, match="lookback"):
        calculate(
            data, RegistrationPolicy(threshold_aed=100, historical_months=12, forecast_days=30)
        )
    with pytest.raises(ValidationError):
        Execute(action="post-journal", idempotency_key="forbidden-post")


def test_monetary_fx_is_not_realized_or_presentation_fx():
    result = closing_revaluation(
        [
            MonetaryBalance(
                reference="SYNTHETIC-USD-receivable",
                foreign_currency="USD",
                functional_currency="AED",
                foreign_units="100",
                carrying_functional="360",
                closing_rate="3.6725",
                monetary_classification_reviewed=True,
            )
        ]
    )
    assert result["rows"][0]["closing_functional"] == "367.25"
    assert result["net_balance_adjustment"] == "7.25"
    assert result["realized_fx"] is None and result["presentation_currency_translation"] is None
    assert result["journal_posted"] is False
    with pytest.raises(ValueError, match="nonmonetary"):
        closing_revaluation(
            [
                MonetaryBalance(
                    reference="land",
                    foreign_currency="USD",
                    functional_currency="AED",
                    foreign_units=100,
                    carrying_functional=100,
                    closing_rate=1,
                    monetary_classification_reviewed=False,
                )
            ]
        )
