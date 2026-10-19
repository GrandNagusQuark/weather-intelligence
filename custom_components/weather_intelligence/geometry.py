"""Pure geometry and location-relevance rules for official warning polygons."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .models import (
    GeometryRelationship,
    LocationAssessment,
    LocationFreshness,
    RelevanceResult,
    SubjectKind,
)

_EARTH_RADIUS_METERS = 6_371_008.8
_EPSILON = 1e-9


def evaluate_person_relevance(
    subject_id: str,
    assessment: LocationAssessment,
    geometry: Mapping[str, Any] | None,
) -> RelevanceResult:
    """Evaluate a person, including the exact reported GPS accuracy radius."""
    if assessment.freshness == LocationFreshness.DEGRADED:
        last_known_relationship, overlap = _evaluate_point_and_accuracy(
            assessment.last_known_fix, geometry
        )
        return RelevanceResult(
            subject_id,
            SubjectKind.PERSON,
            GeometryRelationship.UNKNOWN,
            assessment.freshness,
            overlap,
            "Personal location protection is degraded; the retained fix is not current.",
            last_known_relationship=last_known_relationship,
        )
    if assessment.freshness in {
        LocationFreshness.UNKNOWN,
        LocationFreshness.MISSING,
        LocationFreshness.INTENTIONALLY_UNAVAILABLE,
    }:
        return RelevanceResult(
            subject_id,
            SubjectKind.PERSON,
            GeometryRelationship.UNKNOWN,
            assessment.freshness,
            None,
            "A current or grace-period personal location is unavailable.",
        )
    fix = assessment.fix
    if fix is None or fix.latitude is None or fix.longitude is None:
        return RelevanceResult(
            subject_id,
            SubjectKind.PERSON,
            GeometryRelationship.UNKNOWN,
            assessment.freshness,
            None,
            "Personal coordinates are unavailable.",
        )
    relationship, overlaps = _evaluate_point_and_accuracy(fix, geometry)
    if relationship == GeometryRelationship.INSIDE:
        return RelevanceResult(
            subject_id,
            SubjectKind.PERSON,
            GeometryRelationship.INSIDE,
            assessment.freshness,
            False,
            "The reported point is inside official warning geometry.",
        )
    if relationship == GeometryRelationship.NO_GEOMETRY:
        return RelevanceResult(
            subject_id,
            SubjectKind.PERSON,
            relationship,
            assessment.freshness,
            None,
            "The official alert has no polygon geometry.",
        )
    if relationship == GeometryRelationship.UNKNOWN:
        return RelevanceResult(
            subject_id,
            SubjectKind.PERSON,
            GeometryRelationship.UNKNOWN,
            assessment.freshness,
            None,
            "An outside point lacks usable current accuracy, so fully outside is unconfirmed.",
        )
    return RelevanceResult(
        subject_id,
        SubjectKind.PERSON,
        GeometryRelationship.ACCURACY_OVERLAP if overlaps else GeometryRelationship.OUTSIDE,
        assessment.freshness,
        overlaps,
        (
            "The unmodified reported accuracy circle overlaps official warning geometry."
            if overlaps
            else "The reported point and accuracy circle are fully outside official geometry."
        ),
    )


def _evaluate_point_and_accuracy(
    fix: object | None, geometry: Mapping[str, Any] | None
) -> tuple[GeometryRelationship | None, bool | None]:
    if fix is None:
        return None, None
    latitude = getattr(fix, "latitude", None)
    longitude = getattr(fix, "longitude", None)
    if latitude is None or longitude is None:
        return None, None
    if not geometry:
        return GeometryRelationship.NO_GEOMETRY, None
    point = (longitude, latitude)
    if point_in_geometry(point, geometry):
        return GeometryRelationship.INSIDE, False
    accuracy = getattr(fix, "accuracy_meters", None)
    if accuracy is None or accuracy < 0:
        return GeometryRelationship.UNKNOWN, None
    overlaps = circle_overlaps_geometry(point, accuracy, geometry)
    return (
        GeometryRelationship.ACCURACY_OVERLAP if overlaps else GeometryRelationship.OUTSIDE,
        overlaps,
    )


def evaluate_home_relevance(
    subject_id: str,
    latitude: float | None,
    longitude: float | None,
    geometry: Mapping[str, Any] | None,
) -> RelevanceResult:
    """Evaluate a fixed home point without borrowing a phone accuracy radius."""
    if latitude is None or longitude is None:
        relationship = GeometryRelationship.UNKNOWN
        reason = "Designated-home coordinates are unavailable."
    elif not geometry:
        relationship = GeometryRelationship.NO_GEOMETRY
        reason = "The official alert has no polygon geometry."
    elif point_in_geometry((longitude, latitude), geometry):
        relationship = GeometryRelationship.INSIDE
        reason = "The designated home is inside official warning geometry."
    else:
        relationship = GeometryRelationship.OUTSIDE
        reason = "The designated home is outside official warning geometry."
    return RelevanceResult(
        subject_id,
        SubjectKind.DESIGNATED_HOME,
        relationship,
        LocationFreshness.FRESH,
        None,
        reason,
    )


def point_in_geometry(point: tuple[float, float], geometry: Mapping[str, Any]) -> bool:
    """Return whether a longitude/latitude point is included by Polygon/MultiPolygon."""
    return any(_point_in_polygon(point, polygon) for polygon in _polygons(geometry))


def circle_overlaps_geometry(
    point: tuple[float, float], radius_meters: float, geometry: Mapping[str, Any]
) -> bool:
    """Use the provided radius as-is; no project margin or multiplier is added."""
    if radius_meters < 0:
        return False
    if point_in_geometry(point, geometry):
        return True
    return any(
        _distance_to_ring_meters(point, ring) <= radius_meters
        for polygon in _polygons(geometry)
        for ring in polygon
    )


def distance_to_geometry_boundary(
    point: tuple[float, float], geometry: Mapping[str, Any]
) -> float:
    """Nearest exterior or hole edge in metres, using the shared local projection."""
    return min((_distance_to_ring_meters(point, ring)
                for polygon in _polygons(geometry) for ring in polygon), default=math.inf)


def _polygons(geometry: Mapping[str, Any]) -> Iterable[Sequence[Sequence[Sequence[float]]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, Sequence):
        yield coordinates
    elif geometry_type == "MultiPolygon" and isinstance(coordinates, Sequence):
        yield from coordinates


def _point_in_polygon(
    point: tuple[float, float], polygon: Sequence[Sequence[Sequence[float]]]
) -> bool:
    if not polygon or not _point_in_ring(point, polygon[0]):
        return False
    return not any(_point_in_ring(point, hole) for hole in polygon[1:])


def _point_in_ring(point: tuple[float, float], ring: Sequence[Sequence[float]]) -> bool:
    x, y = point
    inside = False
    if len(ring) < 3:
        return False
    previous = ring[-1]
    for current in ring:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if _point_on_segment(x, y, x1, y1, x2, y2):
            return True
        crosses = (y1 > y) != (y2 > y)
        if crosses and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def _point_on_segment(
    x: float, y: float, x1: float, y1: float, x2: float, y2: float
) -> bool:
    length_squared = (x2 - x1) ** 2 + (y2 - y1) ** 2
    if length_squared <= _EPSILON:
        return math.hypot(x - x1, y - y1) <= _EPSILON
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > _EPSILON:
        return False
    dot = (x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)
    return -_EPSILON <= dot <= length_squared + _EPSILON


def _distance_to_ring_meters(
    point: tuple[float, float], ring: Sequence[Sequence[float]]
) -> float:
    if len(ring) < 2:
        return math.inf
    projected = [_project_meters(point, (float(item[0]), float(item[1]))) for item in ring]
    minimum = math.inf
    previous = projected[-1]
    for current in projected:
        minimum = min(minimum, _distance_to_segment((0.0, 0.0), previous, current))
        previous = current
    return minimum


def _project_meters(
    origin: tuple[float, float], target: tuple[float, float]
) -> tuple[float, float]:
    origin_lon, origin_lat = map(math.radians, origin)
    target_lon, target_lat = map(math.radians, target)
    x = (target_lon - origin_lon) * math.cos((origin_lat + target_lat) / 2)
    y = target_lat - origin_lat
    return x * _EARTH_RADIUS_METERS, y * _EARTH_RADIUS_METERS


def _distance_to_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    fraction = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)))
    closest = (sx + fraction * dx, sy + fraction * dy)
    return math.hypot(px - closest[0], py - closest[1])
