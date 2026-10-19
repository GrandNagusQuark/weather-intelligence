"""Portable, device-scoped marine heads-up preferences; no delivery opt-in."""

import math
from typing import Any, Mapping

MARINE_NEARBY_FIELDS = ("marine_nearby_enabled", "marine_nearby_miles")
DEFAULT_MARINE_RADIUS_MILES = 10.0
MAX_MARINE_RADIUS_MILES = 100.0


def marine_nearby_preferences(value: Mapping[str, Any]) -> dict:
    enabled = value.get("marine_nearby_enabled", False)
    radius = value.get("marine_nearby_miles", DEFAULT_MARINE_RADIUS_MILES)
    if type(enabled) is not bool:
        raise ValueError("Choose whether nearby-water heads-ups are enabled.")
    if (
        isinstance(radius, bool)
        or not isinstance(radius, (float, int))
        or not math.isfinite(radius)
        or not 0.1 <= radius <= MAX_MARINE_RADIUS_MILES
    ):
        raise ValueError("Choose a nearby-water distance from 0.1 to 100 miles.")
    return {"marine_nearby_enabled": enabled, "marine_nearby_miles": float(radius)}
