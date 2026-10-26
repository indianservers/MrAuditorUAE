"""Independent expected-value and fail-closed scenarios for shared audit procedures."""

import csv
import io
import uuid
from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.catalogue import WORKFLOWS
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import ROW_TYPES, SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv
from app.modules.intelligence.schemas import JobInput


def item(**changes):
    return dict(
        id="I1",
        account="AR",
        counterparty="C1",
        reference="INV-1",
        side="receivable",
        currency="AED",
        document_date="2026-05-01",
        due_date="2026-05-31",
        balance_date="2026-06-30",
        amount="100",
        **changes,
    )


def control(**changes):
    return {
        "id": "C1",
        "account": "AR",
        "side": "receivable",
        "currency": "AED",
        "as_of": "2026-06-30",
        "amount": "100",
        **changes,
    }


def settlement(**changes):
    return {
        "id": "S1",
        "item_id": "I1",
        "account": "AR",
        "counterparty": "C1",
        "currency": "AED",
        "date": "2026-07-15",
        "amount": "40",
        "evidence_reference": "BANK-PAYMENT-1",
        "allocation_reference": "ALLOC-1",
        **changes,
    }


def source(kind, rows):
    fields = list(ROW_TYPES[kind].model_fields)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    field = (
        "tax"
        if kind == "import-vat-lines"
        else "requested_amount"
        if kind == "confirmations"
        else "amount"
    )
    totals = {}
    for row in rows:
        if field in row:
            totals[row["currency"]] = totals.get(row["currency"], Decimal(0)) + Decimal(row[field])
    return parse_csv(
        buffer.getvalue().encode(),
        SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type=kind,
            label="SYNTHETIC audit source",
            expected_rows=len(rows),
            control_totals=totals,
            **(
                {
                    "import_taxable_base_control": sum(
                        (Decimal(row["net"]) for row in rows), Decimal(0)
                    )
                }
                if kind == "import-vat-lines"
                else {}
            ),
            nil_reason="Independent declaration of a nil source population" if not rows else None,
        ),
    )


def run(workflow, populations, **parameters):
    country = parameters.pop("country", "AE")
    sources = {
        role: source(WORKFLOWS[workflow][2][role], rows) for role, rows in populations.items()
    }
    params = dict(
        workflow=workflow,
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        title="SYNTHETIC shared workflow",
        rationale="Independently specified audit acceptance scenario",
    )
    if workflow != "subledger-control":
        params["review_through"] = "2026-08-31"
    if workflow in {
        "expense-cutoff",
        "excise-reconciliation",
        "gold-reconciliation",
        "asset-register-review",
    }:
        params["period_start"] = "2026-01-01"
    params.update(parameters)
    validated = WorkflowInput(**params)
    # The job boundary must preserve exactly the same typed contract.
    JobInput(operation="country-workflow", payload=validated.model_dump(mode="json"))
    return calculate(validated, country, sources)


def population(**changes):
    return {"items": [item()], "controls": [control()], "settlements": [settlement()], **changes}


def test_subsequent_settlement_preserves_reporting_balance_and_ages_true_open_items():
    output = run("subsequent-settlements", population())
    row = output["rows"][-1]
    assert not output["blocked"]
    assert row["reporting_date_balance"] == "100"
    assert row["subsequent_settled"] == "40"
    assert row["remaining_balance"] == "60"
    assert row["overdue_days_at_reporting"] == 30
    assert row["state"] == "PARTIALLY_SETTLED"
    assert approval_error(output)


