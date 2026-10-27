"""Explicit reviewed salary eligibility, independently specified boundary amounts."""

from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory import validation
from app.modules.regulatory.pension_profiles import PensionParameters
from app.modules.regulatory.schemas import Rule
from tests.unit.test_pension_profiles import profile, vector
from tests.unit.test_pension_workflow import pension_fixture, run


def threshold_profile():
    body = profile("GOVERNMENT").model_dump(mode="json")
    body["pension_parameters"]["exclusive_eligibility_ceiling"] = "20000"
    return Rule.model_validate(body)


def boundary_vectors():
    cases = []
    for label, amount, expected in [
        ("below", "19999.99", "300"),
        ("at", "20000", "0"),
        ("above", "20000.01", "0"),
    ]:
        basis = vector("GOVERNMENT").pension_basis.model_dump(mode="json")
        basis["amount"] = amount
        cases.append(
            vector(
                "GOVERNMENT",
                id=label,
                pension_basis=basis,
                reported_amount=expected,
                expected_amount=expected,
            )
        )
    return cases


@pytest.mark.parametrize(
    "salary,support,net",
    [("19999.99", "300.00", "1500.00"), ("20000", "0", "1800.00"), ("20000.01", "0", "1800.00")],
)
def test_eligibility_uses_uncapped_salary_and_conserves_resolved_employer_support(
    salary, support, net
):
    bases, rules, reported = pension_fixture()
    for row in bases:
        row["amount"] = salary
    for rule in rules:
        rule["exclusive_eligibility_ceiling"] = None
    rules[2]["exclusive_eligibility_ceiling"] = "20000"
    reported[1]["amount"] = net
    reported[2]["amount"] = support
    result = run(bases, rules, reported)
    assert not result["blocked"] and result["exception_count"] == 0
    rows = {row["component"]: row for row in result["rows"]}
    assert Decimal(rows["PENSION:GOVERNMENT"]["expected_amount"]) == Decimal(support)
    assert rows["PENSION:EMPLOYER"]["expected_amount"] == net
    assert result["expected_total"] == "2500.00"
    if Decimal(salary) >= 20000:
        assert rows["PENSION:GOVERNMENT"]["eligibility_basis"] == salary
        assert "AT_OR_ABOVE" in rows["PENSION:GOVERNMENT"]["eligibility_outcome"]
    assert rows["PENSION:GOVERNMENT"]["exclusive_eligibility_ceiling"] == "20000"


def test_zero_support_requires_an_actual_resolved_government_basis():
    bases, rules, reported = pension_fixture()
    for row in bases:
        row["amount"] = "20000"
    for rule in rules:
        rule["exclusive_eligibility_ceiling"] = None
    rules[2]["exclusive_eligibility_ceiling"] = "20000"
    result = run(bases[:2], rules, reported[:2])
    employer = next(row for row in result["rows"] if row["component"] == "PENSION:EMPLOYER")
    assert result["blocked"] and employer["state"] == "GOVERNMENT_SUPPORT_UNRESOLVED"
    assert employer["expected_amount"] is None


@pytest.mark.parametrize("ceiling", ["0", "-1", "1000", "999.99"])
def test_invalid_or_empty_eligibility_intervals_are_rejected(ceiling):
    params = threshold_profile().pension_parameters.model_dump(mode="json")
    params["exclusive_eligibility_ceiling"] = ceiling
    with pytest.raises(ValidationError):
        PensionParameters.model_validate(params)


def test_threshold_publication_replays_all_three_independent_boundary_cases():
    rule = threshold_profile()
    receipt = validation.run(rule, fingerprint(rule.model_dump(mode="json")), boundary_vectors())
    assert receipt["applicable_case_count"] == 1
    assert receipt["eligibility_boundary_coverage"] == ["above", "at", "below"]
    assert [row["actual"]["amount"] for row in receipt["outcomes"]] == ["300.00", "0", "0"]
    assert validation.require_current(rule, receipt["rule_sha256"], receipt) is receipt


@pytest.mark.parametrize("omit", [0, 1, 2])
def test_missing_boundary_prevents_publication_even_when_remaining_cases_pass(omit):
    rule = threshold_profile()
    cases = boundary_vectors()
    cases.pop(omit)
    with pytest.raises(validation.FixtureMismatch, match="below, at and above"):
        validation.run(rule, fingerprint(rule.model_dump(mode="json")), cases)


def test_declared_ineligibility_cannot_fake_a_threshold_boundary():
    rule = threshold_profile()
    cases = boundary_vectors()
    body = deepcopy(cases[1].model_dump(mode="json"))
    body["pension_basis"]["eligible"] = False
    cases[1] = type(cases[1]).model_validate(body)
    with pytest.raises(validation.FixtureMismatch, match="below, at and above"):
        validation.run(rule, fingerprint(rule.model_dump(mode="json")), cases)


def test_short_rule_without_a_complete_month_retains_only_in_band_blocking_support():
    body = threshold_profile().model_dump(mode="json")
    body.update(effective_from="2026-06-10", effective_to="2026-06-20")
    rule = Rule.model_validate(body)
    case = boundary_vectors()[0].model_copy(
        update={
            "expected_state": "RULE_MISSING_OR_SPLIT_PERIOD",
            "expected_amount": None,
        }
    )
    receipt = validation.run(rule, fingerprint(body), [case])
    assert receipt["support"] == "BLOCKING_ONLY_NO_COMPLETE_WAGE_MONTH"
    assert receipt["applicable_case_count"] == 0
    above = boundary_vectors()[2].model_copy(
        update={
            "expected_state": "RULE_MISSING_OR_SPLIT_PERIOD",
            "expected_amount": None,
        }
    )
    with pytest.raises(validation.FixtureMismatch):
        validation.run(rule, fingerprint(body), [above])
