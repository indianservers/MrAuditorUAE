"""Expected gratuity is not a paid amount, pooled cash or a different service span."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.country_workflows.benefit_settlement_source import (
    BenefitSettlementInput,
    source_rows,
)
from app.modules.country_workflows.schemas import Obligation
from tests.unit.test_dues_allocations import run as allocate
from tests.unit.test_practice_audit_workflows import (
    benefit_employee,
    benefit_rule,
    part_time_employee,
)
from tests.unit.test_shared_audit_workflows import run


def reviewed():
    return run(
        "uae-benefit-review",
        {
            "employees": [benefit_employee(), part_time_employee(id="E2")],
            "rules": [benefit_rule(), benefit_rule(id="PART", work_model="part-time")],
        },
    )


def request(**changes):
    return BenefitSettlementInput.model_validate(
        {
            "result_id": uuid4(),
            "employer_registration": "SYNTHETIC-EMPLOYER",
            "settlement_evidence_version_id": uuid4(),
            "selections": [
                {
                    "result_row_id": "E1",
                    "due_date": "2026-07-14",
                    "due_date_reference": "SYN-SUPPORT-1",
                }
            ],
            "expected_rows": 1,
            "control_total": "2100",
            "label": "Synthetic gratuity expectation",
            "assessment": "Synthetic independently assessed employer, employee identity and due-date support",
            **changes,
        }
    )


def test_expected_amount_not_declared_paid_is_preserved_without_mutating_parent():
    body = reviewed()
    body["rows"][0].update(paid_benefit="999", difference="-1101", state="BENEFIT_DIFFERENCE")
    original = deepcopy(body)
    rows, totals, excluded = source_rows(body, request())
    assert body == original
    row = rows[0]
    assert row["amount"] == "2100.00" and totals == {"AED": "2100.00"}
    assert row["payment_date"] is None
    assert row["benefit_scope"] == {
        "service_start": "2025-07-01",
        "service_end": "2026-06-30",
        "regime": "SYNTHETIC-REGIME",
        "cohort": "SYNTHETIC-COHORT",
        "work_model": "full-time",
        "scheme": "gratuity",
    }
    assert row["source_result_row_id"] == "E1"
    assert row["rule_document_sha256"] == "a" * 64
    assert row["amount_basis"] == "REVIEWED_EXPECTED_BENEFIT_NOT_DECLARED_PAID_AMOUNT"
    assert excluded == [{"source_result_row_id": "E2", "reason": "UNSELECTED_BENEFIT_ROW"}]


def test_full_and_part_time_rows_remain_separate_with_independent_total():
    controls = request().model_dump(mode="json")
    controls.update(expected_rows=2, control_total="3150")
    controls["selections"].append({**controls["selections"][0], "result_row_id": "E2"})
    rows, totals, excluded = source_rows(
        reviewed(), BenefitSettlementInput.model_validate(controls)
    )
    assert [row["amount"] for row in rows] == ["2100.00", "1050.00"]
    assert [row["benefit_scope"]["work_model"] for row in rows] == ["full-time", "part-time"]
    assert totals == {"AED": "3150.00"} and not excluded


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_benefit": None},
        {"expected_benefit": "NaN"},
        {"expected_benefit": "-1"},
        {"expected_benefit": "not a number"},
        {"currency": "INR"},
        {"service_start": None},
        {"service_end": None},
        {"scheme": "alternative"},
        {"work_model": "other"},
        {"work_model_constant_for_service": False},
        {"rule_source_id": ""},
        {"rule_document_version_id": None},
        {"rule_document_sha256": None},
        {"state": "RULE_MISSING"},
    ],
)
def test_unsupported_or_undated_results_cannot_be_relabelled_as_settlement(changes):
    body = reviewed()
    body["rows"][0].update(changes)
    with pytest.raises(ValueError):
        source_rows(body, request())


@pytest.mark.parametrize("changes", [{"workflow": "india-payroll-rules"}, {"blocked": True}])
def test_wrong_or_blocked_workflow_does_not_produce_gratuity(changes):
    with pytest.raises(ValueError, match="resolved UAE"):
        source_rows({**reviewed(), **changes}, request())


def test_zero_expected_gratuity_requires_explicit_zero_control_not_missing_data():
    body = reviewed()
    body["rows"][0]["expected_benefit"] = "0"
    rows, totals, _ = source_rows(body, request(control_total="0"))
    assert rows[0]["amount"] == "0" and totals == {"AED": "0"}


def test_independent_control_cannot_be_replaced_with_the_engine_total():
    with pytest.raises(ValueError, match="amount control"):
        source_rows(reviewed(), request(control_total="2099.99"))


def test_duplicate_missing_and_uncontrolled_selections_are_rejected():
    data = request().model_dump(mode="json")
    with pytest.raises(ValueError):
        request(expected_rows=2)
    with pytest.raises(ValueError):
        request(selections=data["selections"] * 2, expected_rows=2, control_total="4200")
    with pytest.raises(ValueError, match="missing"):
        source_rows(
            reviewed(), request(selections=[{**data["selections"][0], "result_row_id": "UNKNOWN"}])
        )


def settlement():
    rows, _, _ = source_rows(reviewed(), request())
    expected = {key: value for key, value in rows[0].items() if key in Obligation.model_fields}
    expected["id"] = "EXPECTED"
    reported = {**deepcopy(expected), "id": "REPORTED"}
    return {
        "expected": [expected],
        "reported": [reported],
        "bank": [
            {
                "id": "BANK",
                "account": "BANK-1",
                "reference": "PAY",
                "date": "2026-07-10",
                "currency": "AED",
                "amount": "-2100",
            }
        ],
        "allocations": [
            {
                "id": "LINK",
                "expected_id": "EXPECTED",
                "reported_id": "REPORTED",
                "transaction_id": "BANK",
                "currency": "AED",
                "amount": "2100",
                "evidence_reference": "SYN-ADVICE",
                "rationale": "Synthetic explicit employee settlement allocation",
            }
        ],
    }


def compare(data, **changes):
    data = deepcopy(data)
    for role in ("expected", "reported"):
        for row in data[role]:
            row["benefit_scope"] = json.dumps(row["benefit_scope"])
    return allocate(data, as_of="2026-07-31", **changes)


def test_independent_reported_and_booked_bank_evidence_establishes_only_declared_settlement():
    out = compare(settlement())
    row = next(row for row in out["rows"] if row["kind"] == "obligation")
    assert row["expected_amount"] == "2100.00" and row["bank_settled"] == "2100"
    assert row["outstanding_amount"] == "0.00" and row["state"] == "MATCHED"
    assert row["benefit_scope"]["service_start"] == "2025-07-01"


@pytest.mark.parametrize(
    "field,value",
    [
        ("service_start", "2024-07-01"),
        ("service_end", "2026-06-29"),
        ("regime", "OTHER"),
        ("cohort", "OTHER"),
        ("work_model", "part-time"),
    ],
)
def test_bank_cash_cannot_clear_a_different_employment_scope(field, value):
    data = settlement()
    data["reported"][0]["benefit_scope"][field] = value
    with pytest.raises(ValueError, match="Allocation crosses"):
        compare(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"date": "2026-06-29"},
        {"is_reversal": True},
        {
            "date": "2026-07-10",
            "bank_value_date": "2026-07-10",
            "bank_date_basis": "VALUE_DATE_FALLBACK",
        },
    ],
)
def test_advances_reversals_and_value_date_fallback_do_not_establish_final_gratuity(changes):
    data = settlement()
    data["bank"][0].update(changes)
    with pytest.raises(ValueError, match="predates service|unreversed|value-date"):
        compare(data)


def test_domestic_uae_gratuity_scope_is_not_an_indian_payroll_obligation():
    with pytest.raises(ValueError, match="UAE/AED"):
        compare(settlement(), country="IN")


def test_gratuity_requires_scope_and_due_date_cannot_predate_service_end():
    row = settlement()["expected"][0]
    for changed in ({**row, "benefit_scope": None}, {**row, "due_date": "2026-06-29"}):
        with pytest.raises(ValueError):
            Obligation.model_validate(changed)


def test_partial_gratuity_keeps_an_overdue_residual_without_netting_declared_paid_amounts():
    data = settlement()
    data["bank"][0]["amount"] = "-1500"
    data["allocations"][0]["amount"] = "1500"
    out = compare(data)
    row = next(row for row in out["rows"] if row["kind"] == "obligation")
    assert row["outstanding_amount"] == "600.00"
    assert row["state"] == "PARTIALLY_SETTLED" and row["timing_status"] == "OVERDUE_RESIDUAL"
    assert out["exception_count"] > 0


def test_fully_allocated_gratuity_can_still_be_late_against_the_assessed_due_date():
    data = settlement()
    data["bank"][0]["date"] = "2026-07-15"
    row = next(row for row in compare(data)["rows"] if row["kind"] == "obligation")
    assert row["outstanding_amount"] == "0.00"
    assert row["late_settled_amount"] == "2100" and row["state"] == "LATE_PAYMENT"


def test_long_original_employee_identifier_is_preserved_with_a_bounded_derived_row_id():
    body = reviewed()
    identifier = "E" * 120
    body["rows"][0]["id"] = identifier
    data = request().model_dump(mode="json")
    data["selections"][0]["result_row_id"] = identifier
    rows, _, _ = source_rows(body, BenefitSettlementInput.model_validate(data))
    assert rows[0]["subject"] == identifier and len(rows[0]["id"]) <= 120
