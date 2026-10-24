"""Independent synthetic accounting/control expectations for Phase 4."""

from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.country_workflows.audit_schemas import LossRate
from app.modules.ifrs.calculations import calculate
from app.modules.intelligence.matching import reconcile_transactions
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_practice_audit_workflows import purchases, rate
from tests.unit.test_shared_audit_workflows import control, item, run


def payment(**changes):
    return {
        "id": "PAY-1",
        "account": "AR",
        "counterparty": "C1",
        "currency": "AED",
        "date": "2026-06-15",
        "reference": "SYN-bank-receipt",
        "direction": "receipt",
        "amount": "70",
        "confirmation_status": "confirmed",
        "evidence_reference": "SYN-bank-proof",
        **changes,
    }


def allocation(**changes):
    return {
        "id": "ALLOC-1",
        "payment_id": "PAY-1",
        "item_id": "I1",
        "currency": "AED",
        "amount": "40",
        "evidence_reference": "SYN-remittance",
        "rationale": "SYN independently reviewed explicit allocation",
        **changes,
    }


def population():
    return {
        "items": [item()],
        "controls": [control(amount="60")],
        "payments": [payment()],
        "allocations": [allocation()],
    }


def test_partial_receipt_and_unapplied_cash_reconcile_without_forcing_allocation():
    out = run("open-item-allocations", population(), allocation_basis="invoice_face_amounts")
    assert out["remaining_open_items"][0]["amount"] == "60"
    cash = next(r for r in out["rows"] if r["kind"] == "cash_movement")
    assert cash["unapplied_cash"] == "30"
    assert cash["state"] == "UNAPPLIED_CASH"
    assert not out["blocked"]


@pytest.mark.parametrize(
    "case", ["overcash", "overinvoice", "pending", "currency", "party", "unknown", "duplicate"]
)
def test_allocations_fail_closed(case):
    p = population()
    if case == "overcash":
        p["allocations"][0]["amount"] = "71"
    elif case == "overinvoice":
        p["payments"][0]["amount"] = "200"
        p["allocations"][0]["amount"] = "101"
    elif case == "pending":
        p["payments"][0]["confirmation_status"] = "pending"
    elif case == "currency":
        p["payments"][0]["currency"] = "USD"
    elif case == "party":
        p["payments"][0]["counterparty"] = "C2"
    elif case == "unknown":
        p["allocations"][0]["item_id"] = "absent"
    else:
        p["allocations"].append(deepcopy(p["allocations"][0]))
    with pytest.raises(ValueError):
        run("open-item-allocations", p, allocation_basis="invoice_face_amounts")


def test_already_net_balances_cannot_be_silently_allocated_again():
    with pytest.raises(ValueError, match="invoice-face"):
        run("open-item-allocations", population())


def test_amount_and_date_alone_do_not_match_even_when_unique():
    out = reconcile_transactions(
        [transaction(reference="", counterparty="")],
        [transaction(id="S1", reference="", counterparty="")],
    )
    assert not out["matches"]
    assert len(out["unmatched_left"]) == len(out["unmatched_right"]) == 1


def test_unicode_party_identity_is_preserved():
    out = reconcile_transactions(
        [transaction(reference="", counterparty="شركة ألف")],
        [transaction(id="S1", reference="", counterparty="شركة باء")],
    )
    assert not out["matches"]
    out = reconcile_transactions(
        [transaction(reference="مرجع١", counterparty="شركة ألف")],
        [transaction(id="S1", reference="مرجع١", counterparty="شركة ألف")],
    )
    assert out["matches"][0]["rule"] == "REFERENCE_AMOUNT_DATE"


def test_fee_or_reversal_offsets_are_not_net_matched_as_a_settlement():
    out = reconcile_transactions(
        [transaction(amount="100")],
        [transaction(id="S1", amount="110"), transaction(id="S2", amount="-10")],
    )
    assert not out["matches"]


def test_procurement_proposal_is_a_draft_and_holds_sensitive_changes():
    p = purchases()
    p["payments"] = []
    out = run("procurement-match", p)
    assert out["payment_proposals"][0]["state"] == "HOLD"
    for role in ["orders", "invoices"]:
        p[role][0].update(
            approval_status="approved",
            bank_change_verified=True,
            prepared_by="SYN-preparer",
            approved_by="SYN-other-reviewer",
        )
    out = run("procurement-match", p)
    proposal = out["payment_proposals"][0]
    assert proposal["state"] == "DRAFT_REQUIRES_PAYMENT_APPROVAL"
    assert proposal["amount"] == "100"
    assert proposal["payment_instruction_created"] is False
    p["invoices"][0]["payment_hold"] = True
    assert run("procurement-match", p)["payment_proposals"][0]["state"] == "HOLD"


def test_reviewed_forward_rate_components_must_reconcile():
    LossRate.model_validate(
        rate(
            historical_loss_rate="0.08",
            forward_adjustment="0.02",
            forward_evidence="SYN macro forecast",
        )
    )
    with pytest.raises(ValueError):
        LossRate.model_validate(
            rate(
                historical_loss_rate="0.08",
                forward_adjustment="0.01",
                forward_evidence="SYN forecast",
            )
        )


def test_customer_override_reuses_e09_and_preserves_original_estimate():
    body = {
        "approach": "provision_matrix",
        "effective_interest_rate": "0",
        "historical_data_source": "SYN loss history",
        "sicr_methodology": "SYN matrix only",
        "default_definition": "SYN approved",
        "write_off_policy": "SYN no write off",
        "segment_loss_rates": {"A": "0.1"},
        "exposures": [
            {
                "reference": "C1",
                "amount": "100",
                "stage": 2,
                "segment": "A",
                "override_loss": "4",
                "override_reason": "SYN reviewed specific customer assessment",
            }
        ],
        "scenarios": [
            {
                "name": "SYN weighted",
                "probability": "1",
                "pd_12_month": "0",
                "pd_lifetime": "0",
                "lgd": "0",
            }
        ],
    }
    out = calculate("ecl", body)
    assert Decimal(out["schedule"][0]["baseline_ecl"]) == 10
    assert Decimal(out["total_ecl"]) == 4
    body["exposures"][0]["override_reason"] = ""
    with pytest.raises(ValueError, match="override"):
        calculate("ecl", body)
