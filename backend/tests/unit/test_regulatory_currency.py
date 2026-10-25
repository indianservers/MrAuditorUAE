from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.regulatory.evaluation import evaluate
from app.modules.regulatory.schemas import Assessment
from app.modules.regulatory.service import bound_facts, validation_blockers
from tests.unit.test_regulatory_evaluation import fixture


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR"), ("AE", "USD")])
def test_currency_comes_from_entity_without_country_default(country, currency):
    period = SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    facts = bound_facts(
        SimpleNamespace(country=country),
        {"framework": "IFRS", "entity_type": "company"},
        period,
        {},
        functional_currency=currency,
    )
    assert facts["functional_currency"] == currency
    with pytest.raises(HTTPException, match="approved engagement context"):
        bound_facts(
            SimpleNamespace(country=country),
            {"framework": "IFRS", "entity_type": "company"},
            period,
            {"functional_currency": "ZZZ"},
            functional_currency=currency,
        )


def test_published_rate_requires_declared_currency_and_invalid_codes_reject():
    rule = fixture(method="flat_rate", rate="0.125", input_requirements=["tax_base"])
    assert any("currency" in error for error in validation_blockers(rule))
    with pytest.raises(ValueError, match="recognized ISO"):
        fixture(calculation_currency="ZZZ")


@pytest.mark.parametrize("currency", ["AED", "INR", "USD"])
def test_rate_calculation_retains_currency_and_never_converts(currency):
    rule = fixture(
        method="flat_rate",
        rate="0.125",
        calculation_currency=currency,
        input_requirements=["tax_base"],
    )
    facts = {"entity_type": "company", "tax_base": "100.20", "functional_currency": currency}
    result = evaluate(rule, facts, date(2026, 1, 1), date(2026, 12, 31))
    assert result["calculation"]["currency"] == currency
    assert result["calculation"]["unrounded_amount"] == "12.52500"
    for other in (None, "EUR"):
        result = evaluate(
            rule, {**facts, "functional_currency": other}, date(2026, 1, 1), date(2026, 12, 31)
        )
        assert result["applicability"] == "PENDING" and "calculation" not in result


def test_repeated_rule_ids_do_not_duplicate_a_rule_calculation():
    identifier = uuid4()
    with pytest.raises(ValueError, match="only once"):
        Assessment(
            rule_ids=[identifier, identifier],
            facts={},
            rationale="Synthetic duplicated rule selection",
        )
