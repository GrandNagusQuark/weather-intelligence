"""Owned HTTPS transport with public DNS enforcement and no redirect following."""

from __future__ import annotations

import ipaddress
import json
from typing import Any


def public_addresses(addresses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public = [address for address in addresses if ipaddress.ip_address(address["host"]).is_global]
    if not public:
        raise OSError("Reporting destination has no public address")
    return public


class ReportTransport:
    def __init__(self) -> None:
        self._session: Any = None
        self._resolver: Any = None

    def _ensure_session(self):
        import aiohttp

        if self._session is None:
            class PublicResolver(aiohttp.resolver.DefaultResolver):
                async def resolve(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                    return public_addresses(await super().resolve(*args, **kwargs))

            self._resolver = PublicResolver()
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(resolver=self._resolver),
                cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                json_serialize=lambda value: json.dumps(value, ensure_ascii=False),
                timeout=aiohttp.ClientTimeout(total=5),
            )
        return self._session

    async def send(self, endpoint: str, document: dict[str, Any]) -> tuple[int, bool]:
        self._ensure_session()
        async with self._session.post(
            endpoint, json=document, allow_redirects=False,
            headers={"User-Agent": "WeatherIntelligence-Reporting/1"},
        ) as response:
            return response.status, response.headers.get("X-WI-Reporting") == "1"

    async def get_status(self, endpoint):
        import json
        self._ensure_session()
        async with self._session.get(endpoint, allow_redirects=False,
                headers={"User-Agent": "WeatherIntelligence-ServiceStatus/1"}) as response:
            if response.status != 200 or response.headers.get("X-WI-Reporting") != "1":
                raise ValueError("Service status unavailable")
            body = bytearray()
            async for chunk in response.content.iter_chunked(2048):
                body.extend(chunk)
                if len(body) > 4096:
                    raise ValueError("Service status too large")
            return json.loads(body)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
        if self._resolver is not None:
            await self._resolver.close()
