"""Real DB, HTTP, object storage and job execution; scanner/broker are explicit test doubles."""

import csv
import io
import os
import uuid

import pytest
from openpyxl import load_workbook

from app.modules.intelligence.jobs import process
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1",
    reason="Dedicated disposable migrated test database required",
)


def csv_bytes(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def double_boundaries(monkeypatch, scan="CLEAN"):
    from app.api.v1 import audit_evidence
    from app.workers.intelligence import run

    monkeypatch.setattr(audit_evidence, "scan", lambda stream: scan)
    monkeypatch.setattr(run, "apply_async", lambda **kwargs: None)


async def execute(c, h, eid, operation, payload, key=None, failed=None):
    path = f"/api/v1/intelligence/engagements/{eid}"
    key = key or str(uuid.uuid4())
    data = {"operation": operation, "payload": payload}
    submitted = await c.post(path + "/jobs", headers={**h, "Idempotency-Key": key}, json=data)
    assert submitted.status_code == 202, submitted.text
    await process(submitted.json()["id"], h["X-Tenant-ID"])
    job = (await c.get(path + "/jobs/" + submitted.json()["id"], headers=h)).json()
    if failed:
        assert job["status"] == "failed" and job["result_id"] is None, job
        assert failed in job["error_details"]["message"], job
        return job
    assert job["status"] == "completed", job.get("error_details") or job
    return (await c.get(path + "/events/" + job["result_id"], headers=h)).json()


async def source(
    c, h, eid, rows, label, table_type="transactions", totals=None, failed=None, **source_options
):
    base = f"/api/v1/engagements/{eid}/audit"
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": (label + ".csv", csv_bytes(rows), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "table_type": table_type,
            "label": label,
            "expected_rows": len(rows),
            "control_totals": totals if totals is not None else {"AED": "100"},
            **source_options,
        },
        failed=failed,
    )


async def decision(c, h, eid, obj, action="approve", **fields):
    return await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{obj['id']}/review",
        headers=h,
        json={
            "expected_version": obj["version"],
            "action": action,
            "comments": "Synthetic independently documented evidence assessment",
            **fields,
        },
    )


def bank_payload(book, statement, **changes):
    return {
        "workflow": "bank-brs",
        "source_ids": {"books": book["id"], "statement": statement["id"]},
        "as_of": "2026-06-30",
        "title": "SYNTHETIC account reconciliation",
        "rationale": "Controlled independent synthetic book and bank populations",
        "account": "BANK-1",
        "currency": "AED",
        "book_opening": "0",
        "book_closing": "100",
        "statement_opening": "0",
        "statement_closing": "100",
        **changes,
    }


async def test_real_sources_queue_review_export_lineage_and_stale_propagation(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "country-reviewer")
    await grant(c, h, base, reviewer)
    book = await source(c, h, eid, [transaction()], "Book")
    statement = await source(c, h, eid, [transaction(id="S1")], "Statement")
    result = await execute(c, h, eid, "country-workflow", bank_payload(book, statement))
    assert result["body"]["control_comparison"]["unexplained_bridge_residual"] == "0"
    assert (await decision(c, h, eid, result)).status_code == 403
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409
    reviewed = []
    for obj in [book, statement]:
        response = await decision(c, reviewer[0], eid, obj)
        assert response.status_code == 201, response.text
        reviewed.append(response.json())
    original_path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    assert (await c.get(original_path, headers=h)).json()["freshness"] == "STALE"
    current = await execute(
        c, h, eid, "country-workflow", bank_payload(*reviewed), key="country-idempotent"
    )
    duplicate = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/jobs",
        headers={**h, "Idempotency-Key": "country-idempotent"},
        json={"operation": "country-workflow", "payload": bank_payload(*reviewed)},
    )
    assert duplicate.status_code == 202 and duplicate.json()["result_id"] == current["id"]
    approved = await decision(c, reviewer[0], eid, current)
    assert approved.status_code == 201, approved.text
    item = approved.json()
    export = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{item['id']}/export?format=xlsx", headers=h
    )
    assert export.status_code == 200, export.text
    workbook = load_workbook(io.BytesIO(export.content))
    assert workbook["Source and review"]["A1"].value == "Firm"
    paper = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{item['id']}/working-paper",
        headers=h,
        json={
            "reference": "BANK-SYNTHETIC",
            "title": "Synthetic BRS",
            "objective": "Document actual bank evidence and outstanding items",
        },
    )
    assert paper.status_code == 201, paper.text
    graph = await c.get(f"/api/v1/engagements/{eid}/audit/graph", headers=h)
    assert graph.status_code == 200 and any(
        n["kind"] == "intelligence:country-workflow" for n in graph.json()["nodes"]
    )
    assert (
        await c.get(original_path, headers={**h, "X-Tenant-ID": str(uuid.uuid4())})
    ).status_code == 403
    newer = await decision(c, reviewer[0], eid, reviewed[0], action="reject")
    assert newer.status_code == 201, newer.text
    final = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{item['id']}", headers=h)
    ).json()
    assert final["freshness"] == "STALE" and final["sha256"] == item["sha256"]


