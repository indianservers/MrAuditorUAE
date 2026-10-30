"""Month/day offsets roll only inside explicitly retained calendar coverage."""

from datetime import date
from uuid import uuid4

import pytest

from app.modules.grc.deadlines import DeadlineRule, calculate, comparison_trace
from tests.unit.test_business_day_deadlines import parameters
from tests.unit.test_final_foundations import obligation, rule


def rolling(**changes):
    return {
        "coverage_start": "2026-06-01",
        "coverage_end": "2026-07-31",
        "weekend_days": [5, 6],
        "holidays": ["2026-07-01", "2026-07-02"],
        "independent_holiday_count": 2,
        "assessment": "SYNTHETIC independently assessed complete calendar, not a national holiday assertion",
        **changes,
    }


@pytest.mark.parametrize(
    ("trigger", "convention", "start", "end"),
    [
        ("9999-12-31", "following", "9999-12-01", "9999-12-31"),
        ("0001-01-01", "preceding", "0001-01-01", "0001-01-31"),
    ],
)
def test_rolling_beyond_supported_dates_is_a_validation_error(trigger, convention, start, end):
    with pytest.raises(ValueError, match="Calendar adjustment exceeds"):
        rule(
            effective_from="0001-01-01",
            trigger=trigger,
            months_after=0,
            convention=convention,
            rolling_calendar=rolling(
                coverage_start=start,
                coverage_end=end,
                holidays=[trigger],
                independent_holiday_count=1,
            ),
        )


def test_calendar_offsets_then_following_differs_from_counting_business_days():
    data = rule(
        trigger="2026-06-26",
        months_after=0,
        days_after=5,
        convention="following",
        rolling_calendar=rolling(),
    )
    assert calculate(data) == date(2026, 7, 3)
    assert calculate(DeadlineRule.model_validate(parameters(business_calendar=rolling()))) == date(
        2026, 7, 7
    )


def test_preceding_uses_the_same_explicit_coverage_and_holiday_controls():
    data = rule(
        trigger="2026-06-26",
        months_after=0,
        days_after=5,
        convention="preceding",
        rolling_calendar=rolling(),
    )
    assert calculate(data) == date(2026, 6, 30)


def test_month_end_comparison_rolls_the_selected_date_with_source_reference():
    calendar = rolling(
        coverage_start="2027-03-31",
        coverage_end="2027-04-30",
        holidays=["2027-03-31"],
        independent_holiday_count=1,
    )
    data = rule(
        trigger="2026-06-01",
        months_after=1,
        convention="following",
        month_end_policy="preserve_month_end",
        rolling_calendar=calendar,
        later_of=[
            {
                "identifier": "SYN-period",
                "trigger": "2026-06-30",
                "date_basis": "period_end",
                "months_after": 9,
            }
        ],
    )
    assert calculate(data) == date(2027, 4, 1)
    body = {
        "deadline_rule": data.model_dump(mode="json"),
        "deadline": "2027-04-01",
        "calendar_evidence_id": "SYN-CALENDAR",
    }
    trace = comparison_trace(body)
    assert trace["selected_before_rolling"] == "2027-03-31"
    assert trace["calculated_deadline"] == "2027-04-01"
    assert trace["calendar_evidence_id"] == "SYN-CALENDAR"
    assert trace["rolling_calendar_coverage"] == {
        "from": "2027-03-31",
        "through": "2027-04-30",
        "independent_holiday_count": 1,
    }


@pytest.mark.parametrize(
    "convention,changes",
    [
        ("following", {"coverage_start": "2026-07-02"}),
        ("following", {"coverage_end": "2026-07-02"}),
        ("preceding", {"coverage_start": "2026-07-01"}),
    ],
)
def test_missing_coverage_never_becomes_an_assumed_working_date(convention, changes):
    # Keep all declared holidays within the shortened coverage so the failure
    # specifically concerns rolling, not invalid calendar source rows.
    values = rolling(holidays=[], independent_holiday_count=0, **changes)
    if convention == "following" and "coverage_end" in changes:
        values.update(holidays=["2026-07-01", "2026-07-02"], independent_holiday_count=2)
    if convention == "preceding":
        values.update(holidays=["2026-07-01"], independent_holiday_count=1)
    with pytest.raises(ValueError, match="Rolling calendar coverage"):
        rule(
            trigger="2026-06-26",
            months_after=0,
            days_after=5,
            convention=convention,
            rolling_calendar=values,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"convention": "calendar"},
        {"weekend_days": [5, 6]},
        {"holidays": ["2026-07-03"]},
        {"trigger": "2026-06-26T00:00:00"},
        {"days_after": True},
        {"months_after": "0"},
    ],
)
def test_ambiguous_or_mixed_rolling_inputs_are_rejected(changes):
    values = {
        "trigger": "2026-06-26",
        "months_after": 0,
        "days_after": 5,
        "convention": "following",
        "rolling_calendar": rolling(),
        **changes,
    }
    with pytest.raises(ValueError):
        rule(**values)


def test_business_counting_cannot_silently_ignore_a_separate_rolling_calendar():
    with pytest.raises(ValueError, match="Business-day counting"):
        DeadlineRule.model_validate(parameters(rolling_calendar=rolling()))


def test_zero_holidays_require_explicit_control_and_legacy_rules_keep_their_bytes():
    no_holidays = rolling(holidays=[], independent_holiday_count=0)
    assert calculate(
        rule(
            trigger="2026-06-26",
            months_after=0,
            days_after=5,
            convention="following",
            rolling_calendar=no_holidays,
        )
    ) == date(2026, 7, 1)
    with pytest.raises(ValueError, match="independent count"):
        rule(convention="following", rolling_calendar=rolling(holidays=[]))
    assert "rolling_calendar" not in rule().model_dump(mode="json")


def test_rolling_calendar_requires_separate_retained_evidence_for_filing():
    data = rule(
        trigger="2026-06-26",
        months_after=0,
        days_after=5,
        convention="following",
        rolling_calendar=rolling(),
    )
    rule_id = uuid4()
    for calendar_id in [None, rule_id]:
        with pytest.raises(ValueError, match="Rolling deadlines require separate"):
            obligation(
                deadline_rule=data, rule_evidence_id=rule_id, calendar_evidence_id=calendar_id
            )
    obj = obligation(deadline_rule=data, rule_evidence_id=rule_id, calendar_evidence_id=uuid4())
    assert obj.deadline == date(2026, 7, 3)
