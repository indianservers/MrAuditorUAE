from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.ifrs.schemas import Consolidation


def payload():
    members = [
        {
            "engagement_id": str(uuid4()),
            "financial_run_id": str(uuid4()),
            "ownership": "1",
            "power": True,
            "variable_returns": True,
            "ability_to_affect_returns": True,
            "control_rationale": "Synthetic complete-period control assessment",
            "closing_rate": "1",
            "average_rate": "1",
            "historical_rate": "1",
            "rate_source": "Synthetic same-currency source",
            "rate_date": "2026-12-31",
            "acquisition_type": kind,
            "accounting_policy": "Synthetic reviewed accounting policy",
        }
        for kind in ["parent", "business_combination"]
    ]
    return {
        "presentation_currency": "AED",
        "members": members,
        "intercompany_nil_assessment": {
            "member_engagement_ids": [m["engagement_id"] for m in members],
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "rationale": "Synthetic complete reciprocal population independently assessed as nil",
            "source_record_ids": [str(uuid4()), str(uuid4())],
        },
    }


def test_explicit_nil_is_preserved_and_missing_is_not_nil():
    body = payload()
    assert Consolidation.model_validate(body).intercompany_nil_assessment is not None
    del body["intercompany_nil_assessment"]
    assert Consolidation.model_validate(body).intercompany_nil_assessment is None


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_member",
        "different_member",
        "duplicate_source",
        "blank",
        "reversed",
        "elimination",
        "unrealised",
        "pair",
    ],
)
def test_invalid_or_contradictory_nil_assessments(case):
    body = deepcopy(payload())
    nil = body["intercompany_nil_assessment"]
    if case == "duplicate_member":
        nil["member_engagement_ids"][1] = nil["member_engagement_ids"][0]
    elif case == "different_member":
        nil["member_engagement_ids"][1] = str(uuid4())
    elif case == "duplicate_source":
        nil["source_record_ids"][1] = nil["source_record_ids"][0]
    elif case == "blank":
        nil["rationale"] = " " * 20
    elif case == "reversed":
        nil["period_end"] = "2025-12-31"
    elif case == "elimination":
        body["eliminations"] = [
            {
                "reference": "IC1",
                "debit_line": "200",
                "credit_line": "100",
                "amount": "1",
                "reason": "Synthetic elimination",
                "source_record_ids": [str(uuid4())],
            }
        ]
    elif case == "unrealised":
        body["unrealised_profit"] = "1"
    else:
        body["intercompany"] = [
            {
                "reference": "IC1",
                "from_engagement_id": body["members"][0]["engagement_id"],
                "to_engagement_id": body["members"][1]["engagement_id"],
                "debit_line": "200",
                "credit_line": "100",
                "receivable": "0",
                "payable": "0",
                "currency": "AED",
                "difference_type": "matched",
                "evidence": "Synthetic zero pair is still a declared population",
            }
        ]
    with pytest.raises(ValidationError):
        Consolidation.model_validate(body)
