import uuid
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_country_workflows import parsed


def basis(component="PF:EMPLOYEE", **changes):
    return {
        "id": "BASE-" + component,
        "registration": "EPFO-SYNTHETIC",
        "subject": "100000000001",
        "period": "2026-06",
        "component": component,
        "currency": "INR",
        "amount": "20000",
        "rule_group": component,
        "jurisdiction": "IN-CENTRAL",
        "eligible": True,
        "eligibility_reference": "SYNTHETIC-MEMBERSHIP-1",
        "assessment": "Synthetic explicit coverage and wage basis; not legal advice",
        **changes,
    }


def rule(component="PF:EMPLOYEE", **changes):
    return {
        "id": "RULE-" + component,
        "rule_group": component,
        "component": component,
        "jurisdiction": "IN-CENTRAL",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "formula": "rate",
        "rate": "0.12",
        "salary_cap": "15000",
        "rounding": "nearest-rupee",
        "source_url": "https://synthetic.example/payroll/rule",
        "source_sha256": "f" * 64,
        "source_evidence_version_id": "00000000-0000-4000-8000-000000000001",
        "source_version": "Synthetic reviewed fixture 1",
        "evidence_reference": "SYNTHETIC-RULE-EVIDENCE-1",
        "applicability_review": "Synthetic independent expected rates, cohorts and conditions",
        **changes,
    }


def reported(component="PF:EMPLOYEE", **changes):
    return {
        "id": "RETURN-" + component,
        "registration": "EPFO-SYNTHETIC",
        "subject": "100000000001",
        "period": "2026-06",
        "component": component,
        "currency": "INR",
        "amount": "1800",
        **changes,
    }


def run(bases, rules, actual, country="IN", **changes):
    sources = {
        "bases": parsed("payroll-bases", bases),
        "rules": parsed("payroll-rules", rules),
        "reported": parsed("obligations", actual),
    }
    data = WorkflowInput(
        workflow="india-payroll-rules",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        currency="INR",
        title="Synthetic reviewed payroll rules",
        rationale="Source-bound rate fixtures, wage inputs and reported amounts",
        **changes,
    )
    return calculate(data, country, sources)


def pf_fixture():
    components = ["PF:EMPLOYEE", "PF:EPS", "PF:EMPLOYER"]
    return (
        [basis(component) for component in components],
        [rule(), rule("PF:EPS", rate="0.0833"), rule("PF:EMPLOYER", formula="employer-minus-eps")],
        [
            reported(component, amount=value)
            for component, value in zip(components, ("1800", "1250", "550"), strict=True)
        ],
    )


def test_pf_employee_pension_and_residual_employer_contributions():
    result = run(*pf_fixture())
    assert not result["blocked"] and result["exception_count"] == 0
    assert Decimal(result["expected_total"]) == 3600
    rows = {row["component"]: row for row in result["rows"]}
    assert Decimal(rows["PF:EPS"]["expected_amount"]) == 1250
    assert Decimal(rows["PF:EMPLOYER"]["expected_amount"]) == 550
    assert rows["PF:EMPLOYEE"]["rule_document_sha256"] == "f" * 64
    assert not result["statutory_calculation_qualified"]


def test_esi_ceiling_rounding_and_explicit_continuing_coverage():
    bases = [basis(c, amount="17777") for c in ("ESI:EMPLOYEE", "ESI:EMPLOYER")]
    rules = [
        rule("ESI:EMPLOYEE", rate="0.0075", salary_cap=None, rounding="next-rupee"),
        rule("ESI:EMPLOYER", rate="0.0325", salary_cap=None, rounding="next-rupee"),
    ]
    actual = [reported("ESI:EMPLOYEE", amount="134"), reported("ESI:EMPLOYER", amount="578")]
    result = run(bases, rules, actual)
    assert result["exception_count"] == 0 and Decimal(result["expected_total"]) == 712
    for row in bases:
        row["amount"] = "22000"
    actual[0]["amount"], actual[1]["amount"] = "165", "715"
    assert run(bases, rules, actual)["exception_count"] == 0


