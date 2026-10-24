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
    os.getenv("LIVE_ZOHO_LEDGER_SMOKE") != "1",
    reason="Full ledger smoke needs authorized read-only access and independent source totals",
)
async def test_live_zoho_ledger_against_source_controls():
    from decimal import Decimal

    from app.modules.accounting.schemas import ImportOptions
    from app.modules.connectors.ledger import zoho_ledger_row
    from app.modules.ingestion.parser import normalize

    start = date.fromisoformat(os.environ["ACCOUNTING_PERIOD_START"])
    end = date.fromisoformat(os.environ["ACCOUNTING_PERIOD_END"])
    currency = os.environ["ACCOUNTING_FUNCTIONAL_CURRENCY"]
    organization = os.environ["ZOHO_ORGANIZATION_ID"]
    connector = ZohoConnector(
        os.environ["ZOHO_REGION"],
        os.environ["ZOHO_CLIENT_ID"],
        os.environ["ZOHO_CLIENT_SECRET"],
        os.environ["ZOHO_REFRESH_TOKEN"],
    )
    options = ImportOptions(
        client_id="00000000-0000-0000-0000-000000000000",
        entity_id="00000000-0000-0000-0000-000000000000",
        period_id="00000000-0000-0000-0000-000000000000",
        source_system="zoho",
        currency=currency,
    )
    seen = set()
    debit = credit = Decimal(0)
    async for chart in connector.pages(
        "chartofaccounts", organization, {"filter_by": "AccountType.All"}
    ):
        for account in chart["raw"]["chartofaccounts"]:
            async for page in connector.pages(
                "chartofaccounts/accounttransactions",
                organization,
                {
                    "account_id": account["account_id"],
                    "date_start": str(start),
                    "date_end": str(end),
                    "filter_by": "TransactionType.All",
                },
            ):
                for item in page["raw"]["transactions"]:
                    row = zoho_ledger_row(item, account, start, end)
                    assert row["source_id"] not in seen
                    seen.add(row["source_id"])
                    canonical, _ = normalize(row, options, start, end, currency, len(seen))
                    debit += Decimal(canonical["base_debit"])
                    credit += Decimal(canonical["base_credit"])
    assert len(seen) == int(os.environ["ZOHO_EXPECTED_GL_ROWS"])
    assert debit == Decimal(os.environ["ZOHO_EXPECTED_GL_DEBIT"])
    assert credit == Decimal(os.environ["ZOHO_EXPECTED_GL_CREDIT"])
    assert debit == credit


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
