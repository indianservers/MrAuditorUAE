"""Independently controlled expected remittances preserve country and payer scope."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.contribution_source import ContributionSourceInput, source_rows
from app.modules.country_workflows.schemas import Obligation
from tests.unit.test_payroll_rule_workflow import pf_fixture
from tests.unit.test_payroll_rule_workflow import run as payroll_run
from tests.unit.test_pension_workflow import run as pension_run
from tests.unit.test_pension_workflow import scope


def request(country="AE", **changes):
    pension = country == "AE"
    components = (
        [("PENSION:EMPLOYEE", "700.00"), ("PENSION:EMPLOYER", "1500.00")]
        if pension
        else [
            ("PF:EMPLOYEE", "1800"),
            ("PF:EPS", "1250"),
            ("PF:EMPLOYER", "550"),
        ]
    )
    return ContributionSourceInput.model_validate(
        {
            "result_id": str(uuid.uuid4()),
            "due_date_evidence_version_id": str(uuid.uuid4()),
            "groups": [
                dict(
                    registration="PENSION-ESTABLISHMENT" if pension else "EPFO-SYNTHETIC",
                    period="2026-06",
                    component=component,
                    expected_rows=1,
                    amount=amount,
                    due_date="2026-07-15",
                    due_date_reference="SYNTHETIC-DATE-REFERENCE",
                )
                for component, amount in components
            ],
            "pension_scope": scope() if pension else None,
            "label": "Synthetic expected remittances",
            "assessment": "Independent group counts, remittance amounts, payer and due-date evidence",
            **changes,
        }
    )


def test_pension_preserves_employee_rows_and_excludes_the_separate_government_payer():
    rows, totals, excluded = source_rows(pension_run(), request())
    assert len(rows) == 2 and totals == {"AED": "2200.00"}
    assert {row["amount"] for row in rows} == {"700.00", "1500.00"}
    assert all(row["pension_scope"] == scope() and row["due_date"] == "2026-07-15" for row in rows)
    assert all(row["payment_date"] is None for row in rows)
    assert excluded == [
        {"source_result_row_id": "pension:3", "reason": "SEPARATE_GOVERNMENT_PAYER"}
    ]


def test_india_keeps_pf_employee_pension_and_employer_distinct():
    rows, totals, excluded = source_rows(payroll_run(*pf_fixture()), request("IN"))
    assert totals == {"INR": "3600"} and len(rows) == 3 and not excluded
    assert {row["component"] for row in rows} == {"PF:EMPLOYEE", "PF:EPS", "PF:EMPLOYER"}
    assert all("pension_scope" not in row for row in rows)


@pytest.mark.parametrize(
    "field,value",
    [("amount", "700.01"), ("expected_rows", 2), ("period", "2026-05"), ("registration", "OTHER")],
)
def test_independent_controls_cannot_be_replaced_by_calculated_totals(field, value):
    data = request().model_dump(mode="json")
    data["groups"][0][field] = value
    with pytest.raises(ValueError, match="control does not agree"):
        source_rows(pension_run(), ContributionSourceInput.model_validate(data))


@pytest.mark.parametrize("field,value", [("blocked", True), ("expected_total_complete", False)])
def test_partial_or_blocked_calculations_cannot_create_expected_remittances(field, value):
    with pytest.raises(ValueError, match="full contribution calculation"):
        source_rows({**pension_run(), field: value}, request())


def test_government_support_cannot_be_selected_as_employer_remittance():
    data = request().model_dump(mode="json")
    data["groups"][0]["component"] = "PENSION:GOVERNMENT"
    with pytest.raises(ValueError, match="separate payer"):
        source_rows(pension_run(), ContributionSourceInput.model_validate(data))


def test_missing_basis_and_duplicate_settlement_identities_are_blocked():
    body = pension_run()
    body["rows"][0]["basis_source_id"] = None
    with pytest.raises(ValueError, match="resolved assessed contribution basis"):
        source_rows(body, request())
    body = pension_run()
    duplicate = {**body["rows"][0], "id": "DUPLICATE"}
    body["rows"].append(duplicate)
    data = request().model_dump(mode="json")
    data["groups"][0].update(expected_rows=2, amount="1400")
    with pytest.raises(ValueError, match="collide"):
        source_rows(body, ContributionSourceInput.model_validate(data))


def test_duplicate_groups_and_missing_due_date_evidence_are_invalid_requests():
    data = request().model_dump(mode="json")
    data["groups"].append(deepcopy(data["groups"][0]))
    with pytest.raises(ValidationError):
        ContributionSourceInput.model_validate(data)
    data = request().model_dump(mode="json")
    data.pop("due_date_evidence_version_id")
    with pytest.raises(ValidationError):
        ContributionSourceInput.model_validate(data)


def test_other_pension_cohorts_are_visible_as_explicitly_excluded_rows():
    body = pension_run()
    body["rows"].append({**body["rows"][0], "id": "OTHER-COHORT", "membership_cohort": "OTHER"})
    rows, totals, excluded = source_rows(body, request())
    assert len(rows) == 2 and totals == {"AED": "2200.00"}
    assert {item["source_result_row_id"]: item["reason"] for item in excluded}[
        "OTHER-COHORT"
    ] == "OUTSIDE_SELECTED_PENSION_SCOPE"


def test_pension_scope_json_is_typed_and_cannot_be_assigned_to_india_pf():
    import json

    fields = dict(
        id="R1",
        registration="REG",
        subject="PERSON",
        period="2026-06",
        component="PENSION:EMPLOYEE",
        currency="AED",
        amount="700",
    )
    row = Obligation.model_validate({**fields, "pension_scope": json.dumps(scope())})
    assert row.pension_scope.authority == "SYNTHETIC-AUTHORITY"
    with pytest.raises(ValidationError):
        Obligation.model_validate({**fields, "component": "PF:EMPLOYEE", "pension_scope": scope()})
    with pytest.raises(ValidationError):
        Obligation.model_validate({**fields, "pension_scope": "not JSON"})


@pytest.mark.parametrize(
    "actual_scope",
    [None, {**scope(), "scheme": "OTHER-SCHEME"}, {**scope(), "membership_cohort": "OTHER-COHORT"}],
)
def test_bank_allocation_cannot_net_an_unscoped_or_different_pension_return(actual_scope):
    import json

    from tests.unit.test_dues_allocations import example, run

    populations = example(component="PENSION:EMPLOYEE")
    for row in populations["expected"]:
        row["pension_scope"] = json.dumps(scope())
    if actual_scope is not None:
        for row in populations["reported"]:
            row["pension_scope"] = json.dumps(actual_scope)
    with pytest.raises(ValueError, match="pension scope"):
        run(populations)


def test_statutory_comparison_keeps_scope_differences_as_missing_partitions():
    import json

    from app.modules.country_workflows.calculations import calculate
    from app.modules.country_workflows.schemas import WorkflowInput
    from tests.unit.test_country_workflows import parsed

    common = dict(
        id="E1",
        registration="REG",
        subject="PERSON",
        period="2026-06",
        component="PENSION:EMPLOYEE",
        currency="AED",
        amount="700",
        due_date="2026-07-15",
    )
    sources = {
        "expected": parsed("obligations", [{**common, "pension_scope": json.dumps(scope())}]),
        "return": parsed("obligations", [{**common, "id": "R1"}]),
        "payment": parsed("obligations", [{**common, "id": "P1", "payment_date": "2026-07-15"}]),
    }
    data = WorkflowInput(
        workflow="statutory-dues",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-07-31",
        currency="AED",
        title="Synthetic scoped dues",
        rationale="Independent pension scope separation",
    )
    result = calculate(data, "AE", sources)
    assert len(result["rows"]) == 2
    assert all(row["state"] == "MISSING_SOURCE_PARTITION" for row in result["rows"])


def test_negative_contributions_cannot_be_hidden_by_a_positive_group_total():
    body = pension_run()
    body["rows"].append(
        {**body["rows"][0], "id": "NEGATIVE", "subject": "OTHER", "expected_amount": "-100"}
    )
    data = request().model_dump(mode="json")
    data["groups"][0].update(expected_rows=2, amount="600")
    with pytest.raises(ValueError, match="non-negative"):
        source_rows(body, ContributionSourceInput.model_validate(data))


def test_explicit_zero_keeps_its_employee_row_instead_of_becoming_a_missing_population():
    body = pension_run()
    body["rows"][0]["expected_amount"] = "0.00"
    data = request().model_dump(mode="json")
    data["groups"][0]["amount"] = "0"
    rows, totals, _ = source_rows(body, ContributionSourceInput.model_validate(data))
    assert len(rows) == 2 and rows[0]["amount"] == "0.00" and totals == {"AED": "1500.00"}
