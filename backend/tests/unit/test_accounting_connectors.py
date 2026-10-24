import base64
import csv
import io
import json
import uuid
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from app.modules.accounting.schemas import ImportOptions
from app.modules.connectors.catalogue import PROVIDERS
from app.modules.connectors.ledger import zoho_ledger_row
from app.modules.connectors.reports import ReportPackageOptions, inspect_report_set
from app.modules.connectors.tally import parse_export, trial_balance_rows
from app.modules.connectors.zoho import ConnectorError, ZohoConnector
from app.modules.ingestion.parser import ImportProblem, normalize, rows
from tests.phase2.test_connectors import TALLY

START, END = date(2026, 1, 1), date(2026, 12, 31)
SCOPE = {k: str(uuid.uuid4()) for k in ("client_id", "entity_id", "period_id")}


def report_files(tmp_path):
    values = {
        "coa": "account_code,account_name\n100,Cash\n400,Sales\n",
        "tb": "account_code,opening_balance,debit,credit,closing_balance\n100,10,25,0,35\n400,-10,0,25,-35\n",
        "gl": "account_code,journal_ref,posting_date,debit,credit,source_id\n100,INV-1,2026-04-01,25,0,1\n400,INV-1,2026-04-01,0,25,2\n",
    }
    files = {}
    for kind, content in values.items():
        path = tmp_path / (kind + ".csv")
        path.write_text(content)
        files[kind] = (path, path.name)
    return files


@pytest.mark.parametrize("provider", [p["id"] for p in PROVIDERS])
def test_all_sources_retain_identity_and_reconcile(tmp_path, provider):
    options = ReportPackageOptions(**SCOPE, source_system=provider, currency="AED")
    result = inspect_report_set(report_files(tmp_path), options, START, END, "AED")
    assert (
        inspect_report_set(report_files(tmp_path), options, START, END, "AED")["package_id"]
        == result["package_id"]
    )
    assert result["counts"] == {"coa": 2, "tb": 2, "gl": 2}
    assert result["accounts_reconciled"] == 2
    assert result["completeness"] == "independent_source_review_required"
    for kind in ("coa", "tb", "gl"):
        imported = options.import_options(kind)
        assert imported.source_system == provider and not imported.source_complete
        # Metadata is preserved across the upload -> validation schema round trip.
        ImportOptions.model_validate({**imported.model_dump(), "report_package": result})


@pytest.mark.parametrize(
    "kind,before,after,message",
    [
        ("gl", "0,25,2", "0,24,2", "unbalanced"),
        ("gl", "0,25,2", "0,25,1", "Duplicate"),
        ("gl", "400,INV", "999,INV", "missing from chart"),
        ("gl", "2026-04-01", "2025-04-01", "outside selected"),
        ("tb", "100,10,25,0,35", "100,10,24,0,34", "movements"),
        ("tb", "100,10,25,0,35", "100,10,25,0,", "explicit source"),
        ("tb", "100,10,25,0,35", "100,,25,0,25", "explicit source"),
        ("tb", "400,-10,0,25,-35", "400,-9,0,25,-34", "do not balance"),
    ],
)
def test_report_set_rejects_incomplete_or_inconsistent_data(tmp_path, kind, before, after, message):
    files = report_files(tmp_path)
    path = files[kind][0]
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ImportProblem, match=message):
        inspect_report_set(
            files,
            ReportPackageOptions(**SCOPE, source_system="zoho", currency="AED"),
            START,
            END,
            "AED",
        )


def test_report_controls_are_independent_and_checked(tmp_path):
    options = ReportPackageOptions(
        **SCOPE,
        source_system="busy",
        currency="AED",
        controls={
            "gl": {
                "reference": "Source GL report 2026-10-24",
                "expected_rows": 2,
                "expected_debit": "26",
                "expected_credit": "25",
            },
        },
    )
    with pytest.raises(ImportProblem, match="Independent source controls"):
        inspect_report_set(report_files(tmp_path), options, START, END, "AED")


def test_report_column_mapping(tmp_path):
    files = report_files(tmp_path)
    path = files["gl"][0]
    path.write_text(path.read_text().replace("account_code", "ERP Account"))
    options = ReportPackageOptions(
        **SCOPE,
        source_system="sap-s4",
        currency="AED",
        mappings={
            "gl": {"account_code": "ERP Account"},
        },
    )
    assert inspect_report_set(files, options, START, END, "AED")["status"] == "reports_reconciled"


