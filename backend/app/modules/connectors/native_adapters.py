"""Read-only vendor APIs, explicit edition boundaries, and preserved native responses."""

import hashlib
import json
import re
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.modules.connectors.native_auth import token
from app.modules.connectors.native_config import configure, partner_mode
from app.modules.connectors.native_http import AuthorizationError, NativeHTTP, approved_base
from app.modules.connectors.zoho import ConnectorError
from app.modules.ingestion.parser import money

Preserve = Callable[[str, bytes], Awaitable[None]]


def required(item: dict, key: str) -> str:
    value = item.get(key)
    if value is None or str(value).strip() == "":
        raise ConnectorError("Source is missing required field " + key)
    return str(value)


def source_date(value) -> str:
    text = str(value)
    match = re.fullmatch(r"/Date\((-?\d+)(?:[+-]\d{4})?\)/", text)
    if match:
        return datetime.fromtimestamp(int(match[1]) / 1000, UTC).date().isoformat()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        raise ConnectorError("Source posting date is invalid") from None


def gl_row(code, ref, posting, identity, currency, debit=None, credit=None, amount=None, **extra):
    if amount is not None:
        signed = money(str(amount))
        debit, credit = max(signed, Decimal(0)), max(-signed, Decimal(0))
    if debit is None or credit is None:
        raise ConnectorError("Source debit and credit amounts are required")
    return {
        "account_code": str(code),
        "account_name": str(extra.pop("account_name", code)),
        "journal_ref": str(ref),
        "posting_date": source_date(posting),
        "source_id": str(identity),
        "debit": str(debit),
        "credit": str(credit),
        "currency": currency,
        "exchange_rate": "1",
        **{k: str(v) if v is not None else "" for k, v in extra.items()},
    }


def field(item: dict, path: str):
    value = item
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ConnectorError("Documented API response field is missing: " + path)
        value = value[part]
    return value