async def test_quarantine_malformed_controls_country_and_identical_content_fail_closed(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch, scan="QUARANTINED")
    h, _, eid, _ = await setup(c)
    await source(c, h, eid, [transaction()], "Quarantined", failed="quarantined")
    double_boundaries(monkeypatch)
    await source(
        c, h, eid, [transaction()], "Bad controls", totals={"AED": "99"}, failed="control totals"
    )
    a = await source(c, h, eid, [transaction()], "Independent A")
    b = await source(c, h, eid, [transaction()], "Same content B")
    await execute(
        c, h, eid, "country-workflow", bank_payload(a, b), failed="Identical source files"
    )
    independent = await source(c, h, eid, [transaction(id="S1")], "Independent C")
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(a, independent, as_of="2027-06-30"),
        failed="engagement period",
    )
    config = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    ).json()
    assert config["country"] == "AE"
    assert not next(w for w in config["items"] if w["id"] == "india-gst")["available"]
    data = bank_payload(a, independent)
    data["workflow"] = "india-gst"
    await execute(c, h, eid, "country-workflow", data, failed="engagement country")


async def test_unexplained_balance_blocker_cannot_be_overridden_by_review(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "country-controls-reviewer")
    await grant(c, h, base, reviewer)
    a = await source(c, h, eid, [transaction()], "Book controls")
    b = await source(
        c, h, eid, [transaction(id="S1", amount="95")], "Statement controls", totals={"AED": "95"}
    )
    result = await execute(c, h, eid, "country-workflow", bank_payload(a, b))
    assert result["body"]["blocked"]
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409
    row = result["body"]["rows"][0]
    accepted = await decision(c, h, eid, result, action="accept", item_id=row["id"])
    assert accepted.status_code == 201, accepted.text
    assert (await decision(c, reviewer[0], eid, accepted.json())).status_code == 409


async def test_committed_ledger_source_reuses_snapshot_lineage_and_currency_controls(
    environment, monkeypatch
):
    from decimal import Decimal

    from tests.phase2.test_pipeline import committed

    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, _ = await setup(c)
    _, snapshot = await committed(c, h, options)
    tb = (
        await c.get("/api/v1/accounting/trial-balance", headers=h, params={"snapshot_id": snapshot})
    ).json()
    cash = next(r for r in tb["items"] if r["code"] == "100")
    payload = {
        "snapshot_id": snapshot,
        "account_ids": [cash["account_id"] if "account_id" in cash else cash["id"]],
        "bank_account": "BANK-1",
        "currency": "AED",
        "label": "SYNTHETIC committed bank ledger",
        "as_of": "2026-12-31",
    }
    source_result = await execute(c, h, eid, "workflow-ledger", payload)
    assert source_result["kind"] == "workflow-source"
    assert source_result["body"]["row_count"] == 1
    assert Decimal(source_result["body"]["control_totals"]["AED"]) == Decimal("-100.20")
    assert source_result["body"]["rows"][0]["source_record_id"]
    assert any(
        d["type"] == "snapshot" and d["id"] == snapshot for d in source_result["dependencies"]
    )
    await execute(
        c, h, eid, "workflow-ledger", {**payload, "currency": "USD"}, failed="functional-currency"
    )
