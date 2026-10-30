"""Withdrawn positive expectations differ from historical settlement and credit evidence."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.withholding_provisions import ISSUE, saved_withdrawn_expectation
from tests.unit.test_withholding_workflows import population, run


def records(when, reference="206C(1H)", amount="100", role="collector"):
    p = population(role)
    start_year = int(when[:4]) - (int(when[5:7]) < 4)
    for rows in p.values():
        for row in rows:
            row.update(
                rule_reference=reference,
                amount=amount,
                transaction_date=when,
                period=when[:7],
                tax_year_start=f"{start_year}-04-01",
                tax_year_end=f"{start_year + 1}-03-31",
            )
            if row.get("assessment_kind"):
                row.update(
                    assessment_period_start=f"{start_year}-04-01",
                    assessment_period_end=f"{start_year + 1}-03-31",
                )
    return p


@pytest.mark.parametrize("when", ["2025-04-01", "2025-04-02", "2026-05-15"])
@pytest.mark.parametrize("reference", ["206C(1H)", " 206c (1h) ", "TCS:206C(1H)"])
def test_positive_post_withdrawal_expectation_blocks_even_when_all_figures_match(when, reference):
    # Source identifiers reject surrounding whitespace. Internal whitespace/case
    # normalization is tested without bypassing the existing exact-text schema.
    reference = reference.strip()
    out = run(records(when, reference), "collector")
    row = out["rows"][0]
    assert out["blocked"] and row["comparison_state"] == "MATCHED"
    assert row["state"] == "WITHDRAWN_PROVISION_LIABILITY"
    assert row["statutory_scope_issues"] == [ISSUE]
    assert (
        out["withholding_provision_scope"]["positive_expectation_unavailable_from"] == "2025-04-01"
    )
    assert row["amounts"] == {
        role: "100" for role in ("expected", "withheld", "reported", "deposited")
    }
    assert "withdrawn period" in approval_error(out)


def test_historical_liability_is_not_rejected_for_later_payment_or_review():
    out = run(records("2025-03-31"), "collector")
    assert not out["blocked"] and out["rows"][0]["state"] == "MATCHED"
    assert out["rows"][0]["statutory_scope_issues"] == []
    assert approval_error(out) is None


def test_zero_expected_does_not_create_a_positive_liability_or_hide_erroneous_collection():
    p = records("2026-05-15", amount="0")
    p["withheld"][0]["amount"] = "100"
    out = run(p, "collector")
    assert out["rows"][0]["state"] == "VARIANCE"
    assert out["rows"][0]["statutory_scope_issues"] == []
    assert out["rows"][0]["amounts"]["expected"] == "0"
    assert out["rows"][0]["differences_from_expected"]["withheld"] == "100"


def test_other_explicit_provision_is_not_reclassified_by_this_narrow_guard():
    out = run(records("2026-05-15", reference="206C(1G)"), "collector")
    assert not out["blocked"]
    assert out["statutory_calculation_qualified"] is False


@pytest.mark.parametrize("when", ["2025-03-31", "2026-05-15"])
def test_collectee_observations_remain_reviewable_without_credit_entitlement(when):
    out = run(records(when, role="collectee"), "collectee")
    assert not out["blocked"]
    assert out["rows"][0]["credit_entitlement"] == "NOT_DETERMINED"
    assert not saved_withdrawn_expectation(out)
    assert "withholding_provision_scope" not in out


def test_saved_legacy_rows_and_documented_exception_cannot_bypass_boundary():
    out = run(records("2026-05-15"), "collector")
    legacy = deepcopy(out)
    legacy["blocked"] = False
    for row in legacy["rows"]:
        row.pop("statutory_scope_issues")
        row.update(state="MATCHED", auditor_status="EXCEPTION_DOCUMENTED")
    retained = deepcopy(legacy)
    assert "withdrawn period" in approval_error(legacy)
    assert legacy == retained


@pytest.mark.parametrize("workflow", ["india-withholding-liability", "obligation-bank-allocations"])
async def test_legacy_reviewed_positive_expectation_cannot_generate_new_paper(
    monkeypatch, workflow
):
    from fastapi import HTTPException

    from app.api.v1 import intelligence
    from app.modules.intelligence.schemas import GeneratePaper

    body = run(records("2026-05-15"), "collector")
    body.update(review_status="REVIEWED", blocked=False)
    if workflow == "obligation-bank-allocations":
        body["workflow"] = workflow
        for row in body["rows"]:
            row.update(
                kind="obligation",
                expected_amount="100",
                withholding_scope={
                    field: row[field]
                    for field in ("legal_role", "tax_kind", "rule_reference", "transaction_date")
                },
            )
    monkeypatch.setattr(intelligence.audit, "engagement", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(
        intelligence.service, "event", AsyncMock(return_value=SimpleNamespace(body=body))
    )
    create = AsyncMock()
    monkeypatch.setattr(intelligence.audit, "create", create)
    with pytest.raises(HTTPException) as error:
        await intelligence.generate_paper(
            uuid4(),
            uuid4(),
            GeneratePaper(
                reference="LEGACY-TCS",
                title="Historical saved expectation",
                objective="Attempt a new draft from a post-withdrawal positive expectation",
            ),
            None,
            None,
            SimpleNamespace(),
        )
    assert error.value.status_code == 409 and "withdrawn period" in error.value.detail
    create.assert_not_awaited()
