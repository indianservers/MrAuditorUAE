import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import (
    csv_bytes,
    decision,
    double_boundaries,
    execute,
    source,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_payable_open_item_reuse_sign_scope_control_and_staleness(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    rows = [
        {
            "reference": "INV-1",
            "currency": "AED",
            "open_amount": "-100",
            "counterparty": "SUPPLIER-1",
            "account_code": "AP-1",
            "document_date": "2026-06-01",
            "due_date": "2026-06-30",
            "balance_date": "2026-06-30",
            "document_type": "invoice",
            "segment": "SYNTHETIC",
        },
        {
            "reference": "CN-1",
            "currency": "AED",
            "open_amount": "20",
            "counterparty": "SUPPLIER-1",
            "account_code": "AP-1",
            "document_date": "2026-06-05",
            "due_date": "2026-06-30",
            "balance_date": "2026-06-30",
            "document_type": "credit-note",
            "segment": "SYNTHETIC",
        },
    ]
    content = csv_bytes(rows)
    upload = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-credit-negative-payables.csv", content, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    table = await execute(
        c,
        h,
        eid,
        "source-table",
        {"evidence_version_id": upload.json()["id"], "table_kind": "open-items"},
    )
    assert table["body"]["rows"][1]["document_type"] == "credit-note"
    reviewer = await actor(h, "Firm Administrator", "open-table-reviewer")
    second = await actor(h, "Firm Administrator", "open-bridge-reviewer")
    for person in (reviewer, second):
        await grant(c, h, base, person)
    approved = await decision(c, reviewer[0], eid, table)
    assert approved.status_code == 201, approved.text
    payload = {
        "supporting_table_id": approved.json()["id"],
        "evidence_version_id": upload.json()["id"],
        "supporting_scope_assessment": "Reviewed complete payable population, credit-negative source basis and balance date",
        "account_identifier": "AP-1",
        "table_type": "audit-open-items",
        "label": "Synthetic reviewed payable bridge",
        "supporting_side": "payable",
        "supporting_balance_date": "2026-06-30",
        "supporting_amount_sign": "reverse-sign",
        "expected_rows": 2,
        "control_totals": {"AED": "80"},
    }
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {**payload, "supporting_amount_sign": "as-reported"},
        failed="Invalid CSV row",
    )
    prepared = await execute(c, h, eid, "workflow-source", payload)
    assert [row["amount"] for row in prepared["body"]["rows"]] == ["100", "-20"]
    assert prepared["body"]["rows"][0]["supporting_reported_open_amount"] == "-100"
    assert prepared["body"]["rows"][0]["supporting_balance_date_basis"] == "SOURCE_FIELD"
    assert (await decision(c, reviewer[0], eid, prepared)).status_code == 403
    reviewed = await decision(c, second[0], eid, prepared)
    assert reviewed.status_code == 201, reviewed.text
    controls = await source(
        c,
        h,
        eid,
        [
            {
                "id": "GL-AP",
                "account": "AP-1",
                "side": "payable",
                "currency": "AED",
                "as_of": "2026-06-30",
                "amount": "80",
            }
        ],
        "Synthetic independent AP control",
        "balance-controls",
        {"AED": "80"},
    )
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "subledger-control",
            "source_ids": {"items": reviewed.json()["id"], "controls": controls["id"]},
            "as_of": "2026-06-30",
            "title": "Synthetic payable control bridge",
            "rationale": "Reviewed item evidence and independent control-account balance",
        },
    )
    assert result["body"]["exception_count"] == 0 and not result["body"]["blocked"]
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    replaced = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-payables-v2.csv", content + b"\n", "text/csv")},
    )
    assert replaced.status_code == 201, replaced.text
    for identifier in (approved.json()["id"], reviewed.json()["id"], result["id"]):
        detail = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{identifier}", headers=h
        )
        assert detail.status_code == 200 and detail.json()["freshness"] == "STALE"
