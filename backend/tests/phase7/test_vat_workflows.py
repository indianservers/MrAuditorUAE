import os
import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import func, select, text

from app.db.session import Session, tenant_context
from app.modules.accounting.models import JournalLine, SourceRecord
from app.modules.demo.generator import generate
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def prepared(c):
    h, options, eid, base = await setup(c)
    manager = await actor(h, "Tax Manager", "vat-manager")
    partner = await actor(h, "Tax Partner", "vat-partner")
    await grant(c, h, base, manager)
    await grant(c, h, base, partner)
    audit_manager = await actor(h, "Audit Manager", "vat-audit-manager")
    audit_partner = await actor(h, "Audit Partner", "vat-audit-partner")
    await grant(c, h, base, audit_manager)
    await grant(c, h, base, audit_partner)

    async def ready(kind, body):
        if kind == "working-papers":
            obj = await create(c, h, base, kind, body)
            obj = await action(c, h, base, obj, "submit")
            obj = await action(c, audit_manager[0], base, obj, "approve")
            return await action(c, audit_partner[0], base, obj, "approve")
        return await approve(c, h, manager[0], base, await create(c, h, base, kind, body))

    wp = await ready(
        "working-papers",
        {
            "folder": "Synthetic source",
            "sections": [{"heading": "Facts", "text": "Synthetic reviewed support"}],
            "conclusion": "Test only",
        },
    )
    generated = generate(0, 2026, 2, 0)
    options.update(
        expected_rows=generated["rows"],
        expected_debit=generated["debit"],
        expected_credit=generated["credit"],
    )
    bid, sid = await committed(c, h, options, generated["csv"])
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        ids = {
            x: str(y)
            for x, y in (
                await db.execute(
                    select(SourceRecord.source_id, JournalLine.id)
                    .join(JournalLine, JournalLine.source_record_id == SourceRecord.id)
                    .where(SourceRecord.batch_id == uuid.UUID(bid))
                )
            ).all()
        }
    rules = {}
    for category, source, article, start in [
        ("output", "VAT-LAW", "3", "2018-01-01"),
        ("input", "VAT-LAW", "54", "2018-01-01"),
        ("invoice", "VAT-ER", "59", "2018-01-01"),
        ("return", "VAT201", "", "2022-10-01"),
        ("einvoice", "MD66-2026", "One", "2026-05-14"),
        ("integrity", "FTA13-2026", "5", "2026-10-01"),
    ]:
        obj = await ready(
            "vat-rule",
            {
                "rule_key": category,
                "rule_version": 1,
                "category": category,
                "source_id": source,
                "article": article,
                "effective_from": start,
                "known_from": start,
                "source_document_version": "Synthetic official-source metadata fixture",
                "technical_review": "Synthetic technical reviewer",
                "conditions": "Synthetic dated conditions",
                "exceptions": "Professional review required",
            },
        )
        rules[category] = obj["id"]
    p = await ready(
        "vat-profile",
        {
            "trn": "999999999999999",
            "registration_status": "REGISTERED",
            "registered_from": "2024-01-01",
            "filing_frequency": "monthly",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "legal_as_of": "2026-10-18",
            "activities": "Synthetic taxable services",
            "input_recovery_assessment": "Synthetic evidenced business use",
            "jurisdictions": ["AE"],
            "rules": rules,
            "output_control_codes": ["240"],
            "input_control_codes": ["180"],
            "filing_obligations": "Synthetic October return",
            "calendar_review": "Reviewed synthetic Sat/Sun calendar",
        },
    )
    invoices = []
    for raw in generated["invoices"]:
        inv = dict(raw)
        source = inv.pop("source_ids")
        inv.pop("original_index")
        inv.pop("expected_output")
        inv.pop("expected_input")
        inv.update(
            profile_id=p["id"],
            rule_id=rules["output" if inv["direction"] == "sale" else "input"],
            invoice_rule_id=rules["invoice"],
            net_line_ids=[ids[source["400" if inv["direction"] == "sale" else "500"]]],
            output_tax_line_ids=[ids[source["240"]]] if "240" in source else [],
            input_tax_line_ids=[ids[source["180"]]] if "180" in source else [],
            evidence_record_ids=[wp["id"]],
            recovery_evidence_ids=[wp["id"]],
            integrity_review_evidence_id=wp["id"],
        )
        invoices.append(await ready("vat-invoice", inv))
    return h, eid, base, manager, partner, p, invoices, wp, rules, ready


