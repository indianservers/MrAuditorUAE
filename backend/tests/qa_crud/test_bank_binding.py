"""Real source jobs, reviewed account binding, original downloads and staleness.

Scanner and dispatch are explicit test doubles; job processing and DB are real.
"""

import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.native_source_examples import CAMT
from tests.unit.test_bank_accounts import parameters, population

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def retain_native(c, h, eid, content, currency):
    base = f"/api/v1/engagements/{eid}/audit"
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-linked-bank.xml", content, "application/xml")},
    )
    assert upload.status_code == 201, upload.text
    event = await execute(
        c,
        h,
        eid,
        "workflow-source",
        dict(
            evidence_version_id=upload.json()["id"],
            table_type="transactions",
            file_format="camt053",
            label="SYNTHETIC original bank identifier",
            expected_rows=2,
            control_totals={currency: "95"},
        ),
    )
    return event, base + "/evidence-files/" + record["id"] + "/" + upload.json()["id"] + "/download"


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_reviewed_account_alias_binds_native_statement_and_stales_recursively(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "IN":
        h, eid, base = await india_context(c)
        name = "SYNTHETIC ECR India entity"
    else:
        h, _, eid, base = await setup(c)
        name = "FICTIONAL synthetic entity"
    reviewer = await actor(h, "Firm Administrator", "linked-account-reviewer")
    await grant(c, h, base, reviewer)
    assertions = population(country)
    owner_sources = {}
    for role, rows in assertions.items():
        rows[0].update(account="BANK-1", owner_name=name)
        prepared = await source(
            c, h, eid, rows, "SYNTHETIC assessed account " + role, "bank-account-evidence", {}
        )
        response = await decision(c, reviewer[0], eid, prepared)
        assert response.status_code == 201, response.text
        owner_sources[role] = response.json()
    account_payload = parameters(country, account="BANK-1", bank_owner_name=name).model_dump(
        mode="json"
    )
    account_payload["source_ids"] = {role: item["id"] for role, item in owner_sources.items()}
    account = await execute(c, h, eid, "country-workflow", account_payload)
    number = assertions["bank"][0]["account_number"]
    content = CAMT.replace(b"BANK-1", number.encode()).replace(b"AED", currency.encode())
    native, download_path = await retain_native(c, h, eid, content, currency)
    books = await source(
        c,
        h,
        eid,
        [
            dict(
                id="B1",
                account="BANK-1",
                reference="PAY-1",
                date="2026-06-01",
                currency=currency,
                amount="100",
            ),
            dict(
                id="B2",
                account="BANK-1",
                reference="FEE",
                date="2026-06-02",
                currency=currency,
                amount="-5",
            ),
        ],
        "SYNTHETIC ledger code books",
        totals={currency: "95"},
    )
    payload = bank_payload(
        books, native, currency=currency, book_closing="95", statement_closing="95"
    )
    await execute(c, h, eid, "country-workflow", payload, failed="original native")
    linked = {
        **payload,
        "bank_account_review_id": account["id"],
        "bank_account_scope_assessment": "Independently assessed ledger label, original bank number and all June source dates",
    }
    await execute(c, h, eid, "country-workflow", linked, failed="independently reviewed")
    response = await decision(c, reviewer[0], eid, account)
    assert response.status_code == 201, response.text
    account = response.json()
    for obj in [books, native]:
        response = await decision(c, reviewer[0], eid, obj)
        assert response.status_code == 201, response.text
        if obj is books:
            books = response.json()
        else:
            native = response.json()
    linked = {
        **linked,
        "source_ids": {"books": books["id"], "statement": native["id"]},
        "bank_account_review_id": account["id"],
    }
    result = await execute(c, h, eid, "country-workflow", linked)
    assert not result["body"]["blocked"] and result["body"]["exception_count"] == 0
    link = result["body"]["bank_account_evidence"]
    assert link["status"] == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"
    assert link["original_bank_source_account"] == number and link["account"] == "BANK-1"
    assert any(
        dep["type"] == "event" and dep["id"] == account["id"] and dep["sha256"] == account["sha256"]
        for dep in result["dependencies"]
    )
    response = await decision(c, reviewer[0], eid, result)
    assert response.status_code == 201, response.text
    result = response.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    original = await c.get(download_path, headers=h)
    assert original.status_code == 200 and original.content == content
    retained = await c.get(prefix + native["id"], headers=h)
    assert all(row["account"] == number for row in retained.json()["body"]["rows"])
    export = await c.get(prefix + result["id"] + "/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    cover = {
        row[0].value: row[1].value
        for row in load_workbook(io.BytesIO(export.content))["Source and review"]
    }
    assert "REVIEWED_ACCOUNT_DOCUMENTS_LINKED" in cover["bank_account_evidence"]
    assert number in cover["bank_account_evidence"]
    await execute(
        c, h, eid, "country-workflow", {**linked, "as_of": "2026-07-01"}, failed="window end"
    )
    forged = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/jobs",
        headers={**h, "Idempotency-Key": "forged-account-proof"},
        json={
            "operation": "country-workflow",
            "payload": {**linked, "bank_account_review": [account["body"], {}]},
        },
    )
    assert forged.status_code == 422, forged.text
    revised = await decision(c, reviewer[0], eid, owner_sources["bank"], action="reject")
    assert revised.status_code == 201, revised.text
    stale = await c.get(prefix + result["id"], headers=h)
    assert stale.json()["freshness"] == "STALE"
    await execute(c, h, eid, "country-workflow", linked, failed="source is stale")