def test_state_pt_slabs_have_explicit_half_open_boundaries():
    bands = [
        rule(
            "PT",
            id="PT-LOW",
            formula="fixed",
            rate=None,
            salary_cap=None,
            fixed_amount="0",
            threshold_from="0",
            threshold_to="25000",
            jurisdiction="IN-MH",
        ),
        rule(
            "PT",
            id="PT-HIGH",
            formula="fixed",
            rate=None,
            salary_cap=None,
            fixed_amount="200",
            threshold_from="25000",
            jurisdiction="IN-MH",
        ),
    ]
    result = run(
        [basis("PT", amount="25000", jurisdiction="IN-MH")], bands, [reported("PT", amount="200")]
    )
    assert result["exception_count"] == 0 and result["rows"][0]["rule_source_id"] == "PT-HIGH"
    wrong_state = run(
        [basis("PT", amount="25000", jurisdiction="IN-GJ")], bands, [reported("PT", amount="200")]
    )
    assert wrong_state["blocked"] and wrong_state["rows"][0]["expected_amount"] is None


@pytest.mark.parametrize(
    "method,wanted",
    [("nearest-rupee", "1"), ("next-rupee", "1"), ("floor-rupee", "0"), ("paise", "0.50")],
)
def test_rounding_is_part_of_the_reviewed_rule(method, wanted):
    result = run(
        [basis(amount="1")],
        [rule(rate="0.5", salary_cap=None, rounding=method)],
        [reported(amount=wanted)],
    )
    assert result["exception_count"] == 0
    assert Decimal(result["rows"][0]["expected_amount"]) == Decimal(wanted)


@pytest.mark.parametrize(
    "change,state",
    [
        ({"effective_from": "2026-06-02"}, "RULE_MISSING_OR_SPLIT_PERIOD"),
        ({"effective_to": "2026-06-29"}, "RULE_MISSING_OR_SPLIT_PERIOD"),
        ({"rule_group": "OTHER"}, "RULE_MISSING_OR_SPLIT_PERIOD"),
    ],
)
def test_rule_gaps_and_mid_month_changes_block_approval(change, state):
    result = run([basis()], [rule(**change)], [reported()])
    assert result["blocked"] and result["rows"][0]["state"] == state


def test_overlapping_rules_do_not_select_arbitrarily():
    result = run([basis()], [rule(), rule(id="SECOND")], [reported()])
    assert result["blocked"] and result["rows"][0]["state"] == "AMBIGUOUS_RULE"


@pytest.mark.parametrize(
    "dates",
    [
        {"effective_from": "2026-06-16"},
        {"effective_to": "2026-06-15"},
        {"effective_from": "2026-06-30"},
        {"effective_to": "2026-06-01"},
    ],
)
def test_whole_month_policy_does_not_hide_a_competing_partial_month_policy(dates):
    result = run([basis()], [rule(), rule(id="PARTIAL", rate="0.10", **dates)], [reported()])
    assert result["blocked"]
    assert result["rows"][0]["state"] == "RULE_MISSING_OR_SPLIT_PERIOD"
    assert result["rows"][0]["expected_amount"] is None
    assert result["expected_total_complete"] is False


@pytest.mark.parametrize(
    "dates",
    [
        {"effective_to": "2026-05-31"},
        {"effective_from": "2026-07-01"},
    ],
)
def test_rules_outside_the_wage_month_do_not_compete(dates):
    result = run([basis()], [rule(), rule(id="OUTSIDE", rate="0.10", **dates)], [reported()])
    assert not result["blocked"] and result["rows"][0]["state"] == "MATCHED"


def test_partial_month_eps_policy_cannot_be_replaced_by_zero_in_employer_residual():
    bases, rules, actual = pf_fixture()
    rules.append(rule("PF:EPS", id="CHANGED-EPS", effective_from="2026-06-16", rate="0.10"))
    result = run(bases, rules, actual)
    indexed = {row["component"]: row for row in result["rows"]}
    assert result["blocked"] and not result["expected_total_complete"]
    assert indexed["PF:EMPLOYEE"]["expected_amount"] == "1800"
    assert indexed["PF:EPS"]["expected_amount"] is None
    assert indexed["PF:EMPLOYER"]["expected_amount"] is None
    assert indexed["PF:EMPLOYER"]["state"] == "PENSION_COMPONENT_UNRESOLVED"


