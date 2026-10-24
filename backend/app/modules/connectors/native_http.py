"""Bounded, TLS-verified transport with origin-pinned pagination and secret-safe errors."""

import asyncio
import ipaddress
import json
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from app.modules.connectors.zoho import ConnectorError


class AuthorizationError(ConnectorError):
    pass


def origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.hostname}" + (
        f":{parsed.port}" if parsed.port not in {None, 443} else ""
    )


def approved_base(url: str, allowed: list[str], fixed: bool = False) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "\\" in url
        or "%" in parsed.netloc
    ):
        raise ConnectorError("Invalid API service root")
    if not fixed and origin(url) not in {origin(item) for item in allowed}:
        raise ConnectorError("API origin is not on the server CONNECTOR_ALLOWED_ORIGINS allowlist")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (address.is_link_local or address.is_multicast or address.is_unspecified):
        raise ConnectorError("Unsafe API address")
    return url.rstrip("/") + "/"


class NativeHTTP:
    def __init__(self, base: str, headers: dict | None = None, transport=None):
        self.base = base
        self.governor: Any = None
        self.requests = 0
        self.retries = 0
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=15),
            follow_redirects=False,
            verify=True,
            transport=transport,
            headers={"Accept": "application/json", **(headers or {})},
        )

    def url(self, target: str) -> str:
        parsed = urlsplit(target)
        if parsed.username or parsed.password or parsed.fragment or "\\" in target:
            raise ConnectorError("Unsafe API continuation URL")
        url = urljoin(self.base, target)
        path = unquote(urlsplit(url).path)
        root = unquote(urlsplit(self.base).path).rstrip("/") + "/"
        if (
            origin(url) != origin(self.base)
            or not path.startswith(root)
            or any(part in {"..", "."} for part in path.split("/"))
            or "%" in path
        ):
            raise ConnectorError("API continuation escaped its approved service root")
        return url

    async def request(self, target: str, method="GET", array=False, **kwargs) -> tuple[Any, bytes]:
        url = self.url(target)
        for attempt in range(4):
            lease = None
            try:
                if self.governor:
                    lease = await self.governor.acquire()
                self.requests += 1
                async with self.client.stream(method, url, **kwargs) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt < 3:
                        self.retries += 1
                        retry = response.headers.get("Retry-After", "")
                        delay = min(30, int(retry)) if retry.isdigit() else 2**attempt
                        await asyncio.sleep(delay)
                        continue
                    if response.status_code in {401, 403}:
                        raise AuthorizationError(
                            "API authorization or required read scope was denied"
                        )
                    if response.status_code >= 300:
                        raise ConnectorError("Accounting API request failed")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 64 * 1024 * 1024:
                            raise ConnectorError("Accounting API page exceeds 64 MiB")
                value = json.loads(raw, parse_float=Decimal)
                if (
                    not isinstance(value, list if array else dict)
                    or isinstance(value, dict)
                    and (value.get("error") or value.get("Fault"))
                ):
                    raise ConnectorError("Accounting API rejected the read request")
                return value, bytes(raw)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt == 3:
                    raise ConnectorError("Accounting API extraction was interrupted") from None
                await asyncio.sleep(2**attempt)
            except (json.JSONDecodeError, UnicodeError, httpx.DecodingError):
                raise ConnectorError("Accounting API returned invalid JSON") from None
            finally:
                if lease is not None:
                    await self.governor.release(lease)
        raise ConnectorError("Accounting API retry limit exceeded")

    async def close(self):
        await self.client.aclose()

    async def binary(self, target: str, allowed_types: set[str], max_bytes=32 * 1024 * 1024):
        url = self.url(target)
        lease = await self.governor.acquire() if self.governor else None
        try:
            self.requests += 1
            async with self.client.stream("GET", url, headers={"Accept": ", ".join(sorted(allowed_types))}) as response:
                if response.status_code != 200:
                    raise ConnectorError("Source attachment/metadata download failed or redirected")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type not in allowed_types:
                    raise ConnectorError("Unexpected source attachment/metadata content type")
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > max_bytes:
                        raise ConnectorError("Source attachment/metadata exceeds its size limit")
            return bytes(data), content_type
        finally:
            if lease is not None:
                await self.governor.release(lease)