async def test_vat201_actual_sources_return_review_and_stale_export(environment):
    c = environment
    h, eid, base, m, partner, p, invoices, wp, rules, ready = await prepared(c)
    r = await c.post(f"/api/v1/vat/engagements/{eid}/computations/{p['id']}", headers=h)
    assert r.status_code == 201, r.text
    run = r.json()
    result = run["results"]
    assert result["validation"]["ready"]
    assert D(result["net_vat"]) == D("-0.50")
    boxes = {x["box"]: x for x in result["boxes"]}
    assert D(boxes["12"]["vat"]) == 50 and D(boxes["13"]["vat"]) == D("50.50")
    rows = await c.get(f"/api/v1/vat/engagements/{eid}/runs/{run['id']}?limit=1", headers=h)
    assert rows.json()["rows_total"] == 2 and len(rows.json()["results"]["reconciliations"]) == 1
    approval = await create(
        c,
        h,
        base,
        "vat-return",
        {
            "run_id": run["id"],
            "filing_state": "READY_FOR_EXTERNAL_FILING",
            "checklist_complete": True,
            "rationale": "Synthetic return checked",
        },
    )
    approval = await action(c, h, base, approval, "submit")
    await action(c, h, base, approval, "approve", 403)
    approval = await action(c, m[0], base, approval, "approve")
    assert approval["status"] == "REVIEW_REQUIRED"
    approval = await action(c, partner[0], base, approval, "approve")
    assert approval["status"] == "APPROVED"
    exported = await c.get(f"/api/v1/vat/engagements/{eid}/runs/{run['id']}/export/json", headers=h)
    assert exported.json()["approved"]
    await action(c, m[0], base, invoices[0], "reopen")
    exported = await c.get(f"/api/v1/vat/engagements/{eid}/runs/{run['id']}/export/json", headers=h)
    assert not exported.json()["approved"]


async def test_invoice_defects_duplicates_and_date_versions(environment):
    c = environment
    h, eid, base, m, partner, p, invoices, wp, rules, ready = await prepared(c)
    body = {k: v for k, v in invoices[0]["body"].items() if not k.startswith("review_")}
    duplicate = await c.post(
        base + "/vat-invoice",
        headers=h,
        json={"reference": "DUP", "title": "Synthetic duplicate", "body": body},
    )
    assert duplicate.status_code == 409
    invalid = await create(
        c,
        h,
        base,
        "vat-invoice",
        {**body, "invoice_number": "INVALID", "supplier_trn": "", "declared_tax": "99"},
    )
    checked = await c.post(
        f"/api/v1/vat/engagements/{eid}/invoices/{invalid['id']}/validate", headers=h
    )
    assert not checked.json()["valid"] and len(checked.json()["issues"]) >= 2
    await action(c, h, base, invalid, "submit", 409)
    future = await c.post(
        base + "/vat-rule",
        headers=h,
        json={
            "reference": "WRONG-DATE",
            "title": "Wrong retroactive law",
            "body": {
                "rule_key": "bad-2024",
                "rule_version": 1,
                "category": "employee",
                "source_id": "FTA17-2026",
                "article": "2",
                "effective_from": "2024-01-01",
                "known_from": "2024-01-01",
                "source_document_version": "Test",
                "technical_review": "Test",
                "conditions": "Test",
                "exceptions": "Test",
            },
        },
    )
    assert future.status_code == 422


