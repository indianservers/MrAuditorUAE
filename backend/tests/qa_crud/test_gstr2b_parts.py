"""Original numbered-file evidence, real API/storage/jobs; explicit scanner/broker doubles."""

import json
import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_gstr2b_parts import bundle
from tests.unit.test_india_invoice_source import BUYER, SELLER

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def retained_bundle(c, h, eid, base):
    manifest, parts, data = bundle()
    values = data.model_dump(mode="json")
    originals = []
    for name, value in [
        ("manifest", manifest),
        *[("part-" + str(index + 1), item) for index, item in enumerate(parts.values())],
    ]:
        record = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        content = json.dumps(value).encode()
        uploaded = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=h,
            files={"file": ("SYNTHETIC-gstr2b-" + name + ".json", content, "application/json")},
        )
        assert uploaded.status_code == 201, uploaded.text
        originals.append((record, uploaded.json(), content))
    values["evidence_version_id"] = originals[0][1]["id"]
    for part, original in zip(values["gstr2b_parts"], originals[1:], strict=True):
        part["evidence_version_id"] = original[1]["id"]
    return values, originals


async def test_numbered_gstr2b_originals_review_matching_export_and_part_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "gstr2b-batch-reviewer")
    await grant(c, h, base, reviewer)
    data, originals = await retained_bundle(c, h, eid, base)
    result = await execute(c, h, eid, "workflow-source", data)
    assert result["body"]["row_count"] == 8 and result["body"]["control_totals"] == {"INR": "27"}
    assert {item["id"] for item in result["dependencies"] if item["type"] == "evidence"} == {
        item[1]["id"] for item in originals
    }
    assert {row["source_part_evidence_version_id"] for row in result["body"]["rows"]} == {
        item[1]["id"] for item in originals[1:]
    }
    for record, original, content in originals:
        downloaded = await c.get(
            base + "/evidence-files/" + record["id"] + "/" + original["id"] + "/download", headers=h
        )
        assert downloaded.status_code == 200 and downloaded.content == content
    books = [
        dict(
            id="B" + str(index),
            registration=BUYER,
            counterparty=SELLER,
            reference="SYNTHETIC-" + str(index),
            period="2026-06",
            date="2026-06-15",
            currency="INR",
            document_type="invoice",
            component="IGST",
            net=net,
            tax=tax,
            status="active",
        )
        for index, net, tax in ((1, "100", "18"), (2, "50", "9"))
    ]
    register = await source(
        c, h, eid, books, "Synthetic independent split-return books", "tax-documents", {"INR": "27"}
    )
    payload = dict(
        workflow="india-gst",
        source_ids={"books": register["id"], "return": result["id"]},
        as_of="2026-06-30",
        currency="INR",
        title="Synthetic complete numbered GSTR-2B comparison",
        rationale="Independent purchase register and all declared original numbered response files",
    )
    await execute(c, h, eid, "country-workflow", payload, failed="review the assembled GSTR-2B")
    assert (await decision(c, h, eid, result)).status_code == 403
    for role, item in (("books", register), ("return", result)):
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        payload["source_ids"][role] = reviewed.json()["id"]
    compared = await execute(c, h, eid, "country-workflow", payload)
    assert compared["body"]["exception_count"] == 0 and len(compared["body"]["rows"]) == 8
    export = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{compared['id']}/export?format=xlsx",
        headers=h,
    )
    assert export.status_code == 200 and export.content.startswith(b"PK")
    # A new original part version invalidates the source and downstream comparison without rewriting history.
    record = originals[1][0]
    changed = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-changed-part.json",
                b'{"changed":"SYNTHETIC replacement"}',
                "application/json",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    for saved in (result, compared):
        detail = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}", headers=h
        )
        assert detail.json()["freshness"] == "STALE" and detail.json()["sha256"] == saved["sha256"]
    await execute(c, h, eid, "workflow-source", data, failed="superseded")


async def test_numbered_gstr2b_is_unavailable_to_a_uae_engagement(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    data, _ = await retained_bundle(c, h, eid, base)
    await execute(c, h, eid, "workflow-source", data, failed="requires an India engagement")
