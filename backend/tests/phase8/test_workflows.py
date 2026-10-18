"""Real PostgreSQL, source financials, GL and independent TP review; no fabricated workflow completion."""

import csv
import io
import os
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.db.session import Session, tenant_context
from app.modules.accounting.models import Account, JournalLine
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, create, grant
from tests.phase6.test_workflows import prepared as tax_prepared
from tests.phase8.test_calculations import loan

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated PostgreSQL required"
)


async def prepared(c, connected=False):
    (
        h,
        eid,
        base,
        tax_manager,
        partner,
        tax_profile,
        adjustment,
        note,
        tax_rules,
        ready_tax,
        financial,
    ) = await tax_prepared(c)
    manager = await actor(h, "TP Manager", "tp-manager")
    analyst = await actor(h, "TP Analyst", "tp-analyst")
    await grant(c, h, base, manager)
    await grant(c, h, base, analyst)

    async def ready(kind, body, stages=False, who=None):
        preparer = who or analyst[0]
        obj = await create(c, preparer, base, "tp-" + kind, body)
        obj = await action(c, preparer, base, obj, "submit")
        obj = await action(c, manager[0], base, obj, "approve")
        if stages:
            assert obj["status"] == "REVIEW_REQUIRED"
            obj = await action(c, partner[0], base, obj, "approve")
        assert obj["status"] == "APPROVED", obj
        return obj

    rules = {}
    for category, source, article, known in [
        ("relationships", "CT-LAW", "35", "2022-10-10"),
        ("documentation", "MD97-2023", "2", "2023-05-15"),
        ("disclosure", "CTGTXR1", "16.1", "2024-11-11"),
        ("methodology", "OECD2022", "II", "2022-01-20"),
        ("apa", "CTGAPA1", "3", "2025-12-30"),
        ("connected_person", "CT-LAW", "36", "2022-10-10"),
        ("connected_disclosure", "CTGTXR1", "16.2", "2024-11-11"),
    ]:
        obj = await ready(
            "rule",
            {
                "source_id": source,
                "article": article,
                "category": category,
                "rule_key": category,
                "rule_version": 1,
                "effective_from": "2025-12-30" if category == "apa" else "2023-06-01",
                "known_from": known,
                "document_version": "Synthetic reviewed source adoption",
                "technical_review": "Synthetic independent professional rule adoption",
                "conditions": "Synthetic explicit fact patterns only",
            },
            who=h,
        )
        rules[category] = obj["id"]
    profile = await ready(
        "profile",
        {
            "financial_run_id": financial["id"],
            "tax_start": "2026-01-01",
            "tax_end": "2026-12-31",
            "legal_as_of": "2026-10-18",
            "rules": rules,
            "mne_member": True,
            "group_revenue": "4000000000",
            "group_facts": "Synthetic MNE facts and ownership records",
            "financial_classification": "Reviewed approved IFRS source mapping",
        },
    )
    common = {
        "profile_id": profile["id"],
        "evidence_record_ids": [note["id"]],
        "rationale": "Synthetic source-linked fact and economic review",
    }
    parent = await ready(
        "party",
        {
            **common,
            "name": "SYNTHETIC UAE tested entity",
            "jurisdiction": "AE",
            "party_type": "company",
            "synthetic": True,
        },
    )
    counterparty = await ready(
        "party",
        {
            **common,
            "name": "SYNTHETIC Foreign affiliate",
            "jurisdiction": "GB",
            "party_type": "person" if connected else "company",
            "synthetic": True,
        },
    )
    relationship = await ready(
        "relationship",
        {
            **common,
            "from_party_id": parent["id"],
            "to_party_id": counterparty["id"],
            "relationship_type": "director" if connected else "ownership",
            "ownership": "0" if connected else "0.8",
            "effective_from": "2026-01-01",
            "control_facts": "Synthetic reviewed control beyond percentage",
            "decision": "CONNECTED" if connected else "RELATED",
            "related_party_applicable": False if connected else None,
            "connected_person_rule_id": rules["connected_person"] if connected else None,
            "rule_id": rules["relationships"],
        },
    )
    engagement = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        lines = (
            {
                x: row
                for x, row in (
                    await db.execute(
                        select(Account.code, JournalLine)
                        .join(JournalLine, JournalLine.account_id == Account.id)
                        .where(
                            JournalLine.period_id == uuid.UUID(financial["results"]["period_id"])
                        )
                    )
                ).all()
            }
            if "period_id" in financial["results"]
            else {
                x: row
                for x, row in (
                    await db.execute(
                        select(Account.code, JournalLine)
                        .join(JournalLine, JournalLine.account_id == Account.id)
                        .where(
                            Account.code.in_(["400", "500"]),
                            JournalLine.entity_id == uuid.UUID(engagement["entity_id"]),
                            JournalLine.period_id == uuid.UUID(engagement["period_id"]),
                        )
                    )
                ).all()
            }
        )
    transactions = []
    for code, nature, side in [("400", "sales", "revenue"), ("500", "purchases", "expense")]:
        row = lines[code]
        transactions.append(
            await ready(
                "transaction",
                {
                    **common,
                    "relationship_id": relationship["id"],
                    "counterparty_id": counterparty["id"],
                    "transaction_date": str(row.posting_date),
                    "category": "goods",
                    "nature": nature,
                    "side": side,
                    "economic_key": "SYN-" + code,
                    "journal_line_ids": [str(row.id)],
                    "source_amount": str(row.debit - row.credit),
                    "source_currency": row.currency,
                    "base_amount": str(row.base_debit - row.base_credit),
                    "exchange_rate": str(row.exchange_rate),
                    "contract_reference": "SYNTHETIC contract 1",
                    "connected_group_key": "SYN-DIRECTOR-FAMILY" if connected else "",
                    "connected_payment_or_benefit": side == "expense" if connected else None,
                },
            )
        )
    far = await ready(
        "far",
        {
            **common,
            "party_id": parent["id"],
            "functions": ["Distribution"],
            "assets": ["Working capital"],
            "risks": ["Market risk"],
            "actual_conduct": "Synthetic contract and actual conduct reviewed",
            "risk_control": "Synthetic personnel capable of control",
            "tested_party_considerations": "Synthetic routine distributor; independent review",
        },
    )
    method = await ready(
        "method",
        {
            **common,
            "transaction_ids": [x["id"] for x in transactions],
            "far_id": far["id"],
            "method": "TNMM",
            "tested_party_id": parent["id"],
            "pli": "operating_margin",
            "economic_characteristics": "Synthetic routine activity",
            "available_comparables": "Software test population only",
            "rejected_alternatives": {
                x: "Synthetic documented comparability/data limitations"
                for x in ["CUP", "RPM", "COST_PLUS", "PROFIT_SPLIT", "OTHER"]
            },
        },
    )
    return locals()


