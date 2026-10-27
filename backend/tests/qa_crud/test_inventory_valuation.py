import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_inventory_valuation import population

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


async def prepare(c, h, eid, base, reviewer, currency="AED", positions=1):
    documents = {}
    for kind in ("cost", "nrv"):
        record = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-inventory-{kind}.txt",
                    f"SYNTHETIC assessed inventory {kind} evidence only; cost 100 per PCS, selling price 120, completion 5 and selling costs 5; reporting date 2026-06-30".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        documents[kind] = {**uploaded.json(), "record": record["id"]}
    rows = population(currency)
    rows["books"] = [
        {**rows["books"][0], "id": f"SYN-BOOK-{index}", "lot": f"LOT-{index:04d}"}
        for index in range(positions)
    ]
    rows["valuations"] = [
        {
            **rows["valuations"][0],
            "id": f"SYN-PRICE-{index}",
            "lot": f"LOT-{index:04d}",
            "cost_evidence_version_id": "",
            "cost_source_sha256": "",
            "nrv_evidence_version_id": "",
            "nrv_source_sha256": "",
        }
        for index in range(positions)
    ]
    rows["controls"][0]["amount"] = str(1000 * positions)
    selected = {}
    for role, table in (
        ("books", "stock"),
        ("valuations", "inventory-valuations"),
        ("controls", "accounting-controls"),
    ):
        options = {}
        if role == "books":
            options["inventory_quantity_controls"] = [
                {
                    **{field: row[field] for field in ("site", "sku", "lot", "uom", "currency")},
                    "expected_rows": 1,
                    "positive_quantity": "10",
                    "negative_quantity": "0",
                }
                for row in rows[role]
            ]
        elif role == "valuations":
            options = {
                "inventory_valuation_controls": [
                    {
                        "currency": currency,
                        "expected_rows": positions,
                        "cost_value": str(1000 * positions),
                        "nrv_value": str(1100 * positions),
                    }
                ],
                "inventory_cost_document_version_id": documents["cost"]["id"],
                "inventory_nrv_document_version_id": documents["nrv"]["id"],
            }
        totals = {currency: str(1000 * positions)} if role == "controls" else {}
        imported = await source(
            c, h, eid, rows[role], "SYNTHETIC inventory values " + role, table, totals, **options
        )
        reviewed = await decision(c, reviewer[0], eid, imported)
        assert reviewed.status_code == 201, reviewed.text
        selected[role] = reviewed.json()["id"]
    payload = {
        "workflow": "inventory-valuation-control",
        "source_ids": selected,
        "as_of": "2026-06-30",
        "review_through": "2026-07-15",
        "inventory_gl_basis": "gross-cost",
        "inventory_scope_assessment": "Independent fictional cost policy, quantity populations, account mapping and framework applicability assessment; no physical verification",
        "title": "SYNTHETIC inventory valuation and GL control",
        "rationale": "Retained independent cost and NRV evidence and explicitly declared gross-cost GL basis",
        "currency": currency,
    }
    return {"engagement": eid, "sources": selected, "documents": documents, "payload": payload}


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_inventory_valuation_review_export_and_backing_document_staleness(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "inventory-values-source-reviewer")
    await grant(c, h, base, reviewer)
    fixture = await prepare(c, h, eid, base, reviewer, currency)
    result = await execute(c, h, eid, "country-workflow", fixture["payload"])
    assert result["body"]["exception_count"] == 0 and not result["body"]["blocked"]
    assert (
        result["body"]["rows"][0]["valuation_evidence"]["cost_source_sha256"]
        == fixture["documents"]["cost"]["sha256"]
    )
    final = await actor(h, "Firm Administrator", "inventory-values-final-reviewer")
    await grant(c, h, base, final)
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, final[0], eid, result)
    assert approved.status_code == 201, approved.text
    result = approved.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    for view, kind in (("valuations", "valuation-test"), ("gl-controls", "gl-control")):
        response = await c.get(prefix + result["id"] + f"?inventory_view={view}&limit=1", headers=h)
        assert response.status_code == 200, response.text
        assert (
            response.json()["collection_totals"]["rows"] == 1
            and response.json()["body"]["rows"][0]["kind"] == kind
        )
    exported = await c.get(prefix + result["id"] + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    values = [
        value
        for sheet in load_workbook(io.BytesIO(exported.content))
        for row in sheet.values
        for value in row
    ]
    assert "SKU-001" in values and "INV-001" in values
    updated = await c.post(
        base + "/evidence-files/" + fixture["documents"]["nrv"]["record"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-nrv-updated.txt",
                b"SYNTHETIC revised price evidence requiring a new assessment",
                "text/plain",
            )
        },
    )
    assert updated.status_code == 201, updated.text
    assert (await c.get(prefix + result["id"], headers=h)).json()["freshness"] == "STALE"
    await execute(c, h, eid, "country-workflow", fixture["payload"], failed="source is stale")