def test_tally_package_supports_coa_gl_and_source_tb(tmp_path):
    content = TALLY.replace(
        b"<PARENT>Cash-in-hand</PARENT>",
        b"<PARENT>Cash-in-hand</PARENT><OPENINGBALANCE>0</OPENINGBALANCE><CLOSINGBALANCE>-100.25</CLOSINGBALANCE>",
    )
    content = content.replace(
        b"<PARENT>Sales Accounts</PARENT>",
        b"<PARENT>Sales Accounts</PARENT><OPENINGBALANCE>0</OPENINGBALANCE><CLOSINGBALANCE>100.25</CLOSINGBALANCE>",
    )
    path = tmp_path / "test.tally.json"
    path.write_text(
        json.dumps(
            {"company": "FICTIONAL Test", "exports": {"all": base64.b64encode(content).decode()}}
        )
    )
    for kind in ("coa", "tb", "gl"):
        options = ImportOptions(
            **SCOPE, source_system="tally", tally_company="FICTIONAL Test", kind=kind
        )
        extracted = list(rows(path, path.name, options))
        assert len(extracted) == 2
        for index, row in extracted:
            normalize(row, options, START, END, "AED", index)
    result = parse_export(content, "FICTIONAL Test", START, END)
    result["masters"]["Cash"]["closing_balance"] = "-101"
    with pytest.raises(ConnectorError, match="does not roll forward"):
        trial_balance_rows(result)


def test_tally_does_not_import_cancelled_or_optional_vouchers():
    for flag in ("ISCANCELLED", "ISOPTIONAL", "ISDELETED"):
        content = TALLY.replace(b"<VOUCHER>", f"<VOUCHER><{flag}>Yes</{flag}>".encode())
        result = parse_export(content, "FICTIONAL Test", START, END)
        assert result["lines"] == [] and result["excluded_nonposting_vouchers"] == 1


async def test_zoho_account_transactions_without_page_context_are_probed_to_empty():
    requests = []

    def respond(request):
        page = int(request.url.params["page"])
        requests.append(page)
        return httpx.Response(
            200, json={"code": 0, "transactions": [{"id": page}] if page < 3 else []}
        )

    adapter = ZohoConnector(
        "in", "id", "secret", access_token="test", transport=httpx.MockTransport(respond)
    )
    pages = [
        p
        async for p in adapter.pages(
            "chartofaccounts/accounttransactions", "123", {"account_id": "42", "page": 9}
        )
    ]
    assert requests == [1, 2, 3] and pages[-1]["raw"]["transactions"] == []


async def test_zoho_repeated_account_transaction_page_fails():
    adapter = ZohoConnector(
        "in",
        "id",
        "secret",
        access_token="test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": 0, "transactions": [{"id": "same"}]})
        ),
    )
    with pytest.raises(ConnectorError, match="Repeated API page"):
        [p async for p in adapter.pages("chartofaccounts/accounttransactions", "123")]


def transaction(account="100", side="debit"):
    return {
        "account_id": account,
        "transaction_id": "123",
        "transaction_type": "invoice",
        "categorized_transaction_id": "456",
        "transaction_date": "2026-04-01",
        "debit_or_credit": side,
        "debit_amount": "25" if side == "debit" else "0",
        "credit_amount": "25" if side == "credit" else "0",
        "currency_code": "AED",
    }


def test_zoho_system_generated_posting_identity_and_currency():
    item = transaction()
    account = {"account_id": "100", "account_name": "Cash"}
    row = zoho_ledger_row(item, account, START, END)
    assert row["journal_ref"] == "invoice:123" and row["manual"] == "false"
    # An absent exchange rate is 1 only for functional-currency rows.
    options = ImportOptions(**SCOPE, source_system="zoho")
    assert normalize(row, options, START, END, "AED", 2)[0]["base_debit"] == "25"
    item["currency_code"] = "USD"
    with pytest.raises(ImportProblem, match="exchange rate"):
        normalize(zoho_ledger_row(item, account, START, END), options, START, END, "AED", 2)
    item["account_id"] = "999"
    with pytest.raises(ConnectorError, match="account mismatch"):
        zoho_ledger_row(item, account, START, END)


