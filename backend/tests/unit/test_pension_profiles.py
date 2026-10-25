"""Literal pension publication vectors; not a qualified authority rule pack."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory import validation
from app.modules.regulatory.evaluation import evaluate
from app.modules.regulatory.pension_profiles import PensionParameters
from app.modules.regulatory.schemas import Rule
from app.modules.regulatory.validation_schemas import RuleFixture
from tests.unit.test_pension_workflow import pension_fixture
from tests.unit.test_regulatory_evaluation import fixture


def profile(component="EMPLOYEE", **changes):
    _, rules, _ = pension_fixture()
    source = next(rule for rule in rules if rule["component"] == "PENSION:" + component)
    parameters = {
        key: value for key, value in source.items() if key in PensionParameters.model_fields
    }
    return fixture(
        country="AE",
        rule_key="AE-SYNTHETIC-PENSION-" + component,
        framework="IFRS",
        method="pension_profile",
        pension_parameters=parameters,
        period_basis="transaction_date",
        applicability=[],
        input_requirements=["reviewed_assessed_pension_bases"],
        output_requirements=["pension_contributions"],
        **changes,
    )


def vector(component="EMPLOYEE", **changes):
    bases, _, _ = pension_fixture()
    basis = next(row for row in bases if row["component"] == "PENSION:" + component)
    return RuleFixture.model_validate(
        {
            "id": "SYNTHETIC-" + component,
            "kind": "pension_profile",
            "expected_reference": "Literal independently specified synthetic pension vector; not legal data",
            "pension_basis": basis,
            "as_of": "2026-06-30",
            "reported_amount": "700.00",
            "expected_state": "MATCHED",
            "expected_amount": "700.00",
            **changes,
        }
    )


def test_profile_requires_pension_workflow_and_does_not_supply_legal_rates():
    rule = profile()
    assert str(rule.pension_parameters.rate) == "0.07"
    assert rule.validation_status == "AWAITING_VALIDATION"
    result = evaluate(rule, {}, date(2026, 1, 1), date(2026, 12, 31), date(2026, 6, 1))
    assert (
        result["applicability"] == "PENDING" and result["required_workflow"] == "uae-pension-review"
    )
    assert "calculation" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"country": "IN", "rule_key": "IN-SYNTHETIC-PENSION"},
        {"period_basis": "period_start"},
        {"calculation_currency": "AED"},
        {"method": "checklist"},
        {"pension_parameters": None},
        {"rate": "0.1"},
        {"applicability": [{"field": "nationality", "operator": "equals", "values": ["AE"]}]},
    ],
)
def test_misclassified_or_ignored_profile_inputs_are_rejected(changes):
    with pytest.raises(ValidationError):
        Rule.model_validate({**profile().model_dump(mode="json"), **changes})


def test_pension_receipt_preserves_literal_expectations_and_exact_government_offset():
    rule = profile("EMPLOYER")
    case = vector(
        "EMPLOYER", government_amount="300.25", reported_amount="1499.75", expected_amount="1499.75"
    )
    sha = fingerprint(rule.model_dump(mode="json"))
    receipt = validation.run(rule, sha, [case])
    assert receipt["outcomes"][0]["actual"]["amount"] == "1499.75"
    assert receipt["cases"][0]["government_amount"] == "300.25"
    assert validation.require_current(rule, sha, receipt) is receipt
    with pytest.raises(validation.FixtureMismatch):
        validation.run(
            rule, sha, [case.model_copy(update={"expected_amount": case.expected_amount + 1})]
        )


def test_missing_government_is_exercised_as_a_real_refusal_not_a_zero_default():
    rule = profile("EMPLOYER")
    positive = vector(
        "EMPLOYER", government_amount="300", reported_amount="1500", expected_amount="1500"
    )
    missing = vector(
        "EMPLOYER",
        id="MISSING-SUPPORT",
        reported_amount="1500",
        expected_amount=None,
        expected_state="GOVERNMENT_SUPPORT_UNRESOLVED",
    )
    receipt = validation.run(rule, fingerprint(rule.model_dump(mode="json")), [positive, missing])
    assert receipt["applicable_case_count"] == 1
    assert receipt["outcomes"][1]["actual"]["amount"] is None


def test_government_amount_cannot_be_supplied_for_an_employee_profile():
    with pytest.raises(ValueError, match="only to employer-minus-government"):
        validation.run(profile(), "f" * 64, [vector(government_amount="1")])


def test_pension_basis_and_offsets_cannot_leak_into_other_fixture_kinds():
    data = vector().model_dump(mode="json")
    data.update(kind="payroll_profile")
    with pytest.raises(ValidationError):
        RuleFixture.model_validate(data)
    data = vector().model_dump(mode="json")
    data["pension_amount"] = "1"
    with pytest.raises(ValidationError):
        RuleFixture.model_validate(data)


def test_short_lived_pension_amendment_records_blocking_only_support():
    rule = profile(effective_from="2026-06-10", effective_to="2026-06-20")
    case = vector(expected_state="RULE_MISSING_OR_SPLIT_PERIOD", expected_amount=None)
    receipt = validation.run(rule, fingerprint(rule.model_dump(mode="json")), [case])
    assert receipt["support"] == "BLOCKING_ONLY_NO_COMPLETE_WAGE_MONTH"
    assert receipt["applicable_case_count"] == 0


def test_loaded_pension_calculator_is_bound_to_the_receipt(monkeypatch):
    from app.modules.country_workflows import pension_calculations

    rule = profile()
    sha = fingerprint(rule.model_dump(mode="json"))
    receipt = validation.run(rule, sha, [vector()])
    actual = pension_calculations.pension

    def changed(*args, **kwargs):
        return actual(*args, **kwargs)

    monkeypatch.setattr(pension_calculations, "pension", changed)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        validation.require_current(rule, sha, receipt)


def test_selected_wage_months_keep_old_and_new_pension_versions_separate():
    from decimal import Decimal
    from types import SimpleNamespace

    from app.modules.country_workflows.pension_calculations import pension
    from app.modules.country_workflows.pension_schemas import PensionBasis, PensionRule

    bases, rules, reported = pension_fixture()
    basis = PensionBasis.model_validate(bases[0]).model_dump(mode="json")
    old = PensionRule.model_validate(rules[0]).model_dump(mode="json")
    old["selected_wage_months"] = ["2026-05"]
    new = {
        **old,
        "id": "NEW",
        "effective_from": "2026-06-01",
        "rate": "0.14",
        "selected_wage_months": ["2026-06"],
    }
    output = pension(
        SimpleNamespace(as_of=date(2026, 6, 30), currency="AED", tolerance=Decimal(0)),
        {
            "bases": [{**basis, "id": "MAY", "period": "2026-05"}, basis],
            "rules": [old, new],
            "reported": [
                {**reported[0], "id": "MAY", "period": "2026-05"},
                {**reported[0], "amount": "1400"},
            ],
        },
    )
    assert not output["blocked"] and output["exception_count"] == 0
    by_month = {row["period"]: row for row in output["rows"]}
    assert by_month["2026-05"]["rule_source_id"] == old["id"]
    assert by_month["2026-06"]["rule_source_id"] == "NEW"
    assert output["expected_total"] == "2100.00"
