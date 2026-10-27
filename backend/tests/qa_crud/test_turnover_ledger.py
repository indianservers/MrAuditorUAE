"""Real committed ledger authorization, review and turnover source lineage."""

import os
import uuid

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_turnover_bridge import populations

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")

CSV = b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n400,Revenue,OPEN,2026-06-01,0,10,L1,true,false,Opening\n100,Cash,OPEN,2026-06-01,10,0,L2,true,false,Opening\n400,Revenue,SALE,2026-06-15,0,100.20,L3,false,false,Sale\n100,Cash,SALE,2026-06-15,100.20,0,L4,false,false,Sale\n400,Revenue,CREDIT,2026-06-20,5,0,L5,false,false,Credit note\n100,Cash,CREDIT,2026-06-20,0,5,L6,false,false,Credit note\n"


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_committed_turnover_authorization_controls_and_review(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, options, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
        eng = (await c.get(f"/api/v1/engagements/{eid}", headers=h)).json()
        entity = (await c.get(f"/api/v1/entities/{eng['entity_id']}", headers=h)).json()
        options = dict(
            client_id=entity["client_id"], entity_id=eng["entity_id"], period_id=eng["period_id"]
        )
    options.update(
        expected_rows=6,
        expected_debit="115.20",
        expected_credit="115.20",
        source_complete=True,
        currency="AED" if country == "AE" else "INR",
    )
    _, snapshot = await committed(c, h, options, CSV)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    accounts = await c.get(prefix + "/accounts", params={"snapshot_id": snapshot}, headers=h)
    assert accounts.status_code == 200, accounts.text
    account = next(row["id"] for row in accounts.json()["items"] if row["code"] == "400")
    payload = dict(
        snapshot_id=snapshot,
        account_ids=[account],
        registration="100000000000001" if country == "AE" else "27ABCDE1234F1Z5",
        period_start="2026-06-01",
        period_end="2026-06-30",
        currency="AED" if country == "AE" else "INR",
        expected_rows=2,
        expected_amount="95.20",
        assessment="Revenue accounts allocated to the selected registration",
        label="SYNTHETIC committed books turnover",
    )
    response = await c.post(prefix + "/turnover-ledger-source", headers=h, json=payload)
    assert response.status_code == 201, response.text
    prepared = response.json()
    body = prepared["body"]
    assert body["review_status"] == "UNVERIFIED" and body["ledger_line_count"] == 2
    assert body["allowed_source_roles"] == ["books"]
    assert body["control_totals"] == {payload["currency"]: "95.20000000"}
    assert {row["source_journal_reference"] for row in body["rows"]} == {"SALE", "CREDIT"}
    assert all(row["source_record_id"] for row in body["rows"])
    assert (await decision(c, h, eid, prepared)).status_code == 403
    reviewer = await actor(h, "Firm Administrator", "ledger-turnover-reviewer")
    await grant(c, h, base, reviewer)
    checked = await decision(c, reviewer[0], eid, prepared)
    assert checked.status_code == 201, checked.text
    from app.modules.country_workflows.turnover import ROLES

    ids = {"books": checked.json()["id"]}
    rows = populations(country)
    for role in ("scope", "return", "adjustments"):
        records = rows[role]
        for row in records:
            row.update(
                period_start="2026-06-01",
                period_end="2026-06-30",
                registration=payload["registration"],
            )
            if role != "scope":
                row["amount"] = "95.20" if role == "return" else "0"
        normalized = await source(
            c,
            h,
            eid,
            records,
            "SYNTHETIC ledger bridge " + role,
            ROLES[role],
            {} if role == "scope" else {payload["currency"]: records[0]["amount"]},
        )
        reviewed = await decision(c, reviewer[0], eid, normalized)
        assert reviewed.status_code == 201, reviewed.text
        ids[role] = reviewed.json()["id"]
    bridge_payload = dict(
        workflow="tax-turnover-bridge",
        source_ids=ids,
        currency=payload["currency"],
        as_of="2026-06-30",
        title="SYNTHETIC committed GL bridge",
        rationale="Separate reviewed declared scope and return evidence",
    )
    bridge = await execute(c, h, eid, "country-workflow", bridge_payload)
    assert not bridge["body"]["blocked"] and bridge["body"]["rows"][0]["state"] == "MATCHED"
    duplicate = await c.post(prefix + "/turnover-ledger-source", headers=reviewer[0], json=payload)
    assert duplicate.status_code == 201, duplicate.text
    # Preparing from another user's imported ledger does not make its importer independent.
    assert (await decision(c, h, eid, duplicate.json())).status_code == 403
    assert (await decision(c, reviewer[0], eid, duplicate.json())).status_code == 403
    independent = await actor(h, "Firm Administrator", "ledger-turnover-independent")
    await grant(c, h, base, independent)
    duplicate_review = await decision(c, independent[0], eid, duplicate.json())
    assert duplicate_review.status_code == 201, duplicate_review.text
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**bridge_payload, "source_ids": {**ids, "return": duplicate_review.json()["id"]}},
        failed="role",
    )
    for change, status in [
        ({"expected_amount": "-95.20"}, 422),
        ({"expected_rows": 3}, 422),
        ({"period_start": "2020-01-01"}, 422),
        ({"account_ids": [str(uuid.uuid4())]}, 422),
    ]:
        invalid = await c.post(
            prefix + "/turnover-ledger-source", headers=h, json={**payload, **change}
        )
        assert invalid.status_code == status, invalid.text
    nil = await c.post(
        prefix + "/turnover-ledger-source",
        headers=h,
        json={
            **payload,
            "period_start": "2026-07-01",
            "period_end": "2026-07-31",
            "expected_rows": 0,
            "expected_amount": "0",
            "nil_reason": "No posted movements in July selection",
        },
    )
    assert nil.status_code == 201, nil.text
    assert nil.json()["body"]["generated_nil_row"] is True
    assert nil.json()["body"]["rows"][0]["amount"] == "0"
    reviewed_nil = await decision(c, reviewer[0], eid, nil.json())
    assert reviewed_nil.status_code == 201, reviewed_nil.text
    composition = dict(
        source_ids=[checked.json()["id"], reviewed_nil.json()["id"]],
        expected_rows=3,
        expected_amount="95.20",
        currency=payload["currency"],
        label="SYNTHETIC June and July books",
        assessment="Disjoint June movements and assessed July nil period",
    )
    combined = await c.post(
        prefix + "/turnover-books-composition", headers=independent[0], json=composition
    )
    assert combined.status_code == 201, combined.text
    assert combined.json()["body"]["row_count"] == 3
    overlapping = await c.post(
        prefix + "/turnover-books-composition",
        headers=h,
        json={
            **composition,
            "source_ids": [checked.json()["id"], duplicate_review.json()["id"]],
            "expected_rows": 4,
            "expected_amount": "190.40",
        },
    )
    assert overlapping.status_code == 422 and "Overlapping ledger accounts" in overlapping.text
    tb = b"Account Code,Account Name,Opening Balance,Debit,Credit,Closing Balance\n400,Revenue,-10,5,100.20,-105.20\n100,Cash,10,100.20,5,105.20\n"
    _, tb_snapshot = await committed(
        c,
        h,
        {
            **options,
            "kind": "tb",
            "expected_rows": 2,
            "expected_debit": "105.20",
            "expected_credit": "105.20",
        },
        tb,
    )
    invalid = await c.post(
        prefix + "/turnover-ledger-source", headers=h, json={**payload, "snapshot_id": tb_snapshot}
    )
    assert invalid.status_code == 422 and "trial balances" in invalid.text, invalid.text
