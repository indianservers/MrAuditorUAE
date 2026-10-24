import json
import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_india_gstr2b_source import payload
from tests.unit.test_india_invoice_source import BUYER, SELLER

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_native_gstr2b_retained_file_sparse_books_review_and_export(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "gst-source-independent-reviewer")
    await grant(c, h, base, reviewer)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    statement = payload()
    statement["itcsumm"] = {"itcavl": {"nonrevsup": {"b2b": {"igst": 18.0}}}}
    content = json.dumps(statement).encode()
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-gstr2b.json", content, "application/json")},
    )
    assert uploaded.status_code == 201, uploaded.text
    native = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "file_format": "india-gstr2b-json",
            "table_type": "tax-documents",
            "gst_registration": BUYER,
            "gst_period": "2026-06",
            "expected_documents": 1,
            "expected_rows": 4,
            "control_totals": {"INR": "18"},
            "label": "Synthetic original GSTR-2B statement",
        },
    )
    assert native["body"]["native_metadata"]["document_count"] == 1
    assert native["body"]["native_metadata"]["section_document_counts"] == {"b2b": 1}
    assert native["body"]["review_status"] == "UNVERIFIED"
    assert (
        native["body"]["native_metadata"]["itc_summary"]["itcavl"]["nonrevsup"]["b2b"]["igst"]
        == "18.0"
    )
    original = await c.get(
        base + "/evidence-files/" + record["id"] + "/" + uploaded.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == content
    book = {
        "id": "BOOK-PURCHASE-1",
        "registration": BUYER,
        "counterparty": SELLER,
        "reference": "SYNTHETIC-1",
        "period": "2026-06",
        "date": "2026-06-15",
        "currency": "INR",
        "document_type": "invoice",
        "net": "100",
        "tax": "18",
        "component": "IGST",
        "status": "active",
    }
    books = await source(
        c, h, eid, [book], "Synthetic independent purchase register", "tax-documents", {"INR": "18"}
    )
    reviewed = {}
    for role, population in {"books": books, "return": native}.items():
        approved = await decision(c, reviewer[0], eid, population)
        assert approved.status_code == 201, approved.text
        reviewed[role] = approved.json()["id"]
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "india-gst",
            "source_ids": reviewed,
            "as_of": "2026-06-30",
            "currency": "INR",
            "title": "Synthetic native GSTR-2B comparison",
            "rationale": "Independently reviewed books and original source document components",
        },
    )
    assert result["body"]["exception_count"] == 0
    assert len(result["body"]["rows"]) == 4
    assert all(
        row["legal_credit_eligibility"] == "NOT_DETERMINED" for row in result["body"]["rows"]
    )
    export = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}/export?format=xlsx",
        headers=h,
    )
    assert export.status_code == 200 and export.content.startswith(b"PK")
    formats = await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    assert next(
        item for item in formats.json()["source_formats"] if item["id"] == "india-gstr2b-json"
    )["available"]


async def test_gstr2b_partial_provider_response_cannot_create_a_zero_or_completed_source(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-paged-gstr2b.json",
                b'{"code":200,"data":{"status_cd":"3","data":{"fc":2}}}',
                "application/json",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "file_format": "india-gstr2b-json",
            "table_type": "tax-documents",
            "gst_registration": BUYER,
            "gst_period": "2026-06",
            "expected_documents": 0,
            "expected_rows": 0,
            "control_totals": {"INR": "0"},
            "nil_reason": "Synthetic invalid attempt to treat an incomplete response as nil",
            "label": "Synthetic incomplete provider download",
        },
        failed="complete successful document",
    )
