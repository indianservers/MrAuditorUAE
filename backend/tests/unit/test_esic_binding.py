import io
import uuid
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.intelligence.exports import render
from tests.unit.test_country_workflows import parsed
from tests.unit.test_esic_population import population
from tests.unit.test_esic_population import run as population_result
from tests.unit.test_payroll_rule_workflow import basis, reported, rule

COMPONENTS = ("ESI:EMPLOYEE", "ESI:EMPLOYER")


def contribution_populations(components=COMPONENTS):
    bases, actual = [], []
    rules = [
        rule(component, rate=rate, salary_cap=None, rounding="paise")
        for component, rate in zip(COMPONENTS, ("0.01", "0.02"), strict=True)
        if component in components
    ]
    for member in population():
        for component in components:
            scope = {
                "registration": member["registration"],
                "subject": member["subject"],
                "period": member["period"],
            }
            bases.append(
                basis(
                    component,
                    id="B-" + member["subject"] + component,
                    amount=member["amount"],
                    eligible=member["amount"] != "0",
                    **scope,
                )
            )
            amount = (
                "0" if member["amount"] == "0" else "100" if component == "ESI:EMPLOYEE" else "200"
            )
            actual.append(
                reported(component, id="R-" + member["subject"] + component, amount=amount, **scope)
            )
    return {"bases": bases, "rules": rules, "reported": actual}


def parameters(**changes):
    return WorkflowInput.model_validate(
        {
            "workflow": "india-payroll-rules",
            "source_ids": {role: uuid.uuid4() for role in ("bases", "rules", "reported")},
            "as_of": "2026-06-30",
            "currency": "INR",
            "title": "SYNTHETIC ESIC contribution link",
            "rationale": "Explicit fictional assessed ESI bases and synthetic rule rates",
            "esic_population_review_id": uuid.uuid4(),
            "esic_basis_scope_assessment": "Independently assessed full member population, selected components, eligibility and wage-to-basis differences",
            **changes,
        }
    )


def parent():
    body = population_result()
    body["review_status"] = "REVIEWED"
    return body


def run(rows=None, body=None, data=None, **changes):
    data = data or parameters(**changes)
    rows = rows or contribution_populations()
    sources = {
        role: parsed(table, rows[role])
        for role, table in (
            ("bases", "payroll-bases"),
            ("rules", "payroll-rules"),
            ("reported", "obligations"),
        )
    }
    return calculate(
        data,
        "IN",
        sources,
        esic_population_review=(
            body or parent(),
            {"id": str(data.esic_population_review_id), "version": 2, "sha256": "a" * 64},
        ),
    )


def test_complete_member_component_coverage_keeps_zero_wages_and_explicit_eligibility():
    rows, body = contribution_populations(), parent()
    originals = deepcopy((rows, body))
    result = run(rows, body)
    assert (rows, body) == originals and result["exception_count"] == 0
    assert (
        result["esic_population_binding"]["members"] == 2
        and result["esic_population_binding"]["basis_rows"] == 4
    )
    zero = [row for row in result["rows"] if row["subject"] == "0012345679"]
    assert len(zero) == 2 and all(
        row["esic_population_basis"]["eligible_as_assessed"] is False for row in zero
    )
    assert all(
        row["esic_population_basis"]["payroll_last_working_day"] == "2026-06-02" for row in zero
    )
    assert result["statutory_calculation_qualified"] is False


def test_differing_assessed_base_is_retained_without_inferred_wage_equality():
    rows = contribution_populations()
    rows["bases"][0].update(
        amount="8000", assessment="Fictional independently assessed exclusion from observed wages"
    )
    rows["reported"][0]["amount"] = "80"
    result = run(rows)
    row = next(
        row
        for row in result["rows"]
        if row["subject"] == "0012345678" and row["component"] == "ESI:EMPLOYEE"
    )
    assert row["state"] == "MATCHED" and row["assessed_base"] == "8000"
    assert row["esic_payroll_wages"] == "10000" and row["esic_base_minus_payroll_wages"] == "-2000"
    assert row["esic_population_basis"]["basis_assessment"].startswith("Fictional")


