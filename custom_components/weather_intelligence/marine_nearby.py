"""Nearby-water weather relevance, distinct from official location coverage."""

from datetime import datetime
from typing import Any

from .geometry import circle_overlaps_geometry
from .hazard_policy import classify_alert, family_enabled
from .models import HouseholdProfile, LocationFix, OfficialAlert
from .regional_water import water_cell
from .water_detection import WaterAssessment, current_water_state, invalid_water_fix

METERS_PER_MILE = 1609.344
MAX_TOPOLOGY_PAIRS = 100_000


def _polygon_parts(geometry: Any) -> list:
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    return []


def relevant_water_parts(
    point: tuple[float, float], water_id: str, bodies: list[dict], channels: list[dict]
) -> list:
    """A charted continuous channel can connect water parts for heads-ups only.

    Missing chart coverage never implies an open route. Separate components of
    a multipolygon are not joined merely because they share a name or ID.
    """
    from shapely.geometry import Point, shape
    from shapely.ops import unary_union

    waters = []
    for body in bodies:
        geometry = shape(body["geometry"])
        if not geometry.is_valid:
            continue
        waters.extend((body["id"], part) for part in _polygon_parts(geometry))
    seeds = {
        index
        for index, (identifier, part) in enumerate(waters)
        if identifier == water_id and part.covers(Point(point))
    }
    if len(seeds) != 1:
        return []
    charted = [
        part
        for item in channels
        if item["id"].startswith("usace_ncf:")
        for part in _polygon_parts(shape(item["geometry"]))
        if part.is_valid
    ]
    if not charted:
        return [waters[next(iter(seeds))][1]]
    network = _polygon_parts(unary_union(charted))
    if len(network) * len(waters) > MAX_TOPOLOGY_PAIRS:
        return [waters[next(iter(seeds))][1]]
    groups = [
        {
            index
            for index, (_identifier, water) in enumerate(waters)
            if channel.intersection(water).area > 0
        }
        for channel in network
    ]
    reachable = set(seeds)
    changed = True
    while changed:
        previous = len(reachable)
        for group in groups:
            if reachable.intersection(group):
                reachable.update(group)
        changed = len(reachable) != previous
    return [waters[index][1] for index in sorted(reachable)]


def nearby_alert_matches(
    profile: HouseholdProfile,
    fix: LocationFix | None,
    assessment: WaterAssessment | None,
    alerts: tuple[OfficialAlert, ...],
    bodies: list[dict] | None,
    channels: list[dict] | None,
    now: datetime,
) -> list[OfficialAlert]:
    """A positive match never means the user is inside the official warning."""
    if (
        not profile.marine_nearby_enabled
        or not profile.receive_personal_alerts
        or invalid_water_fix(fix, now)
        or current_water_state(assessment, now) is not True
        or assessment is None
        or not assessment.water_id
        or not bodies
    ):
        return []
    assert fix is not None and fix.accuracy_meters is not None
    if assessment.observed_at != fix.observed_at or water_cell(fix.latitude, fix.longitude) is None:
        return []
    point = (fix.longitude, fix.latitude)
    candidates = []
    for alert in alerts:
        end = alert.ends_at or alert.expires_at
        if (
            alert.status.casefold() != "actual"
            or alert.message_type.casefold() not in {"alert", "update"}
            or end is None
            or end <= now
            or (alert.effective_at and alert.effective_at > now)
            or not alert.geometry
            or not classify_alert(alert).automatic
            or not family_enabled(profile, classify_alert(alert), alert.event)
        ):
            continue
        try:
            # Leave point/accuracy-overlap cases entirely to the official router.
            if circle_overlaps_geometry(point, fix.accuracy_meters, alert.geometry):
                continue
            if circle_overlaps_geometry(
                point, profile.marine_nearby_miles * METERS_PER_MILE, alert.geometry
            ):
                candidates.append(alert)
        except (IndexError, KeyError, TypeError, ValueError):
            continue  # Malformed optional geometry must not interrupt direct alerts.
    if not candidates:
        return []
    try:
        from shapely.geometry import mapping, shape
        from shapely.errors import GEOSException
    except ImportError:
        return []

    try:
        waters = relevant_water_parts(point, assessment.water_id, bodies, channels or [])
        result = []
        for alert in candidates:
            warning = shape(alert.geometry)
            if not warning.is_valid:
                continue
            for water in waters:
                footprint = water.intersection(warning)
                # Distance is to warned water, not the centroid or an unrelated
                # landward part of the warning polygon.
                if any(
                    circle_overlaps_geometry(
                        point, profile.marine_nearby_miles * METERS_PER_MILE, mapping(part)
                    )
                    for part in _polygon_parts(footprint)
                ):
                    result.append(alert)
                    break
        return result
    except (KeyError, TypeError, ValueError, GEOSException):
        return []