async def benchmark(c, f, purpose="profitability", allow_ai=True, allow_derived=True):
    dataset = await f["ready"](
        "dataset",
        {
            **f["common"],
            "source_name": "SYNTHETIC SOFTWARE TEST population",
            "license_type": "synthetic",
            "license_reference": "Synthetic generated software-test observations; not market evidence",
            "valid_until": "2029-12-31",
            "authorized_use": True,
            "allow_raw_export": False,
            "allow_derived_export": allow_derived,
            "allow_ai": allow_ai,
            "observation_date": "2026-10-18",
            "data_version": "v1",
        },
    )
    columns = [
        "company_key",
        "name",
        "country",
        "industry",
        "fiscal_year",
        "currency",
        "revenue",
        "cost_sales",
        "opex",
        "assets",
        "value",
        "activity",
        "independence",
        "related_party_exposure",
        "extraordinary_events",
        "observation_date",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for index, margin in enumerate([D(".03"), D(".04"), D(".05"), D(".07"), D(".09")]):
        writer.writerow(
            dict(
                company_key=str(index),
                name="SYNTHETIC comparable " + str(index),
                country="AE",
                industry="TEST",
                fiscal_year=2026,
                currency="AED",
                revenue=100,
                cost_sales=80,
                opex=str(20 - margin * 100),
                assets=100,
                value=str(
                    margin
                    if purpose == "interest"
                    else margin * 10000000
                    if purpose == "remuneration"
                    else margin
                ),
                activity="Synthetic activity",
                independence="Synthetic reviewed",
                related_party_exposure="Synthetic nil",
                extraordinary_events="Synthetic none",
                observation_date="2026-10-01",
            )
        )
    data = stream.getvalue().encode()
    path = f"/api/v1/tp/engagements/{f['eid']}"
    for _ in range(2):
        imported = await c.post(
            path + f"/datasets/{dataset['id']}/import",
            headers=f["analyst"][0],
            files={"file": ("synthetic.csv", data, "text/csv")},
        )
        assert imported.status_code == 201, imported.text
        assert imported.json()["imported"] == 5
    method = f["method"]
    if purpose != "profitability":
        method = await f["ready"](
            "method",
            {
                **f["common"],
                "transaction_ids": [x["id"] for x in f["transactions"]],
                "far_id": f["far"]["id"],
                "method": "CUP",
                "tested_party_id": f["parent"]["id"],
                "pli": "value",
                "economic_characteristics": "Synthetic observed-price instrument",
                "available_comparables": "Synthetic software test observations only",
                "rejected_alternatives": {
                    x: "Synthetic price method review"
                    for x in ["RPM", "COST_PLUS", "TNMM", "PROFIT_SPLIT", "OTHER"]
                },
            },
        )
    study = await f["ready"](
        "study",
        {
            **f["common"],
            "dataset_ids": [dataset["id"]],
            "method_id": method["id"],
            "pli": "value" if purpose != "profitability" else "operating_margin",
            "currency": "AED",
            "fiscal_years": [2026],
            "aggregation": "year_specific",
            "quantile": "inclusive",
            "purpose": purpose,
            "screening_criteria": "Synthetic explicit geography/independence/function/loss/event criteria",
            "comparability_review": "Synthetic test only; no real economic comparables",
        },
        stages=True,
    )
    observations = (
        await c.get(path + f"/observations?dataset_id={dataset['id']}", headers=f["analyst"][0])
    ).json()["items"]
    screen = await f["ready"](
        "screening",
        {
            **f["common"],
            "study_id": study["id"],
            "decisions": [
                {
                    "observation_id": x["id"],
                    "decision": "ACCEPT",
                    "reason": "Synthetic suitable test row",
                    "independence_review": "Synthetic reviewed",
                    "loss_review": "Synthetic reviewed",
                    "functional_review": "Synthetic reviewed",
                }
                for x in observations
            ],
        },
    )
    run = await c.post(path + f"/calculate/{study['id']}", headers=f["analyst"][0])
    assert run.status_code == 201, run.text
    result = run.json()
    assert result["results"]["ready"] and result["results"]["synthetic"]
    if purpose == "profitability":
        assert D(result["results"]["lower_quartile"]) == D(".04")
        assert D(result["results"]["median"]) == D(".05")
        assert D(result["results"]["upper_quartile"]) == D(".07")
    return dataset, study, screen, result


async def test_actual_rp_sales_benchmark_and_segmentation(environment):
    c = environment
    f = await prepared(c)
    path = f"/api/v1/tp/engagements/{f['eid']}"
    matrix = await c.post(path + f"/matrix/{f['profile']['id']}", headers=f["analyst"][0])
    assert matrix.status_code == 201, matrix.text
    rows = (
        await c.get(path + f"/runs/{matrix.json()['id']}?limit=1", headers=f["analyst"][0])
    ).json()
    assert rows["row_counts"]["rows"] == 2 and len(rows["results"]["rows"]) == 1
    segments = await f["ready"](
        "segmentation",
        {
            **f["common"],
            "lines": [
                {
                    "financial_line_code": code,
                    "metric": metric,
                    "classification": "related",
                    "driver": "direct",
                    "allocation": [{"segment": "related", "weight": 1}],
                    "methodology": "Synthetic directly assigned financial statement line",
                }
                for code, metric in [
                    ("100", "assets"),
                    ("300", "other"),
                    ("400", "revenue"),
                    ("500", "cost_sales"),
                ]
            ],
        },
    )
    run = await c.post(path + f"/calculate/{segments['id']}", headers=f["analyst"][0])
    assert run.status_code == 201, run.text
    details = (await c.get(path + f"/runs/{run.json()['id']}", headers=f["analyst"][0])).json()
    assert details["results"]["reconciled"]
    assert D(details["results"]["segments"][0]["operating_margin"]) == D(".6")
    _, _, _, bench = await benchmark(c, f)
    export = await c.get(path + f"/runs/{bench['id']}/export/json", headers=f["analyst"][0])
    assert export.status_code == 200
    assert (
        "population" not in export.json()["results"]
        and "company_results" not in export.json()["results"]
    )
    # Original economic leg cannot be classified twice even with another reference.
    duplicate = await c.post(
        path + "/records/transaction",
        headers=f["analyst"][0],
        json={
            "reference": "DUP",
            "title": "Synthetic duplicate",
            "body": {
                k: v for k, v in f["transactions"][0]["body"].items() if not k.startswith("review_")
            },
        },
    )
    assert duplicate.status_code == 409
    async with Session() as db, db.begin():
        await tenant_context(db, f["h"]["X-Tenant-ID"])
        opposite = await db.scalar(
            select(JournalLine).where(
                JournalLine.journal_id == f["lines"]["400"].journal_id,
                JournalLine.id != f["lines"]["400"].id,
            )
        )
    body = {k: v for k, v in f["transactions"][0]["body"].items() if not k.startswith("review_")}
    body.update(
        journal_line_ids=[str(opposite.id)],
        source_amount=str(opposite.debit - opposite.credit),
        base_amount=str(opposite.base_debit - opposite.base_credit),
        economic_key="OPPOSITE-LEG",
        side="receivable",
        category="assets",
        nature="other",
    )
    opposite_response = await c.post(
        path + "/records/transaction",
        headers=f["analyst"][0],
        json={"reference": "OPPOSITE", "title": "Synthetic opposite leg rejected", "body": body},
    )
    assert opposite_response.status_code == 409, opposite_response.text


async def test_actual_loan_benchmark_credit_and_source_scope(environment):
    c = environment
    f = await prepared(c)
    _, study, _, _ = await benchmark(c, f, purpose="interest")
    body = loan().model_dump(mode="json")
    body.update(
        **f["common"],
        relationship_id=f["relationship"]["id"],
        lender_id=f["parent"]["id"],
        borrower_id=f["counterparty"]["id"],
        benchmark_study_id=study["id"],
        cashflows=[
            {
                "date": "2027-01-01",
                "kind": "repayment",
                "amount": "100000",
                "reference": "Synthetic bullet",
            }
        ],
        expected_outstanding="0",
    )
    obj = await f["ready"]("loan", body)
    result = await c.post(
        f"/api/v1/tp/engagements/{f['eid']}/calculate/{obj['id']}", headers=f["analyst"][0]
    )
    assert result.status_code == 201, result.text
    assert D(result.json()["results"]["total_interest"]) == 10000
    assert result.json()["results"]["benchmark"]["synthetic"]
    assert result.json()["results"]["estimated_impact_at_selected_target"] is None


async def test_licensing_permissions_and_immutable_sources(environment):
    c = environment
    f = await prepared(c)
    dataset, study, screen, bench = await benchmark(c, f, allow_ai=False, allow_derived=False)
    from app.modules.tp.service import clean

    future = await c.post(
        f"/api/v1/tp/engagements/{f['eid']}/records/dataset",
        headers=f["analyst"][0],
        json={
            "reference": "FUTURE",
            "title": "Synthetic future snapshot rejected",
            "body": {**clean(dataset["body"]), "observation_date": "2028-01-01"},
        },
    )
    assert future.status_code == 422
    path = f"/api/v1/tp/engagements/{f['eid']}"
    assert (
        await c.get(path + f"/runs/{bench['id']}/export/json", headers=f["analyst"][0])
    ).status_code == 403
    from sqlalchemy import func

    from app.modules.tp.models import Observation, TPRun

    async with Session() as db, db.begin():
        await tenant_context(db, str(uuid.uuid4()))
        assert (
            await db.scalar(
                select(func.count()).select_from(TPRun).where(TPRun.id == uuid.UUID(bench["id"]))
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Observation)
                .where(Observation.dataset_id == uuid.UUID(dataset["id"]))
            )
            == 0
        )
    auditor = await actor(f["h"], "Auditor", "tp-forbidden")
    await grant(c, f["h"], f["base"], auditor)
    assert (await c.get(path + "/workspace", headers=auditor[0])).status_code == 403
    assert (await c.get(f["base"] + "/tp-study", headers=auditor[0])).status_code == 403
    assert (
        await c.post(
            path + "/ai",
            headers=f["analyst"][0],
            json={
                "profile_id": f["profile"]["id"],
                "source_id": study["id"],
                "task": "benchmark_narrative",
            },
        )
    ).status_code == 403
    loan_body = loan().model_dump(mode="json")
    loan_body.update(
        **f["common"],
        relationship_id=f["relationship"]["id"],
        lender_id=f["parent"]["id"],
        borrower_id=f["counterparty"]["id"],
        benchmark_study_id=study["id"],
    )
    # Use an interest-purpose source so the nested run is economically typed.
    _, interest_study, _, _ = await benchmark(c, f, purpose="interest", allow_ai=False)
    loan_body["benchmark_study_id"] = interest_study["id"]
    agreement = await f["ready"]("loan", loan_body)
    loan_run = await c.post(path + f"/calculate/{agreement['id']}", headers=f["analyst"][0])
    assert loan_run.status_code == 201, loan_run.text
    nested_disclosure = await c.post(
        path + "/ai",
        headers=f["analyst"][0],
        json={
            "profile_id": f["profile"]["id"],
            "source_id": agreement["id"],
            "run_id": loan_run.json()["id"],
            "task": "loan_memo",
        },
    )
    assert nested_disclosure.status_code == 403
    broken = await c.post(
        path + f"/datasets/{dataset['id']}/import",
        headers=f["analyst"][0],
        files={"file": ("invalid.xlsx", b"not a ZIP archive", "application/octet-stream")},
    )
    assert broken.status_code == 422
    async with Session() as db, db.begin():
        await tenant_context(db, f["h"]["X-Tenant-ID"])
        with pytest.raises(Exception, match="immutable|Immutable|append only"):
            await db.execute(
                text("UPDATE tp_comparable_observations SET name='wrong' WHERE dataset_id=:id"),
                {"id": uuid.UUID(dataset["id"])},
            )


