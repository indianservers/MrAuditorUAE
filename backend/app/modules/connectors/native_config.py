"""Edition-specific direct accounting interfaces. No default BUSY/Marg API is invented."""

import re
from decimal import Decimal
from urllib.parse import urlsplit

from pydantic import Field, ValidationError

from app.modules.accounting.schemas import Input
from app.modules.connectors.zoho import ConnectorError

NATIVE_PROVIDERS = {
    "quickbooks",
    "xero",
    "netsuite",
    "sap-b1",
    "sap-s4",
    "dynamics",
    "busy",
    "marg",
}
EDITIONS = {
    "quickbooks": ["online", "desktop-partner-api"],
    "xero": ["cloud"],
    "netsuite": ["suiteql"],
    "sap-b1": ["service-layer"],
    "sap-s4": ["ledger-odata", "entry-view-odata"],
    "dynamics": ["business-central", "finance-odata", "finance-partner-api"],
    "busy": ["partner-api"],
    "marg": ["partner-api"],
}
CREDENTIAL_FIELDS = {
    "quickbooks": ["client_id", "client_secret", "refresh_token", "access_token", "api_key"],
    "xero": ["client_id", "client_secret", "refresh_token", "access_token"],
    "netsuite": ["client_id", "client_secret", "refresh_token", "access_token"],
    "dynamics": ["client_id", "client_secret", "access_token", "api_key"],
    "sap-b1": ["username", "password"],
    "sap-s4": ["username", "password", "access_token"],
    "busy": ["access_token", "api_key", "username", "password"],
    "marg": ["access_token", "api_key", "username", "password"],
}
SETUP_FIELDS = {
    "quickbooks": ["environment"],
    "xero": [],
    "netsuite": ["account_id", "subsidiary_id", "accounting_book"],
    "sap-b1": ["base_url"],
    "sap-s4": ["base_url", "ledger", "accounts_path", "ledger_path"],
    "dynamics": ["directory_tenant", "bc_environment"],
    "busy": ["base_url"],
    "marg": ["base_url"],
}
PARTNER_FIELDS = [
    "base_url",
    "company_path",
    "accounts_path",
    "ledger_path",
    "tb_path",
    "rows_key",
    "next_key",
    "company_id_field",
    "currency_field",
    "company_parameter",
    "start_parameter",
    "end_parameter",
    "api_key_header",
]
SOURCE_DOCS = {
    "quickbooks": "https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/generalledger",
    "xero": "https://developer.xero.com/documentation/api/accounting/journals/",
    "netsuite": "https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157909186990.html",
    "sap-b1": "https://help.sap.com/doc/056f69366b5345a386bb8149f1700c19/10.0/en-US/Service%20Layer%20API%20Reference.html",
    "sap-s4": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/3ab6e6fc510f4840a5508e126ef01e22/80214b5ede2f4e97b640137a4eca208a.html",
    "dynamics": "https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0/resources/dynamics_generalledgerentry",
    "busy": "https://busy.in/faqs/third-party-services/integration/10/",
    "marg": "https://margcompusoft.com/Package/Packages.aspx",
}


