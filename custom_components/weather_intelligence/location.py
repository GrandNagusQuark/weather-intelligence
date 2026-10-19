"""Location freshness and one-shot best-effort refresh behavior."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .const import LAST_KNOWN_CRITICAL_ELIGIBILITY, LOCATION_GRACE_PERIOD
from .models import LocationAssessment, LocationFix, LocationFreshness


class LocationRefreshHook(Protocol):
    """Deployment adapter for requesting one fresh Companion location."""

    def request_location(self, subject_id: str) -> LocationFix | None:
        """Return a refreshed fix when immediately available, otherwise None."""


class LocationMonitor:
    """Classify fixes and prevent repeated refresh requests for one stale epoch."""

    def __init__(self, refresh_hook: LocationRefreshHook | None = None) -> None:
        self._refresh_hook = refresh_hook
        self._attempted_epochs: dict[str, datetime | None] = {}

    def assess(self, subject_id: str, fix: LocationFix | None, now: datetime) -> LocationAssessment:
        if fix is not None and fix.intentionally_unavailable:
            return LocationAssessment(LocationFreshness.INTENTIONALLY_UNAVAILABLE, None, None)
        if fix is None or fix.observed_at is None:
            return LocationAssessment(LocationFreshness.MISSING, None, fix)
        if fix.latitude is None or fix.longitude is None:
            return LocationAssessment(LocationFreshness.MISSING, None, fix)

        age = max(0.0, (now - fix.observed_at).total_seconds())
        if age < LOCATION_GRACE_PERIOD.total_seconds():
            freshness = (
                LocationFreshness.LAST_KNOWN_GRACE
                if fix.reported_stale
                else LocationFreshness.FRESH
            )
            self._attempted_epochs.pop(subject_id, None)
            return LocationAssessment(freshness, age, fix, last_known_fix=fix)

        attempted = self._attempted_epochs.get(subject_id) == fix.observed_at
        if not attempted and self._refresh_hook is not None:
            self._attempted_epochs[subject_id] = fix.observed_at
            refreshed = self._refresh_hook.request_location(subject_id)
            if refreshed is not None and refreshed.observed_at is not None:
                refreshed_age = max(0.0, (now - refreshed.observed_at).total_seconds())
                if refreshed_age < LOCATION_GRACE_PERIOD.total_seconds():
                    self._attempted_epochs.pop(subject_id, None)
                    return LocationAssessment(
                        LocationFreshness.FRESH,
                        refreshed_age,
                        refreshed,
                        last_known_fix=refreshed,
                        refresh_attempted=True,
                    )
            attempted = True

        return LocationAssessment(
            (
                LocationFreshness.UNKNOWN
                if age > LAST_KNOWN_CRITICAL_ELIGIBILITY.total_seconds()
                else LocationFreshness.DEGRADED
            ),
            age,
            None,
            last_known_fix=(
                fix
                if age <= LAST_KNOWN_CRITICAL_ELIGIBILITY.total_seconds()
                else None
            ),
            refresh_attempted=attempted,
        )
