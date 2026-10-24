"""Real HTTP/DB/private storage/Redis; vendor responses are explicit transport doubles."""

import asyncio
import base64
import hmac
import json
import os
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import settings
from app.modules.connectors.native_adapters import NativeAdapter
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import scope

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated migrated test DB and Redis required"
)


async def test_native_replay_preserves_history_and_accepts_independent_balance_controls(
    environment, monkeypatch
):
    from app.modules.connectors import native_service

    client = environment
    headers, options = await scope(client)
    monkeypatch.setattr(settings(), "connector_allowed_origins", ["https://erp.connector.test"])
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("company"):
            data = {"company_id": "company-1", "currency": "AED"}
        elif request.url.path.endswith("accounts"):
            data = {
                "items": [
                    {"account_code": "cash", "account_name": "Cash"},
                    {"account_code": "sales", "account_name": "Sales"},
                ],
                "next": None,
            }
        else:
            data = {
                "items": [
                    {
                        "account_code": code,
                        "account_name": code,
                        "journal_ref": "journal-1",
                        "source_id": code + "-posting",
                        "posting_date": "2026-06-01",
                        "debit": debit,
                        "credit": credit,
                        "currency": "AED",
                    }
                    for code, debit, credit in [("cash", "10", "0"), ("sales", "0", "10")]
                ],
                "next": None,
            }
        return httpx.Response(200, json=data)

    monkeypatch.setattr(
        native_service,
        "NativeAdapter",
        lambda *args: NativeAdapter(*args, transport=httpx.MockTransport(respond)),
    )
    # Preserve version metadata on the injected factory too.
    native_service.NativeAdapter.version = NativeAdapter.version
    response = await client.post(
        "/api/v1/accounting/connections",
        headers=headers,
        json={
            **{k: options[k] for k in ("client_id", "entity_id", "period_id")},
            "provider": "busy",
            "name": "TEST ONLY native connector",
            "credentials": {"access_token": "test-only-vendor-token"},
            "config": {
                "edition": "partner-api",
                "base_url": "https://erp.connector.test/api/",
                "company_id": "company-1",
                "functional_currency": "AED",
                "company_path": "company",
                "accounts_path": "accounts",
                "ledger_path": "entries",
            },
        },
    )
    assert response.status_code == 201, response.text
    connection = response.json()["id"]
    first = await client.post(
        f"/api/v1/connectors/native/{connection}/sync?background=false", headers=headers
    )
    assert first.status_code == 200 and first.json()["status"] == "completed", first.text
    session = first.json()["result"]["resume_session"]
    second = await client.post(
        f"/api/v1/connectors/native/{connection}/sync?background=false&resume_session={session}",
        headers=headers,
    )
    assert second.status_code == 200 and second.json()["status"] == "completed", second.text
    assert second.json()["result"]["checkpoint"]["replayed"] == 2
    assert calls.count("/api/entries") == 1 and calls.count("/api/company") == 2
    assert second.json()["result"]["source_revision"]["removed"] == []
    controls = await client.post(
        f"/api/v1/connectors/operations/{connection}/balance-controls",
        headers=headers,
        json={
            "sync_run_id": second.json()["id"],
            "opening_reference": "independent opening report",
            "closing_reference": "independent closing report",
            "opening": [
                {"account_code": "cash", "balance": "0"},
                {"account_code": "sales", "balance": "0"},
            ],
            "closing": [
                {"account_code": "cash", "balance": "10"},
                {"account_code": "sales", "balance": "-10"},
            ],
        },
    )
    assert controls.status_code == 200 and controls.json()["payload"]["matched"], controls.text
    health = await client.get(f"/api/v1/connectors/operations/{connection}", headers=headers)
    assert health.status_code == 200 and "test-only-vendor-token" not in health.text
    assert any(record["namespace"] == "source_revision" for record in health.json()["records"])
    from app.workers.accounting import process, work

    monkeypatch.setattr(work, "apply_async", lambda **kwargs: None)
    queued = await client.post(
        f"/api/v1/connectors/native/{connection}/sync?resume_session={session}", headers=headers
    )
    assert queued.status_code == 200, queued.text
    user = (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]
    await asyncio.wait_for(process(queued.json()["id"], headers["X-Tenant-ID"], user), timeout=15)
    job = await client.get(f"/api/v1/jobs/{queued.json()['id']}", headers=headers)
    assert job.json()["status"] == "completed", job.text
    assert calls.count("/api/entries") == 1 and calls.count("/api/company") == 3


