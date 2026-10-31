"""Synthetic independent duty/plan controls, not a complete SOX method."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.icfr_scope import BINDING, ROLES, ICFRScope
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_shared_audit_workflows import source


def population(country="AE", both_required=False):
    common = {
        "subject": "SYN-COMPONENT",
        "engagement_country": country,
        "reporting_issuer": "SYN-ISSUER",
        "relationship": "component",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "adoption_status": "reviewed-for-period",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "authority_version": "SYNTHETIC-INDEPENDENTLY-ASSESSED",
        "authority_url": "https://synthetic.example/authority",
        "authority_evidence_version_id": str(uuid.uuid4()),
        "authority_sha256": "1" * 64,
        "assessment_evidence_version_id": str(uuid.uuid4()),
        "assessment_sha256": "2" * 64,
        "assessment": "SYNTHETIC independently assessed issuer/group duty and adoption scope",
    }
    scopes = [
        dict(common, id="S-A", duty="404a", applicability="required"),
        dict(
            common,
            id="S-B",
            duty="404b",
            applicability="required" if both_required else "not-required",
        ),
    ]
    check = {
        "id": "C-A",
        "subject": "SYN-COMPONENT",
        "requirement": "404a:CTRL",
        "state": "supported",
        "evidence_reference": "SYN-CONTROL-EVIDENCE",
        "expires_on": "2026-12-31",
        "rationale": "SYNTHETIC independent test-result assessment",
    }
    checks = [check]
    if both_required:
        checks.append(dict(check, id="C-B", requirement="404b:CTRL"))
    return {"scopes": scopes, "checks": checks}


def run(p=None, country="AE", **changes):
    p = population(country) if p is None else p
    sources = {role: source(ROLES[role], rows) for role, rows in p.items()}
    params = WorkflowInput.model_validate(
        {
            "workflow": "icfr-duty-coverage",
            "title": "SYNTHETIC ICFR duty review",
            "source_ids": {role: uuid.uuid4() for role in sources},
            "period_start": "2026-06-01",
            "as_of": "2026-06-30",
            "subjects": ["SYN-COMPONENT"],
            "required_checks": ["404a:CTRL", "404b:CTRL"]
            if len(p["checks"]) > 1
            else ["404a:CTRL"],
            "rationale": "SYNTHETIC separate management and auditor scope assessed against independent documents",
            **changes,
        }
    )
    return calculate(params, country, sources)


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_separate_assessed_exemption_never_suppresses_management_assessment(country):
    p = population(country)
    original = deepcopy(p)
    result = run(p, country)
    assert p == original and result["blocked"] is False and result["exception_count"] == 0
    assert len(result["rows"]) == 3
    scopes = [row for row in result["rows"] if row["kind"] == "scope-decision"]
    assert [row["state"] for row in scopes] == ["SUPPORTED", "NOT-APPLICABLE"]
    assert (
        result["effectiveness_conclusion"] == result["professional_conclusion"] == "NOT_DETERMINED"
    )
    assert result["statutory_calculation_qualified"] is False


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_management_evidence_does_not_clear_auditor_requirement(country):
    p = population(country, both_required=True)
    p["checks"].pop()
    result = run(p, country, required_checks=["404a:CTRL", "404b:CTRL"])
    assert result["blocked"]
    assert any(r["duty"] == "404b" and r["state"] == "MISSING" for r in result["rows"])


def test_both_required_with_separate_evidence_are_only_declared_coverage():
    result = run(population(both_required=True))
    assert not result["blocked"] and len(result["rows"]) == 4
    assert result["effectiveness_conclusion"] == "NOT_DETERMINED"


def test_missing_auditor_scope_is_pending_even_with_no_auditor_plan():
    p = population()
    p["scopes"].pop()
    result = run(p)
    assert result["blocked"] and result["rows"][-1]["state"] == "MISSING_SCOPE_DECISION"


def test_nil_scopes_never_establish_no_sox_duties():
    result = run({"scopes": [], "checks": []}, required_checks=[])
    assert result["blocked"] and len(result["rows"]) == 2
    assert all(r["state"] == "MISSING_SCOPE_DECISION" for r in result["rows"])


def test_both_explicit_negative_decisions_can_have_a_nil_plan():
    p = population()
    for row in p["scopes"]:
        row["applicability"] = "not-required"
    p["checks"] = []
    result = run(p, required_checks=[])
    assert not result["blocked"] and all(r["state"] == "NOT-APPLICABLE" for r in result["rows"])


@pytest.mark.parametrize(
    "field,value,state",
    [
        ("adoption_status", "pending", "PENDING_AUTHORITY_ADOPTION"),
        ("applicability", "unresolved", "PENDING_APPLICABILITY"),
        ("effective_from", "2026-06-02", "AUTHORITY_WINDOW_NOT_COVERED"),
        ("effective_to", "2026-06-29", "AUTHORITY_WINDOW_NOT_COVERED"),
    ],
)
def test_pending_or_wrong_period_authority_blocks_coverage(field, value, state):
    p = population()
    p["scopes"][0][field] = value
    result = run(p)
    assert result["blocked"] and result["rows"][0]["state"] == state


def test_required_scope_without_any_plan_is_unresolved():
    p = population()
    p["checks"] = []
    assert run(p, required_checks=[])["rows"][0]["state"] == "MISSING_DUTY_PLAN"


@pytest.mark.parametrize(
    "field,value", [("reporting_issuer", "OTHER-ISSUER"), ("relationship", "issuer")]
)
def test_subject_cannot_silently_change_issuer_between_duties(field, value):
    p = population()
    p["scopes"][1][field] = value
    with pytest.raises(ValueError, match="relationship conflicts"):
        run(p)


@pytest.mark.parametrize(
    "field,value",
    [("period_start", "2026-05-01"), ("engagement_country", "IN"), ("subject", "OTHER-SUBJECT")],
)
def test_wrong_period_country_or_subject_facts_are_rejected(field, value):
    p = population()
    p["scopes"][0][field] = value
    with pytest.raises(ValueError, match="period|population"):
        run(p)


@pytest.mark.parametrize(
    "role,message", [("scopes", "Duplicate ICFR subject/duty"), ("checks", "Duplicate ICFR check")]
)
def test_duplicate_observations_never_combine(role, message):
    p = population()
    p[role].append(dict(p[role][0], id="DUPLICATE-ROW"))
    with pytest.raises(ValueError, match=message):
        run(p)


@pytest.mark.parametrize("reference", ["management-report", "404c:CTRL", "404b:"])
def test_unscoped_or_unknown_plan_identifiers_are_rejected(reference):
    with pytest.raises(ValueError, match="404a:<point>"):
        run(required_checks=[reference])


@pytest.mark.parametrize("expiry,blocked", [("2026-06-29", True), ("2026-06-30", False)])
def test_expiry_is_checked_at_exact_period_end(expiry, blocked):
    p = population()
    p["checks"][0]["expires_on"] = expiry
    assert run(p)["blocked"] is blocked


@pytest.mark.parametrize("field", ["evidence_reference", "rationale"])
def test_supported_label_without_assessed_evidence_is_blocked(field):
    p = population()
    p["checks"][0][field] = " "
    assert run(p)["blocked"]


def test_failure_is_retained_without_effectiveness_conclusion():
    p = population()
    p["checks"][0]["state"] = "exception"
    result = run(p)
    assert not result["blocked"] and result["exception_count"] == 1
    assert result["rows"][1]["state"] == "EXCEPTION"
    assert result["effectiveness_conclusion"] == "NOT_DETERMINED"


def test_unplanned_evidence_is_visible_and_blocks_incomplete_plan():
    p = population()
    p["checks"].append(dict(p["checks"][0], id="EXTRA", requirement="404b:OTHER"))
    result = run(p, required_checks=["404a:CTRL"])
    assert result["blocked"] and result["rows"][-1]["state"] == "UNPLANNED_EVIDENCE"


@pytest.mark.parametrize("field", ["authority_evidence_version_id", "authority_sha256"])
def test_authority_and_company_assessment_must_be_distinct(field):
    row = population()["scopes"][0]
    row[field] = row[field.replace("authority", "assessment")]
    with pytest.raises(ValidationError, match="separately"):
        ICFRScope.model_validate(row)


def test_approval_requires_runtime_document_binding():
    result = run()
    assert "retained authority" in approval_error(result)
    assert approval_error({**result, "icfr_scope_document_binding": BINDING}) is None
