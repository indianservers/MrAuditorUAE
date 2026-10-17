"""Optional authorized live smoke tests; never enabled by ordinary CI or local pytest."""

import os
from datetime import date

import httpx
import pytest

from app.modules.connectors.tally import export_request, parse_export
from app.modules.connectors.zoho import ZohoConnector


@pytest.mark.skipif(
    os.getenv("LIVE_ZOHO_SMOKE") != "1",
    reason="Live Zoho requires explicit opt-in and authorized OAuth credentials",
)
async def test_live_zoho_organizations():
    connector = ZohoConnector(
        os.environ["ZOHO_REGION"],
        os.environ["ZOHO_CLIENT_ID"],
        os.environ["ZOHO_CLIENT_SECRET"],
        os.environ["ZOHO_REFRESH_TOKEN"],
    )
    data = await connector.get("organizations", {})
    assert data["code"] == 0 and isinstance(data["organizations"], list)


@pytest.mark.skipif(
    os.getenv("LIVE_TALLY_SMOKE") != "1",
    reason="Live Tally requires an explicitly authorized local installation",
)
async def test_live_tally_export():
    company = os.environ["TALLY_COMPANY"]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "http://127.0.0.1:9000",
            content=export_request(company, "ledgers", date(2026, 1, 1), date(2026, 12, 31)),
        )
        response.raise_for_status()
    assert isinstance(
        parse_export(response.content, company, date(2026, 1, 1), date(2026, 12, 31))["masters"],
        dict,
    )