class NativeAdapter:
    version = "direct-accounting/1.0.0"

    def __init__(
        self,
        provider: str,
        config: dict,
        credentials: dict,
        allowed_origins: list[str],
        preserve: Preserve,
        transport=None,
    ):
        self.provider = provider
        self.config = configure(provider, config, complete=True)
        self.credentials = dict(credentials)
        self.preserve = preserve
        self.transport = transport
        self.allowed_origins = allowed_origins
        self.http: NativeHTTP | None = None
        self.scope_evidence: dict = {}
        self.read_cache: Any = None
        self.refresh_handler: Any = None
        self.governor: Any = None
        self.document_controls: list[dict] = []

    async def start(self):
        c = self.config
        fixed = False
        if partner_mode(c) or self.provider in {"sap-b1", "sap-s4"} or c.edition == "finance-odata":
            base = c.base_url
        elif self.provider == "quickbooks":
            host = (
                "sandbox-quickbooks.api.intuit.com"
                if c.environment == "sandbox"
                else "quickbooks.api.intuit.com"
            )
            base, fixed = f"https://{host}/v3/company/{c.company_id}/", True
        elif self.provider == "xero":
            base, fixed = "https://api.xero.com/api.xro/2.0/", True
        elif self.provider == "netsuite":
            account = c.account_id.lower().replace("_", "-")
            base, fixed = f"https://{account}.suitetalk.api.netsuite.com/services/rest/", True
        elif self.provider == "dynamics":
            base = f"https://api.businesscentral.dynamics.com/v2.0/{quote(c.directory_tenant, safe='')}/{c.bc_environment}/api/v2.0/"
            fixed = True
        else:
            raise ConnectorError("Unsupported direct provider")
        self.http = NativeHTTP(
            approved_base(base, self.allowed_origins, fixed), transport=self.transport
        )
        self.http.governor = self.governor
        if self.provider == "sap-b1":
            await self.login_b1()
        elif self.provider == "sap-s4" or partner_mode(c):
            if self.credentials.get("access_token"):
                self.http.client.headers["Authorization"] = (
                    "Bearer " + self.credentials["access_token"]
                )
            elif self.credentials.get("api_key") and partner_mode(c):
                self.http.client.headers[c.api_key_header] = self.credentials["api_key"]
            elif self.credentials.get("username") and self.credentials.get("password"):
                self.http.client.auth = httpx.BasicAuth(
                    self.credentials["username"], self.credentials["password"]
                )
            else:
                raise ConnectorError("API credentials are required")
        else:
            if self.credentials.get("refresh_token") or (
                self.provider == "dynamics" and self.credentials.get("client_secret")
            ):
                await self.refresh()
            elif self.credentials.get("access_token"):
                self.http.client.headers["Authorization"] = (
                    "Bearer " + self.credentials["access_token"]
                )
            else:
                raise ConnectorError(
                    "OAuth authorization or a secure access credential is required"
                )
            if self.provider == "xero":
                self.http.client.headers["Xero-Tenant-Id"] = c.company_id

    async def login_b1(self):
        assert self.http is not None
        if not all(self.credentials.get(key) for key in ("username", "password")):
            raise ConnectorError("SAP Service Layer username and password are required")
        data, _ = await self.http.request(
            "Login",
            "POST",
            json={
                "CompanyDB": self.config.company_id,
                "UserName": self.credentials["username"],
                "Password": self.credentials["password"],
            },
        )
        if not data.get("SessionId"):
            raise ConnectorError("SAP Service Layer did not establish a session")
        # Some gateways omit Set-Cookie; the returned session is still confidential.
        self.http.client.cookies.set(
            "B1SESSION",
            str(data["SessionId"]),
            domain=urlsplit(self.http.base).hostname or "",
            path="/",
        )
        self.scope_evidence = {
            "company_id": self.config.company_id,
            "verification": "service_layer_login",
        }

    async def refresh(self, force=False):
        assert self.http is not None
        if self.refresh_handler:
            self.credentials = await self.refresh_handler(self.credentials, force)
        else:
            self.credentials = await token(self.provider, self.config, self.credentials, transport=self.transport)
        self.http.client.headers["Authorization"] = "Bearer " + self.credentials["access_token"]

    async def read(self, path: str, resource: str, method="GET", **kwargs) -> dict:
        assert self.http is not None
        async def fetch():
            assert self.http is not None
            try:
                return await self.http.request(path, method, **kwargs)
            except AuthorizationError:
                if self.provider == "sap-b1":
                    await self.login_b1()
                elif self.credentials.get("refresh_token") or (self.provider == "dynamics" and not partner_mode(self.config)):
                    await self.refresh(force=True)
                else:
                    raise
                return await self.http.request(path, method, **kwargs)
        identity_resources = {"CompanyInfo", "company", "Organisation", "subsidiary", "currency", "companyInformation", "CompanyService_GetAdminInfo"}
        if self.read_cache and resource not in identity_resources:
            from app.modules.connectors.runtime import digest

            data, raw = await self.read_cache(digest([self.http.url(path), method, kwargs]), fetch)
        else:
            data, raw = await fetch()
        await self.preserve(resource, raw)
        return data

    async def odata(self, path: str, params: dict | None = None) -> AsyncIterator[dict]:
        assert self.http is not None
        collection_path = urlsplit(self.http.url(path)).path
        seen = set()
        observed = 0
        expected = None
        for _ in range(self.config.max_pages):
            assert self.http is not None
            target = self.http.url(path)
            marker = (target, json.dumps(params, sort_keys=True))
            if marker in seen:
                raise ConnectorError("Repeated OData continuation")
            seen.add(marker)
            data = await self.read(path, path.split("?")[0], params=params)
            container = data.get("d", data)
            if not isinstance(container, dict):
                raise ConnectorError("Invalid OData collection")
            items = container.get("results", container.get("value"))
            if not isinstance(items, list):
                raise ConnectorError("Missing OData collection")
            total = container.get("__count", data.get("@odata.count"))
            if total is not None:
                if expected is not None and int(total) != expected:
                    raise ConnectorError("OData source count changed during extraction")
                expected = int(total)
            observed += len(items)
            for item in items:
                if not isinstance(item, dict):
                    raise ConnectorError("Invalid OData item")
                yield item
            next_url = (
                container.get("__next") or data.get("@odata.nextLink") or data.get("odata.nextLink")
            )
            if not next_url:
                if expected is not None and observed != expected:
                    raise ConnectorError("OData source count does not match received rows")
                return
            if not isinstance(next_url, str) or not items:
                raise ConnectorError("Invalid OData continuation")
            # Validate BEFORE the next request; no credentials leave this API root.
            if next_url.startswith("?"):
                next_url = target.split("?", 1)[0] + next_url
            resolved = self.http.url(next_url)
            if urlsplit(resolved).path != collection_path:
                raise ConnectorError("OData continuation changed the scoped collection")
            path, params = next_url, None
        raise ConnectorError("OData pagination safety limit reached")

    async def extract(
        self, start: date, end: date, currency: str
    ) -> AsyncIterator[tuple[str, dict]]:
        if self.config.functional_currency != currency:
            raise ConnectorError("Configured API functional currency differs from the legal entity")
        await self.start()
        name = "partner" if partner_mode(self.config) else self.provider.replace("-", "_")
        async for item in getattr(self, "extract_" + name)(start, end, currency):
            yield item

    async def extract_sap_b1(self, start, end, currency):
        admin = await self.read("CompanyService_GetAdminInfo", "CompanyService_GetAdminInfo")
        admin = admin.get("AdminInfo", admin)
        source_currency = str(admin.get("LocalCurrency", ""))
        mapped_currency = self.config.currency_aliases.get(source_currency, source_currency)
        if mapped_currency != currency:
            raise ConnectorError(
                "SAP local currency differs from the entity ISO currency; qualify currency aliases explicitly"
            )
        self.scope_evidence["currency"] = currency
        self.scope_evidence["source_currency_code"] = source_currency
        async for account in self.odata("ChartOfAccounts", {"$orderby": "Code"}):
            yield (
                "coa",
                {
                    "account_code": required(account, "Code"),
                    "account_name": required(account, "Name"),
                    "source_id": required(account, "Code"),
                    "source_group": str(account.get("GroupMask", "")),
                },
            )
        async for header in self.odata(
            "JournalEntries",
            {
                "$filter": f"ReferenceDate ge '{start}' and ReferenceDate le '{end}'",
                "$orderby": "JdtNum",
            },
        ):
            ref = required(header, "JdtNum")
            # Fetch the full object: never assume collection responses expand all lines.
            if not ref.isdigit():
                raise ConnectorError("Invalid SAP journal identifier")
            detail = await self.read(f"JournalEntries({ref})", "JournalEntries/detail")
            if str(detail.get("JdtNum")) != ref or not isinstance(
                detail.get("JournalEntryLines"), list
            ):
                raise ConnectorError("SAP journal detail identity or lines are missing")
            for line in detail["JournalEntryLines"]:
                row = gl_row(
                        required(line, "AccountCode"),
                        ref,
                        required(detail, "ReferenceDate"),
                        ref + ":" + required(line, "Line_ID"),
                        currency,
                        required(line, "Debit"),
                        required(line, "Credit"),
                        description=line.get("LineMemo", detail.get("Memo", "")),
                        counterparty=line.get("ShortName", ""),
                        cost_center=line.get("CostingCode", ""),
                    )
                from app.modules.connectors.enrichment import foreign_provenance

                if line.get("FCCurrency"):
                    row = foreign_provenance(row, line["FCCurrency"], line.get("FCDebit"), line.get("FCCredit"), line.get("Rate"))
                row["branch"] = str(line.get("BPLID", ""))
                row["dimensions"] = json.dumps({key: line[key] for key in (
                    "CostingCode", "CostingCode2", "CostingCode3", "CostingCode4", "CostingCode5", "ProjectCode"
                ) if line.get(key)}, sort_keys=True)
                yield "gl", row

    async def extract_sap_s4(self, start, end, currency):
        c = self.config
        # The service root/entity must match the deployed SAP release's metadata.
        path = c.ledger_path or (
            "A_OperationalAcctgDocItemCube"
            if c.edition == "entry-view-odata"
            else "A_GLAccountLineItem"
        )
        if c.metadata_preflight:
            assert self.http is not None
            from app.modules.connectors.enrichment import odata_metadata

            raw, _ = await self.http.binary("$metadata", {"application/xml", "text/xml"}, 8 * 1024 * 1024)
            await self.preserve("service_metadata", raw)
            self.scope_evidence["metadata"] = odata_metadata(raw, path.rsplit("/", 1)[-1], {
                "CompanyCode", "CompanyCodeCurrency", "GLAccount", "PostingDate", "AmountInCompanyCodeCurrency",
                "AccountingDocument", "FiscalYear", *( {"Ledger"} if c.edition == "ledger-odata" else set()),
            })
        company = c.company_id.replace("'", "''")
        filters = f"CompanyCode eq '{company}' and PostingDate ge datetime'{start}T00:00:00' and PostingDate le datetime'{end}T23:59:59'"
        if c.edition == "ledger-odata":
            filters += f" and Ledger eq '{c.ledger}'"
        if c.accounts_path:
            async for account in self.odata(c.accounts_path):
                yield (
                    "coa",
                    {
                        "account_code": required(account, "GLAccount"),
                        "account_name": account.get("GLAccountName")
                        or required(account, "GLAccount"),
                        "source_id": required(account, "GLAccount"),
                    },
                )
        async for line in self.odata(
            path, {"$filter": filters, "$orderby": "CompanyCode,FiscalYear,AccountingDocument"}
        ):
            if (
                required(line, "CompanyCode") != c.company_id
                or required(line, "CompanyCodeCurrency") != currency
            ):
                raise ConnectorError("SAP company/currency mismatch")
            if c.edition == "ledger-odata" and required(line, "Ledger") != c.ledger:
                raise ConnectorError("SAP ledger mismatch")
            ref = ":".join(
                required(line, key) for key in ("CompanyCode", "FiscalYear", "AccountingDocument")
            )
            identity = (
                required(line, "ID")
                if line.get("ID")
                else ref
                + ":"
                + required(
                    line,
                    "LedgerGLLineItem" if c.edition == "ledger-odata" else "AccountingDocumentItem",
                )
            )
            yield (
                "gl",
                gl_row(
                    required(line, "GLAccount"),
                    ref,
                    required(line, "PostingDate"),
                    identity,
                    currency,
                    amount=required(line, "AmountInCompanyCodeCurrency"),
                    account_name=line.get("GLAccountName") or line["GLAccount"],
                    description=line.get("DocumentItemText", ""),
                    cost_center=line.get("CostCenter", ""),
                    counterparty=line.get("Customer") or line.get("Supplier", ""),
                    tax_code=line.get("TaxCode", ""),
                ),
            )
        self.scope_evidence = {
            **self.scope_evidence,
            "company_id": c.company_id,
            "ledger": c.ledger,
            "coverage": "entry_view_only" if c.edition == "entry-view-odata" else "ledger_view",
        }

    async def extract_xero(self, start, end, currency):
        org = await self.read("Organisation", "Organisation")
        organizations = org.get("Organisations", [])
        if (
            len(organizations) != 1
            or organizations[0].get("BaseCurrency") != currency
            or organizations[0].get("OrganisationID") != self.config.company_id
        ):
            raise ConnectorError("Xero organization currency cannot be verified")
        # The tenant header scopes all requests; verify the tenant in OAuth connections.
        connections = NativeHTTP(
            "https://api.xero.com/",
            {"Authorization": "Bearer " + self.credentials["access_token"]},
            self.transport,
        )
        connections.governor = self.governor
        try:
            # /connections returns an array, unlike accounting resources.
            data, raw = await connections.request("connections", array=True)
            if not isinstance(data, list) or self.config.company_id not in {
                r.get("tenantId") for r in data
            }:
                raise ConnectorError("Xero tenant is not authorized")
            await self.preserve("connections", raw)
        finally:
            await connections.close()
        try:
            first_journals = await self.read("Journals", "Journals", params={"offset": 0, "paymentsOnly": "false"})
        except AuthorizationError:
            raise ConnectorError("Xero Journals access denied; verify accounting.journals.read consent and the app's Journals entitlement before syncing") from None
        if not isinstance(first_journals.get("Journals"), list):
            raise ConnectorError("Xero Journals entitlement/response contract cannot be verified")
        accounts = await self.read("Accounts", "Accounts")
        if not isinstance(accounts.get("Accounts"), list):
            raise ConnectorError("Xero chart of accounts is missing")
        for account in accounts["Accounts"]:
            yield (
                "coa",
                {
                    "account_code": required(account, "AccountID"),
                    "account_name": required(account, "Name"),
                    "source_id": required(account, "AccountID"),
                    "source_group": account.get("Type", ""),
                },
            )
        offset = 0
        for _ in range(self.config.max_pages):
            data = first_journals if offset == 0 else await self.read(
                "Journals", "Journals", params={"offset": offset, "paymentsOnly": "false"}
            )
            journals = data.get("Journals")
            if not isinstance(journals, list):
                raise ConnectorError(
                    "Xero journals collection missing (check Advanced-tier entitlement)"
                )
            if not journals:
                break
            numbers = [int(required(journal, "JournalNumber")) for journal in journals]
            if min(numbers) <= offset or len(set(numbers)) != len(numbers):
                raise ConnectorError("Repeated Xero journal offset")
            offset = max(numbers)
            for journal in journals:
                posting = source_date(required(journal, "JournalDate"))
                if not str(start) <= posting <= str(end):
                    continue
                if not isinstance(journal.get("JournalLines"), list) or not journal["JournalLines"]:
                    raise ConnectorError("Xero journal lines are missing")
                for line in journal["JournalLines"]:
                    yield (
                        "gl",
                        gl_row(
                            required(line, "AccountID"),
                            required(journal, "JournalID"),
                            posting,
                            required(line, "JournalLineID"),
                            currency,
                            amount=required(line, "NetAmount"),
                            account_name=line.get("AccountName") or line["AccountID"],
                            description=line.get("Description", ""),
                            tax_code=line.get("TaxType", ""),
                        ),
                    )
        else:
            raise ConnectorError("Xero journal pagination safety limit reached")
        # Preserve native TB reports; their YTD columns are not period movement amounts.
        await self.read(
            "Reports/TrialBalance",
            "Reports/TrialBalance",
            params={"date": str(end), "paymentsOnly": "false"},
        )
        self.scope_evidence = {
            "company_id": self.config.company_id,
            "currency": currency,
            "coverage": "accrual_journals",
            "journals_preflight": "authorized_source_response; not inferred subscription tier",
        }

    async def extract_dynamics(self, start, end, currency):
        if self.config.edition == "finance-odata":
            async for row in self.extract_finance(start, end, currency):
                yield row
            return
        company = self.config.company_id
        root = f"companies({company})/"
        identity = await self.read(f"companies({company})", "company")
        if str(identity.get("id", "")).lower() != company.lower():
            raise ConnectorError("Business Central company mismatch")
        info = await self.read(root + "companyInformation", "companyInformation")
        information = info.get("value", [info])
        if (
            not isinstance(information, list)
            or len(information) != 1
            or information[0].get("currencyCode") != currency
        ):
            raise ConnectorError("Business Central company base currency cannot be verified")
        async for account in self.odata(root + "accounts", {"$orderby": "number"}):
            yield (
                "coa",
                {
                    "account_code": required(account, "number"),
                    "account_name": required(account, "displayName"),
                    "source_id": required(account, "id"),
                    "source_group": account.get("category", ""),
                },
            )
        async for line in self.odata(
            root + "generalLedgerEntries",
            {
                "$filter": f"postingDate ge {start} and postingDate le {end}",
                "$orderby": "entryNumber",
            },
        ):
            # Standard BC omits Transaction No. Document/date grouping is explicitly disclosed.
            ref = (
                required(line, "documentNumber") + ":" + source_date(required(line, "postingDate"))
            )
            yield (
                "gl",
                gl_row(
                    required(line, "accountNumber"),
                    ref,
                    line["postingDate"],
                    required(line, "id"),
                    currency,
                    required(line, "debitAmount"),
                    required(line, "creditAmount"),
                    description=line.get("description", ""),
                ),
            )
        self.scope_evidence = {
            "company_id": company,
            "currency_verification": "companyInformation",
            "journal_grouping": "document_number_and_date; standard API omits transaction number",
        }

    async def extract_finance(self, start, end, currency):
        from app.modules.connectors.enrichment import odata_metadata

        c = self.config
        assert self.http is not None
        raw, _ = await self.http.binary("$metadata", {"application/xml", "text/xml"}, 8 * 1024 * 1024)
        await self.preserve("finance_metadata", raw)
        checks = {}
        for kind, path in (("coa", c.accounts_path), ("gl", c.ledger_path)):
            fields = {value.split(".")[0] for value in c.mappings[kind].values()}
            if kind == "gl":
                fields.update([c.posting_date_field, c.finance_company_field])
            checks[kind] = odata_metadata(raw, path, fields)
        company_rows = [row async for row in self.odata(c.company_path)]
        company = next((row for row in company_rows if str(field(row, c.company_id_field)) == c.company_id), None)
        if not company or field(company, c.currency_field) != currency:
            raise ConnectorError("Dynamics Finance company/base currency cannot be verified")
        for kind, path in (("coa", c.accounts_path), ("gl", c.ledger_path)):
            filters = None
            if kind == "gl":
                company_id = c.company_id.replace("'", "''")
                filters = {"$filter": f"{c.finance_company_field} eq '{company_id}' and {c.posting_date_field} ge {start} and {c.posting_date_field} le {end}"}
            async for source in self.odata(path, filters):
                if kind == "gl" and str(field(source, c.finance_company_field)) != c.company_id:
                    raise ConnectorError("Dynamics Finance legal-entity mismatch")
                row = {key: str(field(source, value)) for key, value in c.mappings[kind].items()}
                row.setdefault("currency", currency)
                if kind == "gl" and not row.get("source_id"):
                    raise ConnectorError("Dynamics Finance requires a native posting identity")
                yield kind, row
        self.scope_evidence = {"company_id": c.company_id, "currency": currency, "edition": "finance-odata", "metadata": checks}

    async def suiteql(self, query: str) -> AsyncIterator[dict]:
        offset = 0
        for _ in range(self.config.max_pages):
            data = await self.read(
                "query/v1/suiteql",
                "SuiteQL",
                "POST",
                params={"limit": 1000, "offset": offset},
                headers={"Prefer": "transient"},
                json={"q": query},
            )
            items = data.get("items")
            if (
                not isinstance(items, list)
                or not isinstance(data.get("hasMore"), bool)
                or int(data.get("offset", -1)) != offset
                or int(data.get("count", -1)) != len(items)
            ):
                raise ConnectorError("NetSuite query pagination cannot be verified")
            for item in items:
                yield item
            if not data["hasMore"]:
                return
            if not items or offset + len(items) >= 100000:
                raise ConnectorError(
                    "NetSuite REST query limit reached; narrow the accounting period"
                )
            offset += len(items)
        raise ConnectorError("NetSuite pagination safety limit reached")

    async def extract_netsuite(self, start, end, currency):
        c = self.config
        discovery = {}
        if c.discover_scope:
            subsidiaries = [r async for r in self.suiteql("SELECT id, name, currency FROM subsidiary ORDER BY id")]
            books = [r async for r in self.suiteql("SELECT id, name FROM accountingbook ORDER BY id")]
            if c.subsidiary_id not in {str(r.get("id")) for r in subsidiaries} or c.accounting_book not in {str(r.get("id")) for r in books}:
                raise ConnectorError("Selected NetSuite subsidiary/book is not visible in the source discovery population")
            discovery = {"subsidiaries": subsidiaries, "accounting_books": books, "consolidation": "separate_company_currency_extracts_required"}
        metadata = await self.read("record/v1/subsidiary/" + c.subsidiary_id, "subsidiary")
        if str(metadata.get("id")) != c.subsidiary_id:
            raise ConnectorError("NetSuite subsidiary mismatch")
        currency_id = str(metadata.get("currency", {}).get("id", ""))
        if not currency_id.isdigit():
            raise ConnectorError("NetSuite subsidiary base currency is unavailable")
        currency_data = await self.read("record/v1/currency/" + currency_id, "currency")
        if currency_data.get("symbol") != currency:
            raise ConnectorError("NetSuite subsidiary currency mismatch")
        async for account in self.suiteql(
            "SELECT id, acctnumber, accountsearchdisplayname FROM account ORDER BY id"
        ):
            yield (
                "coa",
                {
                    "account_code": required(account, "id"),
                    "account_name": required(account, "accountsearchdisplayname"),
                    "source_id": required(account, "id"),
                },
            )
        query = (
            "SELECT t.id AS journal_ref, TO_CHAR(t.trandate,'YYYY-MM-DD') AS posting_date, "
            "tal.account AS account_code, tal.transactionline AS source_line, tal.accountingbook AS accounting_book, "
            "tal.debit AS debit, tal.credit AS credit, tl.memo AS description, tl.subsidiary AS subsidiary "
            "FROM transactionaccountingline tal JOIN transaction t ON t.id=tal.transaction "
            "JOIN transactionline tl ON tl.transaction=tal.transaction AND tl.id=tal.transactionline "
            f"WHERE tal.posting='T' AND tal.accountingbook={c.accounting_book} AND tl.subsidiary={c.subsidiary_id} "
            f"AND t.trandate BETWEEN TO_DATE('{start}','YYYY-MM-DD') AND TO_DATE('{end}','YYYY-MM-DD') "
            "ORDER BY t.id,tal.transactionline,tal.account,tal.accountingbook"
        )
        async for line in self.suiteql(query):
            if (
                str(line.get("subsidiary")) != c.subsidiary_id
                or str(line.get("accounting_book")) != c.accounting_book
            ):
                raise ConnectorError("NetSuite accounting book/subsidiary mismatch")
            identity = ":".join(
                required(line, k)
                for k in ("journal_ref", "source_line", "account_code", "accounting_book")
            )
            yield (
                "gl",
                gl_row(
                    required(line, "account_code"),
                    required(line, "journal_ref"),
                    required(line, "posting_date"),
                    identity,
                    currency,
                    line.get("debit") or "0",
                    line.get("credit") or "0",
                    description=line.get("description", ""),
                ),
            )
        self.scope_evidence = {
            "company_id": c.subsidiary_id,
            "accounting_book": c.accounting_book,
            "currency": currency,
            "coverage": "posting_accounting_lines",
            "scope_discovery": discovery,
        }

    async def extract_quickbooks(self, start, end, currency):
        company = await self.read("companyinfo/" + self.config.company_id, "CompanyInfo")
        company_info = company.get("CompanyInfo")
        # CompanyInfo.Id is the entity ID (commonly "1"), NOT the OAuth realm ID.
        # Realm binding comes from callback verification and the pinned API URL.
        if (
            not isinstance(company_info, dict)
            or not company_info.get("Id")
            or not company_info.get("CompanyName")
        ):
            raise ConnectorError("QuickBooks company identity response is missing")
        if self.config.cdc_since:
            from app.modules.connectors.webhooks import cdc_parameters

            since = datetime.fromisoformat(self.config.cdc_since.replace("Z", "+00:00"))
            await self.read("cdc", "CDC/repair_hints", params=cdc_parameters(since, self.config.cdc_entities))
        position = 1
        for _ in range(self.config.max_pages):
            data = await self.read(
                "query",
                "Account/query",
                params={
                    "query": f"select * from Account where Active IN (true,false) STARTPOSITION {position} MAXRESULTS 1000",
                },
            )
            query = data.get("QueryResponse")
            if not isinstance(query, dict) or not isinstance(query.get("Account", []), list):
                raise ConnectorError("QuickBooks account query is incomplete")
            accounts = query.get("Account", [])
            if not accounts:
                break
            for account in accounts:
                yield (
                    "coa",
                    {
                        "account_code": required(account, "Id"),
                        "account_name": required(account, "Name"),
                        "source_id": required(account, "Id"),
                        "source_group": account.get("AccountType", ""),
                    },
                )
            position += len(accounts)
        else:
            raise ConnectorError("QuickBooks account pagination safety limit reached")
        report = await self.read(
            "reports/GeneralLedger",
            "GeneralLedger",
            params={
                "start_date": str(start),
                "end_date": str(end),
                "accounting_method": "Accrual",
                "columns": "tx_date,txn_type,doc_num,account_name,debt_amt,credit_amt,memo,name",
            },
        )
        header = report.get("Header", {})
        if header.get("Currency") != currency or header.get("ReportBasis") != "Accrual":
            raise ConnectorError("QuickBooks report currency/basis cannot be verified")
        if header.get("StartPeriod") != str(start) or header.get("EndPeriod") != str(end):
            raise ConnectorError("QuickBooks report ignored the selected period")
        contract = quickbooks_report_contract(report)
        documents = {}
        for row in quickbooks_report_rows(report, currency):
            if self.config.include_documents or self.config.tax_details or self.config.include_attachments:
                from app.modules.connectors.enrichment import (
                    match_qbo_posting,
                    qbo_document_type,
                    tax_evidence,
                )

                kind = qbo_document_type(row["source_transaction_type"])
                identity = row["source_transaction_id"]
                if kind and identity.isdigit():
                    key = (kind, identity)
                    if key not in documents:
                        detail = await self.read(kind + "/" + identity, "document/" + kind)
                        document = next((v for k, v in detail.items() if k.lower() == kind), None)
                        if not isinstance(document, dict) or str(document.get("Id")) != identity:
                            raise ConnectorError("QuickBooks source document identity mismatch")
                        documents[key] = document
                        control = {"entity": kind, "id": identity, "tax": tax_evidence(document, "quickbooks")}
                        if self.config.include_attachments:
                            attached = await self.read("query", "Attachable/query", params={"query":
                                "select * from Attachable where AttachableRef.EntityRef.value = '" + identity + "'"})
                            attachments = attached.get("QueryResponse", {}).get("Attachable", [])
                            if not isinstance(attachments, list):
                                raise ConnectorError("QuickBooks attachment metadata is invalid")
                            control["attachments"] = [{"id": str(a.get("Id", "")), "content_type": a.get("ContentType"),
                                "size": a.get("Size"), "status": "metadata_preserved_binary_not_downloaded"} for a in attachments]
                        self.document_controls.append(control)
                    document = documents[key]
                    row = match_qbo_posting(row, document)
                    row["original_currency"] = document.get("CurrencyRef", {}).get("value", "")
                    row["source_exchange_rate"] = str(document.get("ExchangeRate", ""))
                    row["source_fx_status"] = "document_rate_preserved; posting_conversion_not_inferred"
            yield "gl", row
        await self.read(
            "reports/TrialBalance",
            "TrialBalance",
            params={"end_date": str(end), "accounting_method": "Accrual"},
        )
        self.scope_evidence = {
            "company_id": self.config.company_id,
            "company_name": company_info["CompanyName"],
            "verification": "oauth_realm_and_realm_scoped_companyinfo",
            "currency": currency,
            "source_ids": "native_line_when_uniquely_matched; otherwise report_snapshot_identity",
            "report_contract": contract,
            "document_controls": self.document_controls,
        }

    async def extract_partner(self, start, end, currency):
        c = self.config
        company = await self.read(
            c.company_path, "partner/company", params={c.company_parameter: c.company_id}
        )
        if (
            str(field(company, c.company_id_field)) != c.company_id
            or field(company, c.currency_field) != currency
        ):
            raise ConnectorError("Partner API company/currency mismatch")
        for kind, resource in (("coa", c.accounts_path), ("gl", c.ledger_path), ("tb", c.tb_path)):
            if not resource:
                continue
            path = resource
            params: dict | None = {
                c.company_parameter: c.company_id,
                c.start_parameter: str(start),
                c.end_parameter: str(end),
            }
            scope_params = {
                c.company_parameter: c.company_id,
                c.start_parameter: str(start),
                c.end_parameter: str(end),
            }
            assert self.http is not None
            resource_path = urlsplit(self.http.url(resource)).path
            seen = set()
            for _ in range(c.max_pages):
                if path in seen:
                    raise ConnectorError("Repeated partner API continuation")
                seen.add(path)
                data = await self.read(path, "partner/" + kind, params=params)
                items = field(data, c.rows_key)
                continuation = field(data, c.next_key)  # Missing termination evidence fails.
                if not isinstance(items, list):
                    raise ConnectorError("Partner API rows are missing")
                for item in items:
                    if not isinstance(item, dict):
                        raise ConnectorError("Invalid partner API row")
                    mapping = c.mappings.get(kind)
                    row = (
                        {key: str(field(item, value)) for key, value in mapping.items()}
                        if mapping
                        else {key: str(value) for key, value in item.items() if value is not None}
                    )
                    if kind == "gl" and not row.get("source_id"):
                        raise ConnectorError("Partner API requires native posting identifiers")
                    yield kind, row
                if continuation is None or continuation == "":
                    break
                if not isinstance(continuation, str) or not items:
                    raise ConnectorError("Invalid partner API continuation")
                if continuation.startswith("?"):
                    continuation = self.http.url(path).split("?", 1)[0] + continuation
                resolved = self.http.url(continuation)
                if urlsplit(resolved).path != resource_path:
                    raise ConnectorError("Partner continuation changed the scoped resource")
                next_url = httpx.URL(resolved)
                for key, value in scope_params.items():
                    if key in next_url.params and next_url.params[key] != value:
                        raise ConnectorError("Partner continuation changed company/period scope")
                path, params = str(next_url.copy_merge_params(scope_params)), None
            else:
                raise ConnectorError("Partner API pagination safety limit reached")
        self.scope_evidence = {
            "company_id": c.company_id,
            "currency": currency,
            "coverage": "configured_partner_contract",
            "vendor_contract_qualification": "pending",
        }

    async def close(self):
        if self.http:
            await self.http.close()


