"""Seed the owned disposable workflow database for browser verification only.

All documents are synthetic. Malware scanning and broker dispatch are explicit
in-process test doubles during fixture preparation, never server configuration.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only the owned disposable country workflow test database is allowed")
    import pytest

    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import setup
    from tests.qa_crud.test_country_workflows import (
        bank_payload,
        double_boundaries,
        execute,
        source,
    )
    from tests.unit.country_workflow_cases import document, return_box, transaction

    fixture = environment.__wrapped__()
    client = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        h, opts, eid, _base = await setup(client)
        book = await source(client, h, eid, [transaction()], "SYNTHETIC UAE cashbook")
        statement = await source(
            client,
            h,
            eid,
            [transaction(id="S1", amount="95")],
            "SYNTHETIC UAE bank",
            totals={"AED": "95"},
        )
        result = await execute(
            client,
            h,
            eid,
            "country-workflow",
            bank_payload(book, statement, statement_closing="95"),
        )
        vb = await source(
            client,
            h,
            eid,
            [return_box(id="B1")],
            "SYNTHETIC UAE VAT register boxes",
            "return-boxes",
            {"AED": "5"},
        )
        vr = await source(
            client,
            h,
            eid,
            [return_box(id="R1", tax="4")],
            "SYNTHETIC UAE VAT201 boxes",
            "return-boxes",
            {"AED": "4"},
        )
        vat_result = await execute(
            client,
            h,
            eid,
            "country-workflow",
            {
                "workflow": "uae-vat-return",
                "source_ids": {"books": vb["id"], "return": vr["id"]},
                "as_of": "2026-06-30",
                "title": "SYNTHETIC UAE VAT201 box bridge",
                "rationale": "Synthetic independently prepared book allocations and return boxes",
                "required_boxes": ["1:DXB"],
            },
        )
        e = await client.post(
            "/api/v1/entities",
            headers=h,
            json={
                "client_id": opts["client_id"],
                "name": "SYNTHETIC Indian entity",
                "country": "IN",
                "jurisdiction": "Synthetic test only",
                "functional_currency": "INR",
                "presentation_currency": "INR",
            },
        )
        assert e.status_code == 201, e.text
        p = await client.post(
            "/api/v1/financial-periods",
            headers=h,
            json={
                "entity_id": e.json()["id"],
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
            },
        )
        assert p.status_code == 201, p.text
        engagement = await client.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": e.json()["id"],
                "period_id": p.json()["id"],
                "name": "SYNTHETIC India workflow pilot",
                "engagement_type": "External Audit",
            },
        )
        assert engagement.status_code == 201, engagement.text
        india = engagement.json()["id"]
        d = document(currency="INR", component="CGST")
        a = await source(
            client,
            h,
            india,
            [d],
            "SYNTHETIC Indian purchase register",
            "tax-documents",
            {"INR": "5"},
        )
        b = await source(
            client,
            h,
            india,
            [document(id="R1", currency="INR", component="CGST", tax="4")],
            "SYNTHETIC Indian return schedule",
            "tax-documents",
            {"INR": "4"},
        )
        gst = await execute(
            client,
            h,
            india,
            "country-workflow",
            {
                "workflow": "india-gst",
                "source_ids": {"books": a["id"], "return": b["id"]},
                "as_of": "2026-06-30",
                "tax_year_start": "2026-04-01",
                "title": "SYNTHETIC India GST review",
                "rationale": "Synthetic independent canonical return and purchase schedules",
            },
        )
        dest = ROOT / ".local-runtime/country-workflows/fixture.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "scanner_test_double": True,
                    "broker_test_double": True,
                    "uae_engagement": eid,
                    "uae_result": result["id"],
                    "uae_vat_result": vat_result["id"],
                    "uae_book_source": book["id"],
                    "uae_statement_source": statement["id"],
                    "india_engagement": india,
                    "india_result": gst["id"],
                    "tenant": h["X-Tenant-ID"],
                },
                indent=2,
            )
        )
        print(
            "Prepared explicitly synthetic UAE/India browser fixtures in the owned disposable database"
        )
    finally:
        patch.undo()
        await fixture.aclose()


asyncio.run(main())