async def test_asp_sandbox_idempotency_retry_and_readiness(environment):
    c = environment
    h, eid, base, m, partner, p, invoices, wp, rules, ready = await prepared(c)
    body = {
        "invoice_id": invoices[0]["id"],
        "idempotency_key": "sandbox-key-1",
        "buyer_endpoint_id": "SYN-BUYER",
        "supplier_endpoint_id": "SYN-SUPPLIER",
        "schema_version": "auditos-pint-ae-subset/1.0",
        "simulate": "timeout",
    }
    path = f"/api/v1/vat/engagements/{eid}/sandbox"
    first = await c.post(path, headers=h, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["results"]["state"] == "SANDBOX_TIMEOUT"
    again = await c.post(path, headers=h, json=body)
    assert again.json()["replayed"] and first.json()["id"] == again.json()["id"]
    conflict = await c.post(path, headers=h, json={**body, "simulate": "accept"})
    assert conflict.status_code == 409
    retry = await c.post(
        path, headers=h, json={**body, "idempotency_key": "sandbox-key-2", "simulate": "accept"}
    )
    assert (
        retry.json()["results"]["state"] == "SANDBOX_ACCEPTED"
        and not retry.json()["results"]["external_submission"]
    )
    assessment = await ready(
        "vat-einvoicing",
        {
            "profile_id": p["id"],
            "rule_id": rules["einvoice"],
            "annual_revenue": "50000000",
            "government_entity": False,
            "in_scope_b2b_b2g": True,
            "scope_assessment": "Synthetic B2B business scope",
            "identifiers_complete": False,
            "source_mapping_complete": False,
            "sandbox_tested": True,
            "evidence_record_ids": [wp["id"]],
        },
    )
    result = await c.post(
        f"/api/v1/vat/engagements/{eid}/assessments/{assessment['id']}", headers=h
    )
    assert result.status_code == 201 and result.json()["results"]["appointment_due"] == "2026-10-30"


async def test_vat_permissions_no_legacy_ai_bypass_and_immutable_runs(environment):
    c = environment
    h, eid, base, m, partner, p, invoices, wp, rules, ready = await prepared(c)
    from app.modules.vat.models import DemoDataset

    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        db.add(
            DemoDataset(
                tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                seed_version="synthetic-test",
                status="COMPLETE",
                manifest={"other_engagement_private_data": "do not disclose"},
            )
        )
        from app.modules.vat.service import journal_ids

        assert (
            await db.scalar(
                select(func.count())
                .select_from(JournalLine)
                .where(journal_ids([uuid.uuid4() for _ in range(32768)]))
            )
            == 0
        )
    status = await c.get("/api/v1/vat/demo-status", headers=h)
    assert status.status_code == 200
    assert status.json()["items"][0]["synthetic"]
    assert "manifest" not in status.text and "do not disclose" not in status.text
    auditor = await actor(h, "Auditor", "vat-forbidden")
    await grant(c, h, base, auditor)
    assert (await c.get(base + "/vat-invoice", headers=auditor[0])).status_code == 403
    assert (
        await c.get(f"/api/v1/vat/engagements/{eid}/workspace", headers=auditor[0])
    ).status_code == 403
    ai = await c.post(
        base + "/ai-actions",
        headers=auditor[0],
        json={
            "task": "financial_statement_risks",
            "sources": [{"kind": "record", "id": invoices[0]["id"]}],
        },
    )
    assert ai.status_code == 403
    run = (await c.post(f"/api/v1/vat/engagements/{eid}/computations/{p['id']}", headers=h)).json()
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        with pytest.raises(Exception, match="immutable|Immutable|append only"):
            await db.execute(
                text("UPDATE vat_computation_runs SET sha256='modified' WHERE id=:id"),
                {"id": uuid.UUID(run["id"])},
            )


async def test_all_vat_ai_tasks_grounded_independent_and_budgeted(environment, monkeypatch):
    from redis.asyncio import Redis

    from app.core.config import settings
    from app.modules.vat.catalogue import AI_TASKS

    c = environment
    h, eid, base, m, partner, p, invoices, wp, rules, ready = await prepared(c)
    async with Redis.from_url(settings().redis_url) as redis:
        await redis.delete("vat-ai-budget:" + h["X-Tenant-ID"])
    monkeypatch.setattr(settings(), "financial_ai_hourly_requests", 20)
    path = f"/api/v1/vat/engagements/{eid}/ai"
    for task in AI_TASKS:
        r = await c.post(
            path,
            headers=h,
            json={"profile_id": p["id"], "source_id": invoices[0]["id"], "task": task},
        )
        assert r.status_code == 201, r.text
        obj = r.json()
        output = obj["body"]["output"]
        assert (
            obj["status"] == "SUGGESTED"
            and output["uncertainties"]
            and not output["tax_position_approved"]
        )
        assert output["document_processing"] == "NOT_PROCESSED"
        data = {
            "version": obj["version"],
            "decision": "ACCEPTED",
            "rationale": "Synthetic independent VAT review",
        }
        assert (
            await c.post(path + f"/{obj['id']}/decision", headers=h, json=data)
        ).status_code == 403
        reviewed = await c.post(path + f"/{obj['id']}/decision", headers=m[0], json=data)
        assert reviewed.status_code == 200, reviewed.text
    assert (
        await c.post(
            path,
            headers=h,
            json={"profile_id": p["id"], "source_id": invoices[0]["id"], "task": AI_TASKS[0]},
        )
    ).status_code == 429
    result = await c.post(f"/api/v1/vat/engagements/{eid}/computations/{p['id']}", headers=h)
    assert D(result.json()["results"]["net_vat"]) == D("-0.50")


async def test_text_pdf_endpoint_requires_linked_reviewed_clean_evidence(environment, monkeypatch):
    import io

    from reportlab.pdfgen import canvas

    c = environment
    h, eid, base, m, partner, p, invoices, wp, rules, ready = await prepared(c)
    evidence = await create(
        c, h, base, "evidence", {"category": "Synthetic invoice PDF", "retain_until": "2036-12-31"}
    )
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    for index, line in enumerate(
        [
            "SYNTHETIC Tax Invoice",
            "Invoice Number: " + invoices[0]["body"]["invoice_number"],
            "Supplier TRN: 999999999999999",
            "VAT Amount: 50.00",
            "Gross Amount: 1050.00",
        ]
    ):
        pdf.drawString(40, 750 - index * 22, line)
    pdf.save()
    # An explicit deterministic AV fixture isolates document parsing; this is not a real scanner evaluation.
    monkeypatch.setattr("app.api.v1.audit_evidence.scan", lambda _: "CLEAN")
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("synthetic.pdf", stream.getvalue(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence = next(
        x
        for x in (await c.get(base + "/evidence", headers=h)).json()["items"]
        if x["id"] == evidence["id"]
    )
    reviewer = await actor(h, "Audit Manager", "vat-document-reviewer")
    await grant(c, h, base, reviewer)
    evidence = await approve(c, h, reviewer[0], base, evidence)
    inv = await action(c, m[0], base, invoices[0], "reopen")
    body = {k: v for k, v in inv["body"].items() if not k.startswith("review_")}
    body["evidence_record_ids"].append(evidence["id"])
    updated = await c.patch(
        base + "/records/" + inv["id"],
        headers=h,
        json={
            "version": inv["version"],
            "reference": inv["reference"],
            "title": inv["title"],
            "body": body,
        },
    )
    assert updated.status_code == 200, updated.text
    inv = await approve(c, h, m[0], base, updated.json())
    extracted = await c.post(
        f"/api/v1/vat/engagements/{eid}/invoices/{inv['id']}/extract/{evidence['id']}", headers=h
    )
    assert extracted.status_code == 201, extracted.text
    assert not extracted.json()["results"]["visual_verification"]
    assert all(x["matches"] for x in extracted.json()["results"]["comparisons"])