def quickbooks_report_rows(report: dict, currency: str):
    columns = report.get("Columns", {}).get("Column", [])
    keys = [
        next((m.get("Value") for m in col.get("MetaData", []) if m.get("Name") == "ColKey"), "")
        for col in columns
    ]
    if not {"tx_date", "txn_type", "account_name", "debt_amt", "credit_amt"} <= set(keys):
        raise ConnectorError("QuickBooks report is missing required column metadata")
    if not isinstance(report.get("Rows", {}).get("Row"), list):
        raise ConnectorError("QuickBooks report rows are missing")
    occurrences: Counter = Counter()

    def walk(items, account_id=""):
        for item in items:
            if item.get("type") == "Section":
                header = item.get("Header", {}).get("ColData", [])
                section_account = next((str(c["id"]) for c in header if c.get("id")), account_id)
                yield from walk(item.get("Rows", {}).get("Row", []), section_account)
                continue
            if item.get("type") != "Data":
                continue
            cells = item.get("ColData", [])
            if len(cells) != len(keys):
                raise ConnectorError("QuickBooks report row width differs from its metadata")
            values = dict(zip(keys, cells, strict=True))
            posting = values["tx_date"].get("value", "")
            if not posting and any(c.get("value") == "Beginning Balance" for c in cells):
                continue  # Preserve the raw report; never turn a subtotal into a posting.
            code = values["account_name"].get("id") or account_id
            transaction = values["txn_type"].get("id")
            if not code or not transaction:
                raise ConnectorError("QuickBooks report lacks an account or transaction identifier")
            digest = hashlib.sha256(
                json.dumps(item, sort_keys=True, default=str).encode()
            ).hexdigest()
            occurrences[digest] += 1
            yield gl_row(
                code,
                str(transaction),
                posting,
                f"report:{digest}:{occurrences[digest]}",
                currency,
                values["debt_amt"].get("value", "0") or "0",
                values["credit_amt"].get("value", "0") or "0",
                description=values.get("memo", {}).get("value", ""),
                account_name=values["account_name"].get("value", code),
                source_transaction_id=transaction,
                source_transaction_type=values["txn_type"].get("value", ""),
                source_identity_quality="snapshot_scoped",
            )

    yield from walk(report["Rows"]["Row"])


def quickbooks_report_contract(report):
    """Version the actual published column contract, never localized column titles."""
    columns = report.get("Columns", {}).get("Column", [])
    keys = [next((m.get("Value") for m in col.get("MetaData", []) if m.get("Name") == "ColKey"), "") for col in columns]
    if not keys or len(keys) != len(set(keys)) or not {"tx_date", "txn_type", "account_name", "debt_amt", "credit_amt"} <= set(keys):
        raise ConnectorError("Unsupported QuickBooks report column contract")
    from app.modules.connectors.runtime import digest

    return {"parser_version": "qbo-general-ledger/2", "column_keys": keys, "schema_digest": digest(keys),
            "report_name": report.get("Header", {}).get("ReportName", "GeneralLedger")}