async def test_all_thirty_ai_actions_remain_suggestions(environment, monkeypatch):
    from redis.asyncio import Redis

    from app.core.config import settings
    from app.modules.tp.catalogue import AI_TASKS

    c = environment
    f = await prepared(c)
    monkeypatch.setattr(settings(), "financial_ai_hourly_requests", 30)
    async with Redis.from_url(settings().redis_url) as redis:
        await redis.delete("tp-ai-budget:" + f["h"]["X-Tenant-ID"])
    path = f"/api/v1/tp/engagements/{f['eid']}/ai"
    last = None
    for task in AI_TASKS:
        result = await c.post(
            path,
            headers=f["analyst"][0],
            json={"profile_id": f["profile"]["id"], "source_id": f["far"]["id"], "task": task},
        )
        assert result.status_code == 201, result.text
        last = result.json()
        assert last["status"] == "SUGGESTED"
        assert not last["body"]["output"]["arms_length_conclusion_approved"]
    rejected = await c.post(
        path,
        headers=f["analyst"][0],
        json={"profile_id": f["profile"]["id"], "source_id": f["far"]["id"], "task": AI_TASKS[0]},
    )
    assert rejected.status_code == 429
    bypass = await c.post(
        f["base"] + f"/records/{last['id']}/actions",
        headers=f["analyst"][0],
        json={"version": last["version"], "action": "submit", "comments": "Attempt generic path"},
    )
    assert bypass.status_code == 409
    decision = {
        "version": last["version"],
        "decision": "ACCEPTED",
        "rationale": "Synthetic independent review; no figure changes",
    }
    assert (
        await c.post(path + f"/{last['id']}/decision", headers=f["analyst"][0], json=decision)
    ).status_code == 403
    reviewed = await c.post(
        path + f"/{last['id']}/decision", headers=f["manager"][0], json=decision
    )
    assert reviewed.status_code == 200, reviewed.text


