"""Explicit month-end policy, with legacy corresponding-day behavior preserved."""

from copy import deepcopy
from datetime import date

import pytest

from app.modules.grc.deadlines import DeadlineRule, calculate, comparison_trace
from app.modules.grc.schemas import Obligation
from tests.unit.test_business_day_deadlines import parameters
from tests.unit.test_dmcc_audit import payload
from tests.unit.test_final_foundations import rule


@pytest.mark.parametrize(
    "trigger,months,expected,legacy",
    [
        ("2026-06-30", 9, "2027-03-31", "2027-03-30"),
        ("2026-02-28", 9, "2026-11-30", "2026-11-28"),
        ("2024-02-29", 1, "2024-03-31", "2024-03-29"),
        ("2026-04-30", 1, "2026-05-31", "2026-05-30"),
        ("2026-06-29", 8, "2027-02-28", "2027-02-28"),
        ("2026-01-30", 1, "2026-02-28", "2026-02-28"),
        ("2026-05-31", 1, "2026-06-30", "2026-06-30"),
    ],
)
def test_month_end_preservation_is_explicit_and_different_from_legacy_clamping(
    trigger, months, expected, legacy
):
    supplied = {"trigger": trigger, "months_after": months, "effective_from": "2024-01-01"}
    assert calculate(rule(**supplied, month_end_policy="preserve_month_end")) == date.fromisoformat(
        expected
    )
    assert calculate(rule(**supplied)) == date.fromisoformat(legacy)


def test_day_offsets_follow_month_end_selection_and_zero_months_keep_the_original_date():
    assert calculate(
        rule(
            trigger="2026-04-30",
            months_after=1,
            days_after=2,
            month_end_policy="preserve_month_end",
        )
    ) == date(2026, 6, 2)
    assert calculate(
        rule(
            trigger="2026-04-30",
            months_after=0,
            days_after=1,
            month_end_policy="preserve_month_end",
        )
    ) == date(2026, 5, 1)


def test_comparison_trace_retains_month_policy_and_every_tied_or_winning_date():
    values = {
        "trigger": "2026-06-30",
        "months_after": 1,
        "later_of": [
            {
                "identifier": "SYN-other",
                "trigger": "2026-07-30",
                "date_basis": "specified_event",
            }
        ],
    }
    old = rule(**values)
    new = rule(**values, month_end_policy="preserve_month_end")
    old_body = {"deadline_rule": old.model_dump(mode="json"), "deadline": "2026-07-30"}
    new_body = {"deadline_rule": new.model_dump(mode="json"), "deadline": "2026-07-31"}
    original = deepcopy(new_body)
    before, after = comparison_trace(old_body), comparison_trace(new_body)
    assert all(c["selected"] for c in before["candidates"])
    assert after["month_end_policy"] == "preserve_month_end"
    assert [(c["unadjusted_date"], c["selected"]) for c in after["candidates"]] == [
        ("2026-07-31", True),
        ("2026-07-30", False),
    ]
    assert new_body == original
    new_body["deadline"] = "2026-07-30"
    assert comparison_trace(new_body)["state"] == "REASSESSMENT_REQUIRED"


def test_old_serialization_and_the_fixed_dmcc_profile_do_not_silently_change():
    assert "month_end_policy" not in rule().model_dump(mode="json")
    assert (
        rule(month_end_policy="preserve_month_end").model_dump(mode="json")["month_end_policy"]
        == "preserve_month_end"
    )
    body = payload()
    body["deadline_rule"]["month_end_policy"] = "preserve_month_end"
    with pytest.raises(ValueError, match="DMCC profile"):
        Obligation.model_validate(body)


@pytest.mark.parametrize("policy", ["last-day", True, None])
def test_unknown_policies_are_rejected(policy):
    with pytest.raises(ValueError):
        rule(month_end_policy=policy)


def test_business_day_counting_cannot_carry_an_ignored_month_policy():
    with pytest.raises(ValueError, match="Business-day counting"):
        DeadlineRule.model_validate(parameters(month_end_policy="preserve_month_end"))
