"""Read fresh activity evidence belonging to one Companion app registration."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_ACTIVITY_AGE_SECONDS = 300
MIN_ACTIVITY_CONFIDENCE = 80
VEHICLE_ACTIVITIES = {"in_vehicle", "automotive"}
NON_VEHICLE_ACTIVITIES = {
    "on_bicycle",
    "on_foot",
    "running",
    "still",
    "walking",
    "stationary",
    "cycling",
}


@dataclass(frozen=True)
class MarineTravelAssessment:
    vehicle_travel: bool | None = None
    car_connected: bool = False


def driving_assessment(hass: Any, mobile_entry_id: str, now: datetime) -> bool | None:
    """Estimate vehicle travel, not proof of driving a car or evidence of boating."""
    observations = []
    for item, sensor in _fresh_owned_sensors(hass, mobile_entry_id, now):
        if not item.entity_id.startswith("sensor.") or not str(item.unique_id).casefold().endswith(
            ("_detected_activity", "_activity")
        ):
            continue
        confidence = sensor.attributes.get("confidence")
        numeric_confidence = (
            type(confidence) in {int, float}
            and math.isfinite(confidence)
            and MIN_ACTIVITY_CONFIDENCE <= confidence <= 100
        )
        if not (str(confidence).casefold() == "high" or numeric_confidence):
            continue
        # iOS can report multiple activities; its primary state is not necessarily
        # the most likely. Conflicting types cannot establish a travel mode.
        values = {str(sensor.state).casefold()}
        types = sensor.attributes.get("types")
        if isinstance(types, (list, tuple)):
            values.update(str(value).casefold() for value in types)
        vehicle = bool(values & VEHICLE_ACTIVITIES)
        non_vehicle = bool(values & NON_VEHICLE_ACTIVITIES)
        if vehicle and not non_vehicle:
            observations.append(True)
        elif non_vehicle and not vehicle:
            observations.append(False)
    return observations[0] if observations and len(set(observations)) == 1 else None


def marine_travel_assessment(
    hass: Any, mobile_entry_id: str, now: datetime
) -> MarineTravelAssessment:
    """Separate broad vehicle activity from a fresh car-system connection.

    Android Auto is stronger car evidence, not a road map or a guaranteed travel
    mode. No generic Bluetooth-device name or speed is treated as a car connection.
    """
    try:
        car_connected = False
        for item, sensor in _fresh_owned_sensors(hass, mobile_entry_id, now):
            if (
                item.entity_id.startswith("binary_sensor.")
                and str(item.unique_id).casefold().endswith("_android_auto")
                and str(sensor.state).casefold() == "on"
            ):
                car_connected = True
        return MarineTravelAssessment(driving_assessment(hass, mobile_entry_id, now), car_connected)
    except (ImportError, AttributeError, KeyError):
        return MarineTravelAssessment()


def _fresh_owned_sensors(
    hass: Any, mobile_entry_id: str, now: datetime
) -> Iterator[tuple[Any, Any]]:
    if not mobile_entry_id:
        return
    from homeassistant.helpers import entity_registry as er

    for item in er.async_entries_for_config_entry(er.async_get(hass), mobile_entry_id):
        if item.platform != "mobile_app" or item.disabled_by is not None:
            continue
        sensor = hass.states.get(item.entity_id)
        if sensor is None or sensor.attributes.get("restored"):
            continue
        updated = getattr(sensor, "last_reported", None) or getattr(sensor, "last_updated", None)
        if (
            not isinstance(updated, datetime)
            or updated.tzinfo is None
            or not 0 <= (now - updated).total_seconds() <= MAX_ACTIVITY_AGE_SECONDS
        ):
            continue
        yield item, sensor