@pytest.mark.parametrize(
    "field,value",
    [("subject", "9999999999"), ("registration", "99123456789012345"), ("period", "2026-05")],
)
def test_esi_basis_cannot_cross_parent_member_employer_or_month(field, value):
    rows = contribution_populations()
    rows["bases"][0][field] = value
    with pytest.raises(ValueError, match="outside the selected ESIC"):
        run(rows)


def test_zero_wage_missing_basis_is_not_inferred_zero_and_component_selection_is_explicit():
    rows = contribution_populations()
    rows["bases"].pop()
    with pytest.raises(ValueError, match="Every reviewed ESIC member"):
        run(rows)
    employee = contribution_populations(("ESI:EMPLOYEE",))
    result = run(employee, esic_components=["ESI:EMPLOYEE"])
    assert result["exception_count"] == 0 and result["esic_population_binding"]["components"] == [
        "ESI:EMPLOYEE"
    ]
    with pytest.raises(ValueError, match="Every reviewed ESIC member"):
        run(employee)


def test_extra_reported_esi_member_cannot_escape_population_binding():
    rows = contribution_populations()
    rows["reported"].append({**rows["reported"][0], "id": "EXTRA", "subject": "9999999999"})
    with pytest.raises(ValueError, match="Reported ESI contributions extend beyond"):
        run(rows)


@pytest.mark.parametrize(
    "change,error",
    [
        ({"review_status": "UNVERIFIED"}, "independently reviewed"),
        ({"blocked": True}, "independently reviewed"),
        ({"workflow": "other"}, "independently reviewed"),
        ({"esic_population_contract": "other"}, "independently reviewed"),
        ({"parameters": {"as_of": "2026-07-01"}}, "review date is after"),
        ({"rows": []}, "empty ESIC"),
    ],
)
def test_parent_review_contract_and_timing_are_required(change, error):
    with pytest.raises(ValueError, match=error):
        run(body={**parent(), **change})


def test_undocumented_parent_exception_rejected_and_documented_evidence_retained():
    body = parent()
    body["rows"][0].update(state="EXCEPTIONS", reported_paid_days=24)
    with pytest.raises(ValueError, match="Document every ESIC"):
        run(body=body)
    body["rows"][0]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    result = run(body=body)
    assert result["esic_population_binding"]["documented_population_exceptions"] == 1
    row = result["rows"][0]
    assert row["esic_population_basis"]["reported_paid_days"] == 24


def test_link_parameters_are_restricted_and_verified_receipt_is_mandatory():
    for changes in (
        {"esic_basis_scope_assessment": " "},
        {"esic_components": ["ESI:EMPLOYEE", "ESI:EMPLOYEE"]},
        {"esic_population_review_id": None},
        {"workflow": "statutory-dues"},
    ):
        with pytest.raises(ValueError):
            parameters(**changes)
    rows = contribution_populations()
    sources = {
        role: parsed(table, rows[role])
        for role, table in (
            ("bases", "payroll-bases"),
            ("rules", "payroll-rules"),
            ("reported", "obligations"),
        )
    }
    with pytest.raises(ValueError, match="Verify the requested ESIC"):
        calculate(parameters(), "IN", sources)
    unlinked = parameters(esic_population_review_id=None, esic_basis_scope_assessment="")
    assert calculate(unlinked, "IN", sources)["esic_population_binding"]["status"] == "NOT_LINKED"


def test_xlsx_keeps_review_receipt_and_individual_wage_to_basis_adjustment():
    rows = contribution_populations()
    rows["bases"][0]["amount"] = "8000"
    body = run(rows)
    content, _ = render(
        {
            "id": str(uuid.uuid4()),
            "kind": "country-workflow",
            "version": 1,
            "body": body,
            "dependencies": [],
            "sha256": "a" * 64,
            "created_at": "2026-06-30T00:00:00Z",
        },
        "xlsx",
    )
    values = [
        value
        for sheet in load_workbook(io.BytesIO(content))
        for row in sheet.values
        for value in row
    ]
    assert "-2000" in values and "0012345679" in values
