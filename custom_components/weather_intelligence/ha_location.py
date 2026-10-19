"""Privacy-preserving conversion of a Home Assistant Person state to a location fix."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import LocationFix

_UNAVAILABLE_STATES = {"unknown", "unavailable"}


def location_fix_from_person_state(state: Any | None) -> LocationFix | None:
    """Read only documented person location fields; never format or log coordinates."""
    if state is None:
        return None
    attributes = getattr(state, "attributes", {}) or {}
    latitude = _coordinate(attributes.get("latitude"), -90.0, 90.0)
    longitude = _coordinate(attributes.get("longitude"), -180.0, 180.0)
    accuracy = _accuracy(attributes.get("gps_accuracy"))
    observed_at = getattr(state, "last_updated", None)
    if observed_at is not None and not isinstance(observed_at, datetime):
        observed_at = None
    if observed_at is not None and observed_at.tzinfo is None:
        # Home Assistant supplies aware timestamps. A malformed naive value cannot
        # be aged safely, so handle it as missing rather than guessing a timezone.
        observed_at = None
    state_value = str(getattr(state, "state", "unknown")).casefold()
    if state_value in _UNAVAILABLE_STATES:
        # An unavailable transition timestamp is not a fresh GPS observation time.
        observed_at = None
    return LocationFix(
        latitude=latitude,
        longitude=longitude,
        observed_at=observed_at,
        accuracy_meters=accuracy,
        reported_stale=state_value in _UNAVAILABLE_STATES,
    )


def _coordinate(value: Any, minimum: float, maximum: float) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if minimum <= result <= maximum else None


def _accuracy(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None
