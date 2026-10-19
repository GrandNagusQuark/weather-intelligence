"""Water-fix uncertainty helpers and a legacy static-map test reader.

The runtime uses regional public geometry instead of bundling the old world map.
This module itself never logs, persists or sends device locations.
"""

from __future__ import annotations

import math
import sqlite3
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .models import LocationFix

MAX_FIX_AGE = timedelta(minutes=5)
MAX_ACCURACY_METERS = 1000.0
# A conservative ambiguity band, not a guaranteed bound on historical map errors.
SHORELINE_GUARD_METERS = 500.0
NEAR_WATER_METERS = 804.672  # Half a statute mile; notification relevance, not boating detection.
_EDGE = struct.Struct(">7i")
_MICRO = 1_000_000


@dataclass(frozen=True)
class WaterAssessment:
    on_water: bool | None
    reason: str
    observed_at: datetime | None = None
    near_water: bool | None = None
    water_id: str | None = None
    water_name: str | None = None


class LocalWaterMask:
    """Read-only compressed latitude strips; no HA dependencies or downloads."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = (path or Path(__file__).parent / "data/water-mask.sqlite").resolve()

    @lru_cache(maxsize=6)
    def _strip(self, latitude: int) -> bytes:
        with sqlite3.connect(self._path.as_uri() + "?mode=ro", uri=True) as database:
            version = database.execute("SELECT value FROM metadata WHERE key='format'").fetchone()
            if version != ("wi-water-strips-1",):
                raise ValueError("Unsupported local shoreline index")
            row = database.execute(
                "SELECT edges FROM strips WHERE latitude=?", (latitude,)
            ).fetchone()
            if row is None:
                raise ValueError("Incomplete local shoreline index")
        raw = zlib.decompress(row[0])
        if len(raw) % _EDGE.size:
            raise ValueError("Invalid local shoreline index")
        return raw

    def classify_point(
        self, latitude: float, longitude: float, accuracy: float
    ) -> tuple[bool | None, str]:
        """Highest containing shoreline level: land/lake/island/pond = 1/2/3/4."""
        on_water, reason, _near_water = self._classify_point(latitude, longitude, accuracy)
        return on_water, reason

    def _classify_point(
        self, latitude: float, longitude: float, accuracy: float
    ) -> tuple[bool | None, str, bool | None]:
        """Keep surface classification separate from mapped-shoreline proximity."""
        if abs(latitude) >= 80:
            return None, "outside_supported_latitudes", None
        lat = latitude * _MICRO
        lon = longitude * _MICRO
        margin = SHORELINE_GUARD_METERS + accuracy
        search_margin = max(margin, NEAR_WATER_METERS + accuracy)
        lat_margin = search_margin / 111_195.0
        cos_lat = math.cos(math.radians(latitude))
        lon_margin = lat_margin / cos_lat
        inside: dict[int, tuple[bool, int]] = {}
        nearest_shoreline = math.inf
        primary = math.floor(latitude)
        try:
            for strip in range(
                max(-80, math.floor(latitude - lat_margin)),
                min(79, math.floor(latitude + lat_margin)) + 1,
            ):
                for ident, level, west, x1, y1, x2, y2 in _EDGE.iter_unpack(self._strip(strip)):
                    point_x = lon + 360 * _MICRO if lon < west else lon
                    if strip == primary and ((y1 > lat) != (y2 > lat)):
                        crossing_x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
                        if point_x < crossing_x:
                            previous = inside.get(ident, (False, level))[0]
                            inside[ident] = (not previous, level)
                    # Reject far-away segments cheaply before the local distance.
                    if (
                        max(y1, y2) < lat - lat_margin * _MICRO
                        or min(y1, y2) > lat + lat_margin * _MICRO
                        or max(x1, x2) < point_x - lon_margin * _MICRO
                        or min(x1, x2) > point_x + lon_margin * _MICRO
                    ):
                        continue
                    ax, ay = (
                        (x1 - point_x) / _MICRO * 111_195.0 * cos_lat,
                        (y1 - lat) / _MICRO * 111_195.0,
                    )
                    bx, by = (
                        (x2 - point_x) / _MICRO * 111_195.0 * cos_lat,
                        (y2 - lat) / _MICRO * 111_195.0,
                    )
                    dx, dy = bx - ax, by - ay
                    t = (
                        max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
                        if dx or dy
                        else 0.0
                    )
                    nearest_shoreline = min(nearest_shoreline, math.hypot(ax + t * dx, ay + t * dy))
        except (OSError, sqlite3.Error, ValueError, zlib.error):
            return None, "shoreline_data_unavailable", None
        # Do not round a GPS circle straddling the half-mile cutoff into eligibility.
        near_water = (
            True
            if nearest_shoreline + accuracy <= NEAR_WATER_METERS
            else None
            if nearest_shoreline - accuracy <= NEAR_WATER_METERS
            else False
        )
        if nearest_shoreline <= margin:
            return None, "shoreline_or_accuracy_overlap", near_water
        level = max((level for contained, level in inside.values() if contained), default=0)
        return level % 2 == 0, "mapped_water" if level % 2 == 0 else "mapped_land", near_water

    def assess(self, fix: LocationFix | None, now: datetime) -> WaterAssessment:
        reason = invalid_water_fix(fix, now)
        if reason:
            return WaterAssessment(None, reason, fix.observed_at if fix else None)
        assert (
            fix is not None
            and fix.latitude is not None
            and fix.longitude is not None
            and fix.accuracy_meters is not None
        )
        on_water, reason, near_water = self._classify_point(
            fix.latitude, fix.longitude, fix.accuracy_meters
        )
        return WaterAssessment(on_water, reason, fix.observed_at, near_water)


def invalid_water_fix(fix: LocationFix | None, now: datetime) -> str | None:
    if (
        fix is None
        or fix.intentionally_unavailable
        or fix.latitude is None
        or fix.longitude is None
    ):
        return "location_unavailable"
    if not (
        math.isfinite(fix.latitude)
        and math.isfinite(fix.longitude)
        and -90 <= fix.latitude <= 90
        and -180 <= fix.longitude <= 180
    ):
        return "invalid_location"
    if fix.reported_stale or fix.observed_at is None or fix.observed_at.tzinfo is None:
        return "location_stale_or_missing"
    age = now - fix.observed_at
    if age > MAX_FIX_AGE or age < timedelta(seconds=-30):
        return "location_stale_or_missing"
    if (
        fix.accuracy_meters is None
        or not math.isfinite(fix.accuracy_meters)
        or not 0 <= fix.accuracy_meters <= MAX_ACCURACY_METERS
    ):
        return "accuracy_unavailable_or_poor"
    return None


def current_water_state(
    assessment: WaterAssessment | None, now: datetime | None = None
) -> bool | None:
    """An in-memory result must expire even if weather polling stops updating."""
    return _current_assessment_value(assessment, "on_water", now)


def current_near_water_state(
    assessment: WaterAssessment | None, now: datetime | None = None
) -> bool | None:
    """Proximity expires just like surface classification, without relabeling land."""
    return _current_assessment_value(assessment, "near_water", now)


def _current_assessment_value(
    assessment: WaterAssessment | None, field: str, now: datetime | None
) -> bool | None:
    now = now or datetime.now(timezone.utc)
    if (
        assessment is None
        or assessment.observed_at is None
        or assessment.observed_at.tzinfo is None
    ):
        return None
    age = now - assessment.observed_at
    return getattr(assessment, field) if timedelta(seconds=-30) <= age <= MAX_FIX_AGE else None
