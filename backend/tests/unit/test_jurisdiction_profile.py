from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.jurisdictions.profiles import ApplicabilityDecision, profile, resolve_rules


@pytest.mark.parametrize(
    "as_of,applies,expected",
    [
        ("2026-06-01", True, "REVIEWED_APPLICABLE"),
        ("2026-06-01", False, "REVIEWED_NOT_APPLICABLE"),
        ("2025-12-31", True, "OUTSIDE_EFFECTIVE_PERIOD"),
        ("2027-01-01", True, "OUTSIDE_EFFECTIVE_PERIOD"),
    ],
)
def test_effective_dated_professional_decision(as_of, applies, expected):
    config = profile("IN")
    decision = ApplicabilityDecision(
        rule_id=config.rules[0].id,
        applies=applies,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        source_ids=["gst"],
        rationale="Synthetic professional applicability review",
    )
    assert (
        resolve_rules(config, date.fromisoformat(as_of), "company", [decision])[0]["status"]
        == expected
    )


def test_unknown_effectivity_is_not_inferred_and_invalid_dates_rejected():
    assert (
        resolve_rules(profile("IN"), date(2026, 1, 1), "company")[0]["status"]
        == "REQUIRES_PROFESSIONAL_REVIEW"
    )
    with pytest.raises(ValidationError):
        ApplicabilityDecision(
            rule_id="IN-0",
            applies=True,
            effective_from=date(2026, 12, 31),
            effective_to=date(2026, 1, 1),
            source_ids=["gst"],
            rationale="Synthetic invalid period test",
        )