async def test_source_reconciled_services_and_reviewed_localfile_exports(environment):
    from app.modules.tp.catalogue import LOCAL_SECTIONS

    c = environment
    f = await prepared(c)
    path = f"/api/v1/tp/engagements/{f['eid']}"
    matrix_response = await c.post(path + f"/matrix/{f['profile']['id']}", headers=f["analyst"][0])
    assert matrix_response.status_code == 201, matrix_response.text
    matrix = matrix_response.json()
    segment = await f["ready"](
        "segmentation",
        {
            **f["common"],
            "lines": [
                {
                    "financial_line_code": code,
                    "metric": metric,
                    "classification": "related",
                    "driver": "direct",
                    "allocation": [{"segment": "related", "weight": 1}],
                    "methodology": "Synthetic direct source statement assignment",
                }
                for code, metric in [
                    ("100", "assets"),
                    ("300", "other"),
                    ("400", "revenue"),
                    ("500", "cost_sales"),
                ]
            ],
        },
    )
    response = await c.post(path + f"/calculate/{segment['id']}", headers=f["analyst"][0])
    assert response.status_code == 201, response.text
    reconciliation = response.json()
    cost = f["transactions"][1]
    service = await f["ready"](
        "service",
        {
            **f["common"],
            "transaction_ids": [cost["id"]],
            "cost_line_ids": cost["body"]["journal_line_ids"],
            "cost_pool": cost["body"]["base_amount"],
            "allocations": [{"segment": f["counterparty"]["id"], "weight": 1}],
            "allocation_driver": "Synthetic direct beneficiary",
            "methodology": "Actual GL cost pool",
            "markup": ".05",
            "benefit_test": "Synthetic service benefit evidence reviewed",
            "provider_id": f["parent"]["id"],
            "recipients": [f["counterparty"]["id"]],
            "legal_conditions": "No automatic simplified approach assumption",
        },
    )
    response = await c.post(path + f"/calculate/{service['id']}", headers=f["analyst"][0])
    assert response.status_code == 201, response.text
    assert D(response.json()["results"]["allocation_difference"]) == 0
    _, _, _, study = await benchmark(c, f)
    sections = []
    for key in LOCAL_SECTIONS:
        refs = (
            [f["far"]["id"]]
            if key == "far"
            else [f["method"]["id"]]
            if key == "method"
            else [f["note"]["id"]]
        )
        runs = (
            [study["id"]]
            if key == "benchmarking"
            else [matrix["id"]]
            if key == "controlled_transactions"
            else []
        )
        sections.append(
            {
                "key": key,
                "narrative": "SYNTHETIC SOFTWARE TEST ONLY. Independently reviewed source-linked "
                + key.replace("_", " ")
                + ". No real market or tax opinion is expressed.",
                "evidence_ids": refs,
                "run_ids": runs,
                "human_verified": True,
            }
        )
    document = await f["ready"](
        "localfile",
        {
            **f["common"],
            "sections": sections,
            "checklist_complete": True,
            "financial_reconciliation_run_id": reconciliation["id"],
            "license_review": "Synthetic derived exports permitted; no raw observations included",
            "annual_version": 1,
        },
        stages=True,
    )
    response = await c.post(path + f"/calculate/{document['id']}", headers=f["analyst"][0])
    assert response.status_code == 201, response.text
    docrun = response.json()
    assert docrun["results"]["complete"], docrun
    output = Path(__file__).resolve().parents[3] / "docs" / "phase-8" / "export-evidence"
    output.mkdir(parents=True, exist_ok=True)
    for format in ["json", "xlsx", "pdf", "docx"]:
        exported = await c.get(
            path + f"/runs/{docrun['id']}/export/{format}", headers=f["analyst"][0]
        )
        assert exported.status_code == 200, exported.text
        assert len(exported.content) > 200
        (output / ("synthetic-localfile." + format)).write_bytes(exported.content)
    release = await f["ready"](
        "release",
        {
            **f["common"],
            "document_run_id": docrun["id"],
            "client_visible": True,
            "confidential_notes_excluded": True,
            "disclosure_authorization": "SYNTHETIC software test client-safe issue authorized",
        },
        stages=True,
    )
    assert release["body"]["client_document"]["run_sha256"] == docrun["sha256"]
    viewer = await actor(f["h"], "Client Viewer", "tp-client")
    issued = "/api/v1/tp/client-documents"
    assert (await c.get(issued, headers=viewer[0])).json()["items"] == []
    assert (
        await c.get(issued + f"/{release['id']}/download", headers=viewer[0])
    ).status_code == 404
    from app.db.models.platform import Engagement, LegalEntity

    async with Session() as db, db.begin():
        await tenant_context(db, f["h"]["X-Tenant-ID"])
        eng = await db.get(Engagement, uuid.UUID(f["eid"]))
        entity = await db.get(LegalEntity, eng.entity_id)
        client_id = str(entity.client_id)
    grant_response = await c.post(
        "/api/v1/admin/client-access",
        headers=f["h"],
        json={"membership_id": viewer[1], "client_id": client_id},
    )
    assert grant_response.status_code == 200, grant_response.text
    listing = (await c.get(issued, headers=viewer[0])).json()
    assert len(listing["items"]) == 1
    assert "body" not in listing["items"][0] and "dataset_ids" not in listing["items"][0]
    pdf = await c.get(issued + f"/{release['id']}/download", headers=viewer[0])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (await c.get(path + "/workspace", headers=viewer[0])).status_code == 403
    # Malformed bridge bodies are validation errors, never server failures.
    invalid = await c.post(
        path + f"/runs/{docrun['id']}/tax-adjustment", headers=f["manager"][0], json={}
    )
    assert invalid.status_code == 422


