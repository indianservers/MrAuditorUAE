"""Real imports, scoped comparisons, generated reviews and release controls."""

import os
import uuid
from decimal import Decimal

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import action, create, setup
from tests.phase5.test_reporting import CSV, prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_import_comparison_monthly_controls_and_unmapped_filter(environment):
    c = environment
    h, opts, eid, base = await setup(c)
    period = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={"entity_id": opts["entity_id"], "start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert period.status_code == 201, period.text
    prior_options = {
        **opts,
        "period_id": period.json()["id"],
        "expected_rows": 6,
        "expected_debit": "170",
        "expected_credit": "170",
    }
    prior_csv = CSV.replace(b"2026-", b"2025-").replace(b"500,Expense", b"600,Old expense")
    _, prior = await committed(c, h, prior_options, prior_csv)
    opts.update(expected_rows=6, expected_debit="170", expected_credit="170")
    _, current = await committed(c, h, opts, CSV)
    response = await c.get(
        "/api/v1/accounting/trial-balance",
        headers=h,
        params={"snapshot_id": current, "comparison_snapshot_id": prior, "limit": 1},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total"] == 5 and len(result["items"]) == 1
    assert result["completeness"] == "controls_reconciled"
    assert result["monthly_movements"] == [
        {"id": "2026-06", "month": "2026-06", "debit": "70.00000000", "credit": "70.00000000"}
    ]
    assert result["comparison_candidates"][0]["id"] == prior
    rows = (
        await c.get(
            "/api/v1/accounting/trial-balance",
            headers=h,
            params={"snapshot_id": current, "comparison_snapshot_id": prior, "limit": 100},
        )
    ).json()["items"]
    old = next(r for r in rows if r["code"] == "600")
    assert (
        old["comparison_only"]
        and Decimal(old["variance"]) == -20
        and Decimal(old["percentage"]) == -100
    )
    new = next(r for r in rows if r["code"] == "500")
    assert new["percentage"] is None and Decimal(new["variance"]) == 20
    filtered = await c.get(
        "/api/v1/accounting/trial-balance",
        headers=h,
        params={"snapshot_id": current, "unmapped_only": True},
    )
    assert filtered.status_code == 200
    for invalid, code in [(current, 422), (str(uuid.uuid4()), 404)]:
        response = await c.get(
            "/api/v1/accounting/trial-balance",
            headers=h,
            params={"snapshot_id": current, "comparison_snapshot_id": invalid},
        )
        assert response.status_code == code


async def test_generated_draft_review_comparison_and_stale_sources(environment):
    c = environment
    h, eid, base, reviewer, partner, profile, mapping, note, ready = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    first = await c.post(api + "/financial-statements/" + profile["id"], headers=h)
    assert first.status_code == 201, first.text
    first = first.json()
    assert first["results"]["review"]["ready"]
    await ready(
        "adjustment",
        {
            "profile_id": profile["id"],
            "adjustment_type": "journal",
            "standard": "IAS 1",
            "currency": "AED",
            "adjustment_date": "2026-06-01",
            "narration": "SYNTHETIC expense correction",
            "legs": [{"account_code": "500", "debit": "5"}, {"account_code": "100", "credit": "5"}],
        },
    )
    second = await c.post(api + "/financial-statements/" + profile["id"], headers=h)
    assert second.status_code == 201, second.text
    second = second.json()
    response = await c.get(
        api + f"/runs/{second['id']}/review", headers=h, params={"comparison_run_id": first["id"]}
    )
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["ready"] and review["dependencies_current"]
    assert {r.get("line_code") for r in review["changes"]} >= {"100", "500"}
    assert not review["issues"]
    await action(c, reviewer[0], base, mapping, "reopen")
    response = await c.get(api + f"/runs/{second['id']}/review", headers=h)
    assert not response.json()["dependencies_current"] and not response.json()["ready"]
    same = await c.get(
        api + f"/runs/{second['id']}/review", headers=h, params={"comparison_run_id": second["id"]}
    )
    assert same.status_code == 422
    unknown = await c.get(
        api + f"/runs/{second['id']}/review",
        headers=h,
        params={"comparison_run_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404


async def test_duplicate_note_reference_blocks_release(environment):
    c = environment
    h, eid, base, reviewer, partner, profile, mapping, note, ready = await prepared(c)
    await ready(
        "note",
        {
            "profile_id": profile["id"],
            "note_reference": "N1",
            "text": "SYNTHETIC conflicting note",
            "linked_line_codes": ["100", "300", "400", "500"],
        },
    )
    api = f"/api/v1/ifrs/engagements/{eid}"
    response = await c.post(api + "/financial-statements/" + profile["id"], headers=h)
    assert response.status_code == 201, response.text
    run = response.json()
    assert not run["results"]["validation"]["ready"]
    assert any(i["code"] == "duplicate_note_reference" for i in run["results"]["review"]["issues"])
    package = await create(
        c,
        h,
        base,
        "ifrs-financials",
        {"run_id": run["id"], "release_rationale": "SYNTHETIC attempted release"},
    )
    await action(c, h, base, package, "submit", 409)
    output = await c.get(api + f"/runs/{run['id']}/export/json", headers=h)
    assert output.status_code == 200 and not output.json()["released"]


async def test_trial_balance_without_independent_controls_has_no_monthly_claim(environment):
    c = environment
    h, opts, eid, base = await setup(c)
    for key in ("expected_rows", "expected_debit", "expected_credit"):
        opts.pop(key, None)
    opts["kind"] = "tb"
    csv = b"account_code,account_name,opening_balance,debit,credit,closing_balance\n100,Cash,10,25,0,35\n400,Sales,-10,0,25,-35\n"
    _, snapshot = await committed(c, h, opts, csv)
    result = await c.get(
        "/api/v1/accounting/trial-balance", headers=h, params={"snapshot_id": snapshot}
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["completeness"] == "independent_controls_required"
    assert not data["monthly_testable"] and data["monthly_movements"] == []
