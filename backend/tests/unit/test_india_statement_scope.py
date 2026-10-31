"""Statement selection and retained comparative provenance regressions."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.regulatory.india_reporting import (
    aggregate,
    presentation_rows,
    require_reporting_selection,
)


@pytest.mark.parametrize(
    "division,framework,nbfc", [("I", "AS", None), ("II", "Ind AS", False), ("III", "Ind AS", True)]
)
def test_consistent_reviewed_scope(division, framework, nbfc):
    facts = {"schedule_iii_division": division}
    if nbfc is not None:
        facts["nbfc"] = nbfc
    require_reporting_selection([{"facts": facts}], division, framework)


@pytest.mark.parametrize(
    "items,division,framework",
    [
        ([], "II", "Ind AS"),
        ([{"facts": {"schedule_iii_division": "II"}}], "II", "Ind AS"),
        ([{"facts": {"schedule_iii_division": "III", "nbfc": False}}], "III", "Ind AS"),
        ([{"facts": {"schedule_iii_division": "II", "nbfc": True}}], "II", "Ind AS"),
        ([{"facts": {"schedule_iii_division": "II", "nbfc": "false"}}], "II", "Ind AS"),
        ([{"facts": {"schedule_iii_division": "II", "nbfc": 0}}], "II", "Ind AS"),
        (
            [
                {"facts": {"schedule_iii_division": "II", "nbfc": False}},
                {"facts": {"schedule_iii_division": "III", "nbfc": True}},
            ],
            "II",
            "Ind AS",
        ),
        (
            [{"facts": {"schedule_iii_division": "II", "nbfc": False}}, {"facts": {"nbfc": True}}],
            "II",
            "Ind AS",
        ),
        ([{"facts": {"schedule_iii_division": "I"}}], "I", "Ind AS"),
        ([{"facts": {"schedule_iii_division": "III", "nbfc": True}}], "III", "AS"),
    ],
)
def test_missing_wrong_or_conflicting_scope_is_rejected(items, division, framework):
    with pytest.raises(HTTPException):
        require_reporting_selection(items, division, framework)


def line(code, classification, amount):
    return {
        "id": code,
        "code": code,
        "name": "SYNTHETIC " + code,
        "classification": classification,
        "closing": Decimal(amount),
    }


def test_prior_only_account_retains_prior_source_and_current_absence():
    current = [
        line("CASH", "Assets", "120"),
        line("CAPITAL", "Equity", "-100"),
        line("SALE", "Income", "-20"),
    ]
    prior = {
        row["code"]: row
        for row in [line("OLD-CASH", "Assets", "80"), line("CAPITAL", "Equity", "-80")]
    }
    mapping = {
        r["code"]: {"classification": r["classification"], "statement_group": r["classification"]}
        for r in [*current, *prior.values()]
    }
    rows = presentation_rows(current, prior, mapping, {}, "CURRENT", "PRIOR")
    old = next(r for r in rows if r["account_code"] == "OLD-CASH")
    assert old["source_snapshot_id"] is None
    assert old["current_account_in_source"] is False
    assert old["comparative_source_snapshot_id"] == "PRIOR"
    assert old["presented_amount"] == "0" and old["comparative_amount"] == "80"
    cash = next(r for r in rows if r["account_code"] == "CASH")
    assert cash["comparative_source_snapshot_id"] is None
    assert cash["comparative_amount"] is None
    assert cash["comparative_account_in_source"] is False
    assert aggregate(rows)[1:] == (Decimal("20"), Decimal("0"))
    assert aggregate(
        [
            {**r, "presented_amount": r["comparative_amount"]}
            for r in rows
            if r["comparative_account_in_source"]
        ]
    )[1:] == (Decimal(0), Decimal(0))


@pytest.mark.parametrize(
    "failure",
    [
        "unmapped-prior",
        "blank-group",
        "unrecognized-classification",
        "changed-comparative-classification",
    ],
)
def test_comparative_accounts_cannot_disappear_or_silently_change_classification(failure):
    current = [line("A", "Assets", "100")]
    prior = {"B": line("B", "Equity", "-100")}
    mapping = {
        "A": {"classification": "Assets", "statement_group": "Cash"},
        "B": {"classification": "Equity", "statement_group": "Equity"},
    }
    if failure == "unmapped-prior":
        mapping.pop("B")
    elif failure == "blank-group":
        mapping["B"]["statement_group"] = "   "
    elif failure == "unrecognized-classification":
        current[0]["classification"] = "Unclassified"
        mapping["A"]["classification"] = "Unclassified"
    else:
        prior = {"A": line("A", "Equity", "-100")}
    with pytest.raises(HTTPException):
        presentation_rows(current, prior, mapping, {}, "CURRENT", "PRIOR")


@pytest.mark.parametrize("failure", ["unbalanced", "currency"])
async def test_statement_service_rejects_invalid_comparative_before_append(monkeypatch, failure):
    from app.modules.regulatory import india_reporting as reporting

    profile = SimpleNamespace(
        id="MAP",
        version=1,
        mapping={
            "accounts": {
                "A": {"classification": "Assets", "statement_group": "Cash"},
                "B": {"classification": "Equity", "statement_group": "Capital"},
            }
        },
    )
    db = SimpleNamespace(scalar=AsyncMock(return_value=profile))
    ctx = SimpleNamespace(tenant_id="T", user_id="U")
    eng = SimpleNamespace(entity_id="E", period_id="P", id="ENG")
    data = SimpleNamespace(
        division="II",
        applicability_id="CASE",
        mapping_profile_id="MAP",
        snapshot_id="CURRENT",
        comparative_snapshot_id="PRIOR",
    )
    monkeypatch.setattr(
        reporting,
        "resolved",
        AsyncMock(return_value=(SimpleNamespace(country="IN"), {"framework": "Ind AS"})),
    )
    applicability = SimpleNamespace(
        kind="statutory-checklist",
        body={
            "area": "india-disclosures",
            "review_status": "REVIEWED",
            "items": [{"facts": {"schedule_iii_division": "II", "nbfc": False}}],
        },
    )
    monkeypatch.setattr(reporting.intelligence, "event", AsyncMock(return_value=applicability))
    monkeypatch.setattr(reporting.intelligence, "event_receipt", lambda _: {})
    monkeypatch.setattr(reporting, "mapping_receipt", AsyncMock(return_value={}))
    monkeypatch.setattr(
        reporting.intelligence,
        "snapshot",
        AsyncMock(
            side_effect=[(SimpleNamespace(id="CURRENT"), {}), (SimpleNamespace(id="PRIOR"), {})]
        ),
    )
    monkeypatch.setattr(
        reporting,
        "balance",
        AsyncMock(
            side_effect=[
                {
                    "balanced": True,
                    "functional_currency": "INR",
                    "lines": [line("A", "Assets", "100"), line("B", "Equity", "-100")],
                },
                {
                    "balanced": failure != "unbalanced",
                    "functional_currency": "USD" if failure == "currency" else "INR",
                    "lines": [],
                },
            ]
        ),
    )
    append = AsyncMock()
    monkeypatch.setattr(reporting.intelligence, "append", append)
    with pytest.raises(HTTPException, match="Comparative trial balance"):
        await reporting.statements(db, ctx, eng, data, "REQUEST")
    append.assert_not_awaited()


async def test_legacy_statement_draft_is_stale_after_new_scope_contract():
    from app.modules.intelligence.service import current

    result = SimpleNamespace(
        tenant_id="T", kind="india-financial-statements", body={"review_status": "REVIEWED"}
    )
    assert await current(None, SimpleNamespace(tenant_id="T"), result) is False
