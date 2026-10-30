"""Retained multiple-trigger calculations; applicability remains independently assessed."""

from datetime import date
from uuid import uuid4

import pytest

from app.modules.grc.deadlines import DeadlineRule, calculate, missing_obligation_period
from app.modules.grc.schemas import Obligation
from tests.unit.test_business_day_deadlines import parameters
from tests.unit.test_dmcc_audit import payload as dmcc_payload
from tests.unit.test_final_foundations import rule


def first_period(**changes):
    return rule(
        identifier="SYN-period-end-plus-three-months",
        trigger="2027-12-31",
        date_basis="period_end",
        months_after=3,
        later_of=[
            {
                "identifier": "SYN-first-anniversary-plus-nine-months",
                "trigger": "2027-09-30",
                "date_basis": "specified_event",
                "months_after": 9,
            }
        ],
        **changes,
    )


def test_adgm_published_long_first_period_dates_choose_later_candidate():
    # Retained guidance v2, page 35 example 11; date arithmetic only, not entity qualification.
    assert calculate(first_period()) == date(2028, 6, 30)


def test_period_end_can_win_and_reordering_does_not_change_result():
    a = rule(
        trigger="2027-01-01",
        months_after=6,
        later_of=[
            {
                "identifier": "SYN-period-end",
                "trigger": "2027-06-30",
                "date_basis": "period_end",
                "months_after": 3,
            }
        ],
    )
    b = rule(
        trigger="2027-06-30",
        months_after=3,
        later_of=[
            {
                "identifier": "SYN-anniversary",
                "trigger": "2027-01-01",
                "date_basis": "specified_event",
                "months_after": 6,
            }
        ],
    )
    assert calculate(a) == calculate(b) == date(2027, 9, 30)


def test_shortened_period_receipt_can_determine_deadline_and_ties_are_allowed():
    a = rule(
        trigger="2026-12-31",
        months_after=9,
        later_of=[
            {
                "identifier": "SYN-notice-receipt",
                "trigger": "2027-08-10",
                "date_basis": "specified_event",
                "months_after": 3,
            }
        ],
    )
    assert calculate(a) == date(2027, 11, 10)
    a.later_of[0].trigger = date(2027, 6, 30)
    assert calculate(a) == date(2027, 9, 30)


def test_offsets_are_separate_and_final_rolling_applies_after_selection():
    data = rule(
        trigger="2026-01-31",
        months_after=1,
        convention="preceding",
        weekend_days=[5, 6],
        holidays=["2026-02-27"],
        later_of=[
            {
                "identifier": "SYN-other",
                "trigger": "2026-02-26",
                "date_basis": "specified_event",
                "days_after": 1,
            }
        ],
    )
    assert calculate(data) == date(2026, 2, 26)
    assert data.model_dump(mode="json")["later_of"][0]["trigger"] == "2026-02-26"


@pytest.mark.parametrize(
    "change",
    [
        {"identifier": "SYNTHETIC-policy"},
        {"identifier": " "},
        {"trigger": "2025-12-31"},
        {"trigger": "2026-06-30T00:00:00"},
        {"trigger": 1782777600},
        {"months_after": True},
        {"months_after": "3"},
        {"days_after": -1},
        {"trigger": "9999-12-31", "months_after": 1},
    ],
)
def test_invalid_or_unadopted_comparison_inputs_fail_before_calculation(change):
    candidate = {
        "identifier": "SYN-candidate",
        "trigger": "2026-06-30",
        "date_basis": "specified_event",
        "months_after": 3,
        **change,
    }
    with pytest.raises(ValueError):
        rule(later_of=[candidate])


def test_duplicate_candidates_and_business_count_mixing_are_rejected():
    candidate = {
        "identifier": "SYN-other",
        "trigger": "2026-06-30",
        "date_basis": "specified_event",
        "months_after": 3,
    }
    with pytest.raises(ValueError, match="distinct"):
        rule(later_of=[candidate, candidate])
    with pytest.raises(ValueError, match="calendar offsets"):
        DeadlineRule.model_validate(parameters(later_of=[candidate]))
    with pytest.raises(ValueError):
        rule(effective_to="2026-06-01", later_of=[candidate])


def test_legacy_rule_serialization_does_not_add_empty_comparison_fields():
    assert "later_of" not in rule().model_dump(mode="json")
    with pytest.raises(ValueError, match="calendar date range"):
        rule(trigger="9999-12-31", months_after=1)


@pytest.mark.parametrize(
    "changes",
    [
        {"trigger": "2026-01-31T00:00:00"},
        {"trigger": 1769817600},
        {"months_after": "1"},
        {"days_after": True},
    ],
)
def test_primary_comparison_trigger_and_offsets_are_also_explicit(changes):
    with pytest.raises(ValueError):
        rule(
            later_of=[
                {
                    "identifier": "SYN-other",
                    "trigger": "2026-06-30",
                    "date_basis": "specified_event",
                    "months_after": 3,
                }
            ],
            **changes,
        )


def test_comparison_population_is_bounded():
    with pytest.raises(ValueError):
        rule(
            later_of=[
                {
                    "identifier": f"SYN-{n}",
                    "trigger": "2026-06-30",
                    "date_basis": "specified_event",
                    "months_after": 3,
                }
                for n in range(9)
            ]
        )


def test_comparator_period_end_requires_explicit_country_period():
    from tests.unit.test_final_foundations import obligation

    data = obligation(
        deadline_rule=rule(
            trigger="2026-06-01",
            later_of=[
                {
                    "identifier": "SYN-period",
                    "trigger": "2026-06-30",
                    "date_basis": "period_end",
                    "months_after": 3,
                }
            ],
        ),
        rule_evidence_id=uuid4(),
    ).model_dump(mode="json")
    data.update(
        jurisdiction="AE",
        jurisdiction_scope={
            "entity_country": "AE",
            "obligation_country": "AE",
            "relationship": "domestic",
            "applicability": "assessed_applicable",
            "assessment": "SYNTHETIC complete country facts",
        },
        fact_evidence_ids=[str(uuid4())],
        entity_facts={"notice": "SYNTHETIC"},
    )
    assert missing_obligation_period(data)
    with pytest.raises(ValueError, match="explicit obligation period"):
        Obligation.model_validate(data)
    data.update(obligation_period_start="2026-01-01", obligation_period_end="2026-06-30")
    assert not missing_obligation_period(data)
    assert Obligation.model_validate(data).deadline == date(2026, 9, 30)


def test_comparisons_cannot_override_the_adopted_dmcc_profile():
    data = dmcc_payload()
    data["deadline_rule"]["later_of"] = [
        {
            "identifier": "SYN-unsupported-extension",
            "trigger": "2025-12-31",
            "date_basis": "period_end",
            "months_after": 12,
        }
    ]
    with pytest.raises(ValueError, match="DMCC timetable"):
        Obligation.model_validate(data)
