"""Country scope is an evidenced assessment, separate from entity nationality."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.grc.deadlines import state
from app.modules.grc.schemas import Obligation


def payload(entity="AE", obligation="IN", applicability="potential"):
    return {
        "owner_id": str(uuid4()),
        "entity_id": str(uuid4()),
        "module": "vat",
        "source_url": "https://synthetic.invalid/assessed-rule",
        "jurisdiction": obligation,
        "effective_from": "2026-01-01",
        "required_evidence": "Synthetic independently assessed source scope",
        "compliance_assessment": "pending",
        "rule_evidence_id": str(uuid4()),
        "fact_evidence_ids": [str(uuid4())],
        "entity_facts": {"registration": "SYNTHETIC assessed registration"},
        "jurisdiction_scope": {
            "entity_country": entity,
            "obligation_country": obligation,
            "relationship": "domestic" if entity == obligation else "foreign",
            "applicability": applicability,
            "registration_reference": "SYN-REG-001",
            "assessment": "SYNTHETIC independent assessment; no legal qualification",
        },
    }


@pytest.mark.parametrize(
    "entity,obligation", [("AE", "AE"), ("AE", "IN"), ("IN", "IN"), ("IN", "AE"), ("AE", "GB")]
)
def test_explicit_country_relationship_round_trips_without_activating_foreign_rules(
    entity, obligation
):
    data = Obligation.model_validate(payload(entity, obligation))
    assert data.jurisdiction_scope.entity_country == entity
    assert data.jurisdiction_scope.obligation_country == obligation
    assert Obligation.model_validate(data.model_dump(mode="json")) == data


@pytest.mark.parametrize(
    "field,value",
    [
        ("relationship", "domestic"),
        ("entity_country", "ae"),
        ("assessment", "          "),
        ("registration_reference", " SYN-REG "),
    ],
)
def test_inconsistent_or_ambiguous_scope_is_rejected(field, value):
    body = payload()
    body["jurisdiction_scope"][field] = value
    with pytest.raises(ValidationError):
        Obligation.model_validate(body)


@pytest.mark.parametrize("missing", ["rule_evidence_id", "fact_evidence_ids", "entity_facts"])
def test_country_scope_requires_separate_rule_and_entity_facts(missing):
    body = payload()
    body.pop(missing)
    with pytest.raises(ValidationError):
        Obligation.model_validate(body)


def test_rule_and_fact_record_cannot_be_the_same_or_jurisdiction_disagree():
    body = payload()
    body["fact_evidence_ids"] = [body["rule_evidence_id"]]
    with pytest.raises(ValidationError):
        Obligation.model_validate(body)
    body = payload()
    body["jurisdiction"] = "AE"
    with pytest.raises(ValidationError):
        Obligation.model_validate(body)


@pytest.mark.parametrize(
    "applicability,expected",
    [
        ("potential", "APPLICABILITY_PENDING"),
        ("assessed_not_applicable", "ASSESSED_NOT_APPLICABLE"),
        ("assessed_applicable", "OVERDUE"),
    ],
)
def test_calendar_does_not_present_unassessed_foreign_scope_as_a_late_filing(
    applicability, expected
):
    body = payload(applicability=applicability)
    body["deadline"] = "2026-01-01"
    data = Obligation.model_validate(body)
    assert state(data.model_dump(mode="json"), date(2026, 10, 30)) == expected
    if applicability != "assessed_applicable":
        body.update(
            filing_stage="approved_for_submission",
            reviewer_id=str(uuid4()),
            readiness_evidence_ids=[str(uuid4())],
        )
        with pytest.raises(ValidationError):
            Obligation.model_validate(body)


def test_legacy_scope_remains_unassessed_without_being_auto_populated():
    body = payload()
    body.pop("jurisdiction_scope")
    assert Obligation.model_validate(body).jurisdiction_scope is None
    assert state(body, date(2026, 10, 30)) == "UNRESOLVED"


@pytest.mark.parametrize("entity,obligation", [("AE", "IN"), ("IN", "AE"), ("AE", "AE")])
def test_obligation_period_is_explicit_without_a_country_year_default(entity, obligation):
    body = payload(entity, obligation)
    body.update(obligation_period_start="2025-04-01", obligation_period_end="2026-03-31")
    data = Obligation.model_validate(body)
    assert data.obligation_period_start == date(2025, 4, 1)
    assert data.obligation_period_end == date(2026, 3, 31)
    assert Obligation.model_validate(payload(entity, obligation)).obligation_period_end is None


@pytest.mark.parametrize(
    "changes",
    [
        {"obligation_period_start": "2025-04-01"},
        {"obligation_period_end": "2026-03-31"},
        {"obligation_period_start": "2026-04-01", "obligation_period_end": "2026-03-31"},
        {"obligation_period_start": "2025-04-01T00:00:00Z", "obligation_period_end": "2026-03-31"},
        {
            "obligation_period_start": "2025-04-01",
            "obligation_period_end": "2026-03-31",
            "jurisdiction_scope": None,
        },
    ],
)
def test_partial_reversed_timestamp_or_unscoped_periods_are_rejected(changes):
    body = payload()
    body.update(changes)
    with pytest.raises(ValidationError):
        Obligation.model_validate(body)


def test_scoped_period_end_rule_requires_its_own_assessed_period():
    body = payload()
    body["deadline_rule"] = {
        "identifier": "SYNTHETIC-period-rule",
        "version": 1,
        "effective_from": "2025-01-01",
        "trigger": "2026-03-31",
        "date_basis": "period_end",
        "days_after": 7,
        "timezone": "Asia/Kolkata",
    }
    with pytest.raises(ValidationError, match="explicit obligation period"):
        Obligation.model_validate(body)
    body.update(obligation_period_start="2025-04-01", obligation_period_end="2026-03-31")
    assert Obligation.model_validate(body).deadline == date(2026, 4, 7)


@pytest.mark.parametrize(
    "structured,expected", [(True, "PERIOD_SCOPE_PENDING"), (False, "OVERDUE")]
)
def test_historical_scoped_period_requires_reassessment_without_rewriting_history(
    structured, expected
):
    from copy import deepcopy

    from app.modules.grc.deadlines import missing_obligation_period

    body = payload(applicability="assessed_applicable")
    body.update(deadline="2026-04-07", deadline_rule={"date_basis": "period_end"})
    if not structured:
        body.pop("jurisdiction_scope")
    retained = deepcopy(body)
    assert missing_obligation_period(body) is structured
    assert state(body, date(2026, 10, 30)) == expected
    assert body == retained
