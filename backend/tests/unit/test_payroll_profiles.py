"""Synthetic profile contracts and interval boundaries, not statutory rates."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.regulatory.evaluation import evaluate
from app.modules.regulatory.payroll_profiles import PayrollParameters
from app.modules.regulatory.rule_spans import boundaries
from tests.unit.test_payroll_rule_workflow import rule
from tests.unit.test_regulatory_evaluation import fixture


def profile(**changes):
    params = {
        key: value
        for key, value in rule(rate="0.123456789012").items()
        if key in PayrollParameters.model_fields
    }
    return fixture(
        country="IN",
        rule_key="IN-SYNTHETIC-PAYROLL",
        framework="Ind AS",
        method="payroll_profile",
        payroll_parameters=params,
        period_basis="transaction_date",
        applicability=[],
        **changes,
    )


def test_profile_keeps_exact_rates_and_requires_dedicated_employee_workflow():
    obj = profile()
    assert str(obj.payroll_parameters.rate) == "0.123456789012"
    assert obj.professional_review_status == "PENDING"
    result = evaluate(
        obj, {"tax_base": "1000"}, date(2026, 1, 1), date(2026, 12, 31), date(2026, 6, 1)
    )
    assert result["required_workflow"] == "india-payroll-rules"
    assert result["applicability"] == "PENDING" and "calculation" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"country": "AE", "rule_key": "AE-SYNTHETIC-PAYROLL"},
        {"period_basis": "period_end"},
        {"method": "checklist"},
        {"payroll_parameters": None},
        {"calculation_currency": "USD"},
        {"rate": "0.1"},
        {"applicability": [{"field": "entity_type", "operator": "equals", "values": ["company"]}]},
    ],
)
def test_profile_rejects_misclassified_or_ignored_inputs(changes):
    obj = profile().model_dump(mode="json")
    from app.modules.regulatory.schemas import Rule

    with pytest.raises(ValidationError):
        Rule.model_validate({**obj, **changes})


def test_interior_amendment_and_expiry_are_selection_boundaries():
    original = profile()
    amendment = original.model_copy(
        update={"effective_from": date(2026, 6, 10), "effective_to": date(2026, 6, 20)}
    )
    assert boundaries(date(2026, 6, 1), date(2026, 6, 30), [original, amendment]) == [
        date(2026, 6, 1),
        date(2026, 6, 10),
        date(2026, 6, 21),
    ]


def test_interval_end_and_open_ended_maximum_date_do_not_overflow():
    original = profile().model_copy(update={"effective_to": date.max})
    assert boundaries(date(9999, 12, 1), date.max, [original]) == [date(9999, 12, 1)]


def test_wage_month_validation_and_leap_year():
    from fastapi import HTTPException

    from app.modules.country_workflows.payroll_source import month_span

    assert month_span("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))
    with pytest.raises(HTTPException) as error:
        month_span("0000-01")
    assert error.value.status_code == 422


async def test_shadowed_legacy_period_basis_does_not_block_current_typed_profile(monkeypatch):
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.modules.regulatory import service
    from app.modules.regulatory.rule_spans import selection_over_span

    latest = SimpleNamespace(id=uuid.uuid4(), body=profile().model_dump(mode="json"))
    legacy = SimpleNamespace(
        id=uuid.uuid4(),
        body=fixture(
            country="IN", rule_key="IN-SYNTHETIC-PAYROLL", period_basis="period_start"
        ).model_dump(mode="json"),
    )
    result = Mock()
    result.all.return_value = [latest, legacy]
    db = SimpleNamespace(scalars=AsyncMock(return_value=result))
    selected = AsyncMock(return_value=latest)
    monkeypatch.setattr(service, "selection", selected)
    chosen = await selection_over_span(
        db,
        SimpleNamespace(tenant_id=uuid.uuid4()),
        "IN-SYNTHETIC-PAYROLL",
        date(2026, 1, 1),
        date(2026, 12, 31),
        date(2026, 6, 1),
        date(2026, 6, 30),
    )
    assert chosen is latest
