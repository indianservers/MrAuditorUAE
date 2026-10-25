"""Independent synthetic arithmetic and scope expectations, not legal rate packs."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.pension_schemas import PensionBasis, PensionRule
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_country_workflows import parsed


def scope():
    return dict(
        authority="SYNTHETIC-AUTHORITY",
        scheme="SYNTHETIC-SCHEME",
        membership_cohort="CONTINUING-MEMBER",
        pension_country="AE",
        nationality="AE",
        employment_sector="private",
        jurisdiction="AE-DU",
    )


def pension_fixture():
    bases, rules, reported = [], [], []
    for component, rate, value in (
        ("EMPLOYEE", "0.07", "700.00"),
        ("EMPLOYER", "0.18", "1500.00"),
        ("GOVERNMENT", "0.03", "300.00"),
    ):
        common = dict(
            **scope(),
            registration="PENSION-ESTABLISHMENT",
            subject="PERSON-1",
            period="2026-06",
            component="PENSION:" + component,
            currency="AED",
        )
        bases.append(
            dict(
                **common,
                id="B-" + component,
                amount="10000.01",
                eligible=True,
                evidence_reference="SYNTHETIC-PAYROLL",
                membership_reference="SYNTHETIC-CONTINUITY",
                salary_basis_reference="SYNTHETIC-ASSESSED-SALARY",
                assessment="Synthetic assessed contribution salary, cohort and membership",
            )
        )
        reported.append(
            dict(
                **common,
                id="R-" + component,
                amount=value,
                evidence_reference="SYNTHETIC-AUTHORITY-REPORT",
            )
        )
        rules.append(
            dict(
                **scope(),
                id="RULE-" + component,
                component="PENSION:" + component,
                effective_from="2026-01-01",
                effective_to="2026-12-31",
                formula="employer-minus-government" if component == "EMPLOYER" else "rate",
                rate=rate,
                rounding="nearest-fils",
                minimum_basis="1000",
                salary_cap="10000",
                source_url="https://synthetic.example/pension-rule",
                source_sha256="f" * 64,
                source_evidence_version_id="00000000-0000-4000-8000-000000000001",
                source_version="SYNTHETIC-1",
                evidence_reference="SYNTHETIC-RULE",
                applicability_review="Synthetic independently assessed rule; not legal data",
            )
        )
    return bases, rules, reported


def run(bases=None, rules=None, reported=None, country="AE", **parameters):
    default = pension_fixture()
    sources = {
        role: parsed(table, rows if rows is not None else fallback)
        for role, table, rows, fallback in zip(
            ("bases", "rules", "reported"),
            ("pension-bases", "pension-rules", "pension-reported"),
            (bases, rules, reported),
            default,
            strict=True,
        )
    }
    data = WorkflowInput(
        workflow="uae-pension-review",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        currency=parameters.pop("currency", "AED"),
        title="Synthetic pension calculation",
        rationale="Independent synthetic arithmetic and scope verification",
        **parameters,
    )
    return calculate(data, country, sources)


def test_capped_employee_net_employer_and_government_are_separate_and_conserved():
    result = run()
    assert not result["blocked"] and result["exception_count"] == 0
    assert result["expected_total"] == "2500.00" == result["reported_total"]
    rows = {row["component"]: row for row in result["rows"]}
    assert rows["PENSION:EMPLOYEE"]["expected_amount"] == "700.00"
    employer = rows["PENSION:EMPLOYER"]
    assert employer["rounded_gross_contribution"] == "1800.00"
    assert employer["government_support"] == "300.00"
    assert employer["expected_amount"] == "1500.00"
    assert employer["government_basis_source_id"] == "B-GOVERNMENT"
    assert result["statutory_calculation_qualified"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority", "OTHER-AUTHORITY"),
        ("scheme", "OTHER-SCHEME"),
        ("membership_cohort", "NEW-MEMBER"),
        ("nationality", "OM"),
        ("pension_country", "OM"),
        ("employment_sector", "government"),
        ("jurisdiction", "AE-AZ"),
    ],
)
def test_scope_differences_never_borrow_a_rule(field, value):
    bases, rules, reported = pension_fixture()
    bases[0][field] = value
    result = run(bases, rules, reported)
    assert result["blocked"] and not result["expected_total_complete"]
    row = next(row for row in result["rows"] if row["basis_source_id"] == "B-EMPLOYEE")
    assert row["state"] == "RULE_MISSING_OR_SPLIT_PERIOD"
    assert row["expected_amount"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("registration", "OTHER-ESTABLISHMENT"),
        ("subject", "OTHER-PERSON"),
        ("period", "2026-05"),
        ("authority", "OTHER-AUTHORITY"),
        ("scheme", "OTHER-SCHEME"),
        ("membership_cohort", "OTHER-COHORT"),
    ],
)
def test_government_support_must_resolve_under_the_exact_identity(field, value):
    bases, rules, reported = pension_fixture()
    bases[2][field] = value
    result = run(bases, rules, reported)
    employer = next(row for row in result["rows"] if row["component"] == "PENSION:EMPLOYER")
    assert employer["state"] == "GOVERNMENT_SUPPORT_UNRESOLVED"
    assert employer["expected_amount"] is None and result["blocked"]


def test_missing_support_is_not_zero_but_reviewed_ineligible_support_is_zero():
    bases, rules, reported = pension_fixture()
    missing = run(bases[:2], rules, reported[:2])
    assert any(row["state"] == "GOVERNMENT_SUPPORT_UNRESOLVED" for row in missing["rows"])
    bases[2]["eligible"] = False
    reported[2]["amount"], reported[1]["amount"] = "0", "1800"
    result = run(bases, rules, reported)
    assert not result["blocked"] and result["exception_count"] == 0
    assert result["expected_total"] == "2500.00"


def test_support_cannot_exceed_rounded_employer_contribution():
    bases, rules, reported = pension_fixture()
    rules[2]["rate"] = "0.20"
    result = run(bases, rules, reported)
    assert result["blocked"]
    assert (
        next(row for row in result["rows"] if row["component"] == "PENSION:EMPLOYER")["state"]
        == "GOVERNMENT_SUPPORT_EXCEEDS_EMPLOYER_CONTRIBUTION"
    )


@pytest.mark.parametrize(
    "rounding,expected", [("nearest-fils", "0.02"), ("next-fils", "0.02"), ("floor-fils", "0.01")]
)
def test_explicit_fils_rounding_preserves_unrounded_amount(rounding, expected):
    bases, rules, reported = pension_fixture()
    bases[0]["amount"] = "1.5"
    rules[0].update(rate="0.01", minimum_basis="0", rounding=rounding)
    result = run(bases[:1], rules[:1], reported[:1])
    assert result["rows"][0]["unrounded_amount"] == "0.015"
    assert result["rows"][0]["expected_amount"] == expected


@pytest.mark.parametrize(
    "amendment", [dict(effective_from="2026-06-10"), dict(effective_to="2026-06-20")]
)
def test_partial_month_amendment_cannot_be_ignored_behind_a_full_month_rule(amendment):
    bases, rules, reported = pension_fixture()
    additional = {**rules[0], **amendment, "id": "MID-MONTH-AMENDMENT"}
    result = run(bases, [*rules, additional], reported)
    assert result["blocked"]
    assert (
        next(row for row in result["rows"] if row["basis_source_id"] == "B-EMPLOYEE")["state"]
        == "RULE_MISSING_OR_SPLIT_PERIOD"
    )


def test_minimum_is_not_silently_clamped_and_overlapping_full_rules_are_ambiguous():
    bases, rules, reported = pension_fixture()
    bases[0]["amount"] = "999.99"
    result = run(bases, rules, reported)
    assert result["blocked"]
    assert (
        next(row for row in result["rows"] if row["basis_source_id"] == "B-EMPLOYEE")["state"]
        == "ASSESSED_SALARY_BELOW_REVIEWED_MINIMUM"
    )
    bases[0]["amount"] = "1000"
    result = run(bases, [*rules, {**rules[0], "id": "OVERLAP"}], reported)
    assert any(row["state"] == "AMBIGUOUS_RULE" for row in result["rows"])


@pytest.mark.parametrize("role", ["bases", "reported"])
def test_duplicate_population_identities_require_a_restatement(role):
    bases, rules, reported = pension_fixture()
    rows = bases if role == "bases" else reported
    rows.append({**rows[0], "id": "DUPLICATE"})
    with pytest.raises(ValueError, match="Duplicate pension identity"):
        run(bases, rules, reported)


def test_fixed_rules_country_currency_and_open_month_boundaries():
    bases, rules, reported = pension_fixture()
    rules[0].update(formula="fixed", fixed_amount="123.45", rate=None, salary_cap=None)
    assert run(bases, rules, reported)["rows"][0]["expected_amount"] == "123.45"
    with pytest.raises(ValueError, match="unavailable"):
        run(country="IN")
    with pytest.raises(ValueError, match="AED"):
        run(currency="USD")
    bases[0]["period"] = "2026-07"
    with pytest.raises(ValueError, match="must be closed"):
        run(bases, rules, reported)


def test_membership_assessment_and_source_provenance_are_required():
    bases, rules, _ = pension_fixture()
    for field in ("membership_reference", "salary_basis_reference", "assessment"):
        invalid = deepcopy(bases[0])
        invalid[field] = " " * 10
        with pytest.raises(ValidationError):
            PensionBasis.model_validate(invalid)
    invalid = {**rules[0], "source_evidence_version_id": None}
    with pytest.raises(ValidationError):
        PensionRule.model_validate(invalid)


def test_reported_only_scope_cannot_make_expected_total_complete():
    bases, rules, reported = pension_fixture()
    reported.append({**reported[0], "subject": "UNASSESSED-PERSON", "id": "OTHER"})
    result = run(bases, rules, reported)
    assert result["blocked"] and not result["expected_total_complete"]
    assert any(row["state"] == "REPORTED_ONLY" for row in result["rows"])
