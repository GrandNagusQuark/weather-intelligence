"""Match home coordinates locally to public avalanche forecast regions.

Forecast coverage is a regional relevance signal, not a property-level hazard
assessment. Daily danger ratings are deliberately neither retained nor used.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from http.client import HTTPException
from typing import Any, Mapping
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .const import DOMAIN
from .geometry import point_in_geometry

AVALANCHE_REGION_URL = "https://api.avalanche.org/v2/public/products/map-layer"
AVALANCHE_REGION_CACHE_KEY = "avalanche_regions"
REFRESH_SECONDS = 24 * 60 * 60
MAX_CACHE_AGE_SECONDS = 7 * REFRESH_SECONDS
RETRY_SECONDS = 60 * 60
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Any, file: Any, code: int, message: str, headers: Any, url: str) -> None:
        return None


def valid_home_point(latitude: Any, longitude: Any) -> bool:
    return (type(latitude) in {int, float} and type(longitude) in {int, float}
            and math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180)


def _validated_geometry(geometry: Any) -> dict[str, Any] | None:
    if not isinstance(geometry, Mapping):
        return None
    geometry_type, coordinates = geometry.get("type"), geometry.get("coordinates")
    if geometry_type not in {"Polygon", "MultiPolygon"} or not isinstance(coordinates, list) or not coordinates:
        return None
    polygons = [coordinates] if geometry_type == "Polygon" else coordinates
    normalized_polygons = []
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            return None
        normalized_rings = []
        for ring_index, ring in enumerate(polygon):
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                return None
            for point in ring:
                if not isinstance(point, list) or len(point) < 2 or not valid_home_point(point[1], point[0]):
                    return None
            # The shared geometry engine uses planar longitude/latitude rings.
            # Reject dateline-spanning rings rather than guessing their interior.
            if any(abs(first[0] - second[0]) > 180 for first, second in zip(ring, ring[1:])):
                return None
            area = sum(first[0] * second[1] - second[0] * first[1] for first, second in zip(ring, ring[1:]))
            if abs(area) <= 1e-12:
                # Some published GIS shapes contain zero-area islands/holes.
                # They add no coverage, but need not invalidate valid islands.
                if ring_index == 0:
                    break
                continue
            normalized_rings.append(ring)
        if normalized_rings:
            normalized_polygons.append(normalized_rings)
    if not normalized_polygons:
        return None
    return {"type": geometry_type, "coordinates": normalized_polygons[0] if geometry_type == "Polygon" else normalized_polygons}


def parse_regions(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise ValueError("Invalid avalanche region collection")
    features = payload.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 2000:
        raise ValueError("Missing avalanche regions")
    regions = []
    for feature in features:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            continue
        geometry = _validated_geometry(feature.get("geometry"))
        properties = feature.get("properties")
        if geometry is None or not isinstance(properties, Mapping):
            continue
        name, center = properties.get("name"), properties.get("center")
        if not isinstance(name, str) or not name.strip() or not isinstance(center, str) or not center.strip():
            continue
        regions.append({"name": name[:200], "center": center[:200], "geometry": geometry})
    if not regions:
        raise ValueError("No usable avalanche region boundaries")
    return regions


def fetch_region_boundaries() -> list[dict[str, Any]]:
    """Fetch the same nationwide URL for every installation; no user data."""
    request = Request(AVALANCHE_REGION_URL, headers={
        "Accept": "application/geo+json, application/json",
        "User-Agent": "WeatherIntelligence/0.11 (regional onboarding defaults)",
    })
    with build_opener(_NoRedirect).open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        if response.geturl() != AVALANCHE_REGION_URL:
            raise ValueError("Unexpected avalanche feed redirect")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Avalanche region response exceeds size limit")
    return parse_regions(json.loads(body))


class AvalancheRegionLookup:
    """Cache public geometry only, never homes, identities or danger ratings."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._lock = asyncio.Lock()
        self._loaded = False
        self._regions: list[dict[str, Any]] = []
        self._fetched_at = 0.0
        self._next_attempt_at = 0.0

    async def async_refresh(self, executor: Any) -> None:
        async with self._lock:
            now = time.time()
            if not self._loaded:
                self._loaded = True
                try:
                    cached = await self._store.async_load()
                    if isinstance(cached, Mapping) and cached.get("source") == AVALANCHE_REGION_URL:
                        fetched_at = cached.get("fetched_at")
                        if type(fetched_at) in {int, float} and math.isfinite(fetched_at) and 0 <= now - fetched_at <= MAX_CACHE_AGE_SECONDS:
                            regions = cached.get("regions")
                            features = [{"type": "Feature", "properties": region, "geometry": region.get("geometry")}
                                        for region in regions if isinstance(region, Mapping)] if isinstance(regions, list) else []
                            self._regions = parse_regions({"type": "FeatureCollection", "features": features})
                            self._fetched_at = fetched_at
                            self._next_attempt_at = fetched_at + REFRESH_SECONDS
                except (OSError, ValueError, TypeError):
                    pass
            if now < self._next_attempt_at:
                return
            self._next_attempt_at = now + RETRY_SECONDS
            try:
                regions = await executor(fetch_region_boundaries)
            except (OSError, ValueError, TimeoutError, HTTPException):
                return
            self._regions = regions
            self._fetched_at = now
            self._next_attempt_at = now + REFRESH_SECONDS
            try:
                await self._store.async_save({"source": AVALANCHE_REGION_URL, "fetched_at": now, "regions": regions})
            except OSError:
                pass  # A read-only/full disk must not block onboarding.

    def home_in_region(self, latitude: Any, longitude: Any) -> bool | None:
        if not valid_home_point(latitude, longitude) or not 0 <= time.time() - self._fetched_at <= MAX_CACHE_AGE_SECONDS:
            return None
        # Edge matches are uncertain at this map's resolution. Tiny offsets
        # reject exact boundary points without expanding any forecast region.
        offset = 1e-5
        points = ((longitude, latitude), (longitude - offset, latitude),
                  (longitude + offset, latitude), (longitude, latitude - offset),
                  (longitude, latitude + offset))
        for region in self._regions:
            if all(point_in_geometry(point, region["geometry"]) for point in points):
                return True
        return None  # Unmapped does not mean avalanche-free.


async def async_prepare_avalanche_regions(hass: Any, state: Mapping[str, Any]) -> None:
    """Load on DND review, not on the safety-polling or alert-delivery path."""
    if state.get("stage") not in {"alert_dnd", "dnd_options", "dnd_customize", "dnd_confirm", "daily_outlook", "notification_setup"}:
        return
    config = getattr(hass, "config", None)
    if not valid_home_point(getattr(config, "latitude", None), getattr(config, "longitude", None)):
        return
    executor = getattr(hass, "async_add_executor_job", None)
    if not callable(executor):
        return
    domain_data = hass.data.setdefault(DOMAIN, {})
    lookup = domain_data.get(AVALANCHE_REGION_CACHE_KEY)
    if lookup is None:
        from homeassistant.helpers.storage import Store
        lookup = AvalancheRegionLookup(Store(hass, 1, f"{DOMAIN}.avalanche_regions"))
        domain_data[AVALANCHE_REGION_CACHE_KEY] = lookup
    await lookup.async_refresh(executor)


def home_avalanche_region(hass: Any) -> bool | None:
    lookup = getattr(hass, "data", {}).get(DOMAIN, {}).get(AVALANCHE_REGION_CACHE_KEY)
    config = getattr(hass, "config", None)
    if not isinstance(lookup, AvalancheRegionLookup):
        return None
    return lookup.home_in_region(getattr(config, "latitude", None), getattr(config, "longitude", None))
