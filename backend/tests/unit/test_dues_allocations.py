"""Independently specified pooled-payment controls, not qualified statutory rates."""

import io
import json
import uuid
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.intelligence.exports import render
from tests.unit.country_workflow_cases import obligation, transaction
from tests.unit.test_country_workflows import parsed


def example(currency="AED", component="SALARY"):
    common = {"currency": currency, "component": component, "payment_date": None}
    expected = [
        obligation(id="E1", amount="100", period="2026-05", due_date="2026-06-05", **common),
        obligation(id="E2", amount="80", period="2026-06", due_date="2026-06-25", **common),
    ]
    reported = [{**row, "id": "R" + row["id"][1:]} for row in expected]
    bank = [
        transaction(id="B1", amount="-150", date="2026-06-01", currency=currency),
        transaction(id="B2", amount="-30", date="2026-06-28", currency=currency),
    ]
    allocations = [
        {
            "id": "A1",
            "expected_id": "E1",
            "reported_id": "R1",
            "transaction_id": "B1",
            "currency": currency,
            "amount": "100",
            "evidence_reference": "SYNTHETIC-PAYROLL-ADVICE",
            "rationale": "Reviewed fictional payment schedule allocation",
        },
        {
            "id": "A2",
            "expected_id": "E2",
            "reported_id": "R2",
            "transaction_id": "B1",
            "currency": currency,
            "amount": "50",
            "evidence_reference": "SYNTHETIC-PAYROLL-ADVICE",
            "rationale": "Reviewed fictional pooled payment allocation",
        },
        {
            "id": "A3",
            "expected_id": "E2",
            "reported_id": "R2",
            "transaction_id": "B2",
            "currency": currency,
            "amount": "30",
            "evidence_reference": "SYNTHETIC-PAYROLL-ADVICE",
            "rationale": "Reviewed fictional final payment allocation",
        },
    ]
    return {"expected": expected, "reported": reported, "bank": bank, "allocations": allocations}


def parameters(**changes):
    return dict(
        workflow="obligation-bank-allocations",
        source_ids={role: uuid.uuid4() for role in example()},
        as_of="2026-06-30",
        title="SYNTHETIC bank settlement review",
        rationale="Reviewed obligation and settlement source scope",
        obligation_month_start="2026-05",
        obligation_month_end="2026-06",
        settlement_start="2026-06-01",
        bank_payment_sign="debit-negative",
        account="BANK-1",
        **changes,
    )


def run(rows=None, country="AE", **changes):
    rows = deepcopy(rows or example())
    types = {
        "expected": "obligations",
        "reported": "obligations",
        "bank": "transactions",
        "allocations": "obligation-allocations",
    }
    sources = {role: parsed(types[role], records) for role, records in rows.items()}
    return calculate(WorkflowInput(**{**parameters(), **changes}), country, sources)


@pytest.mark.parametrize(
    "country,currency,component",
    [("AE", "AED", "SALARY"), ("AE", "USD", "SALARY"), ("IN", "INR", "PF:EMPLOYEE")],
)
def test_one_bank_debit_covers_multiple_months_partial_and_late_payment(
    country, currency, component
):
    result = run(example(currency, component), country, currency=currency)
    controls = result["allocation_controls"]
    assert controls == {
        "currency": currency,
        "expected_amount": "180",
        "reported_amount": "180",
        "allocated_amount": "180",
        "outstanding_expected": "0",
        "unsettled_reported": "0",
        "bank_outflows": "180",
        "unallocated_bank_outflows": "0",
        "bank_inflows_not_netted": "0",
    }
    first, second = result["rows"][:2]
    assert first["state"] == "MATCHED" and first["bank_settled"] == "100"
    assert second["state"] == "LATE_PAYMENT" and second["late_settled_amount"] == "30"
    assert len(second["payment_allocations"]) == 2 and second["outstanding_amount"] == "0"
    assert result["review_status"] == "UNVERIFIED" and not result["statutory_calculation_qualified"]


def test_partial_payment_unallocated_credit_and_missing_due_date_stay_visible():
    data = example()
    data["allocations"].pop()
    data["bank"].append(transaction(id="REFUND", amount="20", currency="AED"))
    data["expected"][1]["due_date"] = None
    data["reported"][1]["due_date"] = None
    result = run(data)
    second = result["rows"][1]
    assert second["outstanding_amount"] == "30" and second["bank_settled"] == "50"
    assert second["timing_status"] == "PENDING_DUE_DATE"
    assert result["allocation_controls"]["bank_inflows_not_netted"] == "20"
    assert result["allocation_controls"]["unallocated_bank_outflows"] == "30"
    assert (
        next(row for row in result["rows"] if row["id"] == "bank:REFUND")["state"]
        == "UNALLOCATED_BANK_MOVEMENT"
    )


