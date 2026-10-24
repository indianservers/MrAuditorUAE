import base64
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.modules.connectors.controls import (
    SourceControl,
    qualify,
    reconcile_balances,
    revision_summary,
)
from app.modules.connectors.enrichment import (
    foreign_provenance,
    match_qbo_posting,
    odata_metadata,
    tax_evidence,
)
from app.modules.connectors.native_http import NativeHTTP
from app.modules.connectors.quickbooks_desktop import package_rows, request
from app.modules.connectors.tally import date_windows, parse_export
from app.modules.connectors.tally_windows import package_rows as tally_rows
from app.modules.connectors.webhooks import cdc_parameters, verify_quickbooks
from app.modules.connectors.zoho import ConnectorError, ZohoConnector
from tests.phase2.test_connectors import TALLY


def signed(payload):
    raw = json.dumps(payload).encode()
    return raw, base64.b64encode(hmac.digest(b"test-verifier", raw, "sha256")).decode()


def test_webhook_authentication_and_idempotent_event_identity():
    raw, signature = signed(
        {
            "eventNotifications": [
                {
                    "realmId": "123",
                    "dataChangeEvent": {
                        "entities": [
                            {
                                "id": "99",
                                "name": "Invoice",
                                "operation": "Delete",
                                "lastUpdated": datetime.now(UTC).isoformat(),
                            }
                        ]
                    },
                }
            ]
        }
    )
    first = verify_quickbooks(raw, signature, "test-verifier")
    assert first == verify_quickbooks(raw, signature, "test-verifier")
    assert first[0]["operation"] == "Delete"
    with pytest.raises(ConnectorError):
        verify_quickbooks(raw + b" ", signature, "test-verifier")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"eventNotifications": [None]},
        {"eventNotifications": [{"dataChangeEvent": {"entities": "wrong"}}]},
    ],
)
def test_valid_signature_does_not_trust_invalid_envelopes(payload):
    raw, signature = signed(payload)
    with pytest.raises(ConnectorError):
        verify_quickbooks(raw, signature, "test-verifier")


@pytest.mark.parametrize(
    "days,entities", [(31, ["Invoice"]), (-1, ["Invoice"]), (1, ["Invented"]), (1, [])]
)
def test_cdc_rejects_unrecoverable_windows_and_unsupported_entities(days, entities):
    with pytest.raises(ConnectorError):
        cdc_parameters(datetime.now(UTC) - timedelta(days=days), entities)


def test_balance_controls_are_independent_and_find_account_differences():
    ledger = [
        {"account_code": "cash", "base_debit": "5", "base_credit": "0", "opening": False},
        {"account_code": "sales", "base_debit": "0", "base_credit": "5", "opening": False},
    ]
    opening = [
        {"account_code": "cash", "balance": "10"},
        {"account_code": "sales", "balance": "-10"},
    ]
    closing = [
        {"account_code": "cash", "balance": "15"},
        {"account_code": "sales", "balance": "-15"},
    ]
    assert reconcile_balances(ledger, opening, closing)["matched"]
    closing[0]["balance"], closing[1]["balance"] = "14", "-14"
    assert not reconcile_balances(ledger, opening, closing)["matched"]
    with pytest.raises(ConnectorError, match="coverage"):
        reconcile_balances(ledger, opening, [{"account_code": "other", "balance": "0"}])


def test_simulated_run_cannot_be_live_qualified():
    control = SourceControl(reference="independent report", rows=2, debit="5", credit="5")
    run = {
        "status": "completed",
        "manifest": {
            "execution_mode": "simulated",
            "counts": {"gl": 2},
            "functional_totals": {"debit": "5", "credit": "5"},
        },
    }
    assert qualify(run, control, "baseline")["status"] == "needs_live_evidence"
    run["manifest"]["execution_mode"] = "live"
    assert qualify(run, control, "baseline")["status"] == "passed"


def test_revision_deletions_require_full_comparable_population():
    previous, current = {"a": "1", "b": "2"}, {"a": "3", "c": "4"}
    assert revision_summary(previous, current, False)["removed"] == []
    result = revision_summary(previous, current, True)
    assert result["changed"] == ["a"] and result["removed"] == ["b"] and result["added"] == ["c"]


