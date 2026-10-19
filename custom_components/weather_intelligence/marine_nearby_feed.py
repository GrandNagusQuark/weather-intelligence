"""Bounded, background NWS snapshot for optional nearby-water heads-ups."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from .models import OfficialAlert
from .normalization import AlertNormalizationError, parse_feature_collection
from .nws_client import NwsClientError

REFRESH_INTERVAL = timedelta(minutes=1)
MAX_SNAPSHOT_AGE = timedelta(minutes=5)
MAX_RESPONSE_BYTES = 8_000_000
MAX_ALERTS = 5000


def fetch_nearby_snapshot(client: Any) -> tuple[datetime, tuple[OfficialAlert, ...]]:
    response = client.fetch_active(max_bytes=MAX_RESPONSE_BYTES)
    payload = response.payload
    features = payload.get("features")
    pagination = payload.get("pagination") or {}
    if (
        not isinstance(features, list)
        or len(features) > MAX_ALERTS
        or not isinstance(pagination, dict)
        or pagination.get("next")
    ):
        raise AlertNormalizationError("Incomplete nearby-water alert snapshot")
    return response.received_at, tuple(parse_feature_collection(payload, response.received_at))


class MarineNearbyFeed:
    """Never wait for this optional nationwide request before direct warnings."""

    def __init__(self, client: Any, executor: Any) -> None:
        self._client = client
        self._executor = executor
        self._task: asyncio.Task | None = None
        self._next_refresh: datetime | None = None
        self._received_at: datetime | None = None
        self._alerts: tuple[OfficialAlert, ...] = ()
        self.state = "unconfigured"

    def request_refresh(self, enabled: bool, now: datetime) -> None:
        if not enabled:
            self._alerts = ()
            self._received_at = None
            self._next_refresh = None
            self.state = "unconfigured"
            if self._task and not self._task.done():
                self._task.cancel()
            return
        if self._task is not None and not self._task.done():
            return
        if self._next_refresh is not None and now < self._next_refresh:
            return
        self._next_refresh = now + REFRESH_INTERVAL
        self._task = asyncio.create_task(self._async_refresh())

    async def _async_refresh(self) -> None:
        try:
            received_at, alerts = await self._executor(fetch_nearby_snapshot, self._client)
        except (NwsClientError, AlertNormalizationError, OSError, TypeError, ValueError):
            self.state = "degraded"
            return
        self._received_at, self._alerts = received_at, alerts
        self.state = "healthy"

    def alerts(self, now: datetime) -> tuple[OfficialAlert, ...]:
        if (
            self._received_at is None
            or not timedelta(0) <= now - self._received_at < MAX_SNAPSHOT_AGE
        ):
            return ()
        return self._alerts

    async def async_shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
