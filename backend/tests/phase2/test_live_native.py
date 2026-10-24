"""Opt-in, read-only direct connector smoke against independently supplied controls."""

import json
import os
import uuid
from datetime import date
from decimal import Decimal, localcontext

import pytest

from app.modules.accounting.schemas import ImportOptions
from app.modules.connectors.native_adapters import NativeAdapter
from app.modules.ingestion.parser import normalize


@pytest.mark.skipif(
    os.getenv("LIVE_NATIVE_CONNECTOR") != "1",
    reason="Requires explicit opt-in, vendor credentials and independently exported control totals",
)
async def test_live_direct_api_ledger():
    provider = os.environ["NATIVE_PROVIDER"]
    config = json.loads(os.environ["NATIVE_CONFIG_JSON"])
    credentials = json.loads(os.environ["NATIVE_CREDENTIALS_JSON"])
    start = date.fromisoformat(os.environ["ACCOUNTING_PERIOD_START"])
    end = date.fromisoformat(os.environ["ACCOUNTING_PERIOD_END"])
    currency = os.environ["ACCOUNTING_FUNCTIONAL_CURRENCY"]
    allowed = json.loads(os.getenv("CONNECTOR_ALLOWED_ORIGINS", "[]"))

    async def preserve(resource, raw):
        # No live source records or credentials are printed by this smoke check.
        pass

    adapter = NativeAdapter(provider, config, credentials, allowed, preserve)
    count = 0
    debit = credit = Decimal(0)
    identities = set()
    options = ImportOptions.model_validate(
        {
            "client_id": uuid.UUID(int=0),
            "entity_id": uuid.UUID(int=0),
            "period_id": uuid.UUID(int=0),
            "kind": "gl",
            "source_system": provider,
            "currency": currency,
        }
    )
    try:
        with localcontext() as numeric:
            numeric.prec = 48
            async for kind, row in adapter.extract(start, end, currency):
                if kind != "gl":
                    continue
                canonical, _ = normalize(row, options, start, end, currency, count + 2)
                assert canonical["source_id"] not in identities
                identities.add(canonical["source_id"])
                count += 1
                debit += Decimal(canonical["base_debit"])
                credit += Decimal(canonical["base_credit"])
        assert count == int(os.environ["NATIVE_EXPECTED_GL_ROWS"])
        assert debit == Decimal(os.environ["NATIVE_EXPECTED_GL_DEBIT"])
        assert credit == Decimal(os.environ["NATIVE_EXPECTED_GL_CREDIT"])
        assert debit == credit
    finally:
        await adapter.close()
