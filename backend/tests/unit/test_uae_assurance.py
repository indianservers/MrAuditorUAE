from copy import deepcopy
from decimal import Decimal
import uuid
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
            "l": [],
            "v": [],
            "c": [{"period": 1, "amount": "110"}],
        }[f["type"]]
    if i == 151:
        row.update(new_source_id=str(uuid.UUID(int=2)))
    if i == 155:
        row.update(status="approved")
    if i == 158:
        row.update(payment="3")
    if i == 161:
        row.update(capitalization_end="2026-12-31", suspended_days="0", day_basis="365")
    if i == 165:
        row.update(asset_fraction="0.2", prepayment_fraction="0.4")
    if i == 191:
        row.update(arabic_amount="١٬٠٠٠٫٥٠", english_amount="1000.50")
    if i == 192:
        row.update(content_sha256="a" * 64, observed_sha256="a" * 64)
    if i == 193:
        row.update(supporting_sources=[S])
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


@pytest.mark.parametrize("i", range(151, 201))
def test_every_assurance_contract_is_reproducible_and_closed(i):
    data = fixture(i)
    result = calculate(Schedule.model_validate(data))
    assert result == calculate(Schedule.model_validate(deepcopy(data)))
    assert result["rows"][0]["evidence_id"] == S
    assert result["professional_conclusion"] is None
    assert result["rows"][0]["local_ml_mode"] == "unavailable"
    data["rows"][0]["send_to_authority"] = True
    with pytest.raises(ValidationError):
        Schedule.model_validate(data)


@pytest.mark.parametrize(
    "i,changes,key,expected",
    [
        (
            161,
            dict(
                qualifying_expenditure="100000",
                annual_rate="0.05",
                actual_finance_cost="4500",
                capitalization_end="2027-01-01",
            ),
            "candidate_capitalization",
            "4500.00",
        ),
        (
            165,
            dict(cost="100", service_months="10", consumed_months="5"),
            "expense_to_date",
            "60.00",
        ),
        (
            168,
            dict(carrying="600", fair_value="1000", proceeds="1000", lease_liability="400"),
            "recognized_transferred_gain",
            "240.00",
        ),
        (
            184,
            dict(actual_price="12", budget_price="10", actual_units="8", budget_units="10"),
            "revenue_variance",
            "-4.00",
        ),
        (
            199,
            dict(reported_earnings="100", approved_adjustments="20"),
            "adjusted_earnings",
            "120.00",
        ),
        (
            200,
            dict(
                agreed_fee="100",
                approved_variations="20",
                delivered_work_value="150",
                billed="110",
                collected="100",
            ),
            "unapproved_scope_candidate",
            "30.00",
        ),
    ],
)
def test_independent_financial_outcomes(i, changes, key, expected):
    data = fixture(i)
    data["rows"][0].update(changes)
    assert calculate(Schedule.model_validate(data))["rows"][0]["calculations"][key] == Decimal(
        expected
    )


def test_allocation_conserves_contract_and_break_even_is_quantity():
    data = fixture(167)
    data["rows"] = [
        {**data["rows"][0], "reference": str(n), "consideration": "100"} for n in range(3)
    ]
    assert [
        r["calculations"]["allocated_consideration"]
        for r in calculate(Schedule.model_validate(data))["rows"]
    ] == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    data = fixture(188)
    data["rows"][0].update(
        unit_price="10", unit_variable_cost="6", fixed_cost="100", target_profit="20"
    )
    row = calculate(Schedule.model_validate(data))["rows"][0]
    assert row["metrics"]["break_even_units"] == 25 and row["metrics"]["target_profit_units"] == 30
    data["rows"][0]["unit_variable_cost"] = "10"
    assert (
        calculate(Schedule.model_validate(data))["rows"][0]["metrics"]["break_even_units"] is None
    )


def test_close_dependency_checks_all_upstream_and_rejects_cycles():
    data = fixture(190)
    row = data["rows"][0]
    row.update(task_id="A", completed=False)
    data["rows"].append(
        {**row, "reference": "B", "task_id": "B", "completed": True, "dependencies": ["A"]}
    )
    assert all(
        r["metrics"]["finalization_blocked"]
        for r in calculate(Schedule.model_validate(data))["rows"]
    )
    row["dependencies"] = ["B"]
    with pytest.raises(ValidationError, match="Cyclic"):
        Schedule.model_validate(data)


@pytest.mark.parametrize(
    "i,changes",
    [
        (151, {"new_source_id": S}),
        (165, {"resource_control_supported": False}),
        (168, {"proceeds": "2"}),
        (192, {"content_sha256": "bad"}),
        (178, {"distance_km": "0"}),
    ],
)
def test_rejects_unsupported_or_invalid_models(i, changes):
    data = fixture(i)
    data["rows"][0].update(changes)
    with pytest.raises(ValidationError):
        Schedule.model_validate(data)


def test_bilingual_and_ranking_are_honest():
    assert (
        calculate(Schedule.model_validate(fixture(191)))["rows"][0]["calculations"][
            "bilingual_amount_difference"
        ]
        == 0
    )
    data = fixture(178)
    data["rows"][0].update(distance_km="100", fuel_litres="10", reviewed_litres_per_100km="8")
    out = calculate(Schedule.model_validate(data))
    assert out["rows"][0]["metrics"]["variance_fraction"] == Decimal("0.25")
    assert out["summary"]["ranking_mode"] == "rules_baseline"


def test_shared_cost_scenarios_conserve_pool_after_rounding():
    data = fixture(186)
    data["rows"] = [
        {
            **data["rows"][0],
            "reference": str(n),
            "shared_pool": "100",
            "allocation_fraction": a,
            "alternative_fraction": b,
        }
        for n, (a, b) in enumerate(
            [("0.33333333", "0.2"), ("0.33333333", "0.3"), ("0.33333334", "0.5")]
        )
    ]
    rows = calculate(Schedule.model_validate(data))["rows"]
    assert [r["calculations"]["approved_shared_cost"] for r in rows] == [
        Decimal("33.33"),
        Decimal("33.33"),
        Decimal("33.34"),
    ]
    assert sum(r["calculations"]["alternative_shared_cost"] for r in rows) == Decimal("100.00")


def test_capitalization_cannot_include_other_reporting_years():
    data = fixture(161)
    data["rows"][0]["capitalization_start"] = "2025-01-01"
    with pytest.raises(ValidationError, match="reporting period"):
        Schedule.model_validate(data)
