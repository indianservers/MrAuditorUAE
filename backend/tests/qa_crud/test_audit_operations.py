"""Labeled synthetic connected audit/operations demonstrations; no external actions."""

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.dependencies import Context
from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.accounting.models import Account, JournalLine
from app.modules.audit_execution.models import EvidenceVersion
from app.modules.ml import service as ml
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_shared_audit_workflows import prepare
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_audit_operations import allocation, payment
from tests.unit.test_practice_audit_workflows import purchase, rate
from tests.unit.test_shared_audit_workflows import item

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated disposable database"
)
DOCS = Path(__file__).resolve().parents[3] / "docs/engine-strengthening/phase4"
CSV = b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n100,Cash,OPEN,2026-01-01,100,0,L1,true,false,Opening\n300,Capital,OPEN,2026-01-01,0,100,L2,true,false,Opening\n110,Receivables,INV1,2026-06-01,100,0,L3,false,false,Invoice\n400,Revenue,INV1,2026-06-01,0,100,L4,false,false,Invoice\n100,Cash,PAY1,2026-06-15,70,0,L5,false,false,Receipt\n110,Receivables,PAY1,2026-06-15,0,40,L6,false,false,Receipt allocation\n230,Unapplied cash,PAY1,2026-06-15,0,30,L7,false,false,Unapplied receipt\n"


def save(name, body):
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / name).write_text(json.dumps({"synthetic": True, **body}, indent=2, default=str))


async def post(c, h, path, body=None, status=201):
    r = await c.post(path, headers=h, json=body)
    assert r.status_code == status, r.text
    return r.json()


async def base_scope(c):
    h, opts, eid, base = await setup(c)
    manager = await actor(h, "Audit Manager", "operations-manager")
    partner = await actor(h, "Audit Partner", "operations-partner")
    for reviewer in [manager, partner]:
        await grant(c, h, base, reviewer)
    opts.update(expected_rows=7, expected_debit="270", expected_credit="270")
    batch_id, sid = await committed(c, h, opts, CSV)
    opts["supersedes_id"] = batch_id
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        accounts = {
            a.code: str(a.id)
            for a in (
                await db.scalars(
                    select(Account).where(Account.entity_id == uuid.UUID(opts["entity_id"]))
                )
            )
        }
        line = await db.scalar(
            select(JournalLine.id).where(
                JournalLine.snapshot_id == uuid.UUID(sid),
                JournalLine.account_id == uuid.UUID(accounts["110"]),
                JournalLine.base_debit == 100,
            )
        )
    return h, opts, eid, base, manager, partner, sid, accounts, str(line)


