"""Literal independent arithmetic vectors; these do not qualify any legal rate."""

from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory import validation
from app.modules.regulatory.benefit_profiles import BenefitParameters
from app.modules.regulatory.payroll_profiles import PayrollParameters
from app.modules.regulatory.schemas import Rule
from app.modules.regulatory.validation_schemas import RuleFixture
from tests.unit.test_benefit_profiles import profile as benefit_profile
from tests.unit.test_payroll_profiles import profile as payroll_profile
from tests.unit.test_payroll_rule_workflow import basis
from tests.unit.test_payroll_rule_workflow import rule as payroll_parameters
from tests.unit.test_practice_audit_workflows import (
    benefit_employee,
    benefit_rule,
    part_time_employee,
)
from tests.unit.test_regulatory_evaluation import fixture

REFERENCE = "Independently supplied synthetic arithmetic vector; no legal qualification"


def generic_case(**changes):
    return RuleFixture.model_validate(
        {
            "id": "STANDARD",
            "kind": "flat_rate",
            "expected_reference": REFERENCE,
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "facts": {"entity_type": "company", "tax_base": "100.01", "tax_base_currency": "AED"},
            "expected_applicability": "APPLICABLE",
            "expected_amount": "12.50125",
            **changes,
        }
    )


def assert_receipt(rule, cases):
    sha = fingerprint(rule.model_dump(mode="json"))
    receipt = validation.run(rule, sha, cases)
    assert receipt["passed"] and receipt["rule_sha256"] == sha
    assert validation.require_current(rule, sha, receipt) is receipt
    return receipt


def test_exact_unrounded_rate_and_date_currency_boundaries():
    rule = fixture(
        method="flat_rate",
        rate="0.125",
        calculation_currency="AED",
        input_requirements=["tax_base"],
    )
    receipt = assert_receipt(
        rule,
        [
            generic_case(),
            generic_case(
                id="BEFORE",
                period_start="2025-12-31",
                expected_applicability="OUTSIDE_EFFECTIVE_PERIOD",
                expected_amount=None,
            ),
            generic_case(
                id="CURRENCY",
                facts={"entity_type": "company", "tax_base": "100.01", "tax_base_currency": "USD"},
                expected_applicability="PENDING",
                expected_amount=None,
            ),
        ],
    )
    assert Decimal(receipt["outcomes"][0]["actual"]["amount"]) == Decimal("12.50125")
    assert receipt["applicable_case_count"] == 1


def test_checklist_requires_a_demonstrated_applicable_case():
    rule = fixture()
    case = generic_case(kind="checklist", expected_amount=None)
    assert_receipt(rule, [case])
    with pytest.raises(validation.FixtureMismatch):
        validation.run(
            rule,
            "a" * 64,
            [
                generic_case(
                    kind="checklist",
                    expected_amount=None,
                    facts={},
                    expected_applicability="PENDING",
                )
            ],
        )


@pytest.mark.parametrize(
    "part_time,cap,expected",
    [(False, "24", "2100.00"), (True, "24", "1050.00"), (True, "0.1", "150.00")],
)
def test_benefit_vectors_use_actual_employee_calculator(part_time, cap, expected):
    params = benefit_rule(
        work_model="part-time" if part_time else "full-time", maximum_salary_months=cap
    )
    rule = benefit_profile(
        benefit_parameters={
            key: value for key, value in params.items() if key in BenefitParameters.model_fields
        }
    )
    employee = (
        part_time_employee(amount=expected) if part_time else benefit_employee(amount=expected)
    )
    case = RuleFixture(
        id="EMPLOYEE",
        kind="benefit_profile",
        expected_reference=REFERENCE,
        employee=employee,
        as_of="2026-06-30",
        expected_state="MATCHED",
        expected_amount=expected,
    )
    receipt = assert_receipt(rule, [case])
    assert receipt["outcomes"][0]["actual"]["amount"] == expected


@pytest.mark.parametrize(
    "component,changes,pension,expected",
    [
        ("PF:EMPLOYEE", {}, None, "1800"),
        ("PF:EPS", {"rate": "0.0833"}, None, "1250"),
        ("PF:EMPLOYER", {"formula": "employer-minus-eps"}, "1250", "550"),
        (
            "PT",
            {"formula": "fixed", "fixed_amount": "250", "rate": None, "salary_cap": None},
            None,
            "250",
        ),
    ],
)
def test_payroll_vectors_use_actual_rounding_caps_and_pension_offset(
    component, changes, pension, expected
):
    params = payroll_parameters(component, **changes)
    rule = Rule.model_validate(
        {
            **payroll_profile().model_dump(mode="json"),
            "payroll_parameters": {
                key: value for key, value in params.items() if key in PayrollParameters.model_fields
            },
        }
    )
    case = RuleFixture(
        id="WAGE",
        kind="payroll_profile",
        expected_reference=REFERENCE,
        basis=basis(component),
        as_of="2026-06-30",
        reported_amount=expected,
        pension_amount=pension,
        expected_state="MATCHED",
        expected_amount=expected,
    )
    receipt = assert_receipt(rule, [case])
    assert Decimal(receipt["outcomes"][0]["actual"]["amount"]) == Decimal(expected)


