"""Synthetic technical cases; expected arithmetic is independent of engine helpers."""

import uuid
from datetime import date
from decimal import Decimal as D

import pytest

from app.modules.dmtt.calculations import calculate, scope
from app.modules.dmtt.schemas import ScopeInput
from app.modules.tax.calculations import loss_allocation
from app.modules.tax.contracts import TaxExecution
from tests.phase9.test_dmtt import entity, group


def test_incomplete_dmtt_history_and_mne_facts_do_not_mean_out_of_scope():
    result = scope(ScopeInput(fiscal_start=date(2026, 1, 1)))
    assert result["in_scope"] is None and result["status"] == "INCOMPLETE_SCOPE"
    g = group()
    g.preceding_revenues.pop()
    assert calculate(g, [(entity(), D(10000000))])["uae_dmtt"] is None


def test_investment_entity_must_not_disappear_from_uae_topup_assessment():
    with pytest.raises(ValueError, match="investment"):
        calculate(
            group(), [(entity(), D(10000000)), (entity(classification="investment"), D(2000000))]
        )


def test_dmtt_zero_ordinary_calculation_is_distinct_from_safe_harbour():
    result = calculate(group(), [(entity(current_tax="2000000"), D(10000000))])
    assert result["uae_dmtt"] == 0 and result["outcome"] == "NO_TOPUP_CALCULATED"
    assert result["safe_harbours"] == []


def test_duplicate_loss_lots_cannot_double_utilise():
    identifier = uuid.uuid4()
    with pytest.raises(ValueError, match="Duplicate"):
        loss_allocation(D(1000), D(".75"), [{"id": identifier, "available": "500"}] * 2)
    rows = loss_allocation(D(1000), D(".75"), [{"id": identifier, "available": "900"}])
    assert rows[0]["used"] == "750.00" and D(rows[0]["closing"]) == 150


def test_tax_contract_does_not_infer_payment_filing_or_authority_acceptance():
    receipt = TaxExecution(
        **{key: uuid.uuid4() for key in ["tenant_id", "entity_id", "engagement_id", "period_id"]},
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        tax_type="CT",
        calculation_version="synthetic/1",
        input_completeness="partial",
        source_snapshots=[],
        account_mapping_receipt=[],
        calculated_liability="0",
        rounding="Synthetic explicit rounding",
    )
    assert receipt.filing_status == "NOT_SUBMITTED"
    assert receipt.payment_status == "NOT_RECONCILED"
    assert receipt.authority_assessment == "NOT_ESTABLISHED"
    assert receipt.professional_review == "DRAFT_REQUIRES_REVIEW"
