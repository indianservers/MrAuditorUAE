"""Explicit jurisdiction calendars; synthetic holidays are not national calendars."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.grc.deadlines import DeadlineRule, calculate
from app.modules.grc.schemas import Obligation
from tests.unit.test_final_foundations import obligation, rule


def parameters(**changes):
    return {
        "identifier": "SYNTHETIC-event-plus-five-business-days",
        "version": 1,
        "effective_from": "2026-01-01",
        "trigger": "2026-06-26",
        "date_basis": "specified_event",
        "days_after": 5,
        "timezone": "Asia/Dubai",
        "day_count_basis": "business",
        "business_trigger_policy": "exclude",
        "business_calendar": {
            "coverage_start": "2026-06-01",
            "coverage_end": "2026-07-31",
            "weekend_days": [5, 6],
            "holidays": ["2026-06-29"],
            "independent_holiday_count": 1,
            "assessment": "SYNTHETIC independently assessed complete operating calendar, not a legal holiday assertion",
        },
        **changes,
    }


def test_business_day_count_excludes_trigger_weekends_and_explicit_holiday():
    assert calculate(DeadlineRule.model_validate(parameters())) == date(2026, 7, 6)
    # Five calendar days with final-date rolling is a different procedure.
    assert calculate(
        rule(
            trigger="2026-06-26",
            months_after=0,
            days_after=5,
            convention="following",
            weekend_days=[5, 6],
            holidays=["2026-06-29"],
        )
    ) == date(2026, 7, 1)


@pytest.mark.parametrize(
    "weekend,expected", [([5, 6], "2026-07-03"), ([6], "2026-07-02"), ([4, 5], "2026-07-02")]
)
def test_country_choice_never_substitutes_an_assumed_working_week(weekend, expected):
    data = parameters()
    data["business_calendar"].update(weekend_days=weekend, holidays=[], independent_holiday_count=0)
    assert calculate(DeadlineRule.model_validate(data)).isoformat() == expected


@pytest.mark.parametrize("trigger", ["2026-06-27", "2026-06-28"])
def test_weekend_trigger_is_excluded_and_does_not_count_as_a_business_day(trigger):
    assert calculate(DeadlineRule.model_validate(parameters(trigger=trigger))) == date(2026, 7, 6)


@pytest.mark.parametrize(
    "change",
    [
        {"business_calendar": None},
        {"months_after": 1},
        {"days_after": 0},
        {"convention": "following"},
        {"weekend_days": [5, 6]},
        {"holidays": ["2026-06-29"]},
        {"day_count_basis": "calendar"},
    ],
)
def test_mixed_or_unspecified_counting_never_silently_changes_the_deadline(change):
    with pytest.raises(ValueError):
        calculate(DeadlineRule.model_validate(parameters(**change)))


@pytest.mark.parametrize(
    "change",
    [
        {"coverage_end": "2026-06-30"},
        {"coverage_start": "2026-07-01"},
        {"coverage_start": "2026-08-01"},
        {"coverage_end": "2040-01-01"},
        {"weekend_days": []},
        {"weekend_days": list(range(7))},
        {"weekend_days": [5, 5]},
        {"weekend_days": [True]},
        {"weekend_days": ["6"]},
        {"weekend_days": [-1]},
        {"holidays": ["2026-06-29", "2026-06-29"], "independent_holiday_count": 2},
        {"holidays": ["2026-08-01"]},
        {"independent_holiday_count": 0},
        {"independent_holiday_count": True},
        {"assessment": "          "},
    ],
)
def test_calendar_completeness_and_scope_controls(change):
    data = parameters()
    data["business_calendar"].update(change)
    with pytest.raises(ValueError):
        calculate(DeadlineRule.model_validate(data))


def test_legacy_calendar_rule_serialization_remains_unchanged():
    original = rule().model_dump(mode="json")
    assert "day_count_basis" not in original and "business_calendar" not in original
    assert "calendar_evidence_id" not in obligation().model_dump(mode="json")
    assert calculate(DeadlineRule.model_validate(original)) == date(2026, 2, 28)


@pytest.mark.parametrize("calendar_id", [None, "same-as-rule"])
def test_business_deadline_needs_separate_calendar_evidence(calendar_id):
    rule_id = uuid4()
    with pytest.raises(ValueError, match="separate retained calendar evidence"):
        obligation(
            deadline_rule=parameters(),
            rule_evidence_id=rule_id,
            calendar_evidence_id=rule_id if calendar_id else None,
        )


def test_business_calendar_evidence_and_exact_result_are_retained():
    data = obligation(
        deadline_rule=parameters(), rule_evidence_id=uuid4(), calendar_evidence_id=uuid4()
    )
    assert data.deadline == date(2026, 7, 6)
    saved = data.model_dump(mode="json")
    assert saved["deadline_rule"]["day_count_basis"] == "business"
    assert saved["calendar_evidence_id"]
    changed = deepcopy(saved)
    changed["deadline"] = "2026-07-01"
    with pytest.raises(ValueError, match="differs"):
        Obligation.model_validate(changed)


@pytest.mark.parametrize(
    "policy,trigger,days,expected",
    [
        ("include_if_working", "2026-06-26", 1, "2026-06-26"),
        ("exclude", "2026-06-26", 1, "2026-06-30"),
        ("include_if_working", "2026-06-27", 1, "2026-06-30"),
        ("include_if_working", "2026-06-29", 1, "2026-06-30"),
    ],
)
def test_business_trigger_treatment_is_explicit(policy, trigger, days, expected):
    assert (
        calculate(
            DeadlineRule.model_validate(
                parameters(trigger=trigger, days_after=days, business_trigger_policy=policy)
            )
        ).isoformat()
        == expected
    )


def test_business_trigger_policy_cannot_be_omitted():
    data = parameters()
    data.pop("business_trigger_policy")
    with pytest.raises(ValueError):
        DeadlineRule.model_validate(data)


@pytest.mark.parametrize(
    "change",
    [
        {"trigger": 1782432000},
        {"trigger": "2026-06-26T00:00:00Z"},
        {"days_after": True},
        {"days_after": "5"},
        {"days_after": 5.0},
    ],
)
def test_business_event_and_offset_do_not_coerce_timestamps_or_numeric_strings(change):
    with pytest.raises(ValueError):
        DeadlineRule.model_validate(parameters(**change))


@pytest.mark.parametrize(
    "change",
    [
        {"coverage_start": 1780272000},
        {"coverage_end": "2026-07-31T00:00:00Z"},
        {"holidays": [1782691200]},
    ],
)
def test_calendar_dates_do_not_infer_timezones_or_numeric_dates(change):
    data = parameters()
    data["business_calendar"].update(change)
    with pytest.raises(ValueError):
        DeadlineRule.model_validate(data)


@pytest.mark.parametrize(
    "trigger,holiday,expected",
    [
        ("2026-12-31", "2027-01-01", "2027-01-08"),
        ("2028-02-25", None, "2028-03-03"),
    ],
)
def test_business_count_crosses_year_end_and_leap_day_without_calendar_addition(
    trigger, holiday, expected
):
    data = parameters(trigger=trigger)
    data["business_calendar"].update(
        coverage_start=trigger,
        coverage_end=expected,
        holidays=[holiday] if holiday else [],
        independent_holiday_count=1 if holiday else 0,
    )
    assert calculate(DeadlineRule.model_validate(data)).isoformat() == expected


@pytest.mark.parametrize("stage", ["approved_for_submission", "submitted", "acknowledged"])
async def test_approved_filing_calendar_cannot_be_replaced_without_preparing(monkeypatch, stage):
    from app.modules.grc import filing

    reviewer, rid = uuid4(), uuid4()
    original = obligation(
        deadline_rule=parameters(),
        rule_evidence_id=uuid4(),
        calendar_evidence_id=uuid4(),
        entity_facts={"event": "2026-06-26"},
        fact_evidence_ids=[uuid4()],
        reviewer_id=reviewer,
        readiness_evidence_ids=[uuid4()],
        filing_stage=stage,
        submission_evidence_id=uuid4() if stage != "approved_for_submission" else None,
        acknowledgment_evidence_id=uuid4() if stage == "acknowledged" else None,
    )
    previous = SimpleNamespace(body=original.model_dump(mode="json"), status="REVISED")

    async def record(*args):
        return previous if args[3] == rid else SimpleNamespace(kind="evidence")

    monkeypatch.setattr(filing.audit, "get_record", record)
    monkeypatch.setattr(filing, "engagement_permissions", AsyncMock())
    changed = original.model_dump(mode="json")
    changed["calendar_evidence_id"] = str(uuid4())
    ctx, eng = SimpleNamespace(user_id=reviewer, tenant_id=uuid4()), SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException, match="Approved filing inputs changed"):
        await filing.validate_transition(None, ctx, eng, Obligation.model_validate(changed), rid)
    changed["filing_stage"] = "preparing"
    await filing.validate_transition(None, ctx, eng, Obligation.model_validate(changed), rid)


async def test_derived_workpaper_cannot_be_original_business_calendar(monkeypatch):
    from app.modules.grc import service

    data = obligation(
        deadline_rule=parameters(), rule_evidence_id=uuid4(), calendar_evidence_id=uuid4()
    )
    monkeypatch.setattr(service, "owner_scoped", AsyncMock(return_value=False))
    monkeypatch.setattr(
        service, "evidence", AsyncMock(return_value=SimpleNamespace(kind="working-paper"))
    )
    with pytest.raises(HTTPException, match="original retained evidence"):
        await service.validate_body(
            None, SimpleNamespace(), SimpleNamespace(id=uuid4()), "grc-obligation", data
        )
