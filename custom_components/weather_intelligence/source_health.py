"""Explicit source-health state; unavailable or stale never means no risk."""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import SourceHealth, SourceHealthState


class SourceHealthMonitor:
    def __init__(self, stale_after: timedelta = timedelta(minutes=10)) -> None:
        self._stale_after = stale_after
        self._last_success_at: datetime | None = None
        self._health: SourceHealth | None = None

    @property
    def health(self) -> SourceHealth | None:
        return self._health

    def record_success(self, checked_at: datetime, feature_count: int) -> SourceHealth:
        self._last_success_at = checked_at
        self._health = SourceHealth(
            SourceHealthState.HEALTHY,
            checked_at,
            checked_at,
            "NWS alert feed parsed successfully.",
            feature_count,
        )
        return self._health

    def record_failure(self, checked_at: datetime, detail: str) -> SourceHealth:
        self._health = SourceHealth(
            SourceHealthState.DATA_UNAVAILABLE,
            checked_at,
            self._last_success_at,
            detail,
        )
        return self._health

    def record_degraded(self, checked_at: datetime, detail: str) -> SourceHealth:
        self._health = SourceHealth(
            SourceHealthState.SOURCE_DEGRADED,
            checked_at,
            self._last_success_at,
            detail,
        )
        return self._health

    def evaluate_freshness(self, now: datetime) -> SourceHealth:
        if self._last_success_at is None:
            return self.record_failure(now, "No successful NWS alert feed retrieval is available.")
        if now - self._last_success_at > self._stale_after:
            self._health = SourceHealth(
                SourceHealthState.DATA_STALE,
                now,
                self._last_success_at,
                "The last successful NWS alert feed is stale; risk is unknown, not absent.",
            )
        return self._health or self.record_failure(now, "NWS source health is unknown.")
