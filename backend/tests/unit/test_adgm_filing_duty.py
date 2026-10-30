"""Explicit condition and source boundaries, not legal or client qualification."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.grc.adgm_accounts import assess
from app.modules.grc.adgm_filing_duty import (
    DORMANT_CONDITIONS,
    PROFILE,
    SUPPORT_DOCUMENTS,
    UNLIMITED_EXCLUSIONS,
)
from app.modules.grc.schemas import Obligation
from tests.unit.test_adgm_accounts import payload as legacy_payload


def payload(existing=None):
    value = deepcopy(existing) if existing is not None else legacy_payload()
    scope = value["adgm_accounts_scope"]
    scope.update(
        profile=PROFILE,
        filing_procedure="individual_accounts",
        filing_duty_checks={
            "accounts_period_start": value["obligation_period_start"],
            "accounts_period_end": value["obligation_period_end"],
            "reference_period_start": scope["accounting_reference_start"],
            "reference_period_end": scope["accounting_reference_end"],
            "facts": [],
        },
    )
    for key in [
        "restricted_scope_company",
        "unlimited_company",
        "dormant_subsidiary_exemption_claimed",
    ]:
        set_fact(value, key, False)
    return value


def set_fact(value, key, answer):
    facts = value["adgm_accounts_scope"]["filing_duty_checks"]["facts"]
    facts[:] = [fact for fact in facts if fact["key"] != key]
    facts.append(
        {
            "key": key,
            "answer": "unassessed"
            if answer is None
            else "assessed_yes"
            if answer
            else "assessed_no",
            "evidence_ids": value["fact_evidence_ids"][:1] if answer is not None else [],
            "assessment": "SYNTHETIC independent assessment for the explicitly retained year/reference period; not a client conclusion",
        }
    )


def individual_exemption(value):
    value["adgm_accounts_scope"]["filing_duty"] = "assessed_exempt"
    value["jurisdiction_scope"]["applicability"] = "assessed_not_applicable"
    value.pop("deadline_rule", None)
    value.pop("calendar_evidence_id", None)
    return value


def pending(value):
    value["adgm_accounts_scope"]["filing_duty"] = "unassessed"
    value["jurisdiction_scope"]["applicability"] = "potential"
    return value


def duty(value):
    return assess(Obligation.model_validate(value))["filing_duty_assessment"]


def dormant(value=None, delivered=True):
    value = value or payload()
    set_fact(value, "dormant_subsidiary_exemption_claimed", True)
    for key, answer in DORMANT_CONDITIONS.items():
        set_fact(value, key, answer)
    for key in SUPPORT_DOCUMENTS:
        set_fact(value, key, delivered)
    set_fact(value, "support_delivery_within_filing_period_assessed", delivered)
    return value


def unlimited():
    value = payload()
    set_fact(value, "unlimited_company", True)
    for key in UNLIMITED_EXCLUSIONS:
        set_fact(value, key, False)
    return value


def test_ordinary_company_requires_individual_accounts_without_inventing_exemptions():
    result = duty(payload())
    assert result["filing_required"] is True
    assert result["chapter_8_applies"] is True
    assert result["unlimited_company_exemption"] is False
    assert result["dormant_individual_accounts_exemption"] is False
    assert result["issues"] == [] and result["missing_criteria"] == []


def test_restricted_scope_without_notice_or_publication_has_no_chapter8_duty():
    value = payload()
    set_fact(value, "restricted_scope_company", True)
    set_fact(value, "registrar_notice_applies", False)
    set_fact(value, "non_registrable_publication_trigger", False)
    result = duty(individual_exemption(value))
    assert result["chapter_8_applies"] is False
    assert result["filing_required"] is False and result["supporting_documents_required"] is False


@pytest.mark.parametrize(
    "trigger", ["registrar_notice_applies", "non_registrable_publication_trigger"]
)
def test_either_restricted_scope_trigger_can_restore_chapter8_duty(trigger):
    value = payload()
    set_fact(value, "restricted_scope_company", True)
    set_fact(value, trigger, True)
    assert duty(value)["chapter_8_applies"] is True
    assert duty(value)["filing_required"] is True


def test_absent_restricted_scope_notice_is_unknown_not_an_assessed_negative():
    value = payload()
    set_fact(value, "restricted_scope_company", True)
    set_fact(value, "non_registrable_publication_trigger", False)
    result = duty(pending(value))
    assert result["chapter_8_applies"] is None
    assert result["filing_required"] is None
    assert result["missing_criteria"] == ["registrar_notice_applies"]


def test_unlimited_exemption_requires_all_five_negative_exclusion_assessments():
    result = duty(individual_exemption(unlimited()))
    assert result["unlimited_company_exemption"] is True
    assert result["filing_required"] is False


@pytest.mark.parametrize("key", UNLIMITED_EXCLUSIONS)
def test_any_unlimited_exclusion_defeats_that_exemption(key):
    value = unlimited()
    set_fact(value, key, True)
    result = duty(value)
    assert result["unlimited_company_exemption"] is False
    assert result["filing_required"] is True


@pytest.mark.parametrize("key", UNLIMITED_EXCLUSIONS)
def test_missing_unlimited_condition_never_becomes_a_negative_assessment(key):
    value = unlimited()
    set_fact(value, key, None)
    result = duty(pending(value))
    assert result["unlimited_company_exemption"] is None
    assert key in result["missing_criteria"] and result["filing_required"] is None


def test_dormant_individual_exemption_retains_all_five_supporting_filing_duties():
    result = duty(individual_exemption(dormant()))
    assert result["dormant_individual_accounts_exemption"] is True
    assert result["filing_required"] is False and result["supporting_documents_required"] is True
    assert len(result["supporting_documents"]) == 5
    assert all(
        item["delivery_assessment"] == "assessed_yes" for item in result["supporting_documents"]
    )


@pytest.mark.parametrize(
    "key", list(SUPPORT_DOCUMENTS) + ["support_delivery_within_filing_period_assessed"]
)
def test_known_missing_or_late_delivery_does_not_exempt_individual_accounts(key):
    value = dormant()
    set_fact(value, key, False)
    result = duty(value)
    assert result["dormant_individual_accounts_exemption"] is False
    assert result["filing_required"] is True and result["supporting_documents_required"] is True


@pytest.mark.parametrize(
    "key", list(SUPPORT_DOCUMENTS) + ["support_delivery_within_filing_period_assessed"]
)
def test_unknown_delivery_keeps_individual_exemption_pending(key):
    value = dormant()
    set_fact(value, key, None)
    result = duty(pending(value))
    assert result["dormant_individual_accounts_exemption"] is None
    assert result["filing_required"] is None and key in result["missing_criteria"]


@pytest.mark.parametrize("key", list(DORMANT_CONDITIONS))
def test_each_dormant_condition_is_required_including_s424_and_s425(key):
    value = dormant()
    set_fact(value, key, not DORMANT_CONDITIONS[key])
    result = duty(value)
    assert result["dormant_individual_accounts_exemption"] is False
    assert "DORMANT_SUBSIDIARY_CLAIM_CONTRADICTS_ASSESSED_CONDITIONS" in result["issues"]
    value["compliance_assessment"] = "supported"
    with pytest.raises(ValueError, match="Resolve ADGM"):
        Obligation.model_validate(value)


def test_supporting_documents_can_be_scheduled_before_they_are_delivered():
    value = dormant(delivered=None)
    value["adgm_accounts_scope"]["filing_procedure"] = "dormant_subsidiary_supporting_documents"
    result = duty(value)
    assert result["filing_required"] is True and result["issues"] == []
    assert result["dormant_individual_accounts_exemption"] is None
    assert len(result["supporting_documents"]) == 5
    assert Obligation.model_validate(value).deadline.isoformat() == "2027-03-31"


def test_failed_dormant_eligibility_does_not_certify_a_supporting_only_filing():
    value = dormant()
    value["adgm_accounts_scope"]["filing_procedure"] = "dormant_subsidiary_supporting_documents"
    set_fact(value, "guarantee_authenticated", False)
    assert duty(pending(value))["filing_required"] is None


def test_absent_dormant_claim_does_not_create_a_supporting_document_filing():
    value = payload()
    value["adgm_accounts_scope"]["filing_procedure"] = "dormant_subsidiary_supporting_documents"
    result = duty(individual_exemption(value))
    assert result["filing_required"] is False
    assert result["dormant_individual_accounts_exemption"] is False


@pytest.mark.parametrize(
    "field",
    [
        "accounts_period_start",
        "accounts_period_end",
        "reference_period_start",
        "reference_period_end",
    ],
)
def test_checks_cannot_be_reused_for_a_different_year_or_reference_period(field):
    value = payload()
    value["adgm_accounts_scope"]["filing_duty_checks"][field] = "2026-01-01"
    with pytest.raises(ValueError, match="period"):
        Obligation.model_validate(value)


@pytest.mark.parametrize("answer", ["assessed_yes", "assessed_no"])
def test_both_positive_and_negative_facts_require_retained_original_links(answer):
    value = payload()
    value["adgm_accounts_scope"]["filing_duty_checks"]["facts"][0].update(
        answer=answer, evidence_ids=[]
    )
    with pytest.raises(ValueError, match="original evidence"):
        Obligation.model_validate(value)


def test_nested_links_must_already_be_protected_company_fact_sources():
    value = payload()
    value["adgm_accounts_scope"]["filing_duty_checks"]["facts"][0]["evidence_ids"] = [str(uuid4())]
    with pytest.raises(ValueError, match="company-fact evidence link"):
        Obligation.model_validate(value)


def test_declared_exemption_cannot_override_failed_or_missing_conditions():
    unknown = unlimited()
    set_fact(unknown, "limited_parent_at_any_time", None)
    for value in [payload(), pending(unknown)]:
        individual_exemption(value)
        with pytest.raises(ValueError, match="contradicts"):
            Obligation.model_validate(value)


def test_duplicate_conditions_and_v2_fallback_to_a_narrative_are_rejected():
    value = payload()
    facts = value["adgm_accounts_scope"]["filing_duty_checks"]["facts"]
    facts.append(deepcopy(facts[0]))
    with pytest.raises(ValueError, match="distinct criteria"):
        Obligation.model_validate(value)
    value = payload()
    value["adgm_accounts_scope"].pop("filing_duty_checks")
    with pytest.raises(ValueError, match="v2 requires"):
        Obligation.model_validate(value)


def test_legacy_v1_bodies_keep_their_original_serialized_shape():
    data = Obligation.model_validate(legacy_payload())
    body = data.model_dump(mode="json")["adgm_accounts_scope"]
    assert "filing_duty_checks" not in body and "filing_procedure" not in body
    value = payload()
    value["adgm_accounts_scope"]["profile"] = data.adgm_accounts_scope.profile
    with pytest.raises(ValueError, match="explicit ADGM v2"):
        Obligation.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [{"registration": "unassessed"}, {"registration": "assessed_no"}, {"legal_form": "llp"}],
)
def test_unestablished_company_scope_cannot_produce_a_nested_positive_determination(change):
    value = pending(payload())
    value["adgm_accounts_scope"].update(change)
    result = duty(value)
    assert result["filing_required"] is None and result["chapter_8_applies"] is None
    assert result["reason"] == "ADGM_COMPANY_SCOPE_NOT_ESTABLISHED"


def test_invalid_saved_v2_is_reassessment_under_its_retained_profile():
    from app.modules.grc.adgm_accounts import saved_assessment

    result = saved_assessment({"adgm_accounts_scope": {"profile": PROFILE}})
    assert result["state"] == "REVIEW_REQUIRED"
    assert result["profile"] == PROFILE and result["filing_required"] is None