async def test_signed_webhook_receipts_deduplicate_concurrent_callbacks(environment, monkeypatch):
    client = environment
    headers, options = await scope(client)
    monkeypatch.setattr(settings(), "connector_quickbooks_webhook_token", "test-verifier")
    response = await client.post(
        "/api/v1/accounting/connections",
        headers=headers,
        json={
            **{k: options[k] for k in ("client_id", "entity_id", "period_id")},
            "provider": "quickbooks",
            "name": "TEST ONLY webhook",
            "config": {"company_id": "123", "functional_currency": "AED"},
        },
    )
    assert response.status_code == 201, response.text
    raw = json.dumps(
        {
            "eventNotifications": [
                {
                    "realmId": "123",
                    "dataChangeEvent": {
                        "entities": [
                            {
                                "name": "Invoice",
                                "id": "1",
                                "operation": "Delete",
                                "lastUpdated": datetime.now(UTC).isoformat(),
                            }
                        ]
                    },
                }
            ]
        }
    ).encode()
    signature = base64.b64encode(hmac.digest(b"test-verifier", raw, "sha256")).decode()
    path = f"/api/v1/connectors/webhooks/quickbooks/{headers['X-Tenant-ID']}"
    assert (
        await client.post(path, content=raw, headers={"intuit-signature": "invalid"})
    ).status_code == 403
    replies = await asyncio.gather(
        *(client.post(path, content=raw, headers={"intuit-signature": signature}) for _ in range(2))
    )
    assert all(reply.status_code == 202 for reply in replies), [r.text for r in replies]
    assert sum(reply.json()["accepted"] for reply in replies) == 1
    health = await client.get(
        f"/api/v1/connectors/operations/{response.json()['id']}", headers=headers
    )
    assert health.json()["records"][0]["payload"]["state"] == "repair_pending"


async def test_tally_window_history_retains_cancellation_without_activating_postings(environment):
    from datetime import date
    from xml.etree.ElementTree import Element, SubElement, fromstring, tostring

    from app.modules.connectors.tally import parse_export
    from tests.phase2.test_connectors import TALLY
    from tests.phase2.test_pipeline import upload

    client = environment
    headers, options = await scope(client)
    scope_body = {k: options[k] for k in ("client_id", "entity_id", "period_id")}
    response = await client.post(
        "/api/v1/accounting/connections",
        headers=headers,
        json={**scope_body, "provider": "tally", "name": "TEST ONLY Tally revision reader"},
    )
    assert response.status_code == 201, response.text
    connection = response.json()["id"]
    root = fromstring(TALLY)
    data = root.find(".//DATA")
    voucher = data.find("VOUCHER")
    data.remove(voucher)
    company = SubElement(data, "COMPANY", NAME="FICTIONAL Test")
    SubElement(company, "GUID").text = "company-guid"
    masters = tostring(root)
    fingerprint = parse_export(masters, "FICTIONAL Test", date(2026, 1, 1), date(2026, 12, 31))[
        "company_fingerprint"
    ]
    pinned = await client.patch(
        f"/api/v1/connectors/operations/{connection}/tally-identity",
        headers=headers,
        json={"company": "FICTIONAL Test", "company_fingerprint": fingerprint},
    )
    assert pinned.status_code == 200, pinned.text
    options.update(
        source_system="tally",
        tally_company="FICTIONAL Test",
        tally_company_fingerprint=fingerprint,
        expected_rows=None,
        expected_debit=None,
        expected_credit=None,
        source_complete=False,
    )
    results = []
    for cancelled in (False, True):
        if cancelled:
            SubElement(voucher, "ISCANCELLED").text = "Yes"
            SubElement(voucher, "ALTERID").text = "2"
        window = Element("ENVELOPE")
        window.append(voucher)
        raw = (
            json.dumps(
                {
                    "format": "tally-window-package/1",
                    "company": "FICTIONAL Test",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "masters_xml": base64.b64encode(masters).decode(),
                }
            )
            + "\n"
            + json.dumps(
                {
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "xml": base64.b64encode(tostring(window)).decode(),
                }
            )
            + "\n"
        ).encode()
        batch = await upload(client, headers, options, raw, "synthetic-tally.ndjson")
        reply = await client.post(
            f"/api/v1/connectors/operations/{connection}/agent-revisions",
            headers=headers,
            json={"batch_id": batch},
        )
        assert reply.status_code == 200, reply.text
        results.append(reply.json()["revision"])
    assert results[0]["added"] == ["voucher-1"]
    assert results[1]["changed"] == ["voucher-1"] and results[1]["removed"] == []
    assert (await client.get("/api/v1/accounting/ledger", headers=headers)).json()["total"] == 0
