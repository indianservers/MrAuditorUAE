from datetime import date

import pytest

from app.modules.regulatory.evaluation import evaluate
from app.modules.regulatory.schemas import Rule
from app.modules.regulatory.service import validation_blockers


def fixture(**changes):
    """Synthetic rule arithmetic, not an Indian/UAE legal expected tax result."""
    return Rule.model_validate(
        {
            "rule_key": "AE-SYNTHETIC",
            "country": "AE",
            "title": "SYNTHETIC test rule",
            "description": "Synthetic workflow and Decimal verification only",
            "framework": "IFRS",
            "period_basis": "period_start",
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "citations": [
                {
                    "authority": "Synthetic source reference",
                    "legislation": "Synthetic test only",
                    "url": "https://mof.gov.ae/",
                    "paragraph": "TEST",
                }
            ],
            "input_requirements": ["entity_type"],
            "output_requirements": ["reviewed_conclusion"],
            "applicability": [
                {"field": "entity_type", "operator": "equals", "values": ["company"]}
            ],
            "amendment_reason": "Synthetic creation for control testing",
            "expected_sequence": 0,
            **changes,
        }
    )


def test_missing_and_date_bounds_do_not_manufacture_applicability():
    rule = fixture()
    assert evaluate(rule, {}, date(2026, 1, 1), date(2026, 12, 31))["applicability"] == "PENDING"
    assert (
        evaluate(rule, {"entity_type": "trust"}, date(2026, 1, 1), date(2026, 12, 31))[
            "applicability"
        ]
        == "NOT_APPLICABLE"
    )
    assert (
        evaluate(rule, {"entity_type": "company"}, date(2025, 1, 1), date(2025, 12, 31))[
            "applicability"
        ]
        == "OUTSIDE_EFFECTIVE_PERIOD"
    )
    assert (
        evaluate(rule, {"entity_type": "company"}, date(2026, 1, 1), date(2026, 12, 31))[
            "professional_conclusion"
        ]
        == "NOT_DETERMINED"
    )
    assert validation_blockers(rule)


def test_decimal_method_is_explicit_without_assumed_tax_rates():
    rule = fixture(method="flat_rate", rate="0.123456", input_requirements=["tax_base"])
    result = evaluate(
        rule, {"entity_type": "company", "tax_base": "100.01"}, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert result["calculation"]["unrounded_amount"] == "12.34683456"
    assert (
        evaluate(
            rule,
            {"entity_type": "company", "tax_base": "NaN"},
            date(2026, 1, 1),
            date(2026, 12, 31),
        )["applicability"]
        == "PENDING"
    )
    with pytest.raises(ValueError):
        fixture(method="flat_rate")


def test_large_base_preserves_full_unrounded_precision():
    rule = fixture(method="flat_rate", rate="0.123456789012", input_requirements=["tax_base"])
    result = evaluate(
        rule,
        {"entity_type": "company", "tax_base": "99999999999999999999.12345678"},
        date(2026, 1, 1),
        date(2026, 12, 31),
    )
    product = 9999999999999999999912345678 * 123456789012
    expected = f"{product // 10**20}.{product % 10**20:020d}"
    assert result["calculation"]["unrounded_amount"] == expected


@pytest.mark.parametrize("base", ["1e999999999", "1e-999999999", "-0.01", "Infinity"])
def test_unbounded_tax_base_is_pending_instead_of_overflow_or_silent_rounding(base):
    rule = fixture(method="flat_rate", rate="0.1", input_requirements=["tax_base"])
    result = evaluate(
        rule, {"entity_type": "company", "tax_base": base}, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert result["applicability"] == "PENDING"
    assert "calculation" not in result


async def test_numeric_fact_provenance_requires_review_and_exact_source(monkeypatch):
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.modules.intelligence import service as intelligence
    from app.modules.regulatory.schemas import FactSource
    from app.modules.regulatory.service import validate_fact_sources

    rule = fixture(applicability=[{"field": "turnover", "operator": "gte", "values": ["100"]}])
    eng = SimpleNamespace(id=uuid.uuid4())
    deps = []
    assert await validate_fact_sources(None, None, eng, rule, {"turnover": "100"}, {}, deps) == [
        "turnover"
    ]
    source = SimpleNamespace(
        id=uuid.uuid4(),
        root_id=uuid.uuid4(),
        version=1,
        sha256="a" * 64,
        body={"review_status": "REVIEWED", "total": "100.00"},
    )
    lookup = AsyncMock(return_value=source)
    monkeypatch.setattr(intelligence, "event", lookup)
    bindings = {"turnover": FactSource(kind="intelligence", id=source.id, path=["total"])}
    assert (
        await validate_fact_sources(None, None, eng, rule, {"turnover": "100"}, bindings, deps)
        == []
    )
    lookup.assert_awaited_once_with(None, None, eng.id, source.id, True)
    assert deps[0]["sha256"] == source.sha256
    with pytest.raises(HTTPException) as mismatch:
        await validate_fact_sources(None, None, eng, rule, {"turnover": "100.01"}, bindings, [])
    assert mismatch.value.status_code == 422
    source.body["review_status"] = "UNVERIFIED"
    with pytest.raises(HTTPException) as unreviewed:
        await validate_fact_sources(None, None, eng, rule, {"turnover": "100"}, bindings, [])
    assert unreviewed.value.status_code == 409
