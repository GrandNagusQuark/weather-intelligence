"""Small official NWS alerts client with explicit identity and timeout."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .const import NWS_API_BASE_URL, NWS_REQUEST_TIMEOUT_SECONDS


class NwsClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class NwsResponse:
    payload: Mapping[str, Any]
    received_at: datetime
    server_time: datetime | None = None


class NwsAlertClient:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = NWS_REQUEST_TIMEOUT_SECONDS,
        base_url: str = NWS_API_BASE_URL,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("An identifiable NWS User-Agent must be configured")
        if timeout_seconds <= 0:
            raise ValueError("NWS timeout must be positive")
        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")

    def fetch_active(self, *, area: str | None = None, point: tuple[float, float] | None = None,
                     max_bytes: int | None = None) -> NwsResponse:
        if area and point:
            raise ValueError("Choose either an NWS area filter or point filter")
        query: dict[str, str] = {}
        if area:
            query["area"] = area.upper()
        if point:
            latitude, longitude = point
            query["point"] = f"{latitude},{longitude}"
        suffix = f"?{urlencode(query)}" if query else ""
        request = Request(
            f"{self._base_url}/alerts/active{suffix}",
            headers={
                "Accept": "application/geo+json",
                "User-Agent": self._user_agent,
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                from .source_latency import response_server_time
                server_time = response_server_time(getattr(response, "headers", {}))
                if max_bytes is None:
                    payload = json.load(response)
                else:
                    body = response.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise ValueError("NWS regional heads-up response exceeds size budget")
                    payload = json.loads(body)
        except Exception as error:
            raise NwsClientError(f"NWS active-alert request failed: {error}") from error
        if not isinstance(payload, Mapping):
            raise NwsClientError("NWS response was not a JSON object")
        return NwsResponse(payload, datetime.now(timezone.utc), server_time)

    def fetch_point_forecast(self, point: tuple[float, float]) -> NwsResponse:
        """Resolve the official point metadata and fetch its forecast URL."""
        latitude, longitude = point
        metadata = self._fetch_json(f"{self._base_url}/points/{latitude},{longitude}")
        properties = metadata.get("properties")
        forecast_url = properties.get("forecast") if isinstance(properties, Mapping) else None
        if not isinstance(forecast_url, str) or not forecast_url.startswith("https://"):
            raise NwsClientError("NWS point metadata has no secure forecast URL")
        return NwsResponse(self._fetch_json(forecast_url), datetime.now(timezone.utc))

    def _fetch_json(self, url: str) -> Mapping[str, Any]:
        request = Request(url, headers={"Accept": "application/geo+json", "User-Agent": self._user_agent})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.load(response)
        except Exception as error:
            raise NwsClientError(f"NWS request failed: {error}") from error
        if not isinstance(payload, Mapping):
            raise NwsClientError("NWS response was not a JSON object")
        return payload
