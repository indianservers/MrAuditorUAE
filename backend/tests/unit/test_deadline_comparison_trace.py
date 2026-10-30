"""Deadline derivations explain saved inputs without rewriting or qualifying them."""

from copy import deepcopy

import pytest

from app.modules.grc.deadlines import calculate, comparison_trace
from tests.unit.test_deadline_comparisons import first_period
from tests.unit.test_final_foundations import rule


def test_trace_retains_each_calculated_date_selected_trigger_and_evidence_reference():
    data = first_period()
    body = {
        "deadline_rule": data.model_dump(mode="json"),
        "deadline": calculate(data).isoformat(),
        "rule_evidence_id": "SYN-RULE",
        "fact_evidence_ids": ["SYN-INCORPORATION", "SYN-PERIOD"],
    }
    original = deepcopy(body)
    trace = comparison_trace(body)
    assert body == original
    assert trace["state"] == "CONSISTENT_WITH_SAVED_RULE" and not trace["issues"]
    assert trace["selected_before_rolling"] == trace["calculated_deadline"] == "2028-06-30"
    assert [(r["unadjusted_date"], r["selected"]) for r in trace["candidates"]] == [
        ("2028-03-31", False),
        ("2028-06-30", True),
    ]
    assert trace["rule_evidence_id"] == "SYN-RULE"
    assert trace["fact_evidence_ids"] == ["SYN-INCORPORATION", "SYN-PERIOD"]


def test_tied_candidates_and_final_rolling_stay_separate_from_authority_extensions():
    data = rule(
        convention="following",
        weekend_days=[5, 6],
        later_of=[
            {
                "identifier": "SYN-other",
                "date_basis": "specified_event",
                "trigger": "2026-02-27",
                "days_after": 1,
            }
        ],
    )
    body = {
        "deadline_rule": data.model_dump(mode="json"),
        "deadline": "2026-03-02",
        "extension_deadline": "2026-04-01",
    }
    trace = comparison_trace(body)
    assert all(c["selected"] for c in trace["candidates"])
    assert trace["selected_before_rolling"] == "2026-02-28"
    assert trace["calculated_deadline"] == trace["saved_deadline"] == "2026-03-02"
    assert trace["convention"] == "following" and trace["extension_included"] is False
    assert body["extension_deadline"] == "2026-04-01"


@pytest.mark.parametrize("saved", [None, "2028-06-29", "2028-06-30T00:00:00"])
def test_a_missing_or_different_saved_deadline_requires_reassessment_without_repair(saved):
    body = {"deadline_rule": first_period().model_dump(mode="json"), "deadline": saved}
    original = deepcopy(body)
    trace = comparison_trace(body)
    assert body == original
    assert trace["state"] == "REASSESSMENT_REQUIRED"
    assert trace["issues"] == ["SAVED_DEADLINE_DIFFERS_FROM_RETAINED_RULE"]
    assert trace["saved_deadline"] == saved and trace["calculated_deadline"] == "2028-06-30"


@pytest.mark.parametrize("candidates", [["malformed"], [{"identifier": "missing-date"}], "bad", 1])
def test_invalid_retained_candidates_require_reassessment(candidates):
    body = {"deadline_rule": {**first_period().model_dump(mode="json"), "later_of": candidates}}
    assert comparison_trace(body) == {
        "contract": "retained-deadline-comparison/1",
        "state": "REASSESSMENT_REQUIRED",
        "issues": ["RETAINED_DEADLINE_COMPARISON_INVALID"],
    }


def test_ordinary_legacy_deadlines_receive_no_invented_comparison():
    assert comparison_trace({}) is None
    assert comparison_trace({"deadline_rule": rule().model_dump(mode="json")}) is None


@pytest.mark.parametrize("malformed", [None, 1, "not-a-population"])
def test_period_guard_does_not_crash_on_malformed_retained_comparison_population(malformed):
    from app.modules.grc.deadlines import missing_obligation_period

    body = {
        "jurisdiction_scope": {"applicability": "assessed_applicable"},
        "deadline_rule": {"date_basis": "period_end", "later_of": malformed},
    }
    assert missing_obligation_period(body)