async def test_connected_person_remuneration_and_ct_adjustment_bridge(environment):
    c = environment
    f = await prepared(c, connected=True)
    path = f"/api/v1/tp/engagements/{f['eid']}"
    _, study, _, bench = await benchmark(c, f, purpose="remuneration")
    remuneration = await f["ready"](
        "remuneration",
        {
            **f["common"],
            "party_id": f["counterparty"]["id"],
            "transaction_ids": [f["transactions"][1]["id"]],
            "base_salary": "600000",
            "bonus": "100000",
            "allowances": "50000",
            "benefits": "50000",
            "management_fees": 0,
            "responsibilities": "Synthetic director management duties",
            "time_commitment": "Synthetic full-time",
            "experience": "Synthetic fifteen years",
            "size_performance": "Synthetic reviewed business size",
            "study_id": study["id"],
            "adjustment_basis": "No numeric comparability adjustment selected",
        },
    )
    response = await c.post(path + f"/calculate/{remuneration['id']}", headers=f["analyst"][0])
    assert response.status_code == 201, response.text
    run = response.json()
    assert D(run["results"]["total_compensation"]) == 800000
    assert D(run["results"]["difference"]) == 0
    disclosure = await f["ready"](
        "disclosure",
        {
            **f["common"],
            "population_complete": True,
            "exclusions_review": "Synthetic reviewed population",
            "group_aggregation_review": "Synthetic Article 36 family aggregation",
        },
    )
    response = await c.post(path + f"/calculate/{disclosure['id']}", headers=f["analyst"][0])
    assert response.status_code == 201, response.text
    assert D(response.json()["results"]["connected_totals"]["SYN-DIRECTOR-FAMILY"]) == 800000
    assert D(response.json()["results"]["rp_total"]) == 0
    judgment = await f["ready"](
        "judgment",
        {
            **f["common"],
            "run_id": run["id"],
            "conclusion": "NOT_SUPPORTED",
            "proposed_tax_adjustment": "10000",
            "software_test_only": True,
            "no_automatic_percentile_conclusion": True,
        },
        stages=True,
    )
    body = {
        "judgment_id": judgment["id"],
        "tax_profile_id": f["tax_profile"]["id"],
        "tax_rule_id": f["tax_rules"]["adjustments"],
        "account_codes": ["500"],
        "rationale": "Synthetic independently reviewed upward adjustment; not automatic median targeting",
    }
    response = await c.post(path + f"/runs/{run['id']}/tax-adjustment", headers=f["h"], json=body)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "IN_PROGRESS"
    assert D(response.json()["body"]["proposed_adjustment"]) == 10000
    repeated = await c.post(path + f"/runs/{run['id']}/tax-adjustment", headers=f["h"], json=body)
    assert repeated.status_code == 201 and repeated.json()["id"] == response.json()["id"]