def test_partial_policy_for_another_salary_band_does_not_compete():
    result = run(
        [basis()],
        [
            rule(threshold_from="0"),
            rule(id="OTHER-BAND", effective_from="2026-06-16", threshold_from="30000"),
        ],
        [reported()],
    )
    assert not result["blocked"] and result["rows"][0]["state"] == "MATCHED"


def test_missing_pension_is_not_zero_and_excluded_pension_is_explicit():
    bases, rules, actual = pf_fixture()
    missing = run([row for row in bases if row["component"] != "PF:EPS"], rules, actual)
    assert missing["blocked"]
    assert (
        next(row for row in missing["rows"] if row["component"] == "PF:EMPLOYER")["state"]
        == "PENSION_COMPONENT_UNRESOLVED"
    )
    bases[1]["eligible"] = False
    actual[1]["amount"], actual[2]["amount"] = "0", "1800"
    assert run(bases, rules, actual)["exception_count"] == 0


def test_country_future_month_and_duplicate_basis_boundaries():
    with pytest.raises(ValueError, match="country"):
        run([basis()], [rule()], [reported()], country="AE")
    with pytest.raises(ValueError, match="closes after"):
        run([basis(period="2026-07")], [rule()], [reported()])
    with pytest.raises(ValueError, match="Duplicate payroll"):
        run([basis(), basis(id="SECOND")], [rule()], [reported()])


def test_reported_differences_are_retained_without_claiming_payment():
    result = run([basis()], [rule()], [reported(amount="1700"), reported("PT", amount="200")])
    assert result["exception_count"] == 2
    assert {row["state"] for row in result["rows"]} == {"CONTRIBUTION_DIFFERENCE", "REPORTED_ONLY"}
    assert all(
        row["payment_verification"] == "NOT_PERFORMED_BY_CONTRIBUTION_REVIEW"
        for row in result["rows"]
    )


def test_voluntary_employee_rate_does_not_change_employer_contribution():
    bases, rules, actual = pf_fixture()
    rules[0].update(rate="0.18", salary_cap=None)
    actual[0]["amount"] = "3600"
    result = run(bases, rules, actual)
    assert result["exception_count"] == 0
    assert (
        next(row for row in result["rows"] if row["component"] == "PF:EMPLOYER")["expected_amount"]
        == "550"
    )


def test_employee_esi_exemption_does_not_exempt_employer():
    bases = [
        basis("ESI:EMPLOYEE", amount="1000", eligible=False),
        basis("ESI:EMPLOYER", amount="1000"),
    ]
    rules = [
        rule("ESI:EMPLOYEE", rate="0.0075", salary_cap=None, rounding="next-rupee"),
        rule("ESI:EMPLOYER", rate="0.0325", salary_cap=None, rounding="next-rupee"),
    ]
    result = run(
        bases, rules, [reported("ESI:EMPLOYEE", amount="0"), reported("ESI:EMPLOYER", amount="33")]
    )
    assert result["exception_count"] == 0


def test_negative_employer_residual_and_cross_jurisdiction_pension_block():
    bases, rules, actual = pf_fixture()
    rules[1]["rate"] = "0.5"
    result = run(bases, rules, actual)
    assert result["blocked"] and not result["expected_total_complete"]
    assert (
        next(row for row in result["rows"] if row["component"] == "PF:EMPLOYER")["state"]
        == "PENSION_EXCEEDS_EMPLOYER_CONTRIBUTION"
    )
    bases, rules, actual = pf_fixture()
    bases[1]["jurisdiction"], rules[1]["jurisdiction"] = "OTHER", "OTHER"
    result = run(bases, rules, actual)
    assert result["blocked"]
    assert (
        next(row for row in result["rows"] if row["component"] == "PF:EMPLOYER")["state"]
        == "PENSION_JURISDICTION_DIFFERENCE"
    )