class NativeConfig(Input):
    edition: str = Field(default="", max_length=50)
    base_url: str = Field(default="", max_length=500)
    company_id: str = Field(default="", max_length=100, pattern=r"^[^\r\n]*$")
    functional_currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")
    environment: str = Field(default="production", pattern=r"^(production|sandbox)$")
    directory_tenant: str = Field(default="", max_length=100)
    bc_environment: str = Field(default="Production", pattern=r"^[A-Za-z0-9_-]+$")
    account_id: str = Field(default="", pattern=r"^[A-Za-z0-9_-]*$")
    subsidiary_id: str = Field(default="", pattern=r"^[0-9]*$")
    accounting_book: str = Field(default="", pattern=r"^[0-9]*$")
    ledger: str = Field(default="0L", pattern=r"^[A-Za-z0-9]+$")
    chart_of_accounts: str = Field(default="", max_length=30)
    company_path: str = Field(default="", max_length=300)
    accounts_path: str = Field(default="", max_length=300)
    ledger_path: str = Field(default="", max_length=300)
    tb_path: str = Field(default="", max_length=300)
    rows_key: str = Field(default="items", max_length=100)
    next_key: str = Field(default="next", max_length=100)
    company_id_field: str = Field(default="company_id", max_length=100)
    currency_field: str = Field(default="currency", max_length=100)
    company_parameter: str = Field(default="company_id", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    start_parameter: str = Field(default="start_date", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    end_parameter: str = Field(default="end_date", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    api_key_header: str = Field(default="X-API-Key", pattern=r"^X-[A-Za-z0-9-]+$")
    mappings: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=3)
    max_pages: int = Field(default=10000, ge=1, le=10000)
    control_reference: str = Field(default="", max_length=500)
    expected_gl_rows: int | None = Field(default=None, ge=0)
    expected_gl_debit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    expected_gl_credit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    requests_per_minute: int = Field(default=60, ge=1, le=5000)
    requests_per_day: int = Field(default=10000, ge=0, le=10000000)
    concurrency: int = Field(default=2, ge=1, le=20)
    oauth_grant_id: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_-]*$")
    expected_report_schema_digest: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")
    include_documents: bool = False
    include_attachments: bool = False
    tax_details: bool = False
    profile_id: str = Field(default="", max_length=128)
    metadata_preflight: bool = False
    discover_scope: bool = False
    currency_aliases: dict[str, str] = Field(default_factory=dict, max_length=50)
    posting_date_field: str = Field(default="AccountingDate", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    finance_company_field: str = Field(default="dataAreaId", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    cdc_since: str = Field(default="", max_length=40)
    cdc_entities: list[str] = Field(
        default_factory=lambda: ["Invoice", "Bill", "Payment", "JournalEntry"], max_length=20
    )
    supersedes_ids: dict[str, str] = Field(default_factory=dict, max_length=3)


def partner_mode(config: NativeConfig) -> bool:
    return config.edition in {"partner-api", "desktop-partner-api", "finance-partner-api"}


def configure(provider: str, raw: dict, complete: bool = False) -> NativeConfig:
    if provider not in NATIVE_PROVIDERS:
        raise ConnectorError("Unsupported direct API provider")
    try:
        config = NativeConfig.model_validate(raw)
    except ValidationError:
        raise ConnectorError("Invalid direct API configuration") from None
    if not config.edition:
        config.edition = EDITIONS[provider][0]
    if config.edition not in EDITIONS[provider]:
        raise ConnectorError("Unsupported provider edition")
    if complete and (not config.company_id or not config.functional_currency):
        raise ConnectorError("Company identifier and functional currency are required")
    if (
        any(
            value is not None
            for value in (
                config.expected_gl_rows,
                config.expected_gl_debit,
                config.expected_gl_credit,
            )
        )
        and not config.control_reference.strip()
    ):
        raise ConnectorError("Independent source controls require a source report/reference")
    if config.base_url:
        parsed = urlsplit(config.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "%" in parsed.netloc
            or "\\" in config.base_url
        ):
            raise ConnectorError(
                "API base URL must be HTTPS without credentials, query or fragment"
            )
    if provider in {"sap-b1", "sap-s4", "busy", "marg"} or partner_mode(config):
        if complete and not config.base_url:
            raise ConnectorError("The approved API service root is required")
    if (
        complete
        and partner_mode(config)
        and not all((config.company_path, config.accounts_path, config.ledger_path))
    ):
        raise ConnectorError("Partner API requires documented company, accounts and ledger paths")
    if (
        provider == "netsuite"
        and complete
        and not all((config.account_id, config.subsidiary_id, config.accounting_book))
    ):
        raise ConnectorError("NetSuite account, subsidiary and accounting book are required")
    if provider == "netsuite" and config.company_id and config.company_id != config.subsidiary_id:
        raise ConnectorError("NetSuite company identifier must be the selected subsidiary")
    if provider == "dynamics" and not partner_mode(config) and complete:
        if not re.fullmatch(r"[A-Za-z0-9-]+", config.directory_tenant):
            raise ConnectorError("Microsoft directory tenant is required")
        import uuid

        if config.edition == "business-central":
            try:
                uuid.UUID(config.company_id)
            except ValueError:
                raise ConnectorError("Business Central company identifier must be a GUID") from None
        elif not all(
            (
                config.base_url,
                config.company_path,
                config.accounts_path,
                config.ledger_path,
                config.mappings.get("gl"),
                config.mappings.get("coa"),
            )
        ):
            raise ConnectorError(
                "Dynamics Finance requires its deployed read entities and explicit field mappings"
            )
    if config.edition == "finance-odata":
        for path in (config.company_path, config.accounts_path, config.ledger_path):
            if path and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", path):
                raise ConnectorError("Finance OData paths must name published entity sets")
        for mapping in config.mappings.values():
            if any(
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", value)
                for value in mapping.values()
            ):
                raise ConnectorError("Finance fields must be published property paths")
    if provider == "xero" and complete:
        import uuid

        try:
            uuid.UUID(config.company_id)
        except ValueError:
            raise ConnectorError("Xero organization identifier must be a GUID") from None
    if provider == "quickbooks" and not partner_mode(config) and config.company_id:
        if not config.company_id.isdigit():
            raise ConnectorError("QuickBooks Online company identifier must be a numeric realm ID")
    return config
