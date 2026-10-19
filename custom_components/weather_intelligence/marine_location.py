"""Marine notification eligibility using local map estimates and HA's home zone."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .ha_location import location_fix_from_person_state
from .water_detection import (
    WaterAssessment,
    current_near_water_state,
    current_water_state,
    invalid_water_fix,
)

EARTH_RADIUS_METERS = 6_371_008.8


def marine_location_eligible(
    assessment: WaterAssessment | None,
    now: datetime,
    *,
    person_state: Any = None,
    home_zone_state: Any = None,
    vehicle_travel: bool | None = None,
    car_connected: bool = False,
) -> bool:
    """Mapped water overrides home and ambiguous vehicle-system evidence.

    This gate never establishes warning-area relevance, enables a notification,
    or changes DND policy. Those remain independent delivery checks.
    """
    if current_water_state(assessment, now) is True:
        return True
    # Boats can have Android Auto head units. Neither connection nor broad vehicle
    # activity proves road travel, so they suppress only proximity-only eligibility.
    if vehicle_travel is True or car_connected:
        return False
    if current_near_water_state(assessment, now) is not True:
        return False
    fix = location_fix_from_person_state(person_state)
    if invalid_water_fix(fix, now) or assessment is None:
        return False
    if fix.observed_at != assessment.observed_at:
        # A newly moved device needs a new shoreline assessment, not the old result.
        return False
    if str(getattr(person_state, "state", "")).casefold() == "home":
        return False
    if home_zone_state is None or str(getattr(home_zone_state, "state", "")).casefold() in {
        "unknown",
        "unavailable",
    }:
        return False
    attributes = getattr(home_zone_state, "attributes", {}) or {}
    home_latitude = _finite_number(attributes.get("latitude"), -90, 90)
    home_longitude = _finite_number(attributes.get("longitude"), -180, 180)
    radius = _finite_number(attributes.get("radius"), 0, math.inf)
    if home_latitude is None or home_longitude is None or radius is None:
        return False
    latitude_radians, home_latitude_radians = map(math.radians, (fix.latitude, home_latitude))
    longitude_delta = math.radians(fix.longitude - home_longitude)
    haversine = (
        math.sin((latitude_radians - home_latitude_radians) / 2) ** 2
        + math.cos(latitude_radians)
        * math.cos(home_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    distance = 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))
    # Accuracy overlapping home is not evidence that the device has left home.
    return distance - fix.accuracy_meters > radius


def _finite_number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None