def test_fx_evidence_requires_source_rate_and_retains_original_amounts():
    row = {"currency": "AED", "debit": "36.73", "credit": "0"}
    result = foreign_provenance(row, "USD", "10", "0", "3.673")
    assert result["source_fx_status"] == "source_rate_verified" and result["original_debit"] == "10"
    assert foreign_provenance(row, "USD", "10", "0")["source_fx_status"] == "not_supplied"
    with pytest.raises(ConnectorError):
        foreign_provenance(row, "USD", "10", "0", "2")


def test_qbo_ambiguous_lines_never_acquire_fabricated_native_identity():
    row = {
        "source_id": "snapshot:1",
        "source_transaction_id": "123",
        "account_code": "cash",
        "debit": "10",
        "credit": "0",
    }
    line = {
        "Id": "1",
        "Amount": "10",
        "DetailType": "JournalEntryLineDetail",
        "JournalEntryLineDetail": {"AccountRef": {"value": "cash"}},
    }
    assert match_qbo_posting(row, {"Line": [line]})["source_id"] == "txn:123:1:cash"
    result = match_qbo_posting(row, {"Line": [line, {**line, "Id": "2"}]})
    assert result["source_id"] == "snapshot:1" and "ambiguous" in result["source_identity_quality"]


def test_tax_components_report_mismatch_without_reclassifying_taxes():
    result = tax_evidence(
        {"tax_total": "5", "taxes": [{"tax_amount": "3", "tax_id": "GST"}]}, "zoho"
    )
    assert result["components_match"] is False and result["source_tax_codes"] == ["GST"]


def test_odata_discovery_requires_published_entities_and_fields():
    xml = b'<Edmx><Schema><EntityType Name="Posting"><Property Name="Company"/></EntityType><EntityContainer><EntitySet Name="Postings" EntityType="Source.Posting"/></EntityContainer></Schema></Edmx>'
    assert odata_metadata(xml, "Postings", {"Company"})["fields_verified"] == ["Company"]
    with pytest.raises(ConnectorError, match="not published"):
        odata_metadata(xml, "GuessedEndpoint", set())
    with pytest.raises(ConnectorError, match="missing fields"):
        odata_metadata(xml, "Postings", {"Amount"})


async def test_binary_transport_pins_origin_and_releases_quota_on_failure():
    releases = []

    class Governor:
        async def acquire(self):
            return "lease"

        async def release(self, lease):
            releases.append(lease)

    http = NativeHTTP(
        "https://source.example/api/",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"Location": "https://evil.example"})
        ),
    )
    http.governor = Governor()
    try:
        with pytest.raises(ConnectorError, match="redirected"):
            await http.binary("file", {"application/pdf"})
        assert releases == ["lease"]
        with pytest.raises(ConnectorError, match="escaped"):
            await http.binary("https://evil.example/file", {"application/pdf"})
    finally:
        await http.close()


async def test_zoho_detail_and_attachment_use_regional_api_only():
    calls = []

    def respond(r):
        calls.append(r)
        if r.url.path.endswith("/attachment"):
            return httpx.Response(
                200, content=b"%PDF-test", headers={"Content-Type": "application/pdf"}
            )
        return httpx.Response(200, json={"code": 0, "invoice": {"invoice_id": "123"}})

    adapter = ZohoConnector(
        "in", "client", "secret", access_token="token", transport=httpx.MockTransport(respond)
    )
    assert (await adapter.document_detail("invoices", "123", "999"))["invoice"][
        "invoice_id"
    ] == "123"
    assert (await adapter.invoice_attachment("123", "999"))[0] == b"%PDF-test"
    assert all(
        r.url.host == "www.zohoapis.in" and r.url.params["organization_id"] == "999" for r in calls
    )


