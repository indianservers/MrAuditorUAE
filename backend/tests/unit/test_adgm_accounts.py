"""Source-pinned timetable examples and rejected bypasses; no client qualification."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.grc.adgm_accounts import (
    GUIDANCE_SHA256,
    PROFILE,
    REGULATIONS_SHA256,
    assess,
    saved_assessment,
)
from app.modules.grc.schemas import Obligation
from tests.unit.test_dmcc_audit import payload as dmcc_payload


def payload():
    value = dmcc_payload()
    value.pop("dmcc_audit_scope")
    value.pop("dmcc_guideline_evidence_id")
    value.update(
        source_url="https://en.adgm.thomsonreuters.com/rulebook/companies-regulations-2020",
        obligation_period_start="2025-07-01",
        obligation_period_end="2026-07-02",
        adgm_guidance_evidence_id=str(uuid4()),
        calendar_evidence_id=str(uuid4()),
    )
    value["jurisdiction_scope"]["registration_reference"] = "SYNTHETIC-ADGM-1"
    value["deadline_rule"] = {
        "identifier": "SYNTHETIC-ADGM-reference-date",
        "version": 1,
        "effective_from": "2025-01-01",
        "effective_to": "2030-12-31",
        "date_basis": "specified_event",
        "trigger": "2026-06-30",
        "months_after": 9,
        "month_end_policy": "preserve_month_end",
        "timezone": "Asia/Dubai",
        "convention": "following",
        "rolling_calendar": {
            "coverage_start": "2026-01-01",
            "coverage_end": "2030-12-31",
            "weekend_days": [5, 6],
            "holidays": [],
            "independent_holiday_count": 0,
            "assessment": "SYNTHETIC explicitly zero holidays for arithmetic testing, not a national calendar",
        },
    }
    value["adgm_accounts_scope"] = {
        "profile": PROFILE,
        "registration": "assessed_yes",
        "legal_form": "company",
        "company_status_at_reference_end": "private",
        "filing_duty": "assessed_required",
        "duty_basis": "SYNTHETIC independently assessed s415 filing duty and exceptions; no real entity qualification",
        "accounting_reference_start": "2025-07-01",
        "accounting_reference_end": "2026-06-30",
        "incorporation_date": "2020-05-12",
        "period_classification": "subsequent",
        "period_validity": "assessed_valid",
        "shortened_period": "assessed_no",
        "other_authority_modifications": "assessed_none",
        "operative_from": "2025-01-01",
        "operative_through": "2030-12-31",
        "assessed_on": "2026-10-31",
        "assessment": "SYNTHETIC adopted operative window and reference period assessment; not professional qualification",
    }
    return value


def first_long(status="private"):
    value = payload()
    scope = value["adgm_accounts_scope"]
    scope.update(
        company_status_at_reference_end=status,
        incorporation_date="2026-09-30",
        accounting_reference_start="2026-09-30",
        accounting_reference_end="2027-12-31",
        period_classification="first_long",
        first_anniversary="2027-09-30",
        assessed_on="2028-01-31",
    )
    value.update(obligation_period_start="2026-09-30", obligation_period_end="2027-12-31")
    value["deadline_rule"].update(
        trigger="2027-09-30",
        months_after=9 if status == "private" else 6,
        later_of=[
            {
                "identifier": "SYNTHETIC-reference-end",
                "date_basis": "specified_event",
                "trigger": "2027-12-31",
                "months_after": 3,
            }
        ],
    )
    return value


@pytest.mark.parametrize(
    ("status", "months", "expected"), [("private", 9, "2027-03-31"), ("public", 6, "2026-12-31")]
)
def test_reference_date_and_status_at_reference_end_drive_timetable(status, months, expected):
    value = payload()
    value["adgm_accounts_scope"]["company_status_at_reference_end"] = status
    value["deadline_rule"]["months_after"] = months
    data = Obligation.model_validate(value)
    assert data.deadline.isoformat() == expected
    assert data.obligation_period_end.isoformat() == "2026-07-02"
    assert assess(data)["issues"] == []


@pytest.mark.parametrize(
    ("status", "expected"), [("private", "2028-06-30"), ("public", "2028-03-31")]
)
def test_long_first_period_retains_both_s416_candidates(status, expected):
    data = Obligation.model_validate(first_long(status))
    assert data.deadline.isoformat() == expected
    assert assess(data)["state"] == "TIMETABLE_ON_ASSESSED_FACTS"


def test_first_standard_period_and_later_shortening_notice_win_separately():
    value = payload()
    value["adgm_accounts_scope"].update(
        incorporation_date="2025-09-01",
        accounting_reference_start="2025-09-01",
        period_classification="first_standard",
        first_anniversary="2026-09-01",
    )
    value["obligation_period_start"] = "2025-09-01"
    assert assess(Obligation.model_validate(value))["issues"] == []
    value["adgm_accounts_scope"].update(
        shortened_period="assessed_yes",
        shortening_notice_date="2027-02-15",
        shortening_receipt_date="2027-02-15",
        assessed_on="2027-02-16",
    )
    value["deadline_rule"]["later_of"] = [
        {
            "identifier": "SYNTHETIC-shortening",
            "date_basis": "specified_event",
            "trigger": "2027-02-15",
            "months_after": 3,
        }
    ]
    data = Obligation.model_validate(value)
    assert data.deadline.isoformat() == "2027-05-17"  # May 15 is Saturday in the explicit fixture.
    assert assess(data)["issues"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"months_after": 6},
        {"month_end_policy": "clamp"},
        {"date_basis": "period_end", "trigger": "2026-07-02"},
        {"days_after": 1},
        {"timezone": "Asia/Kolkata"},
        {"convention": "preceding"},
        {
            "later_of": [
                {
                    "identifier": "SYNTHETIC-extra",
                    "date_basis": "specified_event",
                    "trigger": "2026-06-30",
                    "months_after": 12,
                }
            ]
        },
    ],
)
def test_profile_rejects_similar_but_different_rules(changes):
    value = payload()
    value["deadline_rule"].update(changes)
    with pytest.raises(ValueError):
        Obligation.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        {"company_status_at_reference_end": "unassessed"},
        {"period_validity": "unresolved"},
        {"other_authority_modifications": "unresolved"},
        {"assessed_on": "2026-10-13"},
        {"operative_through": "2027-01-01"},
        {"incorporation_date": None},
        {"shortened_period": "unassessed"},
    ],
)
def test_unresolved_facts_cannot_support_approval(change):
    value = payload()
    value["adgm_accounts_scope"].update(change)
    if "company_status_at_reference_end" in change:
        value.pop("deadline_rule")
        value.pop("calendar_evidence_id")
    data = Obligation.model_validate(value)
    assert assess(data)["state"] == "REVIEW_REQUIRED"
    value["compliance_assessment"] = "supported"
    with pytest.raises(ValueError, match="Resolve ADGM"):
        Obligation.model_validate(value)


def test_notice_sent_and_received_on_different_days_stays_pending():
    value = payload()
    value["adgm_accounts_scope"].update(
        shortened_period="assessed_yes",
        shortening_notice_date="2026-10-01",
        shortening_receipt_date="2026-10-02",
    )
    value["deadline_rule"]["later_of"] = [
        {
            "identifier": "SYNTHETIC-notice",
            "date_basis": "specified_event",
            "trigger": "2026-10-01",
            "months_after": 3,
        }
    ]
    assert (
        "NOTICE_DATE_AND_REGISTRAR_RECEIPT_REQUIRE_SEPARATE_ASSESSMENT"
        in assess(Obligation.model_validate(value))["issues"]
    )


@pytest.mark.parametrize("role", ["llp", "foundation", "branch"])
def test_other_forms_remain_potential_and_cannot_inherit_company_qualification(role):
    value = payload()
    value["adgm_accounts_scope"]["legal_form"] = role
    value["jurisdiction_scope"]["applicability"] = "potential"
    assert assess(Obligation.model_validate(value))["filing_required"] is None
    value["jurisdiction_scope"]["applicability"] = "assessed_applicable"
    with pytest.raises(ValueError, match="Unresolved ADGM"):
        Obligation.model_validate(value)


def test_exempt_duty_is_an_explicit_assessment_and_has_no_deadline():
    value = payload()
    value["adgm_accounts_scope"]["filing_duty"] = "assessed_exempt"
    value["jurisdiction_scope"]["applicability"] = "assessed_not_applicable"
    with pytest.raises(ValueError, match="exemption"):
        Obligation.model_validate(value)
    value.pop("deadline_rule")
    value.pop("calendar_evidence_id")
    assert assess(Obligation.model_validate(value))["state"] == "ASSESSED_NO_FILING_DUTY"


@pytest.mark.parametrize("applied", ["2027-04-01T00:00:00+04:00", "2027-03-31T20:00:00Z"])
def test_extension_application_after_local_deadline_is_rejected(applied):
    value = payload()
    value.update(extension_deadline="2027-06-30", extension_evidence_id=str(uuid4()))
    value["adgm_accounts_scope"]["extension_applied_at"] = applied
    with pytest.raises(ValueError, match="timely application"):
        Obligation.model_validate(value)


def test_extension_retains_three_month_and_twelve_month_caps():
    value = payload()
    value.update(extension_deadline="2027-06-30", extension_evidence_id=str(uuid4()))
    value["adgm_accounts_scope"]["extension_applied_at"] = "2027-03-31T23:59:59+04:00"
    assert Obligation.model_validate(value).extension_deadline.isoformat() == "2027-06-30"
    value["extension_deadline"] = "2027-07-01"
    with pytest.raises(ValueError, match="twelve-month"):
        Obligation.model_validate(value)


def test_foreign_parent_and_rule_source_aliases_do_not_inherit_adgm_company_scope():
    value = payload()
    value["jurisdiction_scope"].update(entity_country="IN", relationship="foreign")
    with pytest.raises(ValueError, match="own UAE legal entity"):
        Obligation.model_validate(value)
    value = payload()
    value["adgm_guidance_evidence_id"] = value["rule_evidence_id"]
    with pytest.raises(ValueError, match="separate UAE"):
        Obligation.model_validate(value)


def test_saved_invalid_and_old_ordinary_obligations_are_distinct():
    assert saved_assessment({"adgm_accounts_scope": {}})["issues"] == [
        "SAVED_ADGM_SCOPE_REQUIRES_REASSESSMENT"
    ]
    assert saved_assessment({}) is None
    old = dmcc_payload()
    old.pop("dmcc_audit_scope")
    old.pop("dmcc_guideline_evidence_id")
    assert "adgm_accounts_scope" not in Obligation.model_validate(old).model_dump(mode="json")


def test_exact_original_source_hashes_are_retained():
    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/authority-references/adgm-accounts-2026-10-31"
    )
    for filename, expected in [
        ("adgm-companies-consolidated-ver20260626.pdf", REGULATIONS_SHA256),
        ("adgm-annual-accounts-v2-20261014.pdf", GUIDANCE_SHA256),
    ]:
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == expected


def test_public_long_period_can_select_reference_end_instead_of_anniversary():
    value = first_long("public")
    value["adgm_accounts_scope"].update(
        accounting_reference_end="2028-03-29", assessed_on="2028-04-01"
    )
    value["obligation_period_end"] = "2028-03-29"
    value["deadline_rule"]["later_of"][0]["trigger"] = "2028-03-29"
    data = Obligation.model_validate(value)
    assert data.deadline.isoformat() == "2028-06-29"
    assert assess(data)["issues"] == []


@pytest.mark.parametrize("end", ["2026-10-01", "2027-09-29", "2028-04-01"])
def test_implausible_first_long_period_cannot_be_supported(end):
    value = first_long()
    value["adgm_accounts_scope"]["accounting_reference_end"] = end
    value["obligation_period_end"] = end
    value["deadline_rule"]["later_of"][0]["trigger"] = end
    data = Obligation.model_validate(value)
    assert "FIRST_PERIOD_DATES_LENGTH_AND_ANNIVERSARY_REQUIRE_ASSESSMENT" in assess(data)["issues"]


def test_unrelated_accounts_period_does_not_qualify_a_reference_period():
    value = payload()
    value["obligation_period_end"] = "2026-07-08"
    assert (
        "ACCOUNTS_PERIOD_AND_REFERENCE_PERIOD_MAPPING_REQUIRE_ASSESSMENT"
        in assess(Obligation.model_validate(value))["issues"]
    )


def test_long_first_and_shortening_candidates_are_combined_before_rolling():
    value = first_long()
    value["adgm_accounts_scope"].update(
        shortened_period="assessed_yes",
        shortening_notice_date="2028-05-01",
        shortening_receipt_date="2028-05-01",
        assessed_on="2028-05-02",
    )
    value["deadline_rule"]["later_of"].append(
        {
            "identifier": "SYNTHETIC-shortening",
            "date_basis": "specified_event",
            "trigger": "2028-05-01",
            "months_after": 3,
        }
    )
    assert Obligation.model_validate(value).deadline.isoformat() == "2028-08-01"


def test_explicit_calendar_adjusts_selected_day_and_missing_coverage_rejects_it():
    value = payload()
    calendar = value["deadline_rule"]["rolling_calendar"]
    calendar.update(holidays=["2027-03-31"], independent_holiday_count=1)
    assert Obligation.model_validate(value).deadline.isoformat() == "2027-04-01"
    calendar["coverage_end"] = "2027-03-31"
    with pytest.raises(ValueError, match="coverage"):
        Obligation.model_validate(value)


@pytest.mark.parametrize(
    "source", ["rule_evidence_id", "adgm_guidance_evidence_id", "calendar_evidence_id"]
)
def test_extension_outcome_cannot_reuse_rule_guidance_or_calendar(source):
    value = payload()
    value.update(extension_deadline="2027-06-30", extension_evidence_id=value[source])
    value["adgm_accounts_scope"]["extension_applied_at"] = "2027-03-31T23:59:59+04:00"
    with pytest.raises(ValueError, match="outcome must be separate"):
        Obligation.model_validate(value)


def test_naive_extension_timestamp_does_not_imply_dubai_time():
    value = payload()
    value.update(extension_deadline="2027-06-30", extension_evidence_id=str(uuid4()))
    value["adgm_accounts_scope"]["extension_applied_at"] = "2027-03-31T23:59:59"
    with pytest.raises(ValueError, match="timezone"):
        Obligation.model_validate(value)


@pytest.mark.parametrize(
    ("end", "classification", "valid"),
    [
        ("2027-03-29", "first_standard", False),
        ("2027-03-30", "first_standard", True),
        ("2027-09-29", "first_standard", True),
        ("2027-09-30", "first_long", True),
        ("2028-03-29", "first_long", True),
        ("2028-03-30", "first_long", False),
    ],
)
def test_first_reference_period_inclusive_end_boundaries(end, classification, valid):
    value = first_long()
    value["obligation_period_end"] = end
    value["adgm_accounts_scope"].update(
        accounting_reference_end=end, period_classification=classification, assessed_on="2028-04-01"
    )
    if classification == "first_long":
        value["deadline_rule"]["later_of"][0]["trigger"] = end
    else:
        value["deadline_rule"].update(trigger=end, later_of=[])
    issues = assess(Obligation.model_validate(value))["issues"]
    assert ("FIRST_PERIOD_DATES_LENGTH_AND_ANNIVERSARY_REQUIRE_ASSESSMENT" not in issues) is valid


def test_first_accounts_cannot_begin_before_incorporation_within_seven_day_tolerance():
    value = first_long()
    value["obligation_period_start"] = "2026-09-29"
    assert (
        "FIRST_PERIOD_DATES_LENGTH_AND_ANNIVERSARY_REQUIRE_ASSESSMENT"
        in assess(Obligation.model_validate(value))["issues"]
    )


@pytest.mark.parametrize("stage", ["approved_for_submission", "submitted", "acknowledged"])
@pytest.mark.parametrize("change", ["scope", "guidance", "remove_profile"])
async def test_approved_adgm_scope_cannot_change_without_preparing(monkeypatch, stage, change):
    from app.modules.grc import filing

    body = payload()
    reviewer, rid = uuid4(), uuid4()
    body.update(
        filing_stage=stage,
        reviewer_id=str(reviewer),
        readiness_evidence_ids=[str(uuid4())],
        submission_evidence_id=str(uuid4()) if stage != "approved_for_submission" else None,
        acknowledgment_evidence_id=str(uuid4()) if stage == "acknowledged" else None,
    )
    original = Obligation.model_validate(body)
    previous = SimpleNamespace(body=original.model_dump(mode="json"), status="REVISED")

    async def record(*args):
        return previous if args[3] == rid else SimpleNamespace(kind="evidence")

    monkeypatch.setattr(filing.audit, "get_record", record)
    monkeypatch.setattr(filing, "engagement_permissions", AsyncMock())
    changed = original.model_dump(mode="json")
    if change == "scope":
        changed["adgm_accounts_scope"]["assessed_on"] = "2026-11-01"
    elif change == "guidance":
        changed["adgm_guidance_evidence_id"] = str(uuid4())
    else:
        changed.pop("adgm_accounts_scope")
        changed.pop("adgm_guidance_evidence_id")
    ctx, eng = SimpleNamespace(user_id=reviewer, tenant_id=uuid4()), SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException, match="Approved filing inputs changed"):
        await filing.validate_transition(None, ctx, eng, Obligation.model_validate(changed), rid)
    changed["filing_stage"] = "preparing"
    await filing.validate_transition(None, ctx, eng, Obligation.model_validate(changed), rid)
