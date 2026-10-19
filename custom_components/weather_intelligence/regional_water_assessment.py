"""Assess cached mapped water independently of boating or vehicle evidence."""

from datetime import datetime

from .geometry import distance_to_geometry_boundary, point_in_geometry
from .models import LocationFix
from .regional_water import RegionalWaterCache, water_cell
from .water_detection import NEAR_WATER_METERS, WaterAssessment, invalid_water_fix

# Covers provider generalization/rounding, not a claimed bound on survey age/error.
REGIONAL_SHORE_GUARD_METERS = 50.0


def assess_regional_water(
    cache: RegionalWaterCache, fix: LocationFix | None, now: datetime
) -> WaterAssessment:
    reason = invalid_water_fix(fix, now)
    if reason:
        return WaterAssessment(None, reason, fix.observed_at if fix else None)
    assert fix is not None and fix.accuracy_meters is not None
    cell = water_cell(fix.latitude, fix.longitude)
    bodies = cache.bodies(cell, now) if cell is not None else None
    if bodies is None:
        return WaterAssessment(None, "regional_water_unavailable", fix.observed_at)
    point = (fix.longitude, fix.latitude)
    distances = [(body, distance_to_geometry_boundary(point, body["geometry"])) for body in bodies]
    nearest = min((distance for _body, distance in distances), default=float("inf"))
    near = (
        True
        if nearest + fix.accuracy_meters <= NEAR_WATER_METERS
        else None
        if nearest - fix.accuracy_meters <= NEAR_WATER_METERS
        else False
    )
    containing = [
        (body, distance)
        for body, distance in distances
        if point_in_geometry(point, body["geometry"])
    ]
    if nearest <= fix.accuracy_meters + REGIONAL_SHORE_GUARD_METERS:
        return WaterAssessment(
            None, "regional_shoreline_or_accuracy_overlap", fix.observed_at, near
        )
    if not containing:
        # No mapped polygon is not proof of no water. Missing map coverage cannot
        # confirm road travel or automatically disable future boating controls.
        return WaterAssessment(None, "no_regional_water_mapped", fix.observed_at, near)
    unique = containing[0][0] if len(containing) == 1 else None
    return WaterAssessment(
        True,
        "regional_mapped_water",
        fix.observed_at,
        near,
        unique["id"] if unique else None,
        unique["name"] if unique else None,
    )