def test_short_lived_payroll_amendment_records_only_blocking_support():
    rule = Rule.model_validate(
        {
            **payroll_profile().model_dump(mode="json"),
            "effective_from": "2026-06-10",
            "effective_to": "2026-06-20",
        }
    )
    case = RuleFixture(
        id="SPLIT",
        kind="payroll_profile",
        expected_reference=REFERENCE,
        basis=basis(),
        as_of="2026-06-30",
        reported_amount="1800",
        expected_state="RULE_MISSING_OR_SPLIT_PERIOD",
    )
    receipt = assert_receipt(rule, [case])
    assert receipt["support"] == "BLOCKING_ONLY_NO_COMPLETE_WAGE_MONTH"
    assert receipt["applicable_case_count"] == 0


def test_wrong_expected_amount_is_not_accepted_or_replaced_with_machine_output():
    rule = fixture(
        method="flat_rate",
        rate="0.125",
        calculation_currency="AED",
        input_requirements=["tax_base"],
    )
    with pytest.raises(validation.FixtureMismatch) as failure:
        validation.run(rule, "a" * 64, [generic_case(expected_amount="12.50")])
    row = failure.value.outcomes[0]
    assert row["passed"] is False and row["expected"]["amount"] == "12.50"
    assert Decimal(row["actual"]["amount"]) == Decimal("12.50125")


def test_receipts_bind_expected_cases_rule_content_and_implementation(monkeypatch):
    rule = fixture(
        method="flat_rate",
        rate="0.125",
        calculation_currency="AED",
        input_requirements=["tax_base"],
    )
    sha = fingerprint(rule.model_dump(mode="json"))
    receipt = assert_receipt(rule, [generic_case()])
    modified = deepcopy(receipt)
    modified["cases"][0]["expected_amount"] = "12.50"
    for content_sha, proof in (("b" * 64, receipt), (sha, modified), (sha, None)):
        with pytest.raises(HTTPException) as error:
            validation.require_current(rule, content_sha, proof)
        assert error.value.status_code == 409
    monkeypatch.setattr(validation, "implementation_hash", lambda method: "c" * 64)
    with pytest.raises(HTTPException):
        validation.require_current(rule, sha, receipt)


def test_missing_duplicate_and_wrong_kind_cases_fail_closed():
    rule = fixture()
    with pytest.raises(ValueError):
        validation.run(rule, "a" * 64, [])
    case = generic_case(kind="checklist", expected_amount=None)
    with pytest.raises(ValueError):
        validation.run(rule, "a" * 64, [case, case])
    with pytest.raises(ValueError):
        validation.run(rule, "a" * 64, [generic_case()])


def test_receipt_detects_loaded_calculator_change_without_source_file_edits(monkeypatch):
    from app.modules.regulatory import evaluation

    rule = fixture(
        method="flat_rate",
        rate="0.125",
        calculation_currency="AED",
        input_requirements=["tax_base"],
    )
    sha = fingerprint(rule.model_dump(mode="json"))
    receipt = assert_receipt(rule, [generic_case()])
    monkeypatch.setattr(
        evaluation, "evaluate", lambda *args, **kwargs: {"applicability": "PENDING"}
    )
    with pytest.raises(HTTPException) as error:
        validation.require_current(rule, sha, receipt)
    assert error.value.status_code == 409


def test_runtime_fingerprint_is_stable_while_calculation_results_remain_live():
    from tests.unit.test_payroll_rule_workflow import pf_fixture, run

    before = validation.implementation_hash("payroll_profile")
    result = run(*pf_fixture())
    assert len(result["rows"]) == 3
    assert validation.implementation_hash("payroll_profile") == before


def test_employer_fixtures_preserve_resolved_paise_and_missing_pension_refusal():
    params = payroll_parameters("PF:EMPLOYER", formula="employer-minus-eps")
    rule = Rule.model_validate(
        {
            **payroll_profile().model_dump(mode="json"),
            "payroll_parameters": {
                key: value for key, value in params.items() if key in PayrollParameters.model_fields
            },
        }
    )
    positive = RuleFixture(
        id="RESOLVED",
        kind="payroll_profile",
        expected_reference=REFERENCE,
        basis=basis("PF:EMPLOYER"),
        as_of="2026-06-30",
        reported_amount="549.75",
        pension_amount="1250.25",
        expected_state="MATCHED",
        expected_amount="549.75",
    )
    missing = positive.model_copy(
        update={
            "id": "MISSING",
            "pension_amount": None,
            "expected_state": "PENSION_COMPONENT_UNRESOLVED",
            "expected_amount": None,
        }
    )
    receipt = assert_receipt(rule, [positive, missing])
    assert receipt["outcomes"][0]["actual"]["amount"] == "549.75"
    assert receipt["outcomes"][1]["actual"]["state"] == "PENSION_COMPONENT_UNRESOLVED"
    assert receipt["applicable_case_count"] == 1
