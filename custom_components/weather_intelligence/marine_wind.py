"""Source-backed 34-knot DND condition for fresh estimated on-water locations."""

import re
from datetime import datetime
from typing import Any

from .water_detection import WaterAssessment, current_water_state

MINIMUM_WIND = {"kt": 34, "kts": 34, "knot": 34, "knots": 34, "mph": 39, "km/h": 63, "kph": 63}
WIND_VALUE = re.compile(r"^\s*(?:>=?\s*)?(\d+(?:\.\d+)?)\s*(kt|kts|knots?|mph|km/h|kph)\s*$", re.I)
MINIMUM_EVENT_WIND = {
    "gale warning",
    "storm warning",
    "hurricane force wind warning",
    "tropical storm warning",
    "hurricane warning",
    "typhoon warning",
}


def on_water_wind_qualifies(alert: Any, assessment: WaterAssessment | None, now: datetime) -> bool:
    """Do not substitute near-shore proximity, vehicle activity or prose numbers."""
    if current_water_state(assessment, now) is not True:
        return False
    if str(getattr(alert, "event", "")).casefold() in MINIMUM_EVENT_WIND:
        return True
    raw = getattr(alert, "raw_official_payload", None)
    properties = raw.get("properties") if isinstance(raw, dict) else None
    parameters = properties.get("parameters") if isinstance(properties, dict) else None
    if not isinstance(parameters, dict):
        return False
    values = parameters.get("maxWindGust", [])
    if not isinstance(values, (list, tuple)):
        return False
    for value in values:
        match = WIND_VALUE.fullmatch(value) if isinstance(value, str) else None
        if match and float(match[1]) >= MINIMUM_WIND[match[2].casefold()]:
            return True
    return False
