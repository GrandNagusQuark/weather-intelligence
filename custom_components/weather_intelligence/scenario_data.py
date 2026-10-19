"""Sanitized NWS-shaped records used only by explicit manual review scenarios."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [-97.6, 35.4],
        [-97.4, 35.4],
        [-97.4, 35.6],
        [-97.6, 35.6],
        [-97.6, 35.4],
    ]],
}

_FEATURES = (
    {
        "id": "urn:oid:sanitized-review-initial",
        "type": "Feature",
        "geometry": _POLYGON,
        "properties": {
            "id": "urn:oid:sanitized-review-initial",
            "sent": "2026-05-20T17:00:00+00:00",
            "effective": "2026-05-20T17:00:00+00:00",
            "onset": "2026-05-20T17:00:00+00:00",
            "expires": "2026-05-20T18:00:00+00:00",
            "ends": "2026-05-20T18:00:00+00:00",
            "status": "Actual",
            "messageType": "Alert",
            "category": "Met",
            "severity": "Extreme",
            "certainty": "Likely",
            "urgency": "Immediate",
            "event": "Tornado Warning",
            "instruction": "TAKE COVER NOW! Move to a basement or interior room.",
            "parameters": {
                "VTEC": ["/O.NEW.KOUN.TO.W.0123.260520T1700Z-260520T1800Z/"],
                "tornadoDetection": ["RADAR INDICATED"],
                "tornadoDamageThreat": ["CONSIDERABLE"],
            },
        },
    },
    {
        "id": "urn:oid:sanitized-review-update",
        "type": "Feature",
        "geometry": _POLYGON,
        "properties": {
            "id": "urn:oid:sanitized-review-update",
            "sent": "2026-05-20T17:25:00+00:00",
            "effective": "2026-05-20T17:25:00+00:00",
            "onset": "2026-05-20T17:25:00+00:00",
            "expires": "2026-05-20T18:30:00+00:00",
            "ends": "2026-05-20T18:30:00+00:00",
            "status": "Actual",
            "messageType": "Update",
            "category": "Met",
            "severity": "Extreme",
            "certainty": "Observed",
            "urgency": "Immediate",
            "event": "Tornado Warning",
            "instruction": "TAKE COVER NOW! Move to a basement or interior room.",
            "references": [{"identifier": "urn:oid:sanitized-review-initial"}],
            "parameters": {
                "VTEC": ["/O.CON.KOUN.TO.W.0123.260520T1700Z-260520T1830Z/"],
                "tornadoDetection": ["OBSERVED"],
                "tornadoDamageThreat": ["CONSIDERABLE"],
            },
        },
    },
    {
        "id": "urn:oid:sanitized-review-cancel",
        "type": "Feature",
        "geometry": None,
        "properties": {
            "id": "urn:oid:sanitized-review-cancel",
            "sent": "2026-05-20T17:40:00+00:00",
            "effective": "2026-05-20T17:40:00+00:00",
            "expires": "2026-05-20T17:40:00+00:00",
            "ends": "2026-05-20T17:40:00+00:00",
            "status": "Actual",
            "messageType": "Cancel",
            "category": "Met",
            "severity": "Extreme",
            "certainty": "Observed",
            "urgency": "Immediate",
            "event": "Tornado Warning",
            "references": [{"identifier": "urn:oid:sanitized-review-update"}],
            "parameters": {
                "VTEC": ["/O.CAN.KOUN.TO.W.0123.000000T0000Z-260520T1740Z/"],
                "tornadoDetection": ["OBSERVED"],
                "tornadoDamageThreat": ["CONSIDERABLE"],
            },
        },
    },
)


def tornado_scenario_features() -> tuple[dict[str, Any], ...]:
    """Return a private copy so one scenario cannot mutate another."""
    return deepcopy(_FEATURES)