async def test_revenue_receipt_ecl_selection_evidence_review(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, opts, eid, base, manager, partner, sid, accounts, invoice_line = await base_scope(c)
    source_reviewer = await actor(h, "Firm Administrator", "operations-source-reviewer")
    await grant(c, h, base, source_reviewer)
    profile = await approve(
        c,
        h,
        manager[0],
        base,
        await create(
            c,
            h,
            base,
            "ifrs-profile",
            {
                "snapshot_id": sid,
                "presentation_currency": "AED",
                "technical_validation": "SYN entity full IFRS technical fixture",
            },
        ),
    )
    revenue = await approve(
        c,
        h,
        manager[0],
        base,
        await create(
            c,
            h,
            base,
            "ifrs-revenue",
            {
                "profile_id": profile["id"],
                "contract_reference": "SYN-contract",
                "contract_assessment": "SYN supplied signed goods contract",
                "reporting_date": "2026-12-31",
                "fixed_price": "100",
                "constraint_rationale": "SYN no variable consideration",
                "billed_to_date": "100",
                "obligations": [
                    {
                        "reference": "SYN-goods",
                        "standalone_price": "100",
                        "recognition": "point_in_time",
                        "satisfied_on": "2026-06-01",
                    }
                ],
            },
        ),
    )
    recognized = await post(c, h, f"/api/v1/ifrs/engagements/{eid}/calculate/{revenue['id']}")
    assert Decimal(recognized["results"]["recognised_to_date"]) == 100
    sources = await prepare(
        c,
        h,
        source_reviewer,
        eid,
        [
            (
                "items",
                "audit-open-items",
                [{**item(), "balance_date": "2026-12-31"}],
                {"AED": "100"},
            ),
            ("payments", "cash-payments", [payment()], {"AED": "70"}),
            ("allocations", "item-allocations", [allocation()], {"AED": "40"}),
        ],
    )
    ledger = await execute(
        c,
        h,
        eid,
        "workflow-ledger",
        {
            "source_kind": "balance-controls",
            "balance_side": "receivable",
            "snapshot_id": sid,
            "account_ids": [accounts["110"]],
            "bank_account": "AR",
            "currency": "AED",
            "label": "SYN actual AR GL control",
            "as_of": "2026-12-31",
        },
    )
    sources["controls"] = (await decision(c, source_reviewer[0], eid, ledger)).json()["id"]
    assessment = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "open-item-allocations",
            "allocation_basis": "invoice_face_amounts",
            "source_ids": sources,
            "as_of": "2026-12-31",
            "title": "SYN invoice and cash allocations",
            "rationale": "SYN face invoices and bank-confirmed cash reconciled to actual GL",
        },
    )
    assert assessment["body"]["remaining_open_items"][0]["amount"] == "60"
    assert (
        next(r for r in assessment["body"]["rows"] if r.get("kind") == "cash_movement")[
            "unapplied_cash"
        ]
        == "30"
    )
    assessment = (await decision(c, h, eid, assessment, "accept", item_id="cash:PAY-1")).json()
    approved = await decision(c, source_reviewer[0], eid, assessment)
    assert approved.status_code == 201, approved.text
    assessment = approved.json()
    remaining = await post(
        c,
        h,
        f"/api/v1/intelligence/engagements/{eid}/events/{assessment['id']}/remaining-open-items",
        {},
    )
    remaining = (await decision(c, source_reviewer[0], eid, remaining)).json()
    rates = await source(
        c,
        h,
        eid,
        [
            rate(
                historical_loss_rate="0.08",
                forward_adjustment="0.02",
                forward_evidence="SYN forecast",
            )
        ],
        "SYN loss-rate evidence",
        "ecl-loss-rates",
        {},
    )
    rates = (await decision(c, source_reviewer[0], eid, rates)).json()
    ecl = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "receivables-ecl",
            "source_ids": {
                "items": remaining["id"],
                "controls": sources["controls"],
                "rates": rates["id"],
            },
            "as_of": "2026-12-31",
            "title": "SYN ECL on remaining receivable",
            "rationale": "SYN reviewed forward/historical matrix and actual GL control",
        },
    )
    assert Decimal(ecl["body"]["total_ecl_by_currency"]["AED"]) == 6
    assert not ecl["body"]["blocked"]
    ecl = (await decision(c, source_reviewer[0], eid, ecl)).json()
    risk = await approve(
        c,
        h,
        partner[0],
        base,
        await create(
            c,
            h,
            base,
            "risks",
            {
                "level": "assertion",
                "inherent_risk": "high",
                "control_risk": "not_assessed",
                "response": "SYN inspect invoice/receipt and valuation",
                "assertions": ["existence", "valuation"],
            },
        ),
    )
    procedure = await approve(
        c,
        h,
        manager[0],
        base,
        await create(
            c,
            h,
            base,
            "procedures",
            {
                "methodology_version": "SYN/1",
                "objective": "SYN test invoice and valuation evidence",
                "required_evidence": "SYN reviewed invoice source and bank receipt",
                "instructions": "SYN inspect invoice, remittance and trace actual GL",
                "risk_ids": [risk["id"]],
                "procedure_type": "details",
                "sources": [
                    {"kind": "intelligence", "id": ecl["id"]},
                    {"kind": "record", "id": revenue["id"]},
                ],
            },
        ),
    )
    sample = await post(
        c,
        h,
        base + "/select-sample",
        {
            "snapshot_id": sid,
            "method": "judgmental",
            "selected_line_ids": [invoice_line],
            "selection_rationale": "SYN targeted invoice and allocation evidence",
            "objective": "SYN existence and valuation",
            "population_definition": "SYN selected AR invoice within retained ledger",
        },
    )
    assert sample["result"]["selection_class"] == "targeted"
    assert not sample["result"]["projection_supported"]
    source_event = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{sources['items']}", headers=h)
    ).json()
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        ev = await db.get(EvidenceVersion, uuid.UUID(source_event["body"]["evidence_version_id"]))
        evidence_id = str(ev.record_id)
    evidence = (await c.get(base + "/records/" + evidence_id, headers=h)).json()
    await approve(c, h, manager[0], base, evidence)
    test_body = {
        "sample_id": sample["id"],
        "procedure_id": procedure["id"],
        "steps_performed": "SYN inspected retained invoice and cash allocation; independently recalculated ECL6",
        "population_completeness": "SYN source7 records debit270 credit270",
        "reconciliation": "AR100 less40 receipt =60 control",
        "methodology_rationale": "SYN targeted selection; no projection",
        "conclusion": "SYN selected procedures performed; no population assurance",
        "results": [
            {
                "line_id": invoice_line,
                "outcome": "passed",
                "evidence_ids": [evidence_id],
                "observations": "SYN documentary evidence reviewed",
            }
        ],
        "sources": [
            {"kind": "sample", "id": sample["id"]},
            {"kind": "intelligence", "id": ecl["id"]},
        ],
    }
    await post(
        c,
        h,
        base + "/testing",
        {
            "reference": "SYN-invalid-projection",
            "title": "SYN blocked projection",
            "body": {**test_body, "projected_misstatement": "1"},
        },
        status=422,
    )
    testing = await create(c, h, base, "testing", test_body)
    testing = await action(c, h, base, testing, "submit")
    testing = await action(c, manager[0], base, testing, "approve")
    testing = await action(c, partner[0], base, testing, "approve")
    assert testing["status"] == "APPROVED"
    save(
        "revenue-cycle.json",
        {
            "revenue": recognized,
            "allocations": assessment,
            "ecl": ecl,
            "sample": sample,
            "testing": testing,
        },
    )
    await committed(c, h, opts, CSV.replace(b"Receipt allocation", b"SYN corrected receipt allocation"))
    graph = (await c.get(base + "/graph", headers=h)).json()
    retained = next(row for row in graph["nodes"] if row["id"] == testing["id"])
    assert retained["freshness"] == "STALE"
    await action(c, partner[0], base, testing, "lock", expected=409)
    save("audit-source-revision.json", {"historical_test": testing, "current_dependency_state": retained,
                                      "stale_approval_http_status": 409})