def test_tally_identity_alterations_and_allocations_remain_evidence():
    company = b'<COMPANY NAME="FICTIONAL Test"><GUID>company-guid</GUID><BOOKSFROM>20260101</BOOKSFROM></COMPANY>'
    content = TALLY.replace(b"<BODY>", b"<BODY>" + company).replace(
        b"<GUID>voucher-1</GUID>", b"<GUID>voucher-1</GUID><ALTERID>7</ALTERID>"
    )
    result = parse_export(content, "FICTIONAL Test", date(2026, 1, 1), date(2026, 12, 31))
    assert result["voucher_revisions"][0]["alter_id"] == "7" and len(result["lines"]) == 2
    assert result["company_fingerprint"]
    with pytest.raises(ConnectorError, match="fingerprint"):
        parse_export(
            content.replace(b"company-guid", b"restored-company"),
            "FICTIONAL Test",
            date(2026, 1, 1),
            date(2026, 12, 31),
            expected_fingerprint=result["company_fingerprint"],
        )


def test_tally_window_packages_reject_missing_period_coverage(tmp_path):
    options = SimpleNamespace(
        tally_company="FICTIONAL Test", tally_company_fingerprint=None, kind="gl"
    )
    masters = TALLY[: TALLY.index(b"<VOUCHER>")] + b"</DATA></BODY></ENVELOPE>"
    path = tmp_path / "source.ndjson"
    header = {
        "format": "tally-window-package/1",
        "company": options.tally_company,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "masters_xml": base64.b64encode(masters).decode(),
    }
    path.write_text(json.dumps(header) + "\n", encoding="utf-8")
    with pytest.raises(ConnectorError, match="terminal"):
        list(tally_rows(path, options))
    assert list(date_windows(date(2026, 1, 1), date(2026, 1, 3), 2)) == [
        (date(2026, 1, 1), date(2026, 1, 2)),
        (date(2026, 1, 3), date(2026, 1, 3)),
    ]


def test_desktop_sdk_permits_only_query_requests_and_keeps_native_accounts():
    with pytest.raises(ConnectorError):
        request("InvoiceAdd", date(2026, 1, 1), date(2026, 12, 31))
    assert "GeneralDetailReportQueryRq" in request("gl", date(2026, 1, 1), date(2026, 12, 31))

    def envelope(body):
        return (
            '<QBXML><QBXMLMsgsRs><QueryRs statusCode="0">'
            + body
            + "</QueryRs></QBXMLMsgsRs></QBXML>"
        )

    package = {
        "format": "quickbooks-desktop-sdk/1",
        "expected_company": "Test",
        "company_xml": envelope("<CompanyRet><CompanyName>Test</CompanyName></CompanyRet>"),
        "accounts_xml": envelope(
            "<AccountRet><ListID>native-id</ListID><FullName>Cash</FullName></AccountRet>"
        ),
        "ledger_xml": [],
    }
    assert (
        list(package_rows(package, SimpleNamespace(kind="coa")))[0]["account_code"] == "native-id"
    )


def test_zoho_delta_filters_only_documented_resources_and_overlap_boundary():
    from app.modules.connectors.incremental import modified_filter

    stamp = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert "last_modified_time" in modified_filter("invoices", stamp)
    assert "last_modified_time" in modified_filter("bills", stamp)
    assert modified_filter("chartofaccounts/accounttransactions", stamp) == {}
    assert modified_filter("invoices", None) == {}