@pytest.mark.parametrize(
    "changes,state",
    [
        ({"currency": "USD"}, "SETTLEMENT_IDENTITY_MISMATCH"),
        ({"counterparty": "C2"}, "SETTLEMENT_IDENTITY_MISMATCH"),
        ({"account": "OTHER"}, "SETTLEMENT_IDENTITY_MISMATCH"),
        ({"item_id": "UNKNOWN"}, "UNKNOWN_ITEM"),
        ({"amount": "-20"}, "SETTLEMENT_SIGN_MISMATCH"),
        ({"date": "2026-06-30"}, "OUTSIDE_REVIEW_WINDOW"),
        ({"date": "2026-09-01"}, "OUTSIDE_REVIEW_WINDOW"),
    ],
)
def test_invalid_settlements_cannot_reduce_exposure_or_be_approved(changes, state):
    output = run("subsequent-settlements", population(settlements=[settlement(**changes)]))
    assert output["blocked"]
    assert output["rows"][-1]["remaining_balance"] == "100"
    assert state in [r["state"] for r in output["rows"]]
    for row in output["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(output)


def test_overallocation_blocked_and_duplicate_payment_allocation_rejected():
    output = run("subsequent-settlements", population(settlements=[settlement(amount="101")]))
    assert output["blocked"] and output["rows"][-1]["state"] == "OVERALLOCATED"
    with pytest.raises(ValueError, match="Duplicate settlement"):
        run("subsequent-settlements", population(settlements=[settlement(), settlement(id="S2")]))


def test_one_bank_payment_may_have_distinct_explicit_allocations():
    output = run(
        "subsequent-settlements",
        population(
            settlements=[
                settlement(amount="40"),
                settlement(id="S2", allocation_reference="ALLOC-2", amount="60"),
            ]
        ),
    )
    assert output["rows"][-1]["state"] == "MATCHED"
    assert output["rows"][-1]["remaining_balance"] == "0"
    assert not output["blocked"]


def test_credit_note_allocations_preserve_signed_balance():
    credit = item()
    credit.update(amount="-100", document_type="credit-note")
    output = run(
        "subsequent-settlements",
        population(
            items=[credit],
            controls=[control(amount="-100")],
            settlements=[settlement(amount="-40")],
        ),
    )
    assert output["rows"][-1]["remaining_balance"] == "-60"


@pytest.mark.parametrize(
    "controls,state",
    [
        ([], "MISSING_CONTROL"),
        ([control(amount="99")], "CONTROL_DIFFERENCE"),
    ],
)
def test_gl_differences_block_approval(controls, state):
    output = run("subledger-control", {"items": [item()], "controls": controls})
    assert output["blocked"] and output["rows"][0]["state"] == state


def test_cross_currency_control_totals_do_not_net_and_duplicate_controls_fail():
    usd = item()
    usd.update(id="I2", currency="USD", amount="-100", document_type="credit-note")
    output = run("subledger-control", {"items": [item(), usd], "controls": [control()]})
    assert output["blocked"] and len(output["rows"]) == 2
    with pytest.raises(ValueError, match="Duplicate account"):
        run("subledger-control", {"items": [item()], "controls": [control(), control(id="C2")]})


def response(**changes):
    return {
        "id": "R1",
        "item_id": "I1",
        "counterparty": "C1",
        "currency": "AED",
        "as_of": "2026-06-30",
        "requested_amount": "100",
        "response_amount": "100",
        "status": "received",
        "requested_on": "2026-07-01",
        "responded_on": "2026-07-10",
        "contact_verified": True,
        "independently_received": True,
        "evidence_reference": "RESPONSE-1",
        **changes,
    }


@pytest.mark.parametrize(
    "changes,state,blocked",
    [
        ({}, "MATCHED", False),
        ({"response_amount": "90"}, "RESPONSE_DIFFERENCE", False),
        ({"status": "disputed"}, "DISPUTED", False),
        ({"contact_verified": False}, "INDEPENDENCE_EVIDENCE_MISSING", True),
        ({"independently_received": False}, "INDEPENDENCE_EVIDENCE_MISSING", True),
        ({"evidence_reference": ""}, "INDEPENDENCE_EVIDENCE_MISSING", True),
        ({"currency": "USD"}, "CONFIRMATION_SCOPE_MISMATCH", True),
        ({"requested_amount": "101"}, "CONFIRMATION_SCOPE_MISMATCH", True),
        ({"responded_on": "2026-09-01"}, "OUTSIDE_REVIEW_WINDOW", True),
    ],
)
def test_external_confirmation_requires_scope_and_independence(changes, state, blocked):
    output = run(
        "balance-confirmations",
        {"items": [item()], "controls": [control()], "responses": [response(**changes)]},
    )
    assert output["blocked"] is blocked and output["rows"][-1]["state"] == state


def test_nonresponses_remain_exceptions_and_multiple_current_responses_are_rejected():
    output = run(
        "balance-confirmations", {"items": [item()], "controls": [control()], "responses": []}
    )
    assert output["rows"][-1]["state"] == "NOT_REQUESTED"
    assert approval_error(output)
    with pytest.raises(ValueError, match="one current confirmation"):
        run(
            "balance-confirmations",
            {
                "items": [item()],
                "controls": [control()],
                "responses": [response(), response(id="R2")],
            },
        )


@pytest.mark.parametrize(
    "recognition,posting,state",
    [
        ("2026-06-29", None, "UNRECORDED_LIABILITY"),
        ("2026-06-29", "2026-07-02", "LATE_RECOGNITION"),
        ("2026-07-01", "2026-06-30", "WRONG_PERIOD"),
        ("2025-12-31", "2026-01-01", "WRONG_PERIOD"),
        ("2026-06-30", "2026-06-30", "MATCHED"),
        ("2026-07-01", "2026-07-02", "MATCHED"),
    ],
)
def test_cutoff_is_based_on_recognition_not_invoice_date(recognition, posting, state):
    document = dict(
        id="D1",
        counterparty="V1",
        reference="INV-1",
        currency="AED",
        amount="100",
        invoice_date="2026-07-02",
        recognition_date=recognition,
        posting_date=posting,
        evidence_reference="RECEIPT-1",
        recognition_basis="goods-received",
    )
    output = run("expense-cutoff", {"documents": [document]})
    assert output["rows"][0]["state"] == state


def test_missing_review_window_and_invalid_sign_are_rejected_at_submission():
    with pytest.raises(ValueError, match="review window"):
        WorkflowInput(
            workflow="subsequent-settlements",
            source_ids={"items": uuid.uuid4()},
            as_of="2026-06-30",
            title="SYNTHETIC",
            rationale="Missing input test",
        )
    bad = deepcopy(item())
    bad["amount"] = "-100"
    with pytest.raises(ValueError, match="Invalid CSV"):
        source("audit-open-items", [bad])
