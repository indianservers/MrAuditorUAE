import hashlib
import json
import os
import uuid

import pytest
from sqlalchemy import select

from app.db.models.platform import User
from app.db.session import Session, tenant_context
from tests.integration.test_platform import environment as environment
from tests.integration.test_platform import setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1",
    reason="Requires migrated disposable PostgreSQL and Redis",
)


async def scope(client):
    headers, _ = await setup(client)
    c = await client.post(
        "/api/v1/clients",
        headers=headers,
        json={"code": "SYNTHETIC", "name": "FICTIONAL Gulf Example LLC — synthetic test only"},
    )
    e = await client.post(
        "/api/v1/entities",
        headers=headers,
        json={
            "client_id": c.json()["id"],
            "name": "FICTIONAL synthetic entity",
            "country": "AE",
            "jurisdiction": "Synthetic",
            "functional_currency": "AED",
            "presentation_currency": "AED",
        },
    )
    p = await client.post(
        "/api/v1/financial-periods",
        headers=headers,
        json={"entity_id": e.json()["id"], "start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    return headers, {
        "client_id": c.json()["id"],
        "entity_id": e.json()["id"],
        "period_id": p.json()["id"],
        "expected_rows": 4,
        "expected_debit": "110.30",
        "expected_credit": "110.30",
        "source_complete": True,
    }


CSV = b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n100,Cash,OPEN,2026-01-01,10.10,0,L1,true,false,Opening\n300,Equity,OPEN,2026-01-01,0,10.10,L2,true,false,Opening\n500,Expense,1,2026-12-26,100.20,0,L3,false,true,Adjustment\n100,Cash,1,2026-12-26,0,100.20,L4,false,true,Adjustment\n"


async def upload(client, headers, options, data=CSV, filename="synthetic.csv"):
    response = await client.post(
        "/api/v1/accounting/imports",
        headers=headers,
        data={"options": json.dumps(options)},
        files={"file": (filename, data, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def committed(client, headers, options, data=CSV):
    identifier = await upload(client, headers, options, data)
    validation = await client.post(
        f"/api/v1/accounting/imports/{identifier}/validate", headers=headers
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["status"] == "validated", validation.text
    result = await client.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=headers)
    assert result.status_code == 200, result.text
    details = (await client.get(f"/api/v1/accounting/imports/{identifier}", headers=headers)).json()
    return identifier, details["snapshot_id"]


async def test_full_pipeline_and_lineage(environment, tmp_path):
    client = environment
    headers, options = await scope(client)
    identifier, snapshot = await committed(client, headers, options)
    assert await upload(client, headers, options) == identifier
    preview = await client.get(f"/api/v1/accounting/imports/{identifier}/preview", headers=headers)
    assert len(preview.json()["rows"]) == 4
    balance = await client.get(
        "/api/v1/accounting/trial-balance", headers=headers, params={"snapshot_id": snapshot}
    )
    assert balance.status_code == 200, balance.text
    result = balance.json()
    assert result["balanced"] and result["total"] == 3
    cash = next(r for r in result["items"] if r["code"] == "100")
    assert str(cash["closing"]) == "-90.10000000"
    mapping = {
        "client_id": options["client_id"],
        "entity_id": options["entity_id"],
        "period_id": options["period_id"],
        "name": "Approved synthetic mapping",
        "approved": True,
        "mapping": {
            "accounts": {
                "100": {"classification": "Assets", "statement_group": "Cash"},
                "300": {"classification": "Equity"},
                "500": {"classification": "Expenses"},
            }
        },
    }
    response = await client.post("/api/v1/accounting/mappings", headers=headers, json=mapping)
    assert response.status_code == 201, response.text
    analytics = await client.post(
        "/api/v1/analytics/runs",
        headers=headers,
        json={
            "snapshot_id": snapshot,
            "holidays": ["2026-12-26"],
            "materiality": "50",
            "year_end": "2026-12-31",
        },
    )
    assert analytics.status_code == 201, analytics.text
    assert len(analytics.json()["result"]["rules"]) == 25
    run = analytics.json()["id"]
    findings = (
        await client.get("/api/v1/analytics/findings", headers=headers, params={"run_id": run})
    ).json()
    assert findings["total"] > 0
    ledger = (await client.get("/api/v1/accounting/ledger", headers=headers)).json()
    assert ledger["total"] == 4
    line = ledger["items"][0]["id"]
    lineage = await client.get("/api/v1/accounting/lineage/" + line, headers=headers)
    assert lineage.status_code == 200 and lineage.json()["source_record"]["raw"]
    reconciliation = await client.post(
        "/api/v1/reconciliation/runs", headers=headers, json={"snapshot_id": snapshot}
    )
    assert reconciliation.status_code == 201, reconciliation.text
    assert reconciliation.json()["status"] == "insufficient_evidence"
    sample = await client.post(
        "/api/v1/sampling/runs",
        headers=headers,
        json={"snapshot_id": snapshot, "method": "random", "size": 1, "seed": 42},
    )
    assert sample.status_code == 201, sample.text
    for task in [
        "account-classification",
        "anomaly-explanation",
        "audit-procedures",
        "financial-commentary",
    ]:
        response = await client.post(
            "/api/v1/ai/" + task,
            headers=headers,
            json={"snapshot_id": snapshot, "line_ids": [line], "analytics_run_id": run},
        )
        assert response.status_code == 200, response.text
        assert response.json()["output"]["requires_review"] is True
    after = (await client.get("/api/v1/accounting/ledger", headers=headers)).json()
    assert after == ledger
    evidence = {
        "synthetic": True,
        "import": identifier,
        "snapshot": snapshot,
        "trial_balance": result,
        "analytics": analytics.json(),
        "reconciliation": reconciliation.json(),
        "sampling": sample.json(),
    }
    from pathlib import Path

    Path(os.getenv("EVIDENCE_DIRECTORY", "../docs/evidence")).mkdir(parents=True, exist_ok=True)
    (
        Path(os.getenv("EVIDENCE_DIRECTORY", "../docs/evidence")) / "phase-2-pipeline.json"
    ).write_text(json.dumps(evidence, indent=2), encoding="utf-8")


async def test_failed_import_and_replacement(environment):
    client = environment
    headers, options = await scope(client)
    invalid = CSV.replace(b"0,100.20,L4", b"0,100.10,L4")
    identifier = await upload(client, headers, options, invalid)
    result = await client.post(f"/api/v1/accounting/imports/{identifier}/validate", headers=headers)
    assert result.json()["status"] == "blocked"
    assert (
        await client.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=headers)
    ).status_code == 409
    first, snapshot = await committed(client, headers, options)
    replacement = {**options, "supersedes_id": first}
    second, new_snapshot = await committed(client, headers, replacement)
    assert second != first and new_snapshot != snapshot
    assert (await client.get("/api/v1/accounting/ledger", headers=headers)).json()["total"] == 4
    assert (
        await client.get(
            "/api/v1/accounting/trial-balance", headers=headers, params={"snapshot_id": snapshot}
        )
    ).status_code == 200


async def test_tenant_and_client_scope_denial(environment):
    client = environment
    headers, options = await scope(client)
    mismatch = {**options, "client_id": str(uuid.uuid4())}
    response = await client.post(
        "/api/v1/accounting/imports",
        headers=headers,
        data={"options": json.dumps(mismatch)},
        files={"file": ("test.csv", CSV)},
    )
    assert response.status_code == 404
    response = await client.post(
        "/api/v1/accounting/imports",
        data={"options": json.dumps(options)},
        files={"file": ("test.csv", CSV)},
    )
    assert response.status_code == 401
    identifier, snapshot = await committed(client, headers, options)
    assert (
        await client.get(
            "/api/v1/accounting/imports/" + identifier,
            headers={**headers, "X-Tenant-ID": str(uuid.uuid4())},
        )
    ).status_code == 403
    assert (
        await client.get(
            "/api/v1/accounting/trial-balance",
            headers=headers,
            params={"snapshot_id": str(uuid.uuid4())},
        )
    ).status_code == 404


async def test_resumable_upload(environment):
    client = environment
    headers, options = await scope(client)
    response = await client.post(
        "/api/v1/accounting/uploads",
        headers=headers,
        json={
            "options": options,
            "filename": "synthetic.csv",
            "total_size": len(CSV),
            "sha256": hashlib.sha256(CSV).hexdigest(),
        },
    )
    assert response.status_code == 201, response.text
    identifier = response.json()["id"]
    assert (
        await client.post(f"/api/v1/accounting/uploads/{identifier}/complete", headers=headers)
    ).status_code == 409
    for _ in range(2):
        response = await client.put(
            f"/api/v1/accounting/uploads/{identifier}/chunks/0", headers=headers, content=CSV
        )
        assert response.status_code == 200, response.text
    response = await client.get(f"/api/v1/accounting/uploads/{identifier}", headers=headers)
    assert response.json()["received"] == [0]
    response = await client.post(
        f"/api/v1/accounting/uploads/{identifier}/complete", headers=headers
    )
    assert response.status_code == 200, response.text
    assert (
        await client.post(f"/api/v1/accounting/uploads/{identifier}/complete", headers=headers)
    ).json() == response.json()


@pytest.mark.parametrize("method", ["random", "systematic", "mus", "high_value", "full"])
async def test_sampling_api_methods(environment, method):
    client = environment
    headers, options = await scope(client)
    _, snapshot = await committed(client, headers, options)
    response = await client.post(
        "/api/v1/sampling/runs",
        headers=headers,
        json={"snapshot_id": snapshot, "method": method, "size": 2, "seed": 42, "threshold": "10"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["result"]["selected_count"] > 0
    if method == "mus":
        assert response.json()["result"]["excluded_negative"] == 1


async def test_accounting_worker_and_reauthorization(environment, monkeypatch):
    from sqlalchemy import update

    from app.db.models.platform import BackgroundJob, Membership
    from app.workers.accounting import process, work

    client = environment
    headers, options = await scope(client)
    identifier = await upload(client, headers, options)
    monkeypatch.setattr(work, "apply_async", lambda **kwargs: None)
    response = await client.post(
        f"/api/v1/accounting/imports/{identifier}/validate?background=true", headers=headers
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    async with Session() as db:
        user = await db.scalar(select(User))
    await process(job_id, headers["X-Tenant-ID"], str(user.id))
    result = await client.get("/api/v1/jobs/" + job_id, headers=headers)
    assert result.json()["status"] == "completed" and result.json()["progress"] == 100
    assert (await client.get("/api/v1/accounting/imports/" + identifier, headers=headers)).json()[
        "status"
    ] == "validated"
    await client.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=headers)
    snapshot = (
        await client.get("/api/v1/accounting/imports/" + identifier, headers=headers)
    ).json()["snapshot_id"]
    response = await client.post(
        "/api/v1/analytics/runs?background=true", headers=headers, json={"snapshot_id": snapshot}
    )
    assert response.status_code == 201, response.text
    await process(response.json()["id"], headers["X-Tenant-ID"], str(user.id))
    result = await client.get("/api/v1/jobs/" + response.json()["id"], headers=headers)
    assert result.json()["status"] == "completed", result.text
    for path, body in [
        ("reconciliation", {"snapshot_id": snapshot}),
        ("sampling", {"snapshot_id": snapshot, "method": "random", "size": 1}),
    ]:
        response = await client.post(
            f"/api/v1/{path}/runs?background=true", headers=headers, json=body
        )
        await process(response.json()["id"], headers["X-Tenant-ID"], str(user.id))
        assert (await client.get("/api/v1/jobs/" + response.json()["id"], headers=headers)).json()[
            "status"
        ] == "completed"
    response = await client.post(
        "/api/v1/ai/anomaly-explanation?background=true",
        headers=headers,
        json={"snapshot_id": snapshot},
    )
    await process(response.json()["id"], headers["X-Tenant-ID"], str(user.id))
    assert (await client.get("/api/v1/jobs/" + response.json()["id"], headers=headers)).json()[
        "status"
    ] == "completed"
    async with Session() as db:
        async with db.begin():
            await tenant_context(db, headers["X-Tenant-ID"])
            job = BackgroundJob(
                tenant_id=uuid.UUID(headers["X-Tenant-ID"]),
                created_by=user.id,
                idempotency_key="revoked-phase2",
                job_type="analytics",
                payload={"snapshot_id": snapshot},
            )
            db.add(job)
            await db.flush()
            revoked_id = job.id
            await db.execute(update(Membership).values(status="disabled"))
    await process(str(revoked_id), headers["X-Tenant-ID"], str(user.id))
    async with Session() as db:
        await tenant_context(db, headers["X-Tenant-ID"])
        job = await db.get(BackgroundJob, revoked_id)
        assert job.status == "failed" and job.error_category == "authorization"


async def test_tb_only_reconciliation_and_profiles(environment):
    client = environment
    headers, options = await scope(client)
    _, snapshot = await committed(client, headers, options)
    profile_options = {key: options[key] for key in ["client_id", "entity_id", "period_id"]}
    mapping = await client.post(
        "/api/v1/accounting/mappings",
        headers=headers,
        json={
            **profile_options,
            "name": "Reusable headings",
            "mapping": {"columns": {"account_code": "Code", "account_name": "Name"}},
        },
    )
    assert mapping.status_code == 201, mapping.text
    renamed = CSV.replace(b"Account Code,Account Name", b"Code,Name")
    bad = await upload(
        client,
        headers,
        {
            **options,
            "profile_id": mapping.json()["id"],
            "supersedes_id": (
                await client.get("/api/v1/accounting/imports", headers=headers)
            ).json()["items"][0]["id"],
        },
        renamed,
    )
    assert (
        await client.post(f"/api/v1/accounting/imports/{bad}/validate", headers=headers)
    ).json()["status"] == "validated"
    tb = b"Account Code,Account Name,Opening Balance,Debit,Credit,Closing Balance\n100,Cash,10.10,0,100.20,-90.10\n300,Equity,-10.10,0,0,-10.10\n500,Expense,0,100.20,0,100.20\n"
    tb_options = {
        **profile_options,
        "kind": "tb",
        "expected_rows": 3,
        "expected_debit": "100.20",
        "expected_credit": "100.20",
        "source_complete": True,
    }
    _, control = await committed(client, headers, tb_options, tb)
    balance = await client.get(
        "/api/v1/accounting/trial-balance", headers=headers, params={"snapshot_id": control}
    )
    assert balance.status_code == 200 and balance.json()["journal_level_testable"] is False
    reconciliation = await client.post(
        "/api/v1/reconciliation/runs",
        headers=headers,
        json={"snapshot_id": snapshot, "comparison_snapshot_id": control},
    )
    assert reconciliation.status_code == 201, reconciliation.text
    assert (
        next(
            c for c in reconciliation.json()["result"]["checks"] if c["test"] == "gl_to_source_tb"
        )["status"]
        == "passed"
    )
    assert (
        await client.post("/api/v1/analytics/runs", headers=headers, json={"snapshot_id": control})
    ).status_code == 409
    result = await client.post(
        "/api/v1/accounting/trial-balance", headers=headers, json={"snapshot_id": snapshot}
    )
    assert result.status_code == 200, result.text


async def test_connector_metadata_and_encrypted_sync(environment, monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import settings
    from app.modules.accounting.models import Connection
    from app.modules.connectors.zoho import ZohoConnector

    monkeypatch.setattr(settings(), "connector_encryption_key", Fernet.generate_key().decode())
    client = environment
    headers, options = await scope(client)

    async def get(self, resource, params):
        if resource == "organizations":
            return {
                "code": 0,
                "organizations": [
                    {"organization_id": "123", "name": "FICTIONAL", "currency_code": "AED"}
                ],
            }
        return {"code": 0, resource: [], "page_context": {"page": 1, "has_more_page": False}}

    async def token(self, code=None, redirect_uri=None):
        self.access_token = "synthetic-access"
        self.refresh_token = "synthetic-refresh"
        return {"access_token": self.access_token, "refresh_token": self.refresh_token}

    monkeypatch.setattr(ZohoConnector, "get", get)
    monkeypatch.setattr(ZohoConnector, "token", token)
    data = {key: options[key] for key in ["client_id", "entity_id", "period_id"]}
    response = await client.post(
        "/api/v1/accounting/connections",
        headers=headers,
        json={
            **data,
            "provider": "zoho",
            "name": "TEST ONLY",
            "credentials": {"client_id": "test", "client_secret": "never-return-me"},
        },
    )
    assert response.status_code == 201, response.text
    assert "never-return-me" not in response.text and "encrypted_credentials" not in response.text
    identifier = response.json()["id"]
    authorization = await client.post(
        f"/api/v1/connectors/zoho/{identifier}/authorize",
        headers=headers,
        json={"redirect_uri": "http://localhost:8000/oauth/zoho"},
    )
    assert authorization.status_code == 200, authorization.text
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(authorization.json()["authorization_url"]).query)["state"][0]
    callback = await client.post(
        f"/api/v1/connectors/zoho/{identifier}/callback",
        headers=headers,
        json={"state": state, "code": "test-code"},
    )
    assert callback.status_code == 200, callback.text
    assert (
        await client.post(
            f"/api/v1/connectors/zoho/{identifier}/callback",
            headers=headers,
            json={"state": state, "code": "replay"},
        )
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/connectors/zoho/{identifier}/organizations", headers=headers)
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/connectors/zoho/{identifier}/organization",
            headers=headers,
            json={"organization_id": "123"},
        )
    ).status_code == 200
    result = await client.post(
        f"/api/v1/connectors/zoho/{identifier}/sync?background=false", headers=headers
    )
    assert result.status_code == 200, result.text
    assert (
        result.json()["completeness"] == "insufficient_evidence"
        and result.json()["result"]["complete_general_ledger"] is False
    )
    async with Session() as db:
        await tenant_context(db, headers["X-Tenant-ID"])
        connection = await db.get(Connection, uuid.UUID(identifier))
        assert "never-return-me" not in connection.encrypted_credentials


async def test_synthetic_fixture_demonstration(environment):
    from pathlib import Path

    client = environment
    headers, options = await scope(client)
    fixture = Path("tests/fixtures/phase2")
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    options.update(
        expected_rows=manifest["rows"],
        expected_debit=manifest["debit"],
        expected_credit=manifest["credit"],
    )
    identifier, snapshot = await committed(
        client, headers, options, (fixture / "synthetic-general-ledger.csv").read_bytes()
    )
    analytics = await client.post(
        "/api/v1/analytics/runs",
        headers=headers,
        json={
            "snapshot_id": snapshot,
            "year_end": "2026-12-31",
            "holidays": ["2026-12-26"],
            "weekend_days": [5, 6],
            "calendar_rationale": "Synthetic fixture explicitly uses a Monday to Friday operating calendar",
            "materiality": "100000",
            "voucher_sequential": True,
        },
    )
    assert analytics.status_code == 201, analytics.text
    results = {r["rule_id"]: r for r in analytics.json()["result"]["rules"]}
    for rule in ["J01", "J02", "J05", "J08", "J09", "J10"]:
        assert results[rule]["flagged_count"] > 0
    reconciliation = await client.post(
        "/api/v1/reconciliation/runs", headers=headers, json={"snapshot_id": snapshot}
    )
    sample = await client.post(
        "/api/v1/sampling/runs",
        headers=headers,
        json={"snapshot_id": snapshot, "method": "mus", "size": 5, "seed": 42},
    )
    assert sample.status_code == 201, sample.text
    finding = (
        await client.get(
            "/api/v1/analytics/findings",
            headers=headers,
            params={"run_id": analytics.json()["id"], "limit": 1},
        )
    ).json()["items"][0]
    ai = await client.post(
        "/api/v1/ai/anomaly-explanation",
        headers=headers,
        json={
            "snapshot_id": snapshot,
            "line_ids": [finding["line_id"]],
            "analytics_run_id": analytics.json()["id"],
        },
    )
    assert ai.status_code == 200, ai.text
    review = await client.post(
        "/api/v1/ai/suggestions/" + ai.json()["suggestion_id"] + "/review",
        headers=headers,
        json={"decision": "approved"},
    )
    assert review.status_code == 200 and review.json()["ledger_modified"] is False
    invalid = await upload(
        client, headers, options, (fixture / "synthetic-unbalanced.csv").read_bytes()
    )
    assert (
        await client.post(f"/api/v1/accounting/imports/{invalid}/validate", headers=headers)
    ).json()["status"] == "blocked"
    tb = (
        await client.get(
            "/api/v1/accounting/trial-balance", headers=headers, params={"snapshot_id": snapshot}
        )
    ).json()
    evidence = {
        "synthetic": True,
        "company": manifest["company"],
        "import": identifier,
        "snapshot": snapshot,
        "trial_balance": tb,
        "analytics": analytics.json(),
        "reconciliation": reconciliation.json(),
        "sampling": sample.json(),
        "ai_explanation": ai.json(),
        "human_review": review.json(),
        "invalid_import_rejected": True,
    }
    directory = Path(os.getenv("EVIDENCE_DIRECTORY", "../docs/evidence"))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "phase-2-demonstration.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )


async def test_risk_sampling_currency_and_review_guards(environment):
    client = environment
    headers, options = await scope(client)
    _, snapshot = await committed(client, headers, options)
    policy = await client.post(
        "/api/v1/accounting/currencies",
        headers=headers,
        json={"code": "AED", "precision": 2, "rounding": "ROUND_HALF_UP"},
    )
    assert policy.status_code == 200, policy.text
    result = await client.get(
        "/api/v1/accounting/trial-balance", headers=headers, params={"snapshot_id": snapshot}
    )
    assert result.json()["display_rounding"] == "ROUND_HALF_UP"
    run = await client.post(
        "/api/v1/analytics/runs", headers=headers, json={"snapshot_id": snapshot}
    )
    sample = await client.post(
        "/api/v1/sampling/runs",
        headers=headers,
        json={
            "snapshot_id": snapshot,
            "method": "risk",
            "size": 1,
            "analytics_run_id": run.json()["id"],
        },
    )
    assert sample.status_code == 201, sample.text
    selected = await client.get("/api/v1/sampling/runs/" + sample.json()["id"], headers=headers)
    assert selected.status_code == 200 and selected.json()["selection"]["total"] == 1
    assert (
        await client.get("/api/v1/analytics/runs/" + run.json()["id"], headers=headers)
    ).status_code == 200
    assert (await client.get("/api/v1/analytics/rules", headers=headers)).status_code == 200
    assert (
        await client.get(
            "/api/v1/accounting/ledger?sort=posting_date&date_from=2026-12-01&date_to=2026-12-31",
            headers=headers,
        )
    ).json()["total"] == 2


async def test_zoho_native_journal_and_chart_staging(environment, monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import settings
    from app.modules.connectors.zoho import ZohoConnector

    monkeypatch.setattr(settings(), "connector_encryption_key", Fernet.generate_key().decode())
    client = environment
    headers, options = await scope(client)

    async def get(self, resource, params):
        if resource == "organizations":
            return {
                "code": 0,
                "organizations": [{"organization_id": "123", "currency_code": "AED"}],
            }
        if resource == "chartofaccounts/accounttransactions":
            account = params["account_id"]
            debit = account == "101"
            return {
                "code": 0,
                "transactions": [
                    {
                        "account_id": account,
                        "transaction_id": "501",
                        "transaction_type": "journal",
                        "transaction_date": "2026-06-01",
                        "categorized_transaction_id": account,
                        "currency_code": "AED",
                        "debit_or_credit": "debit" if debit else "credit",
                        "debit_amount": "100" if debit else "0",
                        "credit_amount": "0" if debit else "100",
                    }
                ],
                "page_context": {"page": 1, "has_more_page": False},
            }
        if resource in {"journals/501", "journals/502"}:
            return {
                "code": 0,
                "journal": {
                    "journal_date": "2025-06-01" if resource.endswith("502") else "2026-06-01",
                    "currency_code": "AED",
                    "exchange_rate": 1,
                    "status": "published",
                    "line_items": [
                        {
                            "line_id": "1",
                            "account_id": "101",
                            "account_name": "Cash",
                            "debit_or_credit": "debit",
                            "amount": 100,
                            "bcy_amount": 100,
                        },
                        {
                            "line_id": "2",
                            "account_id": "202",
                            "account_name": "Income",
                            "debit_or_credit": "credit",
                            "amount": 100,
                            "bcy_amount": 100,
                        },
                    ],
                },
            }
        data = []
        if resource == "journals":
            data = [{"journal_id": "501"}, {"journal_id": "502"}]
        if resource == "chartofaccounts":
            data = [
                {"account_id": "101", "account_name": "Cash", "account_type": "cash"},
                {"account_id": "202", "account_name": "Income", "account_type": "income"},
            ]
        return {"code": 0, resource: data, "page_context": {"page": 1, "has_more_page": False}}

    monkeypatch.setattr(ZohoConnector, "get", get)
    body = {key: options[key] for key in ["client_id", "entity_id", "period_id"]}
    response = await client.post(
        "/api/v1/accounting/connections",
        headers=headers,
        json={
            **body,
            "provider": "zoho",
            "name": "TEST ONLY native extraction",
            "credentials": {
                "client_id": "synthetic",
                "client_secret": "synthetic",
                "refresh_token": "synthetic",
            },
        },
    )
    assert response.status_code == 201, response.text
    connection = response.json()["id"]
    selected = await client.post(
        f"/api/v1/connectors/zoho/{connection}/organization",
        headers=headers,
        json={"organization_id": "123"},
    )
    assert selected.status_code == 200, selected.text
    sync = await client.post(
        f"/api/v1/connectors/zoho/{connection}/sync?background=false", headers=headers
    )
    assert sync.status_code == 200, sync.text
    result = sync.json()["result"]
    for key in ["derived_import_batch_id", "derived_chart_batch_id"]:
        identifier = result[key]
        validation = await client.post(
            f"/api/v1/accounting/imports/{identifier}/validate", headers=headers
        )
        assert validation.json()["status"] == "validated", validation.text
        assert (
            await client.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=headers)
        ).status_code == 200
    assert sync.json()["completeness"] == "insufficient_evidence"
    assert result["extracted_lines"] == 2 and result["extracted_accounts"] == 2
    assert result["ledger_coverage"] == "all_account_transaction_types"
    # Manual-journal details remain evidence and are never double-counted into GL.
    assert sum(o["resource"] == "journal_detail" for o in result["objects"]) == 2


@pytest.mark.parametrize("format", ["xml", "json"])
async def test_tally_native_package_pipeline(environment, format):
    import base64

    from tests.phase2.test_connectors import TALLY

    client = environment
    headers, options = await scope(client)
    options.update(
        source_system="tally",
        tally_company="FICTIONAL Test",
        expected_rows=2,
        expected_debit="100.25",
        expected_credit="100.25",
    )
    package = (
        TALLY
        if format == "xml"
        else json.dumps({"exports": {"native": base64.b64encode(TALLY).decode()}}).encode()
    )
    identifier = await upload(client, headers, options, package, "synthetic-tally." + format)
    validation = await client.post(
        f"/api/v1/accounting/imports/{identifier}/validate", headers=headers
    )
    assert validation.json()["status"] == "validated", validation.text
    assert (
        await client.post(f"/api/v1/accounting/imports/{identifier}/commit", headers=headers)
    ).status_code == 200
    assert (await client.get("/api/v1/accounting/ledger", headers=headers)).json()["total"] == 2


async def test_approved_source_group_classification_reuse(environment):
    client = environment
    headers, options = await scope(client)
    body = {key: options[key] for key in ["client_id", "entity_id", "period_id"]}
    profile = await client.post(
        "/api/v1/accounting/mappings",
        headers=headers,
        json={
            **body,
            "name": "Approved source category rule",
            "approved": True,
            "mapping": {
                "groups": {
                    "bank": {"classification": "Assets", "statement_group": "Cash and banks"}
                }
            },
        },
    )
    assert profile.status_code == 201, profile.text
    data = b"account_code,account_name,source_group\nBANK-X,Test bank,bank\n"
    options.update(
        kind="coa",
        expected_rows=1,
        expected_debit=None,
        expected_credit=None,
        source_complete=False,
    )
    await committed(client, headers, options, data)
    account = (await client.get("/api/v1/accounting/accounts", headers=headers)).json()["items"][0]
    assert (
        account["classification"] == "Assets"
        and account["mapping_profile_id"] == profile.json()["id"]
    )


async def test_job_cancel_retry_state_transitions(environment, monkeypatch):
    from app.db.models.platform import BackgroundJob
    from app.workers.accounting import process, work

    client = environment
    headers, options = await scope(client)
    identifier = await upload(client, headers, options)
    monkeypatch.setattr(work, "apply_async", lambda **kwargs: None)
    job = await client.post(
        f"/api/v1/accounting/imports/{identifier}/validate?background=true", headers=headers
    )
    cancelled = await client.post("/api/v1/jobs/" + job.json()["id"] + "/cancel", headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (
        await client.post("/api/v1/jobs/" + job.json()["id"] + "/retry", headers=headers)
    ).status_code == 409
    async with Session() as db:
        async with db.begin():
            await tenant_context(db, headers["X-Tenant-ID"])
            user = await db.scalar(select(User))
            failed = BackgroundJob(
                tenant_id=uuid.UUID(headers["X-Tenant-ID"]),
                created_by=user.id,
                idempotency_key="explicit-retry",
                job_type="import.validate",
                payload={"batch_id": identifier},
                status="failed",
            )
            db.add(failed)
            await db.flush()
            failed_id = failed.id
    retried = await client.post("/api/v1/jobs/" + str(failed_id) + "/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    await process(str(failed_id), headers["X-Tenant-ID"], str(user.id))
    assert (await client.get("/api/v1/jobs/" + str(failed_id), headers=headers)).json()[
        "status"
    ] == "completed"
