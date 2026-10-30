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