async def test_finance_metadata_drives_native_read_entities_and_date_types():
    from app.modules.connectors.native_adapters import NativeAdapter

    xml = b"""<Edmx><Schema Namespace="Source"><EntityType Name="Company"><Property Name="code" Type="Edm.String"/><Property Name="currency" Type="Edm.String"/></EntityType><EntityType Name="Account"><Property Name="code" Type="Edm.String"/><Property Name="name" Type="Edm.String"/></EntityType><EntityType Name="Posting"><Property Name="code" Type="Edm.String"/><Property Name="ref" Type="Edm.String"/><Property Name="id" Type="Edm.String"/><Property Name="debit" Type="Edm.Decimal"/><Property Name="credit" Type="Edm.Decimal"/><Property Name="AccountingDate" Type="Edm.DateTimeOffset"/><Property Name="dataAreaId" Type="Edm.String"/></EntityType><EntityContainer><EntitySet Name="Companies" EntityType="Source.Company"/><EntitySet Name="Accounts" EntityType="Source.Account"/><EntitySet Name="Postings" EntityType="Source.Posting"/></EntityContainer></Schema></Edmx>"""
    calls, evidence = [], []

    def respond(r):
        calls.append(r)
        if r.url.path.endswith("$metadata"):
            return httpx.Response(200, content=xml, headers={"Content-Type": "application/xml"})
        if r.url.path.endswith("Companies"):
            value = [{"code": "USMF", "currency": "USD"}]
        elif r.url.path.endswith("Accounts"):
            value = [{"code": "cash", "name": "Cash"}]
        else:
            assert "2027-01-01T00:00:00Z" in r.url.params["$filter"]
            value = [
                {
                    "code": "cash",
                    "ref": "journal",
                    "id": "native-line",
                    "debit": "10",
                    "credit": "0",
                    "AccountingDate": "2026-10-01T00:00:00Z",
                    "dataAreaId": "USMF",
                }
            ]
        return httpx.Response(200, json={"value": value})

    async def preserve(resource, raw):
        evidence.append(resource)

    adapter = NativeAdapter(
        "dynamics",
        {
            "edition": "finance-odata",
            "base_url": "https://finance.example/data/",
            "directory_tenant": "directory",
            "company_id": "USMF",
            "functional_currency": "USD",
            "company_path": "Companies",
            "company_id_field": "code",
            "accounts_path": "Accounts",
            "ledger_path": "Postings",
            "mappings": {
                "coa": {"account_code": "code", "account_name": "name"},
                "gl": {
                    "account_code": "code",
                    "source_id": "id",
                    "journal_ref": "ref",
                    "posting_date": "AccountingDate",
                    "debit": "debit",
                    "credit": "credit",
                },
            },
        },
        {"access_token": "private-token"},
        ["https://finance.example"],
        preserve,
        httpx.MockTransport(respond),
    )
    try:
        result = [row async for row in adapter.extract(date(2026, 1, 1), date(2026, 12, 31), "USD")]
        assert result[-1][1]["source_id"] == "native-line" and "finance_metadata" in evidence
        assert all(r.url.host == "finance.example" for r in calls)
    finally:
        await adapter.close()


async def test_quickbooks_attachment_pagination_never_forwards_bearer_to_cdn():
    from app.modules.connectors.native_adapters import NativeAdapter

    calls, stored = [], []

    def respond(request):
        calls.append(request)
        if request.url.host == "approved-cdn.example":
            assert "authorization" not in request.headers
            return httpx.Response(
                200, content=b"%PDF-test", headers={"Content-Type": "application/pdf"}
            )
        items = (
            []
            if "STARTPOSITION 2" in request.url.params["query"]
            else [
                {
                    "Id": "1",
                    "ContentType": "application/pdf",
                    "TempDownloadUri": "https://approved-cdn.example/evidence?signature=test-only",
                    "AttachableRef": [{"EntityRef": {"type": "Invoice", "value": "10"}}],
                }
            ]
        )
        return httpx.Response(200, json={"QueryResponse": {"Attachable": items}})

    async def preserve(resource, raw):
        stored.append((resource, raw))

    adapter = NativeAdapter(
        "quickbooks",
        {"company_id": "1000", "functional_currency": "AED"},
        {"access_token": "api-only-token"},
        ["https://approved-cdn.example"],
        preserve,
        httpx.MockTransport(respond),
    )
    try:
        await adapter.start()
        result = await adapter.qbo_attachments("10", "invoice")
        assert result[0]["status"] == "binary_preserved" and len(calls) == 3
        assert any(
            resource == "Attachable/binary/1" and raw == b"%PDF-test" for resource, raw in stored
        )
        blocked = await adapter.attachment(
            {"Id": "2", "TempDownloadUri": "https://unapproved.example/file"}
        )
        assert "requires_operator_approval" in blocked["status"] and len(calls) == 3
    finally:
        await adapter.close()
