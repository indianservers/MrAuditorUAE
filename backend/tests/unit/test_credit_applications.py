from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import calculate as workflow_calculate
from app.modules.country_workflows.catalogue import WORKFLOWS
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_shared_audit_workflows import control, run, source
from tests.unit.test_shared_audit_workflows import item as original_item


def item(**changes):
    return {**original_item(), "document_type": "invoice", **changes}


def population():
    return {
        "items": [
            item(),
            item(id="CN1", reference="CN-1", amount="-40", document_type="credit-note"),
        ],
        "controls": [control(amount="60")],
        "applications": [
            {
                "id": "A1",
                "credit_item_id": "CN1",
                "invoice_item_id": "I1",
                "currency": "AED",
                "date": "2026-06-01",
                "amount": "25",
                "evidence_reference": "SYN-reviewed-note",
                "allocation_reference": "SYN-allocation-1",
                "rationale": "Synthetic independently assessed application to the invoice",
            }
        ],
    }


def calculate(p):
    return run("credit-note-applications", p, allocation_basis="pre_application_balances")


@pytest.mark.parametrize("side,currency", [("receivable", "AED"), ("payable", "INR")])
def test_partial_credit_application_preserves_signed_control_and_residual(side, currency):
    p = population()
    for row in p["items"] + p["controls"]:
        row.update(side=side, currency=currency)
    p["applications"][0]["currency"] = currency
    before = deepcopy(p)
    out = calculate(p)
    assert p == before
    assert not out["blocked"]
    assert [row["amount"] for row in out["remaining_open_items"]] == ["75", "-15"]
    credit = next(row for row in out["rows"] if row.get("item_id") == "CN1")
    assert credit["state"] == "UNAPPLIED_CREDIT" and credit["application_ids"] == ["A1"]
    assert out["rows"][-1]["subledger_amount"] == "60"
    assert out["rows"][-1]["state"] == "MATCHED"


def test_full_credit_application_retains_zero_credit_in_population():
    p = population()
    p["applications"][0]["amount"] = "40"
    out = calculate(p)
    assert out["exception_count"] == 0
    assert [r["amount"] for r in out["remaining_open_items"]] == ["60", "0"]


def test_credit_can_split_across_invoices_without_changing_gl_balance():
    p = population()
    p["items"].append(item(id="I2", reference="INV-2", amount="20"))
    p["controls"][0]["amount"] = "80"
    p["applications"].append(
        {
            **p["applications"][0],
            "id": "A2",
            "invoice_item_id": "I2",
            "allocation_reference": "SYN-allocation-2",
            "amount": "15",
        }
    )
    out = calculate(p)
    assert [r["amount"] for r in out["remaining_open_items"]] == ["75", "0", "5"]
    assert not out["blocked"] and out["exception_count"] == 0


@pytest.mark.parametrize(
    "case",
    [
        "party",
        "account",
        "side",
        "currency",
        "application-currency",
        "future",
        "predates",
        "missing",
        "overcredit",
        "overinvoice",
        "duplicate-evidence",
        "self",
        "zero",
        "negative",
    ],
)
def test_invalid_applications_fail_closed(case):
    p = population()
    application = p["applications"][0]
    if case in {"party", "account", "side", "currency"}:
        field, value = {
            "party": ("counterparty", "Other"),
            "account": ("account", "AP"),
            "side": ("side", "payable"),
            "currency": ("currency", "USD"),
        }[case]
        p["items"][1][field] = value
    elif case == "application-currency":
        application["currency"] = "USD"
    elif case in {"future", "predates"}:
        application["date"] = "2026-07-01" if case == "future" else "2026-04-30"
    elif case == "missing":
        application["invoice_item_id"] = "absent"
    elif case == "overcredit":
        application["amount"] = "41"
    elif case == "overinvoice":
        p["items"][0]["amount"] = "20"
    elif case == "duplicate-evidence":
        p["applications"].append({**application, "id": "different-id", "amount": "1"})
    elif case == "self":
        application["invoice_item_id"] = "CN1"
    else:
        application["amount"] = "0" if case == "zero" else "-1"
    with pytest.raises(ValueError):
        calculate(p)


def test_already_net_balance_basis_is_not_accepted():
    with pytest.raises(ValueError, match="pre-application"):
        run("credit-note-applications", population())


def test_matching_application_does_not_override_missing_or_wrong_gl_control():
    p = population()
    p["controls"][0]["amount"] = "61"
    out = calculate(p)
    assert out["blocked"] and out["rows"][-1]["difference"] == "-1"


def test_duplicate_document_cannot_be_given_new_row_id_to_increase_available_credit():
    p = population()
    p["items"].append({**p["items"][1], "id": "CN-alias"})
    with pytest.raises(ValueError, match="Duplicate open-item document"):
        calculate(p)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR"), ("GB", "GBP")])
def test_same_application_engine_uses_engagement_country_without_local_tax_assumption(
    country, currency
):
    p = population()
    for rows in p.values():
        for row in rows:
            row["currency"] = currency
    sources = {
        role: source(WORKFLOWS["credit-note-applications"][2][role], rows)
        for role, rows in p.items()
    }
    data = WorkflowInput(
        workflow="credit-note-applications",
        allocation_basis="pre_application_balances",
        source_ids={role: uuid4() for role in sources},
        as_of="2026-06-30",
        title="Synthetic country credit application",
        rationale="Explicit reviewed credit applications with no tax treatment assumption",
    )
    out = workflow_calculate(data, country, sources)
    assert [r["amount"] for r in out["remaining_open_items"]] == ["75", "-15"]
    assert out["statutory_calculation_qualified"] is False