@pytest.mark.parametrize(
    "country,currency,component", [("AE", "AED", "SALARY"), ("IN", "INR", "PF:EMPLOYEE")]
)
@pytest.mark.parametrize("workflow", ["bank-subsequent-clearance", "obligation-bank-allocations"])
async def test_reviewed_account_alias_applies_to_clearance_and_obligation_links(
    environment, monkeypatch, country, currency, component, workflow
):
    from decimal import Decimal

    from tests.unit.test_bank_clearance import population as clearance_population
    from tests.unit.test_dues_allocations import example as dues_population
    from tests.unit.test_dues_allocations import parameters as dues_parameters

    c = environment
    double_boundaries(monkeypatch)
    if country == "IN":
        h, eid, base = await india_context(c)
        name = "SYNTHETIC ECR India entity"
    else:
        h, _, eid, base = await setup(c)
        name = "FICTIONAL synthetic entity"
    reviewer = await actor(h, "Firm Administrator", "account-allocation-reviewer")
    await grant(c, h, base, reviewer)
    owner_ids = {}
    assertions = population(country)
    for role, rows in assertions.items():
        rows[0].update(account="BANK-1", owner_name=name)
        item = await source(
            c, h, eid, rows, "SYNTHETIC scoped owner " + role, "bank-account-evidence", {}
        )
        response = await decision(c, reviewer[0], eid, item)
        assert response.status_code == 201, response.text
        owner_ids[role] = response.json()["id"]
    account_payload = parameters(
        country,
        account="BANK-1",
        bank_owner_name=name,
        as_of="2026-08-31" if workflow == "bank-subsequent-clearance" else "2026-06-30",
    ).model_dump(mode="json")
    item = await execute(
        c, h, eid, "country-workflow", {**account_payload, "source_ids": owner_ids}
    )
    response = await decision(c, reviewer[0], eid, item)
    assert response.status_code == 201, response.text
    account = response.json()
    number = assertions["bank"][0]["account_number"]
    if workflow == "bank-subsequent-clearance":
        records = clearance_population(currency)
        bank_role = "statement"
        types = {
            "outstanding": "bank-outstanding",
            "statement": "transactions",
            "allocations": "bank-clearances",
        }
        payload = {
            "workflow": workflow,
            "as_of": "2026-06-30",
            "review_through": "2026-08-31",
            "account": "BANK-1",
            "currency": currency,
            "title": "SYNTHETIC linked clearance",
            "rationale": "Independent account proof over original item and subsequent review window",
        }
    else:
        records = dues_population(currency, component)
        bank_role = "bank"
        types = {
            "expected": "obligations",
            "reported": "obligations",
            "bank": "transactions",
            "allocations": "obligation-allocations",
        }
        payload = {
            key: value
            for key, value in dues_parameters(currency=currency).items()
            if key != "source_ids"
        }
    for row in records[bank_role]:
        row["account"] = number
    ids = {}
    for role, rows in records.items():
        totals = {currency: str(sum((Decimal(row["amount"]) for row in rows), Decimal(0)))}
        item = await source(
            c, h, eid, rows, "SYNTHETIC linked financial " + role, types[role], totals
        )
        response = await decision(c, reviewer[0], eid, item)
        assert response.status_code == 201, response.text
        ids[role] = response.json()["id"]
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **payload,
            "source_ids": ids,
            "bank_account_review_id": account["id"],
            "bank_account_scope_assessment": "Independently assessed actual account number and the complete operation-specific window",
        },
    )
    link = result["body"]["bank_account_evidence"]
    assert link["status"] == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"
    assert link["bank_source_role"] == bank_role
    assert link["original_bank_source_account"] == number
    assert link["source_account_binding"] == "CANONICAL_ACCOUNT_NUMBER_AGREES_TO_REVIEWED_DOCUMENTS"
    assert link["window_end"] == (
        "2026-08-31" if workflow == "bank-subsequent-clearance" else "2026-06-30"
    )
    original = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{ids[bank_role]}", headers=h
    )
    assert all(row["account"] == number for row in original.json()["body"]["rows"])
