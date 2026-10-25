"""Firm source retention and rule use; scanner is an explicit boundary double."""

import json
import os
import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError

from app.db.session import Session, tenant_context
from app.modules.lineage.storage import ObjectStore
from app.modules.regulatory.models import RuleSourceDocument
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_regulatory_evaluation import fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


def rule_payload(country="AE", key="SYNTHETIC-SOURCE"):
    return fixture(
        country=country,
        rule_key=country + "-" + key,
        framework="IFRS" if country == "AE" else "Ind AS",
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-24",
    ).model_dump(mode="json")


async def propose(c, h, payload):
    response = await c.post("/api/v1/regulatory/rules", headers=h, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def decide(c, h, identifier, *, action="approve", sequence=1):
    return await c.post(
        f"/api/v1/regulatory/rules/{identifier}/decisions",
        headers=h,
        json={
            "action": action,
            "expected_sequence": sequence,
            "comments": "Synthetic independent source copy and rule-content assessment",
        },
    )


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_retained_sources_publication_integrity_and_downstream_staleness(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "source-reviewer")
    await grant(c, h, base, reviewer)
    payload = rule_payload(country)
    document = await retain(c, h, payload)
    assert "object_key" not in document and "object_version" not in document
    listed = await c.get("/api/v1/regulatory/sources", headers=h, params={"country": country})
    assert listed.status_code == 200 and listed.json()["items"][0]["id"] == document["id"]
    downloaded = await c.get(f"/api/v1/regulatory/sources/{document['id']}/download", headers=h)
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"SYNTHETIC")
    assert downloaded.headers["content-security-policy"].startswith("sandbox")
    identifier = await propose(c, h, payload)
    assert (await decide(c, h, identifier)).status_code == 403
    approved = await decide(c, reviewer[0], identifier)
    assert approved.status_code == 201, approved.text
    assert approved.json()["body"]["verified_source_copies"][0]["sha256"] == document["sha256"]
    published = await decide(c, h, identifier, action="publish", sequence=2)
    assert published.status_code == 201, published.text
    cp = f"/api/v1/jurisdictions/engagements/{eid}/context"
    context = await c.post(
        cp,
        headers=h,
        json={
            "country": country,
            "framework": "IFRS" if country == "AE" else "Ind AS",
            "entity_type": "company",
            "as_of": "2026-12-31" if country == "AE" else "2027-03-31",
            "base_version": 0,
            "reason": "Synthetic explicit country and reporting framework for retained-source assessment",
        },
    )
    assert context.status_code == 201, context.text
    context_review = await c.post(
        cp + "/decision",
        headers=reviewer[0],
        json={
            "request_id": context.json()["id"],
            "approve": True,
            "comments": "Independent synthetic engagement reporting context review",
        },
    )
    assert context_review.status_code == 201, context_review.text
    assessed = await c.post(
        f"/api/v1/regulatory/engagements/{eid}/assessments",
        headers=h,
        json={
            "rule_ids": [identifier],
            "facts": {"entity_type": "company"},
            "rationale": "Synthetic rule mechanics using retained reference bytes",
        },
    )
    assert assessed.status_code == 201, assessed.text
    event_path = f"/api/v1/intelligence/engagements/{eid}/events/{assessed.json()['id']}"
    assert (await c.get(event_path, headers=h)).json()["freshness"] == "CURRENT"
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        stored = await db.get(RuleSourceDocument, uuid.UUID(document["id"]))
        key, version = stored.object_key, stored.object_version
    with ObjectStore().local(key, version) as path:
        original = path.read_bytes()
        try:
            path.write_bytes(original.replace(b"SYNTHETIC", b"SYNTHETIX", 1))
            assert (
                await c.get(f"/api/v1/regulatory/sources/{document['id']}/download", headers=h)
            ).status_code == 409
            stale = await c.get(event_path, headers=h)
            assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
            assert stale.json()["sha256"] == assessed.json()["sha256"]
        finally:
            path.write_bytes(original)
    assert (await c.get(event_path, headers=h)).json()["freshness"] == "CURRENT"
    async with Session() as db, db.begin():
        await tenant_context(db, str(uuid.uuid4()))
        assert await db.get(RuleSourceDocument, uuid.UUID(document["id"])) is None
    with pytest.raises(DBAPIError, match="append only"):
        async with Session() as db, db.begin():
            await tenant_context(db, h["X-Tenant-ID"])
            await db.execute(
                update(RuleSourceDocument)
                .where(RuleSourceDocument.id == uuid.UUID(document["id"]))
                .values(title="Forbidden rewrite")
            )


async def test_source_binding_mismatches_and_source_uploader_independence(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, _, _ = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "source-uploading-reviewer")
    for field, value in (
        ("document_sha256", "b" * 64),
        ("url", "https://mof.gov.ae/other"),
        ("retrieved_on", "2026-10-23"),
        ("source_document_id", str(uuid.uuid4())),
    ):
        payload = rule_payload(key="SYNTHETIC-" + field.upper().replace("_", "-"))
        await retain(c, h, payload)
        payload["citations"][0][field] = value
        identifier = await propose(c, h, payload)
        assert (await decide(c, reviewer[0], identifier)).status_code == 409
    payload = rule_payload(key="SYNTHETIC-WRONG-SOURCE-COUNTRY")
    copy_payload = {**payload, "country": "IN"}
    await retain(c, h, copy_payload)
    # The shared citation object now references the India-only source.
    identifier = await propose(c, h, payload)
    assert (await decide(c, reviewer[0], identifier)).status_code == 409
    payload = rule_payload(key="SYNTHETIC-UPLOADER")
    await retain(c, h, payload, uploader=reviewer[0])
    identifier = await propose(c, h, payload)
    assert (await decide(c, reviewer[0], identifier)).status_code == 403


@pytest.mark.parametrize("status,expected", [("QUARANTINED", 409), ("REJECTED", 422)])
async def test_uncleared_sources_do_not_create_usable_copies(
    environment, monkeypatch, status, expected
):
    c = environment
    double_boundaries(monkeypatch, status)
    h, _, _, _ = await setup(c)
    response = await c.post(
        "/api/v1/regulatory/sources",
        headers=h,
        data={
            "metadata": json.dumps(
                {
                    "title": "SYNTHETIC unverified source",
                    "country": "AE",
                    "source_url": "https://mof.gov.ae/",
                    "retrieved_on": "2026-10-24",
                }
            )
        },
        files={"file": ("SYNTHETIC.txt", b"SYNTHETIC uncleared source", "text/plain")},
    )
    assert response.status_code == expected, response.text
    assert (await c.get("/api/v1/regulatory/sources", headers=h)).json()["items"] == []
