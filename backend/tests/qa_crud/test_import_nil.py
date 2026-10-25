"""Retained nil evidence, review boundaries, exact controls and recursive staleness."""

import csv
import hashlib
import io
import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_import_vat import line

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required")


@pytest.mark.parametrize("mixed", [False, True])
async def test_nil_import_retained_context_review_bridge_and_staleness(environment, monkeypatch, mixed):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "nil-import-reviewer")
    await grant(c, h, base, reviewer)

    async def upload(label, raw):
        record = await create(c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"})
        response = await c.post(base + "/evidence-files/" + record["id"], headers=h,
                                files={"file": (label + ".csv", raw, "text/csv")})
        assert response.status_code == 201, response.text
        return record, response.json()

    raw = b"SYNTHETIC nil import supporting assessment,not client evidence\nno adjustments,independently assessed\n"
    context_record, context = await upload("SYNTHETIC nil context", raw)
    selected, unreviewed = {}, {}
    for role in ("customs", "portal", "books"):
        if mixed:
            row = line(evidence_reference="SYNTHETIC-" + role)
            prepared = await source(c, h, eid, [row], "SYNTHETIC " + role, table_type="import-vat-lines", totals={"AED": "50"}, import_taxable_base_control="1000")
        else:
            buffer = io.StringIO()
            csv.DictWriter(buffer, fieldnames=list(line())).writeheader()
            _, document = await upload("SYNTHETIC empty " + role, buffer.getvalue().encode())
            prepared = await execute(c, h, eid, "workflow-source", {
                "evidence_version_id": document["id"], "table_type": "import-vat-lines",
                "label": "SYNTHETIC empty " + role, "expected_rows": 0,
                "nil_reason": "Independently assessed synthetic nil import population",
                "control_totals": {"AED": "0"}, "import_taxable_base_control": "0",
            })
        unreviewed[role] = prepared["id"]
        reviewed = await decision(c, reviewer[0], eid, prepared)
        assert reviewed.status_code == 201, reviewed.text
        selected[role] = reviewed.json()["id"]
    payload = {
        "workflow": "uae-import-vat", "source_ids": selected, "as_of": "2026-06-30",
        "title": "SYNTHETIC nil import comparison", "rationale": "Explicit assessed nil populations and retained independent scope evidence",
        "import_nil_scope": {
            "registration": "100000000000001", "period_start": "2026-04-01", "period_end": "2026-06-30",
            "kinds": ["adjustment"] if mixed else ["declaration", "adjustment"],
            "context_evidence_version_id": context["id"], "context_sha256": hashlib.sha256(raw).hexdigest(),
            "assessment": "Independent synthetic nil population assessed against separate retained evidence",
        },
    }
    # An unreviewed source may not establish a nil claim.
    await execute(c, h, eid, "country-workflow", {**payload, "source_ids": unreviewed}, failed="review")
    wrong = {**payload, "import_nil_scope": {**payload["import_nil_scope"], "context_sha256": "0"*64}}
    await execute(c, h, eid, "country-workflow", wrong, failed="hash differs")
    result = await execute(c, h, eid, "country-workflow", payload)
    assert not result["body"]["blocked"]
    assert result["body"]["import_nil_scope"]["binding_status"] == "VERIFIED_RETAINED_CONTEXT"
    assert (await decision(c, h, eid, result)).status_code == 403
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    reviewed = reviewed.json()
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    boxes = {"7": {"expected_rows": 0, "taxable_amount": "0", "tax": "0"}}
    if not mixed:
        boxes["6"] = dict(boxes["7"])
    request = {"source_role": "books", "boxes": boxes, "label": "SYNTHETIC nil VAT201 boxes", "assessment": "Independently checked zero detail count, taxable base and tax"}
    bridge = await c.post(prefix + f"/events/{reviewed['id']}/import-vat-box-source", headers=h, json=request)
    assert bridge.status_code == 201, bridge.text
    bridge = bridge.json()
    assert bridge["body"]["review_status"] == "UNVERIFIED"
    assert all(row["tax"] == "0" and row["population_basis"] == "EXPLICIT_EVIDENCED_NIL" for row in bridge["body"]["rows"])
    approved = await decision(c, reviewer[0], eid, bridge)
    assert approved.status_code == 201, approved.text
    approved = approved.json()
    filed = await source(c, h, eid, [
        {"id": "SYN-FILED-" + box, "registration": "100000000000001", "period_start": "2026-04-01", "period_end": "2026-06-30", "box": box, "currency": "AED", "taxable_amount": "0", "tax": "0", "adjustment": "0"}
        for box in sorted(boxes)
    ], "SYNTHETIC independently retained nil filed boxes", table_type="return-boxes", totals={"AED": "0"})
    filed_reviewed = await decision(c, reviewer[0], eid, filed)
    assert filed_reviewed.status_code == 201, filed_reviewed.text
    vat = await execute(c, h, eid, "country-workflow", {
        "workflow": "uae-vat-return", "source_ids": {"books": approved["id"], "return": filed_reviewed.json()["id"]},
        "as_of": "2026-06-30", "title": "SYNTHETIC nil import filed comparison",
        "rationale": "Explicit reviewed nil book boxes against separately retained assessed filed evidence",
        "required_boxes": sorted(boxes), "restrict_to_required_boxes": True,
        "box_scope_assessment": "Only the explicit nil import boxes are compared, with other boxes outside this assessment",
    })
    assert vat["body"]["exception_count"] == 0 and len(vat["body"]["rows"]) == len(boxes)
    exported = await c.get(prefix + f"/events/{reviewed['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    newer = await c.post(base + "/evidence-files/" + context_record["id"], headers=h,
                         files={"file": ("SYNTHETIC replaced context.csv", raw + b"replacement,requires reassessment\n", "text/csv")})
    assert newer.status_code == 201, newer.text
    for item in (reviewed, approved, vat):
        stale = await c.get(prefix + f"/events/{item['id']}", headers=h)
        assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
    denied = await c.post(prefix + f"/events/{reviewed['id']}/import-vat-box-source", headers=h, json=request)
    assert denied.status_code == 409
