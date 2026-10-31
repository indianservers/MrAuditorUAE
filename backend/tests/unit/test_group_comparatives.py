from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.ifrs.group_comparatives import apply


def examples():
    previous = {
        "currency": "AED",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "members": [
            {
                "entity_id": "parent",
                "ownership": "1",
                "acquisition_type": "parent",
                "engagement_id": "prior-parent",
            },
            {
                "entity_id": "subsidiary",
                "ownership": "0.8",
                "acquisition_type": "business_combination",
                "engagement_id": "prior-sub",
            },
        ],
        "lines": [
            {
                "line_code": "cash",
                "section": "assets",
                "category": "operating",
                "current": "80",
                "source_accounts": [{"source_amount": "40", "rate": "2", "translated": "80"}],
            },
            {
                "line_code": "ppe",
                "section": "assets",
                "category": "operating",
                "current": "20",
                "source_accounts": [{"source_amount": "20", "rate": "1", "translated": "20"}],
            },
            {
                "line_code": "equity",
                "section": "equity",
                "category": "operating",
                "current": "-100",
                "source_accounts": [],
            },
        ],
    }
    current = deepcopy(previous)
    current.update(period_start="2026-01-01", period_end="2026-12-31")
    current["members"][0]["engagement_id"] = "current-parent"
    current["members"][1]["engagement_id"] = "current-sub"
    current["lines"] = [
        {
            "line_code": "cash",
            "section": "assets",
            "category": "operating",
            "current": "250",
            "source_accounts": [{"source_amount": "50", "rate": "5", "translated": "250"}],
        },
        {
            "line_code": "equity",
            "section": "equity",
            "category": "operating",
            "current": "-200",
            "source_accounts": [],
        },
        {
            "line_code": "income",
            "section": "income",
            "category": "operating",
            "current": "-50",
            "source_accounts": [],
        },
    ]
    return current, previous


def test_complete_prior_chart_keeps_prior_only_lines_and_original_translation():
    current, previous = examples()
    before_current, before_previous = deepcopy(current), deepcopy(previous)
    rows = {row["line_code"]: row for row in apply(current, previous)}
    assert rows["cash"]["comparative"] == 80
    assert rows["cash"]["current"] == "250"
    assert rows["cash"]["comparative_source_accounts"] == previous["lines"][0]["source_accounts"]
    assert rows["ppe"]["comparative"] == 20
    assert rows["ppe"]["current"] == 0
    assert rows["ppe"]["comparative_presence"] == "PRIOR_ONLY_LINE_RETAINED"
    assert rows["income"]["comparative"] == 0
    assert rows["income"]["comparative_presence"] == "ABSENT_FROM_COMPLETE_PRIOR_CHART"
    assert sum(Decimal(str(row["current"])) for row in rows.values()) == 0
    assert sum(row["comparative"] for row in rows.values()) == 0
    assert current == before_current and previous == before_previous
    rows["cash"]["comparative_source_accounts"][0]["rate"] = "changed"
    assert previous == before_previous


@pytest.mark.parametrize(
    "case",
    [
        "currency",
        "gap",
        "overlap",
        "reversed",
        "missing_identity",
        "duplicate_entity",
        "ownership",
        "member",
        "classification",
        "category",
        "current_duplicate",
        "prior_duplicate",
    ],
)
def test_incompatible_sources_are_not_silently_reclassified_or_retranslated(case):
    current, previous = examples()
    if case == "currency":
        previous["currency"] = "INR"
    elif case == "gap":
        previous["period_end"] = "2025-11-30"
    elif case == "overlap":
        previous["period_end"] = "2026-01-01"
    elif case == "reversed":
        previous["period_start"] = "2026-01-01"
    elif case == "missing_identity":
        del previous["members"][0]["entity_id"]
    elif case == "duplicate_entity":
        previous["members"][1]["entity_id"] = "parent"
    elif case == "ownership":
        previous["members"][1]["ownership"] = "0.7"
    elif case == "member":
        previous["members"][1]["entity_id"] = "another-company"
    elif case == "classification":
        previous["lines"][0]["section"] = "liabilities"
    elif case == "category":
        previous["lines"][0]["category"] = "financing"
    elif case == "current_duplicate":
        current["lines"].append(deepcopy(current["lines"][0]))
    else:
        previous["lines"].append(deepcopy(previous["lines"][0]))
    with pytest.raises(ValueError):
        apply(current, previous)
