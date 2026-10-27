from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.tax.calculations import audit_statement_obligation


def profile(**changes):
    values = dict(
        tax_start=date(2026, 1, 1),
        tax_end=date(2026, 12, 31),
        legal_as_of=date(2026, 10, 27),
        classification="resident_juridical",
        resident=True,
        revenue=Decimal("50000000"),
        audited_financials_required=False,
        audited_financials_evidence_id=None,
    )
    return SimpleNamespace(**{**values, **changes})


@pytest.mark.parametrize(
    "start,decision", [(date(2024, 12, 31), "MD82-2023"), (date(2025, 1, 1), "MD84-2025")]
)
@pytest.mark.parametrize(
    "revenue,required",
    [("49999999.99999999", False), ("50000000", False), ("50000000.00000001", True)],
)
def test_threshold_is_strict_and_period_start_selects_decision(start, decision, revenue, required):
    result = audit_statement_obligation(profile(tax_start=start, revenue=Decimal(revenue)))
    assert result["decision"] == decision
    assert result["required_for_ct"] is required
    assert bool(result["issues"]) is required


@pytest.mark.parametrize("start", [date(2024, 1, 1), date(2025, 1, 1)])
def test_qfzp_requirement_is_not_removed_by_nil_revenue_or_checkbox(start):
    result = audit_statement_obligation(
        profile(tax_start=start, classification="qfzp", revenue=Decimal(0))
    )
    assert result["required_for_ct"] is True
    assert result["reasons"] == ["QFZP_REGARDLESS_OF_REVENUE"]
    assert len(result["issues"]) == 2


@pytest.mark.parametrize(
    "classification",
    ["nonresident_juridical", "permanent_establishment", "family_foundation", "exempt_person"],
)
def test_unknown_legal_or_revenue_scope_is_not_a_negative_conclusion(classification):
    result = audit_statement_obligation(
        profile(classification=classification, revenue=Decimal("90000000"))
    )
    assert result["required_for_ct"] is None and result["threshold_revenue"] is None
    assert result["assessment"] == "REVIEW_REQUIRED"


def test_tax_group_cannot_be_satisfied_by_standalone_document():
    result = audit_statement_obligation(
        profile(
            classification="tax_group",
            revenue=Decimal(0),
            audited_financials_required=True,
            audited_financials_evidence_id="synthetic",
        )
    )
    assert result["required_for_ct"] is True
    assert result["statement_kind"] == "AUDITED_SPECIAL_PURPOSE_FINANCIAL_STATEMENTS"
    assert result["issues"] and result["assessment"] == "REVIEW_REQUIRED"


def test_declared_additional_obligation_still_requires_document_below_ct_threshold():
    result = audit_statement_obligation(profile(audited_financials_required=True))
    assert result["required_for_ct"] is False
    assert result["issues"] == ["Required audited financial statements evidence missing"]


def test_matching_requirement_and_document_resolves_only_documentation_check():
    result = audit_statement_obligation(
        profile(
            revenue=Decimal("50000001"),
            audited_financials_required=True,
            audited_financials_evidence_id="synthetic",
        )
    )
    assert not result["issues"]
    assert result["assessment"] == "CT_DOCUMENTATION_CHECK_RESOLVED"
    assert "No company-law" in result["limitations"][1]


def test_modern_instrument_is_not_applied_before_it_was_issued():
    result = audit_statement_obligation(profile(legal_as_of=date(2025, 3, 24)))
    assert result["required_for_ct"] is None
    assert result["assessment"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("assessment", [None, {"contract": "outdated-contract"}])
async def test_legacy_ct_run_requires_regeneration_without_rewriting_results(
    monkeypatch, assessment
):
    from copy import deepcopy
    from unittest.mock import AsyncMock

    from app.modules.tax import contracts, service

    monkeypatch.setattr(contracts, "current", AsyncMock(return_value=True))
    body = {} if assessment is None else {"audit_statement_obligation": assessment}
    previous = deepcopy(body)
    result = SimpleNamespace(kind="corporate-tax", dependencies=[], results=body)
    assert not await service.dependencies_current(None, None, None, result)
    assert result.results == previous
