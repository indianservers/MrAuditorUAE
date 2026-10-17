"""Official Zoho Books v3 resources. Resource extracts are not claimed to be a complete GL."""

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from urllib.parse import urlencode

import httpx

REGIONS = {
    suffix: (f"https://accounts.zoho.{suffix}", f"https://www.zohoapis.{suffix}/books/v3")
    for suffix in ["com", "eu", "in", "com.au", "jp", "ca", "com.cn", "sa", "ae"]
}
REGIONS["ca"] = ("https://accounts.zohocloud.ca", "https://www.zohoapis.ca/books/v3")

RESOURCES = {
    "chartofaccounts": "chartofaccounts",
    "journals": "journals",
    "invoices": "invoices",
    "bills": "bills",
    "creditnotes": "creditnotes",
    "contacts": "contacts",
}
SCOPES = "ZohoBooks.settings.READ,ZohoBooks.accountants.READ,ZohoBooks.invoices.READ,ZohoBooks.bills.READ,ZohoBooks.creditnotes.READ,ZohoBooks.contacts.READ"


class ConnectorError(ValueError):
    pass


class ZohoConnector:
    version = "zoho-books-v3/2.0.0"

    def __init__(
        self,
        region: str,
        client_id: str,
        client_secret: str,
        refresh_token: str = "",
        access_token: str = "",
        transport=None,
    ):
        if region not in REGIONS:
            raise ConnectorError("Unapproved Zoho region")
        self.accounts, self.api = REGIONS[region]
        self.client_id, self.client_secret, self.refresh_token, self.access_token = (
            client_id,
            client_secret,
            refresh_token,
            access_token,
        )
        self.transport = transport
        self.last_raw: bytes = b""

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        if len(state) < 32:
            raise ConnectorError("Strong state required")
        return (
            self.accounts
            + "/oauth/v2/auth?"
            + urlencode(
                {
                    "scope": SCOPES,
                    "client_id": self.client_id,
                    "response_type": "code",
                    "access_type": "offline",
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "prompt": "consent",
                }
            )
        )

    async def token(self, code: str | None = None, redirect_uri: str | None = None) -> dict:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code" if code else "refresh_token",
        }
        if code:
            payload.update(code=code, redirect_uri=redirect_uri or "")
        else:
            payload["refresh_token"] = self.refresh_token
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=30, follow_redirects=False
            ) as client:
                response = await client.post(self.accounts + "/oauth/v2/token", data=payload)
                response.raise_for_status()
                data = response.json(parse_float=Decimal)
                self.last_raw = response.content
                if not data.get("access_token"):
                    raise ConnectorError("Authorization revoked or token exchange denied")
                if data.get("api_domain") and data["api_domain"] != self.api.removesuffix(
                    "/books/v3"
                ):
                    raise ConnectorError("Zoho token data-center mismatch")
                self.access_token = data["access_token"]
                if data.get("refresh_token"):
                    self.refresh_token = data["refresh_token"]
                return {"access_token": self.access_token, "refresh_token": self.refresh_token}
        except (httpx.HTTPError, KeyError) as exc:
            raise ConnectorError("Zoho token exchange failed") from exc

    async def get(self, resource: str, params: dict) -> dict:
        refreshed = False
        for attempt in range(4):
            if not self.access_token:
                await self.token()
            try:
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=30, follow_redirects=False
                ) as client:
                    response = await client.get(
                        self.api + "/" + resource,
                        params=params,
                        headers={"Authorization": "Zoho-oauthtoken " + self.access_token},
                    )
                if response.status_code == 401 and not refreshed:
                    await self.token()
                    refreshed = True
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        await asyncio.sleep(min(8, 2**attempt))
                        continue
                if response.status_code in {401, 403}:
                    raise ConnectorError(
                        "Missing organization access, scope or revoked credentials"
                    )
                response.raise_for_status()
                data = response.json(parse_float=Decimal)
                self.last_raw = response.content
                if data.get("code") != 0:
                    raise ConnectorError("Zoho API rejected extraction")
                return data
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 3:
                    raise ConnectorError("Zoho network extraction incomplete") from None
                await asyncio.sleep(2**attempt)
            except httpx.HTTPStatusError:
                raise ConnectorError("Zoho extraction incomplete") from None
        raise ConnectorError("Zoho retry limit reached")

    async def pages(
        self, resource: str, organization_id: str | None, extra: dict | None = None
    ) -> AsyncIterator[dict]:
        if resource not in {*RESOURCES, "organizations"}:
            raise ConnectorError("Unsupported Zoho resource")
        key = RESOURCES.get(resource, resource)
        seen = set()
        for page in range(1, 10001):
            params = {"page": page, "per_page": 200, **(extra or {})}
            if organization_id:
                params["organization_id"] = organization_id
            data = await self.get(resource, params)
            if not isinstance(data.get(key), list):
                raise ConnectorError("Missing resource page")
            # Preserve the exact page before any normalization.
            yield {"resource": resource, "page": page, "raw": data}
            context = data.get("page_context")
            if not context or "has_more_page" not in context:
                raise ConnectorError("Pagination completeness cannot be established")
            if int(context.get("page", page)) != page:
                raise ConnectorError("Repeated or partial pagination")
            if not context["has_more_page"]:
                return
            if not data[key]:
                raise ConnectorError("Empty intermediate page")
            marker = str(data[key][0])
            if marker in seen:
                raise ConnectorError("Repeated API page")
            seen.add(marker)
        raise ConnectorError("Zoho pagination safety limit")

    async def journal_detail(self, journal_id: str, organization_id: str) -> dict:
        if not journal_id.isdigit():
            raise ConnectorError("Invalid journal identifier")
        return await self.get("journals/" + journal_id, {"organization_id": organization_id})