async def test_tp_job_controls_require_owner_and_exact_operation(environment, monkeypatch):
    from app.db.models.platform import BackgroundJob, Membership
    from app.workers.accounting import work

    c = environment
    f = await prepared(c)
    monkeypatch.setattr(work, "apply_async", lambda **kwargs: None)
    async with Session() as db, db.begin():
        await tenant_context(db, f["h"]["X-Tenant-ID"])
        member = await db.get(Membership, uuid.UUID(f["analyst"][1]))
        jobs = []
        for kind, state in [
            ("tp.calculate", "pending"),
            ("tp.calculate", "failed"),
            ("analytics", "pending"),
        ]:
            job = BackgroundJob(
                tenant_id=uuid.UUID(f["h"]["X-Tenant-ID"]),
                created_by=member.user_id,
                job_type=kind,
                status=state,
                idempotency_key=str(uuid.uuid4()),
                payload={"engagement_id": f["eid"], "record_id": f["far"]["id"]},
            )
            db.add(job)
            await db.flush()
            jobs.append(str(job.id))
    path = f"/api/v1/tp/engagements/{f['eid']}/jobs/"
    assert (await c.post(path + jobs[0] + "/cancel", headers=f["manager"][0])).status_code == 403
    cancelled = await c.post(path + jobs[0] + "/cancel", headers=f["analyst"][0])
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled", (
        cancelled.text
    )
    retried = await c.post(path + jobs[1] + "/retry", headers=f["analyst"][0])
    assert retried.status_code == 200 and retried.json()["status"] == "pending", retried.text
    assert (await c.post(path + jobs[2] + "/cancel", headers=f["analyst"][0])).status_code == 404


