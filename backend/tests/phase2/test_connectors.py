from datetime import date

import httpx
import pytest

from app.modules.connectors.tally import export_request, parse_export
from app.modules.connectors.zoho import ConnectorError, ZohoConnector


@pytest.mark.parametrize("mode", ["ok", "rate", "refresh", "partial", "forbidden", "bad_region"])
async def test_zoho_pagination_refresh_errors(mode, monkeypatch):
    calls = []
    throttled = False

    async def sleep(seconds):
        pass

    monkeypatch.setattr("app.modules.connectors.zoho.asyncio.sleep", sleep)

    def respond(request):
        nonlocal throttled
        calls.append(request)
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(
                200, json={"access_token": "new-token", "api_domain": "https://www.zohoapis.ae"}
            )
        if mode == "forbidden":
            return httpx.Response(403)
        if mode == "rate" and not throttled:
            throttled = True
            return httpx.Response(429)
        if mode == "refresh" and request.headers.get("Authorization") == "Zoho-oauthtoken old":
            return httpx.Response(401)
        page = int(request.url.params.get("page", "1"))
        if mode == "partial" and page == 2:
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "chartofaccounts": [{"account_id": str(page), "account_name": "Synthetic"}],
                "page_context": {"page": page, "has_more_page": page == 1},
            },
        )

    if mode == "bad_region":
        with pytest.raises(ConnectorError):
            ZohoConnector("attacker.invalid", "id", "secret")
        return
    adapter = ZohoConnector(
        "ae", "id", "secret", "refresh", "old", transport=httpx.MockTransport(respond)
    )
    if mode in {"partial", "forbidden"}:
        with pytest.raises(ConnectorError):
            [page async for page in adapter.pages("chartofaccounts", "123")]
    else:
        pages = [page async for page in adapter.pages("chartofaccounts", "123")]
        assert len(pages) == 2 and pages[1]["raw"]["chartofaccounts"][0]["account_id"] == "2"
        assert all(r.url.host in {"www.zohoapis.ae", "accounts.zoho.ae"} for r in calls)
        if mode == "refresh":
            assert adapter.access_token == "new-token"


async def test_zoho_oauth_state_and_wrong_dc():
    adapter = ZohoConnector(
        "ae",
        "client",
        "secret",
        "refresh",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"access_token": "token", "api_domain": "https://www.zohoapis.com"}
            )
        ),
    )
    assert "accounts.zoho.ae" in adapter.authorization_url("https://example.com/callback", "x" * 32)
    with pytest.raises(ConnectorError):
        adapter.authorization_url("https://example.com", "short")
    with pytest.raises(ConnectorError):
        await adapter.token()


TALLY = b"""<ENVELOPE><BODY><DATA><COMPANYNAME>FICTIONAL Test</COMPANYNAME><LEDGER NAME="Cash"><PARENT>Cash-in-hand</PARENT></LEDGER><LEDGER NAME="Sales"><PARENT>Sales Accounts</PARENT></LEDGER><VOUCHER><GUID>voucher-1</GUID><DATE>20261226</DATE><NARRATION>Synthetic sale</NARRATION><ALLLEDGERENTRIES.LIST><LEDGERNAME>Cash</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-100.25</AMOUNT></ALLLEDGERENTRIES.LIST><ALLLEDGERENTRIES.LIST><LEDGERNAME>Sales</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>100.25</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER></DATA></BODY></ENVELOPE>"""


def test_tally_realistic_vouchers_and_request():
    result = parse_export(TALLY, "FICTIONAL Test", date(2026, 1, 1), date(2026, 12, 31))
    assert result["lines"][0]["debit"] == "100.25" and result["lines"][1]["credit"] == "100.25"
    assert not result["warnings"]
    request = export_request("A & B", "vouchers", date(2026, 1, 1), date(2026, 12, 31))
    assert b"A &amp; B" in request and b"AuditOSDateFilter" in request


@pytest.mark.parametrize(
    "content",
    [
        b"bad",
        b'<!DOCTYPE doc [<!ENTITY xx SYSTEM "file:///secret">]><doc>&xx;</doc>',
        TALLY.replace(b"voucher-1", b""),
        TALLY.replace(b"20261226", b"bad"),
        TALLY.replace(b"-100.25", b"USD 100"),
        TALLY.replace(b"FICTIONAL Test", b"Other company"),
    ],
)
def test_tally_rejects_bad_xml(content):
    with pytest.raises(ConnectorError):
        parse_export(content, "FICTIONAL Test", date(2026, 1, 1), date(2026, 12, 31))


def test_tally_missing_master_and_duplicate_id():
    content = TALLY.replace(b'<LEDGER NAME="Sales"><PARENT>Sales Accounts</PARENT></LEDGER>', b"")
    assert any(
        w["rule"] == "missing_ledger_master"
        for w in parse_export(content, "FICTIONAL Test", date(2026, 1, 1), date(2026, 12, 31))[
            "warnings"
        ]
    )
    from xml.etree.ElementTree import fromstring, tostring

    root = fromstring(TALLY)
    data = root.find(".//DATA")
    data.append(fromstring(tostring(data.find("VOUCHER"))))
    with pytest.raises(ConnectorError):
        parse_export(tostring(root), "FICTIONAL Test", date(2026, 1, 1), date(2026, 12, 31))