async def test_report_endpoint_preflight_and_batch_lineage(tmp_path, monkeypatch):
    from app.api.v1 import connectors

    files = report_files(tmp_path)
    created = []

    async def check(*args):
        return SimpleNamespace(functional_currency="AED"), SimpleNamespace(
            start_date=START, end_date=END
        )

    async def upload(db, ctx, options, filename, stream, request_id):
        batch = SimpleNamespace(id=uuid.uuid4(), options=options.model_dump(mode="json"))
        created.append(batch)
        return batch

    monkeypatch.setattr(connectors, "check_scope", check)
    monkeypatch.setattr(connectors, "upload", upload)
    monkeypatch.setattr(
        connectors, "settings", lambda: SimpleNamespace(max_upload_bytes=64 * 1024 * 1024)
    )

    async def call():
        return await connectors.report_package(
            None,
            None,
            SimpleNamespace(state=SimpleNamespace(request_id="test")),
            json.dumps({**SCOPE, "source_system": "netsuite", "currency": "AED"}),
            **{
                kind: UploadFile(io.BytesIO(path.read_bytes()), filename=name)
                for kind, (path, name) in files.items()
            },
        )

    result = await call()
    assert len(created) == 3 and len(result["batch_ids"]) == 3
    assert all(b.options["report_package"]["package_id"] == result["package_id"] for b in created)
    files["gl"][0].write_text(files["gl"][0].read_text().replace("0,25,2", "0,24,2"))
    with pytest.raises(HTTPException) as exc:
        await call()
    assert exc.value.status_code == 422 and len(created) == 3


@pytest.mark.parametrize("failure", [False, True])
async def test_zoho_sync_extracts_full_postings_and_never_stages_partial_data(monkeypatch, failure):
    from app.modules.connectors import service

    connection = SimpleNamespace(
        **{k: uuid.UUID(v) for k, v in SCOPE.items()},
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        provider="zoho",
        organization_id="123",
        region="in",
        encrypted_credentials="encrypted",
    )
    created, stored = [], []

    async def scoped(db, ctx, model, identifier, *args):
        if model.__name__ == "Connection":
            return connection
        if model.__name__ == "LegalEntity":
            return SimpleNamespace(functional_currency="AED")
        return SimpleNamespace(start_date=START, end_date=END)

    async def put_private(db, ctx, stream):
        stored.append(stream.read())
        return {"object_key": str(len(stored)), "sha256": "test", "size": len(stored[-1])}

    async def upload(db, ctx, options, name, stream, request_id):
        created.append((options, list(csv.DictReader(io.StringIO(stream.read().decode())))))
        return SimpleNamespace(id=uuid.uuid4())

    def respond(request):
        resource = request.url.path.removeprefix("/books/v3/")
        if resource == "chartofaccounts":
            data = [
                {"account_id": "100", "account_name": "Cash"},
                {"account_id": "400", "account_name": "Sales"},
            ]
        elif resource == "chartofaccounts/accounttransactions":
            account = request.url.params["account_id"]
            if failure and account == "400":
                return httpx.Response(403)
            assert request.url.params["date_start"] == "2026-01-01"
            data = [transaction(account, "debit" if account == "100" else "credit")]
        else:
            data = []
        key = "transactions" if resource.endswith("accounttransactions") else resource
        return httpx.Response(
            200, json={"code": 0, key: data, "page_context": {"page": 1, "has_more_page": False}}
        )

    adapter = ZohoConnector(
        "in", "id", "secret", access_token="test", transport=httpx.MockTransport(respond)
    )

    class DB:
        def add(self, run):
            run.id = uuid.uuid4()

        async def flush(self):
            pass

    monkeypatch.setattr(service, "scoped", scoped)
    monkeypatch.setattr(service, "put_private", put_private)
    monkeypatch.setattr(service, "upload", upload)
    monkeypatch.setattr(
        service, "decrypt", lambda value: {"client_id": "id", "client_secret": "secret"}
    )
    monkeypatch.setattr(service, "encrypt", lambda value: "encrypted")
    monkeypatch.setattr(service, "ZohoConnector", lambda *args: adapter)
    result = await service.zoho_sync(DB(), None, connection.id)
    assert stored  # Native responses survive a later API failure.
    assert result["completeness"] == "insufficient_evidence"
    if failure:
        assert result["status"] == "failed" and not created
    else:
        assert [c[0].kind for c in created] == ["gl", "coa"]
        assert len(created[0][1]) == 2
        assert {r["manual"] for r in created[0][1]} == {"false"}
        assert result["result"]["accounts_with_completed_pagination"] == 2
        assert result["result"]["complete_general_ledger"] is False
