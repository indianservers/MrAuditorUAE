import csv
import io
import json
import uuid
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.modules.accounting.schemas import ImportOptions
from app.modules.connectors.native_adapters import NativeAdapter
from app.modules.connectors.native_config import configure
from app.modules.connectors.native_http import NativeHTTP, approved_base
from app.modules.connectors.zoho import ConnectorError
from app.modules.ingestion.parser import normalize

START, END = date(2026, 1, 1), date(2026, 12, 31)
GUID = "11111111-1111-1111-1111-111111111111"
SCOPE = {key: uuid.uuid4() for key in ("client_id", "entity_id", "period_id")}
VARIANTS = [
    (p, "")
    for p in ("quickbooks", "xero", "netsuite", "sap-b1", "sap-s4", "dynamics", "busy", "marg")
] + [
    ("quickbooks", "desktop-partner-api"),
    ("dynamics", "finance-partner-api"),
    ("sap-s4", "entry-view-odata"),
]


def configuration(provider, edition=""):
    company = (
        "1" if provider == "netsuite" else GUID if provider in {"xero", "dynamics"} else "1000"
    )
    return configure(
        provider,
        {
            "edition": edition,
            "company_id": company,
            "functional_currency": "AED",
            "base_url": "https://erp.example/api/",
            "accounts_path": "accounts" if provider == "sap-s4" else "chart",
            "company_path": "company",
            "ledger_path": "ledger" if provider == "sap-s4" else "entries",
            "directory_tenant": GUID,
            "account_id": "TEST_SB1",
            "subsidiary_id": "1" if provider == "netsuite" else "",
            "accounting_book": "1",
        },
    ).model_dump()


