"""OAuth tokens never enter source manifests, URLs, serializers or job results."""

from urllib.parse import urlencode

import httpx

from app.modules.connectors.native_config import NativeConfig
from app.modules.connectors.native_http import NativeHTTP, origin
from app.modules.connectors.zoho import ConnectorError

OAUTH = {
    "quickbooks": (
        "https://appcenter.intuit.com/connect/oauth2",
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        "com.intuit.quickbooks.accounting",
    ),
    "xero": (
        "https://login.xero.com/identity/connect/authorize",
        "https://identity.xero.com/connect/token",
        "offline_access accounting.transactions.read accounting.settings.read accounting.journals.read accounting.reports.read",
    ),
}


def authorization_url(provider: str, credentials: dict, redirect: str, state: str) -> str:
    if provider not in OAUTH:
        raise ConnectorError(
            "This interface uses secure API credentials rather than browser consent"
        )
    if not credentials.get("client_id") or not credentials.get("client_secret"):
        raise ConnectorError("OAuth client ID and secret are required")
    endpoint, _, scope = OAUTH[provider]
    return (
        endpoint
        + "?"
        + urlencode(
            {
                "client_id": credentials["client_id"],
                "response_type": "code",
                "scope": scope,
                "redirect_uri": redirect,
                "state": state,
            }
        )
    )


async def token(
    provider: str,
    config: NativeConfig,
    credentials: dict,
    code: str | None = None,
    redirect: str | None = None,
    transport=None,
) -> dict:
    if provider in OAUTH:
        endpoint = OAUTH[provider][1]
    elif provider == "netsuite":
        endpoint = f"https://{config.account_id.lower().replace('_', '-')}.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token"
    elif provider == "dynamics":
        endpoint = f"https://login.microsoftonline.com/{config.directory_tenant}/oauth2/v2.0/token"
    else:
        raise ConnectorError("Token refresh is not supported by this credential type")
    if not credentials.get("client_id") or not credentials.get("client_secret"):
        raise ConnectorError("OAuth client credentials are missing")
    body = {"grant_type": "authorization_code" if code else "refresh_token"}
    if code:
        body.update(code=code, redirect_uri=redirect or "")
    else:
        body["refresh_token"] = credentials.get("refresh_token", "")
    auth: httpx.BasicAuth | None = httpx.BasicAuth(
        credentials["client_id"], credentials["client_secret"]
    )
    if provider == "dynamics":
        body = {
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "scope": ((origin(config.base_url) + "/.default")
                      if config.edition == "finance-odata" else "https://api.businesscentral.dynamics.com/.default"),
        }
        auth = None
    elif not code and not body["refresh_token"]:
        raise ConnectorError("An authorized refresh token is required")
    http = NativeHTTP(endpoint.rsplit("/", 1)[0] + "/", transport=transport)
    try:
        data, _ = await http.request(endpoint, "POST", data=body, auth=auth)
        if not isinstance(data.get("access_token"), str) or not data["access_token"]:
            raise ConnectorError("OAuth did not return an access token")
        return {
            **credentials,
            "access_token": data["access_token"],
            **({"refresh_token": data["refresh_token"]} if data.get("refresh_token") else {}),
        }
    finally:
        await http.close()
