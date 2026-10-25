"""Actual retained series/context files, independent review and source replacement."""

import io
import json
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_document_series import parameters, payload, row

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


async def retain_series(c, h, eid, base, variance=False):
    body = payload()
    if variance:
        body["doc_issue"]["doc_det"][0]["docs"][0].update(cancel=1, net_issue=9)
    original_ids = {}
    records = {}
    for kind, value in (
        ("response", body),
        (
            "context",
            {
                "classification": "SYNTHETIC_NOT_AUTHENTICATED",
                "gstin": row()["registration"],
                "period": "2026-06",
                "section": "doc_issue",
                "assessment": "Independent request scope with complete original section retained",
            },
        ),
    ):
        record = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC document-series {kind}.json",
                    json.dumps(value).encode(),
                    "application/json",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        original_ids[kind] = uploaded.json()["id"]
        records[kind] = record["id"]
    options = parameters(
        evidence_version_id=original_ids["response"],
        gstr1_context_evidence_version_id=original_ids["context"],
        document_series_controls={
            "issued": 10,
            "cancelled": 1 if variance else 2,
            "net_issued": 9 if variance else 8,
        },
    ).model_dump(mode="json")
    reported = await execute(c, h, eid, "workflow-source", options)
    books = await source(
        c,
        h,
        eid,
        [row()],
        "SYNTHETIC independent document-series register",
        "gst-document-series",
        {},
        document_series_controls={"issued": 10, "cancelled": 2, "net_issued": 8},
    )
    return {
        "books": books,
        "reported": reported,
        "originals": original_ids,
        "records": records,
        "options": options,
    }


@pytest.mark.parametrize("variance", [False, True])
async def test_retained_document_series_review_export_and_context_replacement(
    environment, monkeypatch, variance
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    retained = await retain_series(c, h, eid, base, variance)
    reviewer = await actor(h, "Firm Administrator", "document-series-reviewer")
    await grant(c, h, base, reviewer)
    args = {
        "workflow": "india-document-series",
        "source_ids": {role: retained[role]["id"] for role in ("books", "reported")},
        "as_of": "2026-06-30",
        "currency": "INR",
        "tolerance": "1000",
        "title": "SYNTHETIC document cancellation review",
        "rationale": "Independent serial ranges and issued/cancelled/net counts assessed exactly",
    }
    await execute(c, h, eid, "country-workflow", args, failed="Independently review")
    for role in ("books", "reported"):
        assert (await decision(c, h, eid, retained[role])).status_code == 403
        reviewed = await decision(c, reviewer[0], eid, retained[role])
        assert reviewed.status_code == 201, reviewed.text
        args["source_ids"][role] = reviewed.json()["id"]
    result = await execute(c, h, eid, "country-workflow", args)
    assert result["body"]["exception_count"] == int(variance)
    assert result["body"]["document_series_scope"] == {
        "registration": row()["registration"],
        "period": "2026-06",
    }
    assert result["body"]["rows"][0]["differences"]["cancelled"] == (-1 if variance else 0)
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == (409 if variance else 201), approved.text
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    exported = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.content), read_only=True)
    values = list(workbook["Rows"].values)
    details = dict(zip(values[0], values[1], strict=True))
    assert details["serial_from"] == "SYN/0001" and '"cancelled": 2' in details["books_counts"]
    workbook.close()
    raw = await c.get(
        base
        + f"/evidence-files/{retained['records']['response']}/{retained['originals']['response']}/download",
        headers=h,
    )
    assert raw.status_code == 200
    if not variance:
        assert json.loads(raw.content)["doc_issue"] == payload()["doc_issue"]
    replacement = await c.post(
        base + "/evidence-files/" + retained["records"]["context"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC changed series context.json",
                b'{"classification":"SYNTHETIC_REPLACED_REQUEST_SCOPE"}',
                "application/json",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    stale = await c.get(prefix + f"/events/{result['id']}", headers=h)
    assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
    native_stale = await c.get(prefix + f"/events/{args['source_ids']['reported']}", headers=h)
    assert native_stale.json()["freshness"] == "STALE"
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409


async def test_document_series_country_and_scope_guards(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    config = await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    assert (
        next(item for item in config.json()["items"] if item["id"] == "india-document-series")[
            "available"
        ]
        is False
    )
    await source(
        c,
        h,
        eid,
        [row()],
        "SYNTHETIC wrong-country series",
        "gst-document-series",
        {},
        document_series_controls={"issued": 10, "cancelled": 2, "net_issued": 8},
        failed="India engagement",
    )
