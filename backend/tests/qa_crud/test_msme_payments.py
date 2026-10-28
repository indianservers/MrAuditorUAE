"""Real DB/source/review/export mechanics; fixtures do not qualify law or clients."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_msme_payments import TYPES, config, populations

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def test_msme_reviewed_sources_payment_result_export_and_withdrawal(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "msme-independent-reviewer")
    await grant(c, h, base, reviewer)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    catalogue = (await c.get(prefix + "/country-workflows", headers=h)).json()
    assert next(w for w in catalogue["items"] if w["id"] == "india-msme-payment-timing")[
        "available"
    ]
    assert "msme-invoices" in catalogue["source_contracts"]
    rows = populations()
    rows["invoices"][0].update(invoice_date="2026-04-01", delivery_date="2026-04-01")
    rows["bank"][0]["date"] = "2026-04-16"
    sources = {}
    for role, records in rows.items():
        totals = (
            {"INR": "-100"}
            if role == "bank"
            else {"INR": "100"}
            if role in {"invoices", "allocations"}
            else {}
        )
        sources[role] = await source(
            c, h, eid, records, "SYNTHETIC MSE " + role, TYPES[role], totals
        )
    payload = {
        **config(),
        "as_of": "2026-04-30",
        "obligation_month_start": "2026-04",
        "obligation_month_end": "2026-04",
        "settlement_start": "2026-04-01",
        "source_ids": {role: r["id"] for role, r in sources.items()},
    }
    await execute(c, h, eid, "country-workflow", payload, failed="Independently review all")
    for role, obj in sources.items():
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()
    payload["source_ids"] = {role: r["id"] for role, r in sources.items()}
    result = await execute(c, h, eid, "country-workflow", payload)
    row = result["body"]["rows"][0]
    assert row["due_date"] == "2026-04-16" and row["state"] == "MATCHED"
    assert row["late_paid_amount"] == row["overdue_unpaid_amount"] == "0"
    assert (await decision(c, h, eid, result)).status_code == 403
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    exported = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.content))
    exported_rows = list(workbook["Rows"].values)
    assert len(exported_rows) == 2
    due_column = exported_rows[0].index("due_date")
    assert exported_rows[1][due_column] == "2026-04-16"
    assert any("SYNTHETIC" in str(cell) for line in exported_rows for cell in line)
    original = deepcopy(result["body"])
    rejected = await decision(c, reviewer[0], eid, sources["assessments"], "reject")
    assert rejected.status_code == 201, rejected.text
    stale = (await c.get(prefix + "/events/" + result["id"], headers=h)).json()
    assert stale["freshness"] == "STALE" and stale["body"] == original


async def test_msme_sources_and_workflow_are_not_available_for_uae(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, _ = await setup(c)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    catalogue = (await c.get(prefix + "/country-workflows", headers=h)).json()
    assert not next(w for w in catalogue["items"] if w["id"] == "india-msme-payment-timing")[
        "available"
    ]
    assert not any(t.startswith("msme-") for t in catalogue["source_contracts"])
    await source(
        c,
        h,
        eid,
        populations()["invoices"],
        "SYNTHETIC wrong-country MSE",
        "msme-invoices",
        {"INR": "100"},
        failed="India engagement",
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**config(), "as_of": "2026-06-30"},
        failed="India engagement",
    )
