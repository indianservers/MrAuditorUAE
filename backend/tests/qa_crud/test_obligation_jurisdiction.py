"""Synthetic cross-border obligation records; no foreign tax engine activation."""

import os
from copy import deepcopy
from uuid import UUID

import pytest

from app.core.security import decode_token
from app.db.models.platform import FinancialPeriod
from app.db.session import Session, tenant_context
from app.modules.grc.service import clean
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.unit.test_obligation_jurisdiction import payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated migrated database"
)


async def test_uae_entity_retains_explicit_indian_obligation_without_switching_country(
    environment, monkeypatch
):
    double_boundaries(monkeypatch)
    c = environment
    h, opts, eid, audit_base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "synthetic-foreign-scope-reviewer")
    await grant(c, h, audit_base, reviewer)
    originals = []
    for role in ("rule", "facts", "readiness"):
        paper = await create(
            c, h, audit_base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        upload = await c.post(
            audit_base + "/evidence-files/" + paper["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-{role}.txt",
                    f"SYNTHETIC independent {role}; not client qualification".encode(),
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 201, upload.text
        paper = (await c.get(audit_base + "/records/" + paper["id"], headers=h)).json()
        originals.append(paper)
    base = f"/api/v1/grc/engagements/{eid}"

    async def engagement_period_end():
        async with Session() as db, db.begin():
            await tenant_context(db, h["X-Tenant-ID"])
            period = await db.get(FinancialPeriod, UUID(opts["period_id"]))
            return period.end_date.isoformat()

    assert await engagement_period_end() == "2026-12-31"
    body = payload()
    body.update(
        owner_id=str(decode_token(h["Authorization"].split()[1])),
        entity_id=opts["entity_id"],
        rule_evidence_id=originals[0]["id"],
        fact_evidence_ids=[originals[1]["id"]],
        readiness_evidence_ids=[originals[2]["id"]],
        reviewer_id=reviewer[3],
        effective_from="2025-04-01",
        obligation_period_start="2025-04-01",
        obligation_period_end="2026-03-31",
        deadline=None,
        deadline_rule={
            "identifier": "SYNTHETIC-foreign-period-rule",
            "version": 1,
            "effective_from": "2025-01-01",
            "effective_to": "2026-12-31",
            "trigger": "2026-03-31",
            "date_basis": "period_end",
            "days_after": 7,
            "timezone": "Asia/Kolkata",
        },
        deadline_kind="firm_internal",
        notifications_enabled=True,
        reminder_days=[0],
    )

    async def post(value):
        return await c.post(
            base + "/records/obligation",
            headers=h,
            json={
                "reference": "SYN-FOREIGN-IN",
                "title": "Synthetic Indian obligation of UAE entity",
                "body": value,
            },
        )

    denied = await post(body)
    assert denied.status_code == 409, denied.text
    originals = [await approve(c, h, reviewer[0], audit_base, paper) for paper in originals]
    derived = await create(
        c,
        h,
        audit_base,
        "working-papers",
        {
            "narrative": "SYNTHETIC derived summary, not original country-scope evidence",
            "folder": "Planning",
            "sections": [{"heading": "Synthetic summary", "text": "Derived assessment only"}],
            "conclusion": "SYNTHETIC summary is not original rule or entity-fact evidence",
            "sources": [{"kind": "record", "id": originals[1]["id"]}],
        },
    )
    manager = await actor(h, "Audit Manager", "synthetic-country-scope-manager")
    partner = await actor(h, "Audit Partner", "synthetic-country-scope-partner")
    await grant(c, h, audit_base, manager)
    await grant(c, h, audit_base, partner)
    derived = await approve(c, h, manager[0], audit_base, derived)
    derived = await action(c, partner[0], audit_base, derived, "approve")
    assert derived["status"] == "APPROVED"
    wrong_source = deepcopy(body)
    wrong_source["fact_evidence_ids"] = [derived["id"]]
    denied = await post(wrong_source)
    assert denied.status_code == 422 and "original rule and entity-fact evidence" in denied.text
    wrong = deepcopy(body)
    wrong["jurisdiction_scope"].update(entity_country="IN", relationship="domestic")
    denied = await post(wrong)
    assert denied.status_code == 422 and "actual legal entity" in denied.text, denied.text
    wrong_period = deepcopy(body)
    wrong_period["deadline_rule"]["trigger"] = "2026-12-31"
    denied = await post(wrong_period)
    assert denied.status_code == 422 and "explicit obligation period end" in denied.text
    created = await post(body)
    assert created.status_code == 201, created.text
    assert created.json()["body"]["deadline"] == "2026-04-07"
    assert created.json()["body"]["obligation_period_end"] == "2026-03-31"
    obj = await approve(c, h, reviewer[0], base, created.json())
    assert obj["body"]["jurisdiction_scope"]["relationship"] == "foreign"
    calendar = (await c.get(base + "/compliance-calendar", headers=h)).json()
    assert calendar["items"][0]["calendar_state"] == "APPLICABILITY_PENDING"
    assert calendar["items"][0]["jurisdiction_scope"] == body["jurisdiction_scope"]
    assert calendar["items"][0]["obligation_period_start"] == "2025-04-01"
    assert calendar["items"][0]["obligation_period_end"] == "2026-03-31"
    assert calendar["items"][0]["deadline"] == "2026-04-07"
    filtered = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert filtered.status_code == 200 and filtered.json()["items"] == calendar["items"]
    absent = await c.get(base + f"/compliance-calendar?record_id={UUID(int=0)}", headers=h)
    assert absent.status_code == 200 and absent.json()["items"] == []
    assert await engagement_period_end() == "2026-12-31"
    reminders = await c.post(base + "/compliance-reminders", headers=h)
    assert reminders.status_code == 200 and reminders.json()["recorded"] == 0
    metadata = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    ).json()
    assert metadata["country"] == "AE" and metadata["default_currency"] == "AED"
    obj = await action(c, reviewer[0], base, obj, "reopen")
    changed = clean(obj["body"])
    changed["filing_stage"] = "preparing"
    changed["jurisdiction_scope"]["applicability"] = "assessed_applicable"
    update = await c.patch(
        base + f"/records/{obj['id']}",
        headers=h,
        json={
            "version": obj["version"],
            "reference": obj["reference"],
            "title": obj["title"],
            "body": changed,
        },
    )
    assert update.status_code == 200, update.text
    obj = update.json()

    async def step(headers, stage):
        response = await c.post(
            base + f"/obligations/{obj['id']}/filing-stage",
            headers=headers,
            json={"version": obj["version"], "stage": stage},
        )
        assert response.status_code == 200, response.text
        return response.json()

    obj = await step(h, "under_review")
    obj = await approve(c, h, reviewer[0], base, obj)
    obj = await step(reviewer[0], "approved_for_submission")
    obj = await action(c, reviewer[0], base, obj, "reopen")
    retained = deepcopy(obj["body"])
    changed = deepcopy(clean(retained))
    changed["jurisdiction_scope"]["registration_reference"] = "SYN-REPLACEMENT"
    denied = await c.patch(
        base + f"/records/{obj['id']}",
        headers=h,
        json={
            "version": obj["version"],
            "reference": obj["reference"],
            "title": obj["title"],
            "body": changed,
        },
    )
    assert denied.status_code == 409 and "Approved filing inputs changed" in denied.text
    changed = deepcopy(clean(retained))
    changed["obligation_period_start"] = "2025-03-01"
    denied = await c.patch(
        base + f"/records/{obj['id']}",
        headers=h,
        json={
            "version": obj["version"],
            "reference": obj["reference"],
            "title": obj["title"],
            "body": changed,
        },
    )
    assert denied.status_code == 409 and "Approved filing inputs changed" in denied.text
    obj = await approve(c, h, reviewer[0], base, obj)
    retained = deepcopy(obj["body"])
    await action(c, reviewer[0], audit_base, originals[1], "reopen")
    after = (await c.get(audit_base + f"/records/{obj['id']}", headers=h)).json()
    assert after["body"] == retained
    calendar = (await c.get(base + "/compliance-calendar", headers=h)).json()
    assert (
        calendar["items"][0]["freshness"] == "STALE"
        and calendar["items"][0]["reassessment_required"] is True
    )

    # Explicit load fixtures: unreviewed synthetic drafts, not additional client cases.
    from app.modules.audit_execution.models import AuditRecord
    from app.modules.grc.schemas import Obligation

    draft = Obligation.model_validate(
        {
            "owner_id": body["owner_id"],
            "entity_id": opts["entity_id"],
            "module": "policy",
            "source_url": "https://synthetic.invalid/load-fixture",
            "jurisdiction": "SYNTHETIC",
            "effective_from": "2026-01-01",
            "required_evidence": "Synthetic unreviewed load fixture only",
            "compliance_assessment": "not_assessed",
        }
    ).model_dump(mode="json")
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        db.add_all(
            [
                AuditRecord(
                    tenant_id=UUID(h["X-Tenant-ID"]),
                    engagement_id=UUID(eid),
                    created_by=UUID(body["owner_id"]),
                    prepared_by=UUID(body["owner_id"]),
                    kind="grc-obligation",
                    reference=f"SYNTHETIC-LOAD-{index}",
                    title="Synthetic unreviewed draft",
                    body=draft,
                )
                for index in range(201)
            ]
        )
    bounded = (await c.get(base + "/compliance-calendar", headers=h)).json()
    assert len(bounded["items"]) == 200
    assert not any(item["record_id"] == obj["id"] for item in bounded["items"])
    filtered = await c.get(base + f"/compliance-calendar?record_id={obj['id']}", headers=h)
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()["items"]) == 1
    assert filtered.json()["items"][0]["record_id"] == obj["id"]
    assert filtered.json()["items"][0]["freshness"] == "STALE"