async def test_gl_view_is_independent_of_first_hundred_valuation_rows(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "inventory-paging-reviewer")
    await grant(c, h, base, reviewer)
    fixture = await prepare(c, h, eid, base, reviewer, positions=121)
    result = await execute(c, h, eid, "country-workflow", fixture["payload"])
    assert result["collection_totals"]["rows"] == 122 and len(result["body"]["rows"]) == 100
    response = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}?inventory_view=gl-controls&limit=1",
        headers=h,
    )
    assert response.status_code == 200, response.text
    assert response.json()["body"]["rows"][0]["recorded_book_value"] == "121000"
    assert response.json()["collection_totals"]["rows"] == 1


async def test_inventory_valuation_rejects_unreviewed_books_wrong_hash_and_self_supporting_file(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "inventory-negative-reviewer")
    await grant(c, h, base, reviewer)
    fixture = await prepare(c, h, eid, base, reviewer)
    rows = population()
    rows["books"][0]["lot"] = "LOT-0000"
    quantity = [
        {
            "site": "SYN-WAREHOUSE",
            "sku": "SKU-001",
            "lot": "LOT-0000",
            "uom": "PCS",
            "currency": "AED",
            "expected_rows": 1,
            "positive_quantity": "10",
            "negative_quantity": "0",
        }
    ]
    unreviewed = await source(
        c,
        h,
        eid,
        rows["books"],
        "SYNTHETIC unreviewed inventory",
        "stock",
        {},
        inventory_quantity_controls=quantity,
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**fixture["payload"], "source_ids": {**fixture["sources"], "books": unreviewed["id"]}},
        failed="Independently review inventory",
    )
    rows["valuations"][0].update(
        cost_evidence_version_id=fixture["documents"]["cost"]["id"],
        cost_source_sha256="0" * 64,
        nrv_evidence_version_id=fixture["documents"]["nrv"]["id"],
        nrv_source_sha256=fixture["documents"]["nrv"]["sha256"],
    )
    controls = [{"currency": "AED", "expected_rows": 1, "cost_value": "1000", "nrv_value": "1100"}]
    await source(
        c,
        h,
        eid,
        rows["valuations"],
        "SYNTHETIC wrong cost hash",
        "inventory-valuations",
        {},
        inventory_valuation_controls=controls,
        failed="hash",
    )
    selected = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{fixture['sources']['valuations']}",
        headers=h,
    )
    evidence = selected.json()["body"]["evidence_version_id"]
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": evidence,
            "table_type": "inventory-valuations",
            "label": "SYNTHETIC self-supporting cost assessment",
            "expected_rows": 1,
            "inventory_valuation_controls": controls,
            "inventory_cost_document_version_id": evidence,
            "inventory_nrv_document_version_id": fixture["documents"]["nrv"]["id"],
        },
        failed="distinct retained cost/NRV documents",
    )
