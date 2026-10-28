"""Real retained account/native-bank linkage; scan and dispatch are explicit doubles."""

import os
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_bank_accounts import parameters, population
from tests.unit.test_merchant_settlements import COMPONENTS, ROLES, payload, populations

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_native_merchant_account_link_and_review_withdrawal(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
        owner = "FICTIONAL synthetic entity"
    else:
        h, eid, base = await india_context(c)
        owner = "SYNTHETIC ECR India entity"
    reviewer = await actor(h, "Firm Administrator", "merchant-account-reviewer")
    await grant(c, h, base, reviewer)
    scope = population(country)
    account_sources = {}
    for role, rows in scope.items():
        rows[0].update(account="ACCT", owner_name=owner)
        obj = await source(
            c, h, eid, rows, "SYNTHETIC merchant account " + role, "bank-account-evidence", {}
        )
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        account_sources[role] = reviewed.json()["id"]
    params = parameters(country, account="ACCT", bank_owner_name=owner).model_dump(mode="json")
    params["source_ids"] = account_sources
    account = await execute(c, h, eid, "country-workflow", params)
    approved = await decision(c, reviewer[0], eid, account)
    assert approved.status_code == 201, approved.text
    account = approved.json()
    number = scope["bank"][0]["account_number"]
    raw = (
        (
            Path(__file__).resolve().parents[3]
            / "docs/country-workflows/sample-inputs/SYNTHETIC-UAE-bank-browser.xml"
        )
        .read_bytes()
        .replace(b"SYNTHETIC-UAE-BANK", number.encode())
        .replace(b"100.20", b"800.00")
        .replace(b"AED", currency.encode())
    )
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("SYNTHETIC-merchant-bank.xml", raw, "application/xml")},
    )
    assert upload.status_code == 201, upload.text
    bank = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": upload.json()["id"],
            "file_format": "camt053",
            "table_type": "transactions",
            "label": "SYNTHETIC original merchant bank",
            "expected_rows": 1,
            "control_totals": {currency: "800"},
        },
    )
    data = populations(country)
    data["allocations"][0]["bank_transaction_id"] = bank["body"]["rows"][0]["id"]
    retained = {}
    for role, rows in data.items():
        if role == "bank":
            obj = bank
        else:
            controls = {currency: "1120" if role == "books" else "800"}
            extra = (
                {
                    "merchant_component_controls": {
                        currency: {field: rows[0][field] for field in COMPONENTS}
                    }
                }
                if role == "processor"
                else {}
            )
            obj = await source(
                c, h, eid, rows, "SYNTHETIC linked merchant " + role, ROLES[role], controls, **extra
            )
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        retained[role] = reviewed.json()["id"]
    request = payload(
        currency=currency,
        source_ids=retained,
        bank_account_review_id=account["id"],
        bank_account_scope_assessment="Synthetic original bank identifier and full June account-document scope assessment",
    )
    result = await execute(c, h, eid, "country-workflow", request)
    assert result["body"]["bank_account_evidence"]["status"] == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"
    assert result["body"]["bank_account_evidence"]["original_bank_source_account"] == number
    assert Decimal(result["body"]["rows"][0]["bank_difference"]) == 0
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    result = approved.json()
    downloaded = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + upload.json()["id"] + "/download",
        headers=h,
    )
    assert downloaded.status_code == 200 and downloaded.content == raw
    before = deepcopy(result["body"])
    withdrawn = await decision(c, reviewer[0], eid, account, "reject")
    assert withdrawn.status_code == 201, withdrawn.text
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    stale = (await c.get(prefix + "/events/" + result["id"], headers=h)).json()
    assert stale["freshness"] == "STALE" and stale["body"] == before
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409