async def test_transitive_far_changes_invalidate_benchmark_and_require_parent_review(environment):
    c = environment
    f = await prepared(c)
    _, study, _, run = await benchmark(c, f)
    path = f"/api/v1/tp/engagements/{f['eid']}"
    returned = await action(c, f["manager"][0], f["base"], f["far"], "return")
    stale = await c.get(path + f"/runs/{run['id']}", headers=f["analyst"][0])
    assert stale.status_code == 200 and not stale.json()["dependencies_current"]
    assert (
        await c.get(path + f"/runs/{run['id']}/export/json", headers=f["analyst"][0])
    ).status_code == 409
    submitted = await action(c, f["analyst"][0], f["base"], returned, "submit")
    reviewed = await action(c, f["manager"][0], f["base"], submitted, "approve")
    assert reviewed["status"] == "APPROVED"
    # Reapproval does not retroactively update the method's prior assessment.
    recalculated = await c.post(path + f"/calculate/{study['id']}", headers=f["analyst"][0])
    assert recalculated.status_code == 409, recalculated.text
    assert "parent review" in recalculated.text


async def test_manual_specialist_calculators_do_not_claim_external_ratings_or_market_rates(
    environment,
):
    c = environment
    f = await prepared(c)
    path = f"/api/v1/tp/engagements/{f['eid']}"
    _, study, _, _ = await benchmark(c, f)
    cases = [
        (
            "credit",
            {
                "borrower_id": f["counterparty"]["id"],
                "debt": "100000",
                "cash": "20000",
                "ebit": "50000",
                "interest": "10000",
                "current_assets": "50000",
                "current_liabilities": "25000",
                "operating_cashflow": "20000",
                "standalone_assessment": "SYNTHETIC manually supplied borrower facts",
                "group_support": "No inferred support",
                "country_risk": "Synthetic review",
                "proxy_label": "INTERNAL SOFTWARE TEST BAND",
                "proxy_methodology": "Uncalibrated internal assessment; no agency rating",
                "benchmark_matching_review": "Manual review required",
            },
            "interest_coverage",
            D(5),
        ),
        (
            "royalty",
            {
                "party_id": f["counterparty"]["id"],
                "transaction_ids": [f["transactions"][0]["id"]],
                "dempe": {
                    k: "Synthetic function evidence reviewed"
                    for k in [
                        "development",
                        "enhancement",
                        "maintenance",
                        "protection",
                        "exploitation",
                    ]
                },
                "legal_ownership": "Synthetic legal ownership",
                "economic_ownership": "No automatic DEMPE conclusion",
                "revenue_base": "2000000",
                "rate": ".05",
            },
            "royalty",
            D(100000),
        ),
        (
            "guarantee",
            {
                "relationship_id": f["relationship"]["id"],
                "characterization": "guarantee",
                "principal": "100000",
                "selected_rate": ".01",
                "days": 365,
                "denominator": 365,
                "benefit_assessment": "Synthetic reviewed benefit",
                "credit_evidence": "Synthetic internal facts only",
                "pricing_methodology": "Reviewed simple supplied rate; not market evidence",
            },
            "fee",
            D(1000),
        ),
        (
            "comparability",
            {
                "study_id": study["id"],
                "tested_receivables": 20,
                "tested_inventory": 10,
                "tested_payables": 5,
                "tested_revenue": 100,
                "comparable_receivables": 10,
                "comparable_inventory": 10,
                "comparable_payables": 5,
                "comparable_revenue": 100,
                "financing_rate": ".05",
                "rate_source": "Synthetic supplied financing assumption",
                "selected": True,
            },
            "margin_adjustment",
            D(".005"),
        ),
    ]
    for kind, body, key, expected in cases:
        paper = await f["ready"](kind, {**f["common"], **body})
        response = await c.post(path + f"/calculate/{paper['id']}", headers=f["analyst"][0])
        assert response.status_code == 201, response.text
        assert D(response.json()["results"][key]) == expected