def responder(provider, config, calls, failure=None):
    partner = "partner-api" in config["edition"]

    def respond(request):
        calls.append(request)
        path = request.url.path
        if "/token" in path or path.endswith("/connect/token"):
            return httpx.Response(
                200, json={"access_token": "new-secret", "refresh_token": "rotated-secret"}
            )
        if failure == "forbidden" and (path.endswith("entries") or path.endswith("Journals")):
            return httpx.Response(403, json={"sensitive_error": "should-not-be-exposed"})
        if partner:
            if path.endswith("company"):
                return httpx.Response(
                    200, json={"company_id": config["company_id"], "currency": "AED"}
                )
            if path.endswith("chart"):
                items = [
                    {"account_code": "100", "account_name": "Cash", "source_id": "100"},
                    {"account_code": "400", "account_name": "Sales", "source_id": "400"},
                ]
            else:
                items = [
                    {
                        "account_code": code,
                        "journal_ref": "9",
                        "posting_date": "2026-04-01",
                        "debit": d,
                        "credit": c,
                        "currency": "AED",
                        "source_id": code,
                    }
                    for code, d, c in (("100", "25", "0"), ("400", "0", "25"))
                ]
            result = {"items": items, "next": None}
            if failure == "unbalanced" and path.endswith("entries"):
                items[-1]["credit"] = "24"
            if failure == "missing_termination":
                result.pop("next")
            return httpx.Response(200, json=result)
        if provider == "quickbooks":
            if "/companyinfo/" in path:
                return httpx.Response(
                    200, json={"CompanyInfo": {"Id": "1", "CompanyName": "FICTIONAL test company"}}
                )
            if path.endswith("query"):
                items = (
                    []
                    if "STARTPOSITION 3" in request.url.params["query"]
                    else [{"Id": "100", "Name": "Cash"}, {"Id": "400", "Name": "Sales"}]
                )
                return httpx.Response(200, json={"QueryResponse": {"Account": items}})
            if path.endswith("GeneralLedger"):
                keys = ["tx_date", "txn_type", "account_name", "debt_amt", "credit_amt"]
                data = {
                    "Header": {
                        "Currency": "AED",
                        "ReportBasis": "Accrual",
                        "StartPeriod": str(START),
                        "EndPeriod": str(END),
                    },
                    "Columns": {
                        "Column": [{"MetaData": [{"Name": "ColKey", "Value": k}]} for k in keys]
                    },
                    "Rows": {
                        "Row": [
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "2026-04-01"},
                                    {"value": "Invoice", "id": "9"},
                                    {"value": code, "id": code},
                                    {"value": d},
                                    {"value": c},
                                ],
                            }
                            for code, d, c in (("100", "25", "0"), ("400", "0", "25"))
                        ]
                    },
                }
                if failure == "wrong_period":
                    data["Header"]["StartPeriod"] = "2025-01-01"
                return httpx.Response(200, json=data)
            return httpx.Response(200, json={"Rows": {"Row": []}})
        if provider == "xero":
            if path == "/connections":
                return httpx.Response(200, json=[{"tenantId": config["company_id"]}])
            if path.endswith("Organisation"):
                return httpx.Response(
                    200,
                    json={
                        "Organisations": [
                            {"BaseCurrency": "AED", "OrganisationID": config["company_id"]}
                        ]
                    },
                )
            if path.endswith("Accounts"):
                return httpx.Response(
                    200,
                    json={
                        "Accounts": [{"AccountID": code, "Name": code} for code in ("100", "400")]
                    },
                )
            if path.endswith("Journals"):
                items = (
                    []
                    if request.url.params["offset"] == "1"
                    else [
                        {
                            "JournalID": "9",
                            "JournalNumber": 1,
                            "JournalDate": "/Date(1775001600000+0000)/",
                            "JournalLines": [
                                {"JournalLineID": code, "AccountID": code, "NetAmount": amount}
                                for code, amount in (("100", "25"), ("400", "-25"))
                            ],
                        }
                    ]
                )
                return httpx.Response(200, json={"Journals": items})
            return httpx.Response(200, json={"Reports": []})
        if provider == "sap-b1":
            if path.endswith("Login"):
                assert request.method == "POST"
                return httpx.Response(200, json={"SessionId": "session-secret"})
            assert "B1SESSION=session-secret" in request.headers.get("cookie", "")
            if path.endswith("CompanyService_GetAdminInfo"):
                return httpx.Response(200, json={"LocalCurrency": "AED"})
            if path.endswith("ChartOfAccounts"):
                return httpx.Response(
                    200, json={"value": [{"Code": code, "Name": code} for code in ("100", "400")]}
                )
            if path.endswith("JournalEntries"):
                return httpx.Response(200, json={"value": [{"JdtNum": 9}]})
            return httpx.Response(
                200,
                json={
                    "JdtNum": 9,
                    "ReferenceDate": "2026-04-01",
                    "JournalEntryLines": [
                        {"AccountCode": code, "Line_ID": i, "Debit": d, "Credit": c}
                        for i, (code, d, c) in enumerate((("100", "25", "0"), ("400", "0", "25")))
                    ],
                },
            )
        if provider == "sap-s4":
            if path.endswith("accounts"):
                return httpx.Response(
                    200,
                    json={
                        "d": {
                            "results": [
                                {"GLAccount": code, "GLAccountName": code}
                                for code in ("100", "400")
                            ]
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "d": {
                        "results": [
                            {
                                "CompanyCode": config["company_id"],
                                "CompanyCodeCurrency": "AED",
                                "Ledger": "0L",
                                "FiscalYear": "2026",
                                "AccountingDocument": "9",
                                "LedgerGLLineItem": code,
                                "AccountingDocumentItem": code,
                                "GLAccount": code,
                                "AmountInCompanyCodeCurrency": amount,
                                "PostingDate": "2026-04-01T00:00:00",
                            }
                            for code, amount in (("100", "25"), ("400", "-25"))
                        ]
                    }
                },
            )
        if provider == "dynamics":
            if path.endswith("companyInformation"):
                return httpx.Response(200, json={"value": [{"currencyCode": "AED"}]})
            if path.endswith("accounts"):
                return httpx.Response(
                    200,
                    json={
                        "value": [
                            {"number": code, "id": code, "displayName": code}
                            for code in ("100", "400")
                        ]
                    },
                )
            if path.endswith("generalLedgerEntries"):
                return httpx.Response(
                    200,
                    json={
                        "value": [
                            {
                                "id": code,
                                "documentNumber": "9",
                                "postingDate": "2026-04-01",
                                "accountNumber": code,
                                "debitAmount": d,
                                "creditAmount": c,
                            }
                            for code, d, c in (("100", "25", "0"), ("400", "0", "25"))
                        ]
                    },
                )
            return httpx.Response(200, json={"id": config["company_id"]})
        if provider == "netsuite":
            if "/subsidiary/" in path:
                return httpx.Response(200, json={"id": "1", "currency": {"id": "2"}})
            if "/currency/" in path:
                return httpx.Response(200, json={"symbol": "AED"})
            assert request.method == "POST" and request.headers["Prefer"] == "transient"
            query = json.loads(request.content)["q"]
            assert query.startswith("SELECT ")
            if "FROM account " in query:
                items = [{"id": code, "accountsearchdisplayname": code} for code in ("100", "400")]
            else:
                assert "tal.accountingbook=1" in query and "tl.subsidiary=1" in query
                items = [
                    {
                        "journal_ref": "9",
                        "posting_date": "2026-04-01",
                        "account_code": code,
                        "source_line": code,
                        "accounting_book": "1",
                        "subsidiary": "1",
                        "debit": d,
                        "credit": c,
                    }
                    for code, d, c in (("100", "25", None), ("400", None, "25"))
                ]
            return httpx.Response(
                200, json={"items": items, "hasMore": False, "count": len(items), "offset": 0}
            )
        raise AssertionError("Unexpected source request")

    return respond


@pytest.mark.parametrize("provider,edition", VARIANTS)
async def test_direct_vendor_requests_normalize_all_supported_interfaces(provider, edition):
    config = configuration(provider, edition)
    calls, evidence = [], []

    async def preserve(resource, raw):
        evidence.append((resource, raw))

    adapter = NativeAdapter(
        provider,
        config,
        {"access_token": "api-secret", "username": "reader", "password": "password-secret"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(responder(provider, config, calls)),
    )
    try:
        result = [item async for item in adapter.extract(START, END, "AED")]
    finally:
        await adapter.close()
    assert len([r for kind, r in result if kind == "gl"]) == 2
    assert len([r for kind, r in result if kind == "coa"]) == 2
    for kind, row in result:
        options = ImportOptions(**SCOPE, source_system=provider, kind=kind, currency="AED")
        normalize(row, options, START, END, "AED", 2)
    assert all(r.method == "GET" or r.url.path.endswith(("Login", "suiteql")) for r in calls)
    assert evidence and all(
        b"api-secret" not in raw and b"session-secret" not in raw for _, raw in evidence
    )
    if provider == "xero":
        assert [r.url.params["offset"] for r in calls if r.url.path.endswith("Journals")] == [
            "0",
            "1",
        ]


@pytest.mark.parametrize(
    "target",
    [
        "https://attacker.invalid/api/rows",
        "//attacker.invalid/api/rows",
        "../tokens",
        "%2e%2e/tokens",
        "https://erp.example/api2/data",
    ],
)
async def test_pagination_cannot_leak_credentials_outside_api_root(target):
    calls = []
    http = NativeHTTP(
        "https://erp.example/api/",
        {"Authorization": "Bearer never-leak"},
        httpx.MockTransport(lambda r: calls.append(r)),
    )
    try:
        with pytest.raises(ConnectorError):
            await http.request(target)
        assert not calls
    finally:
        await http.close()


def test_unapproved_custom_origin_and_invalid_editions_fail():
    with pytest.raises(ConnectorError, match="allowlist"):
        approved_base("https://attacker.invalid/api/", [])
    with pytest.raises(ConnectorError, match="Unsafe API"):
        approved_base("https://169.254.169.254/api/", ["https://169.254.169.254"])
    with pytest.raises(ConnectorError, match="edition"):
        configure("quickbooks", {"edition": "desktop"})
    with pytest.raises(ConnectorError, match="documented"):
        configure(
            "busy",
            {
                "base_url": "https://erp.example/api/",
                "company_id": "1",
                "functional_currency": "AED",
            },
            True,
        )


@pytest.mark.parametrize(
    "provider,failure",
    [("busy", "missing_termination"), ("quickbooks", "wrong_period"), ("xero", "forbidden")],
)
async def test_failed_native_extract_retains_prior_evidence(provider, failure):
    config = configuration(provider)
    evidence = []

    async def preserve(resource, raw):
        evidence.append(raw)

    adapter = NativeAdapter(
        provider,
        config,
        {"access_token": "secret"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(responder(provider, config, [], failure)),
    )
    try:
        with pytest.raises(ConnectorError):
            [r async for r in adapter.extract(START, END, "AED")]
        assert evidence
    finally:
        await adapter.close()


async def test_odata_cross_origin_next_link_is_rejected_before_request():
    calls = []

    async def preserve(resource, raw):
        pass

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"value": [{"id": "1"}], "@odata.nextLink": "https://attacker.invalid/api/steal"},
        )

    adapter = NativeAdapter(
        "busy",
        configuration("busy"),
        {"access_token": "secret"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(respond),
    )
    try:
        await adapter.start()
        with pytest.raises(ConnectorError, match="escaped"):
            [r async for r in adapter.odata("entries")]
        assert len(calls) == 1
    finally:
        await adapter.close()


@pytest.mark.parametrize(
    "provider,failure",
    [
        (p, None)
        for p in ("quickbooks", "xero", "netsuite", "sap-b1", "sap-s4", "dynamics", "busy", "marg")
    ]
    + [("xero", "forbidden"), ("busy", "unbalanced"), ("xero", "source_count")],
)
async def test_direct_sync_creates_batches_only_after_complete_balanced_extract(
    provider, failure, monkeypatch
):
    from app.modules.connectors import native_service as service

    config = configuration(provider)
    if failure == "source_count":
        config.update(control_reference="Independent source report", expected_gl_rows=3)
    connection = SimpleNamespace(
        **SCOPE,
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        provider=provider,
        config=config,
        encrypted_credentials="encrypted",
    )
    created, objects = [], []
    credentials = {"access_token": "secret", "username": "reader", "password": "secret"}

    async def scoped(*args):
        return connection

    async def check(*args):
        return SimpleNamespace(functional_currency="AED"), SimpleNamespace(
            start_date=START, end_date=END
        )

    async def put(db, ctx, stream):
        objects.append(stream.read())
        return {"object_key": str(len(objects)), "size": len(objects[-1])}

    async def upload(db, ctx, options, filename, stream, request_id):
        created.append((options, list(csv.DictReader(io.StringIO(stream.read().decode())))))
        return SimpleNamespace(id=uuid.uuid4())

    class DB:
        def add(self, obj):
            obj.id = uuid.uuid4()

        async def flush(self):
            pass

    monkeypatch.setattr(service, "scoped", scoped)
    monkeypatch.setattr(service, "check_scope", check)
    monkeypatch.setattr(
        service,
        "settings",
        lambda: SimpleNamespace(connector_allowed_origins=["https://erp.example"]),
    )
    monkeypatch.setattr(service, "decrypt", lambda value: credentials)
    monkeypatch.setattr(service, "encrypt", lambda value: "encrypted")
    monkeypatch.setattr(service, "record", lambda *args: None)
    monkeypatch.setattr(service, "put_private", put)
    monkeypatch.setattr(service, "upload", upload)
    monkeypatch.setattr(
        service,
        "NativeAdapter",
        lambda *args: NativeAdapter(
            *args, transport=httpx.MockTransport(responder(provider, config, [], failure))
        ),
    )
    # Preserve the class version used for lineage metadata as well as the factory.
    service.NativeAdapter.version = NativeAdapter.version
    result = await service.direct_sync(DB(), None, connection.id)
    assert objects and result["result"]["complete_general_ledger"] is False
    if failure:
        assert result["status"] == "failed" and not created
    else:
        assert result["status"] == "completed" and {options.kind for options, _ in created} == {
            "coa",
            "gl",
        }
        assert all(
            options.source_system == provider and options.source_sync_run_id
            for options, _ in created
        )
        assert all(len(rows) == 2 for _, rows in created)


async def test_native_oauth_state_is_scoped_consumed_and_realm_checked(monkeypatch):
    import hashlib
    from datetime import UTC, datetime, timedelta

    from fastapi import HTTPException

    from app.api.v1 import connectors as api
    from app.modules.connectors import native_auth

    config = configuration("quickbooks")
    connection = SimpleNamespace(
        provider="quickbooks",
        config=config,
        encrypted_credentials=json.dumps(
            {
                "client_id": "id",
                "client_secret": "secret",
                "oauth_state_hash": hashlib.sha256(b"x" * 32).hexdigest(),
                "oauth_expires": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
                "redirect_uri": "https://app.example/callback",
            }
        ),
    )
    calls = []

    async def scoped(*args):
        return connection

    async def exchange(*args):
        calls.append(args)
        return {**args[2], "access_token": "confidential-token", "refresh_token": "rotated"}

    monkeypatch.setattr(api, "scoped", scoped)
    monkeypatch.setattr(api, "encrypt", json.dumps)
    monkeypatch.setattr(api, "decrypt", json.loads)
    monkeypatch.setattr(native_auth, "token", exchange)
    for state, realm, code in (("y" * 32, "1000", 403), ("x" * 32, "9999", 422)):
        with pytest.raises(HTTPException) as exc:
            await api.direct_callback(
                uuid.uuid4(),
                api.DirectOAuthCallback(code="one-time", state=state, realm_id=realm),
                None,
                None,
            )
        assert exc.value.status_code == code and not calls
    data = api.DirectOAuthCallback(code="one-time", state="x" * 32, realm_id="1000")
    result = await api.direct_callback(uuid.uuid4(), data, None, None)
    assert result["status"] == "authorized" and "confidential-token" not in str(result)
    assert len(calls) == 1
    with pytest.raises(HTTPException) as exc:
        await api.direct_callback(uuid.uuid4(), data, None, None)
    assert exc.value.status_code == 403 and len(calls) == 1


@pytest.mark.parametrize("provider", ["quickbooks", "xero", "netsuite", "dynamics"])
async def test_native_refresh_retains_rotated_credentials(provider):
    config = configuration(provider)
    calls = []

    async def preserve(*args):
        pass

    adapter = NativeAdapter(
        provider,
        config,
        {"client_id": "id", "client_secret": "secret", "refresh_token": "old"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(responder(provider, config, calls)),
    )
    try:
        await adapter.start()
        assert adapter.credentials["refresh_token"] == "rotated-secret"
        assert adapter.http.client.headers["Authorization"] == "Bearer new-secret"
        assert len(calls) == 1
    finally:
        await adapter.close()


async def test_native_rate_limit_retry_and_secret_safe_failure(monkeypatch):
    from app.modules.connectors import native_http

    delays = []
    calls = []

    async def sleep(delay):
        delays.append(delay)

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "9999"})
        return httpx.Response(200, json={"Fault": {"Detail": "token-must-not-leak"}})

    monkeypatch.setattr(native_http.asyncio, "sleep", sleep)
    client = NativeHTTP("https://erp.example/api/", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(ConnectorError) as exc:
            await client.request("entries")
        assert delays == [30] and len(calls) == 2
        assert "token-must-not-leak" not in str(exc.value)
    finally:
        await client.close()


@pytest.mark.parametrize("provider", ["sap-b1", "dynamics"])
async def test_company_currency_probe_rejects_mismatched_base_currency(provider):
    config = configuration(provider)
    calls = []
    original = responder(provider, config, calls)

    def respond(request):
        if request.url.path.endswith("CompanyService_GetAdminInfo"):
            return httpx.Response(200, json={"LocalCurrency": "USD"})
        if request.url.path.endswith("companyInformation"):
            return httpx.Response(200, json={"value": [{"currencyCode": "USD"}]})
        return original(request)

    async def preserve(*args):
        pass

    adapter = NativeAdapter(
        provider,
        config,
        {"access_token": "secret", "username": "reader", "password": "secret"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(respond),
    )
    try:
        with pytest.raises(ConnectorError, match="currency"):
            [r async for r in adapter.extract(START, END, "AED")]
    finally:
        await adapter.close()


async def test_native_configuration_accepts_drafts_and_never_returns_secrets(monkeypatch):
    from app.api.v1 import connectors as api

    async def scope(*args):
        pass

    class DB:
        def add(self, obj):
            obj.id = uuid.uuid4()

        async def flush(self):
            pass

    monkeypatch.setattr(api, "check_scope", scope)
    monkeypatch.setattr(api, "encrypt", lambda value: "secret-ciphertext")
    ctx = SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
    draft = await api.create(
        api.ConnectionCreate(**SCOPE, provider="busy", name="BUSY test"), DB(), ctx
    )
    assert draft["status"] == "credentials_pending" and draft["config"]["edition"] == "partner-api"
    secured = await api.create(
        api.ConnectionCreate(
            **SCOPE,
            provider="xero",
            name="Xero test",
            credentials={"client_secret": "do-not-return"},
        ),
        DB(),
        ctx,
    )
    assert "do-not-return" not in str(secured) and "encrypted_credentials" not in secured


async def test_odata_cannot_switch_companies_on_same_origin():
    calls = []

    async def preserve(*args):
        pass

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "value": [{"id": "1"}],
                "@odata.nextLink": "https://erp.example/api/companies(other)/entries?$skip=1",
            },
        )

    adapter = NativeAdapter(
        "busy",
        configuration("busy"),
        {"access_token": "secret"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(respond),
    )
    try:
        await adapter.start()
        with pytest.raises(ConnectorError, match="scoped collection"):
            [r async for r in adapter.odata("companies(selected)/entries")]
        assert len(calls) == 1
    finally:
        await adapter.close()


async def test_partner_next_page_cannot_change_company_parameter():
    calls = []
    config = configuration("busy")
    original = responder("busy", config, calls)

    async def preserve(*args):
        pass

    def respond(request):
        response = original(request)
        if request.url.path.endswith("chart"):
            body = response.json()
            body["next"] = "https://erp.example/api/chart?company_id=another&cursor=2"
            return httpx.Response(200, json=body)
        return response

    adapter = NativeAdapter(
        "busy",
        config,
        {"access_token": "secret"},
        ["https://erp.example"],
        preserve,
        httpx.MockTransport(respond),
    )
    try:
        with pytest.raises(ConnectorError, match="company/period scope"):
            [r async for r in adapter.extract(START, END, "AED")]
        assert len(calls) == 2
    finally:
        await adapter.close()