@pytest.mark.parametrize(
    "role,index,field,value,error",
    [
        ("allocations", 0, "amount", "101", "overallocated"),
        ("allocations", 1, "amount", "51", "overallocated"),
        ("allocations", 0, "reported_id", "R2", "crosses"),
        ("allocations", 0, "transaction_id", "ABSENT", "missing"),
        ("allocations", 0, "currency", "INR", "crosses"),
        ("bank", 0, "account", "OTHER", "account or currency"),
        ("bank", 0, "currency", "USD", "account or currency"),
        ("bank", 0, "date", "2026-05-31", "settlement window"),
        ("bank", 0, "date", "2026-07-01", "settlement window"),
        ("bank", 0, "amount", "150", "outflows"),
        ("expected", 0, "period", "2026-04", "outside"),
        ("expected", 0, "amount", "-100", "Negative"),
        ("reported", 0, "payment_date", "2026-06-01", "independent allocated"),
    ],
)
def test_invalid_allocation_or_source_scope_fails_closed(role, index, field, value, error):
    data = example()
    data[role][index][field] = value
    with pytest.raises(ValueError, match=error):
        run(data)


def test_duplicate_allocations_and_restatement_overlap_are_rejected():
    for role, error in (
        ("allocations", "Duplicate obligation/reported/bank"),
        ("expected", "Duplicate obligation identity"),
    ):
        data = example()
        data[role].append({**data[role][0], "id": "DUPLICATE"})
        with pytest.raises(ValueError, match=error):
            run(data)


def test_missing_month_and_reported_variance_are_not_zeroed():
    data = example()
    data["reported"][1]["amount"] = "90"
    result = run(data, obligation_month_start="2026-04")
    assert "REPORTED_AMOUNT_VARIANCE" in result["rows"][1]["issues"]
    missing = next(row for row in result["rows"] if row["kind"] == "coverage")
    assert missing["period"] == "2026-04" and missing["state"] == "MISSING_EXPECTED_MONTH"
    assert result["allocation_controls"]["unsettled_reported"] == "10"


def test_country_component_rules_and_explicit_positive_sign():
    with pytest.raises(ValueError, match="Indian domestic"):
        run(example(component="PF:EMPLOYEE"))
    with pytest.raises(ValueError, match="withdrawn"):
        run(example("INR", "TCS:206C(1H)"), "IN", currency="INR")
    data = example()
    for row in data["bank"]:
        row["amount"] = row["amount"].lstrip("-")
    assert (
        run(data, bank_payment_sign="debit-positive")["allocation_controls"]["allocated_amount"]
        == "180"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"bank_payment_sign": None},
        {"settlement_start": None},
        {"account": " "},
        {"obligation_month_end": "2026-07"},
        {"obligation_month_start": "2010-01"},
    ],
)
def test_scope_requires_explicit_bounded_choices(changes):
    with pytest.raises(ValueError):
        WorkflowInput(**{**parameters(), **changes})


def test_export_keeps_late_amount_allocations_and_residual_controls_exact():
    body = run()
    event = {
        "id": "SYNTHETIC-DUES",
        "kind": "country-workflow",
        "version": 1,
        "sha256": "a" * 64,
        "created_at": "2026-06-30T00:00:00Z",
        "body": body,
        "dependencies": [],
    }
    content, _ = render(event, "xlsx")
    workbook = load_workbook(io.BytesIO(content))
    cover = dict(workbook["Source and review"].values)
    controls = json.loads(cover["allocation_controls"])
    assert controls["allocated_amount"] == "180" and controls["outstanding_expected"] == "0"
    assert json.loads(cover["payment_scope"])["bank_payment_sign"] == "debit-negative"
    exported = list(workbook["Rows"].values)
    records = [dict(zip(exported[0], values, strict=True)) for values in exported[1:]]
    second = next(row for row in records if row["id"] == "obligation:E2")
    assert second["late_settled_amount"] == "30" and second["state"] == "LATE_PAYMENT"
    assert {row["transaction_id"] for row in json.loads(second["payment_allocations"])} == {
        "B1",
        "B2",
    }


@pytest.mark.parametrize(
    "country,currency,component", [("AE", "AED", "SALARY"), ("IN", "INR", "PF:EMPLOYEE")]
)
def test_canonical_reversal_flag_blocks_settlement_and_remains_visible(
    country, currency, component
):
    rows = example(currency, component)
    for row in rows["bank"]:
        row["is_reversal"] = row["id"] == "B1"
    with pytest.raises(ValueError, match="unreversed bank outflows"):
        run(rows, country, currency=currency)
    rows["allocations"] = [rows["allocations"][2]]
    result = run(rows, country, currency=currency)
    bank = next(row for row in result["rows"] if row["id"] == "bank:B1")
    assert bank["state"] == "REVERSAL_NOT_SETTLEMENT"
    assert bank["is_reversal"] is True
    assert bank["allocated"] == "0"
    assert bank["unallocated_bank_amount"] == "150"
    assert result["allocation_controls"]["outstanding_expected"] == "150"
