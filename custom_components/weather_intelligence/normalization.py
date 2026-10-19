"""Normalize NWS GeoJSON features without discarding the official record."""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .models import OfficialAlert

_VTEC_PATTERN = re.compile(
    r"/O\.(?P<action>[A-Z]{3})\.(?P<office>[A-Z0-9]{4})\."
    r"(?P<phenomena>[A-Z]{2})\.(?P<significance>[A-Z])\."
    r"(?P<event_tracking_number>\d{4})\."
)


class AlertNormalizationError(ValueError):
    """Raised when a feature cannot be identified safely."""


def parse_nws_feature(feature: Mapping[str, Any], received_at: datetime) -> OfficialAlert:
    """Create the minimum stable internal alert record from an NWS feature."""
    properties = _mapping(feature.get("properties"))
    official_id = str(properties.get("id") or feature.get("id") or "").strip()
    if not official_id:
        raise AlertNormalizationError("NWS feature has no official message identifier")

    event = str(properties.get("event") or "Unknown NWS alert").strip()
    parameters = _mapping(properties.get("parameters"))
    vtec_lines = _string_values(parameters.get("VTEC"))
    vtec_match = next(
        (match for value in vtec_lines if (match := _VTEC_PATTERN.search(value))),
        None,
    )
    references = _reference_ids(properties.get("references"))

    if vtec_match:
        incident_key = "nws:{office}:{phenomena}:{significance}:{event}".format(
            office=vtec_match.group("office"),
            phenomena=vtec_match.group("phenomena"),
            significance=vtec_match.group("significance"),
            event=vtec_match.group("event_tracking_number"),
        )
        vtec_action = vtec_match.group("action")
    elif references:
        incident_key = f"nws-reference:{references[0]}"
        vtec_action = None
    else:
        incident_key = f"nws-message:{official_id}"
        vtec_action = None

    raw_geometry = feature.get("geometry")
    geometry = copy.deepcopy(raw_geometry) if isinstance(raw_geometry, Mapping) else None

    return OfficialAlert(
        source="NWS",
        official_message_id=official_id,
        incident_key=incident_key,
        sender=_optional_string(properties.get("sender")),
        event=event,
        message_type=str(properties.get("messageType") or "Alert"),
        status=str(properties.get("status") or "Actual"),
        category=_optional_string(properties.get("category")),
        sent_at=_parse_datetime(properties.get("sent")),
        effective_at=_parse_datetime(properties.get("effective")),
        onset_at=_parse_datetime(properties.get("onset")),
        expires_at=_parse_datetime(properties.get("expires")),
        ends_at=_parse_datetime(properties.get("ends")),
        severity=_optional_string(properties.get("severity")),
        urgency=_optional_string(properties.get("urgency")),
        certainty=_optional_string(properties.get("certainty")),
        headline=_optional_string(properties.get("headline")),
        description=_optional_string(properties.get("description")),
        instruction=_optional_string(properties.get("instruction")),
        area_description=_optional_string(properties.get("areaDesc")),
        geometry=geometry,
        affected_zones=_string_values(properties.get("affectedZones")),
        tornado_detection=_first_parameter(parameters, "tornadoDetection"),
        tornado_damage_threat=_first_parameter(parameters, "tornadoDamageThreat"),
        thunderstorm_damage_threat=_first_parameter(parameters, "thunderstormDamageThreat"),
        flash_flood_damage_threat=_first_parameter(parameters, "flashFloodDamageThreat"),
        vtec_action=vtec_action,
        replaced_message_ids=references,
        received_at=_as_utc(received_at),
        raw_official_payload=copy.deepcopy(dict(feature)),
    )


def parse_feature_collection(
    payload: Mapping[str, Any], received_at: datetime
) -> list[OfficialAlert]:
    """Normalize all identifiable features in an NWS FeatureCollection."""
    features = payload.get("features")
    if not isinstance(features, list):
        raise AlertNormalizationError("NWS response does not contain a features list")
    return [parse_nws_feature(_mapping(feature), received_at) for feature in features]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        return tuple(str(item) for item in value)
    return ()


def _first_parameter(parameters: Mapping[str, Any], key: str) -> str | None:
    values = _string_values(parameters.get(key))
    return values[0] if values else None


def _reference_ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(
            part.split(",")[1].strip()
            for part in value.split()
            if len(part.split(",")) >= 2
        )
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for reference in value:
        if isinstance(reference, Mapping):
            identifier = reference.get("identifier")
            if identifier:
                result.append(str(identifier))
        elif reference:
            result.append(str(reference))
    return tuple(result)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError as error:
        raise AlertNormalizationError(f"Invalid official timestamp: {value}") from error


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise AlertNormalizationError("Timestamps must include a time zone")
    return value.astimezone(timezone.utc)