async def test_procurement_bank_revision_and_reapproval(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "operations-bank-reviewer")
    await grant(c, h, base, reviewer)
    sources = await prepare(
        c,
        h,
        reviewer,
        eid,
        [
            (
                role,
                "purchase-lines",
                [
                    purchase(
                        kind,
                        approval_status="approved",
                        bank_change_verified=True,
                        prepared_by="SYN-buyer",
                        approved_by="SYN-independent",
                    )
                ],
                {"AED": "100"},
            )
            for role, kind in [
                ("orders", "order"),
                ("receipts", "receipt"),
                ("invoices", "invoice"),
                ("payments", "payment"),
            ]
        ],
    )
    procurement = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "procurement-match",
            "source_ids": sources,
            "as_of": "2026-06-30",
            "title": "SYN order receipt invoice payment",
            "rationale": "SYN independent order receipt invoice and paid-cash sources",
        },
    )
    assert not procurement["body"]["rows"][0]["exceptions"]
    from app.modules.country_workflows.audit_schemas import PurchaseLine

    nil_evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + nil_evidence["id"],
        headers=h,
        files={
            "file": (
                "SYN-proposal-stage-nil-payments.csv",
                (",".join(PurchaseLine.model_fields) + "\n").encode(),
                "text/csv",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    nil_source = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "table_type": "purchase-lines",
            "expected_rows": 0,
            "control_totals": {"AED": "0"},
            "nil_reason": "SYN proposal-stage supplied payments are nil; not a claim about complete bank activity",
            "label": "SYN proposal stage nil payment source",
        },
    )
    nil_source = (await decision(c, reviewer[0], eid, nil_source)).json()
    proposal_stage = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "procurement-match",
            "source_ids": {**sources, "payments": nil_source["id"]},
            "as_of": "2026-06-30",
            "title": "SYN pre-settlement proposal stage",
            "rationale": "SYN matching yields a draft; subsequent banking evidence is separately supplied",
        },
    )
    assert (
        proposal_stage["body"]["payment_proposals"][0]["state"] == "DRAFT_REQUIRES_PAYMENT_APPROVAL"
    )
    assert not proposal_stage["body"]["payment_proposals"][0]["payment_instruction_created"]
    books = await source(
        c,
        h,
        eid,
        [transaction(amount="-100", counterparty="V1")],
        "SYN payable ledger cash",
        totals={"AED": "-100"},
    )
    statement = await source(
        c,
        h,
        eid,
        [transaction(id="BANK1", amount="-100", counterparty="V1")],
        "SYN bank debit",
        totals={"AED": "-100"},
    )
    books = (await decision(c, reviewer[0], eid, books)).json()
    statement = (await decision(c, reviewer[0], eid, statement)).json()
    payload = bank_payload(
        books,
        statement,
        book_opening="200",
        statement_opening="200",
        book_closing="100",
        statement_closing="100",
    )
    first = await execute(c, h, eid, "country-workflow", payload)
    first = (await decision(c, reviewer[0], eid, first)).json()
    assert first["body"]["review_status"] == "REVIEWED"
    assert first["body"]["control_comparison"]["statement_balance_control"] == "0"
    correction = await decision(c, reviewer[0], eid, statement, "reject")
    assert correction.status_code == 201
    old = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{first['id']}", headers=h)
    ).json()
    assert old["freshness"] == "STALE"
    corrected = await source(
        c,
        h,
        eid,
        [transaction(id="BANK-NEW", amount="-100", counterparty="V1")],
        "SYN corrected bank source",
        totals={"AED": "-100"},
    )
    corrected = (await decision(c, reviewer[0], eid, corrected)).json()
    second = await execute(
        c,
        h,
        eid,
        "country-workflow",
        bank_payload(
            books,
            corrected,
            book_opening="200",
            statement_opening="200",
            book_closing="100",
            statement_closing="100",
        ),
    )
    second = (await decision(c, reviewer[0], eid, second)).json()
    assert second["body"]["review_status"] == "REVIEWED"
    second = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{second['id']}", headers=h)
    ).json()
    assert second["freshness"] == "CURRENT"
    save(
        "procurement-bank-revision.json",
        {
            "procurement": procurement,
            "draft_payment_proposal": proposal_stage,
            "historical_reconciliation": old,
            "reapproved_reconciliation": second,
        },
    )


