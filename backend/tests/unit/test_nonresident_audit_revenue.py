from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.tax.audit_revenue import NonresidentAuditRevenue
from app.modules.tax.calculations import audit_statement_obligation
from app.modules.tax.schemas import TaxProfile

U = "00000000-0000-4000-8000-000000000001"


def scope(**changes):
    return NonresidentAuditRevenue.model_validate(
        dict(
            amount="0",
            currency="AED",
            period_start="2026-01-01",
            period_end="2026-12-31",
            scope="uae_pe_and_nexus",
            population_complete=True,
            assessment="Synthetic reviewed complete UAE PE and nexus population",
            evidence_id=U,
            source_path=["financial_tables", 0, "values"],
            **{},
        )
        | changes
    )


def profile(**changes):
    values = dict(
        financial_run_id=U,
        classification="nonresident_juridical",
        legal_form="Synthetic foreign company",
        registration_details="Synthetic",
        residence_assessment="Nonresident",
        resident=False,
        licensed_activities="Synthetic",
        ownership_assessment="Synthetic",
        tax_start="2026-01-01",
        tax_end="2026-12-31",
        legal_as_of="2026-10-27",
        rules={"standard": U},
        revenue="100000000",
        revenue_source="Synthetic sourced revenue",
        scope_assessment="Synthetic scoped tax assessment",
        pillar_two_in_scope=False,
        audited_financials_required=False,
        nonresident_audit_revenue=scope().model_dump(mode="json"),
    )
    return TaxProfile.model_validate(values | changes)


@pytest.mark.parametrize(
    "amount,required", [("0", False), ("50000000", False), ("50000000.00000001", True)]
)
def test_retained_scoped_revenue_is_used_instead_of_total_profile_revenue(amount, required):
    result = audit_statement_obligation(profile(nonresident_audit_revenue=scope(amount=amount)))
    assert result["required_for_ct"] is required
    assert Decimal(result["threshold_revenue"]) == Decimal(amount)
    assert result["nonresident_revenue_scope"]["evidence_id"] == U


def test_incomplete_zero_is_not_nil_clearance():
    result = audit_statement_obligation(
        profile(nonresident_audit_revenue=scope(population_complete=False))
    )
    assert result["required_for_ct"] is None and result["threshold_revenue"] is None
    assert result["issues"]


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "USD"},
        {"scope": "worldwide"},
        {"population_complete": 1},
        {"population_complete": "true"},
        {"source_path": ["rows", -1]},
        {"source_path": [True]},
        {"assessment": "          "},
        {"period_end": "2025-01-01"},
    ],
)
def test_unassessed_or_unsafe_source_contract_is_rejected(change):
    with pytest.raises(ValidationError):
        scope(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"classification": "resident_juridical", "resident": True},
        {"tax_start": "2024-01-01"},
        {"tax_end": "2026-11-30"},
        {"resident": True},
    ],
)
def test_profile_boundary_must_match(change):
    with pytest.raises(ValidationError):
        profile(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"amount": "1"},
        {"amount": True},
        {"amount": 0.0},
        {"period_start": "2026-02-01"},
        {"scope": "worldwide"},
        {"currency": "USD"},
        {"population_complete": 1},
        {"assessment": "Different scope assessment"},
    ],
)
def test_retained_source_object_must_agree(change):
    selected = scope()
    body = {"financial_tables": [{"values": selected.facts() | change}]}
    original = deepcopy(body)
    with pytest.raises(ValueError, match="retained source object"):
        selected.verify_body(body)
    assert body == original


def test_source_decimal_scale_can_differ_without_changing_value():
    selected = scope(amount="100.00")
    selected.verify_body(
        {"financial_tables": [{"values": selected.facts() | {"amount": "100.0000"}}]}
    )