async def test_actual_analytics_baseline_feedback_to_idempotent_workpaper(environment):
    c = environment
    h, _, eid, base, manager, partner, sid, _, _ = await base_scope(c)
    analytics = await post(c, h, "/api/v1/analytics/runs", {"snapshot_id": sid, "round_unit": "10"})
    assert analytics["status"] == "completed"
    rules = analytics["result"]["rules"]
    assert next(r for r in rules if r["rule_id"] == "J01")["status"] == "not_testable"
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        excluded = await db.scalar(
            select(JournalLine.id).where(
                JournalLine.snapshot_id == uuid.UUID(sid), JournalLine.base_credit == 40
            )
        )
    sample_request = {
        "snapshot_id": sid,
        "method": "random",
        "seed": 123,
        "size": 1,
        "certainty_threshold": "100",
        "exclusions": [
            {"line_id": str(excluded), "reason": "SYN separately tested cash allocation"}
        ],
        "objective": "SYN reproducible selected residual plus certainty stratum",
        "population_definition": "Five nonopening retained lines before justified exclusion",
    }
    selected1 = await post(c, h, base + "/select-sample", sample_request)
    selected2 = await post(c, h, base + "/select-sample", sample_request)
    samples = [
        (await c.get("/api/v1/sampling/runs/" + s["id"], headers=h)).json()
        for s in [selected1, selected2]
    ]
    assert samples[0]["result"]["population"] == 5
    assert samples[0]["result"]["certainty_selected"] == 2
    assert samples[0]["result"]["eligible_residual_population"] == 2
    assert samples[0]["result"]["selected_count"] == 3
    assert {r["line_id"] for r in samples[0]["selection"]["items"]} == {
        r["line_id"] for r in samples[1]["selection"]["items"]
    }
    assert str(excluded) not in {r["line_id"] for r in samples[0]["selection"]["items"]}
    paper = await approve(
        c,
        h,
        manager[0],
        base,
        await create(
            c,
            h,
            base,
            "procedures",
            {
                "methodology_version": "SYN-review/1",
                "objective": "SYN reviewed journal evidence",
                "required_evidence": "SYN retained ledger",
                "instructions": "SYN inspect selected ledger entries",
                "sources": [{"kind": "snapshot", "id": sid}],
            },
        ),
    )
    ctx = Context(
        decode_token(h["Authorization"].split()[1]), uuid.UUID(h["X-Tenant-ID"]), frozenset()
    )
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        dataset = await ml.execute_job(db, ctx, {"operation": "dataset", "engagement_id": eid})
        result = await ml.execute_job(
            db,
            ctx,
            {
                "operation": "baseline",
                "source_id": dataset["id"],
                "mode": "statistical_baseline",
                "offset": 0,
                "limit": 100,
            },
        )
        prediction = await ml.get(db, ctx, uuid.UUID(result["id"]), "inference")
        prediction_data = dict(prediction.body)
    assert prediction_data["execution_mode"] == "statistical_baseline"
    assert prediction_data["production_validated"] is False
    selected = max(prediction_data["predictions"], key=lambda r: r["score"])
    assert selected["review_rank"] == 1
    feedback = await post(
        c,
        h,
        f"/api/v1/ml/predictions/{result['id']}/feedback",
        {
            "transaction_id": selected["transaction_id"],
            "label": "insufficient_evidence",
            "evidence_id": paper["id"],
            "rationale": "SYN human review; original indicator is not a confirmed misstatement",
        },
    )
    assert feedback["body"]["eligible_for_training"] is False
    workpaper = await post(c, h, base + f"/ml-feedback/{feedback['id']}/working-paper", {})
    retry = await post(c, h, base + f"/ml-feedback/{feedback['id']}/working-paper", {})
    assert retry["id"] == workpaper["id"]
    assert workpaper["status"] == "IN_PROGRESS"
    engineer = await actor(h, "ML Engineer", "operations-ml-access")
    await grant(c, h, base, (manager[0], manager[1], engineer[2], manager[3]))
    await grant(c, h, base, (partner[0], partner[1], engineer[2], partner[3]))
    workpaper = await action(c, h, base, workpaper, "submit")
    queued = (await c.get(base + "/review-queue", headers=manager[0])).json()
    assert workpaper["id"] in {row["id"] for row in queued["items"]}
    workpaper = await action(c, manager[0], base, workpaper, "approve")
    workpaper = await action(c, partner[0], base, workpaper, "approve")
    assert workpaper["status"] == "APPROVED"
    save(
        "journal-review.json",
        {
            "analytics": analytics,
            "prediction": prediction_data,
            "feedback": feedback,
            "approved_workpaper": workpaper,
            "idempotent_retry_id": retry["id"],
        },
    )
