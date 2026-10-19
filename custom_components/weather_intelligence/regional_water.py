"""Bounded regional USGS water geometry; cached public maps, never location fixes.

This adapter does not establish boating, bridge use or navigable connections.
Requests identify a coarse map cell, not a person or exact GPS point. Callers
must opt in before scheduling downloads, and must not await them on alert delivery.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

WATERBODY_URL = (
    "https://3dhp.nationalmap.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer/60/query"
)
CELL_DEGREES = 0.25
MAX_RESPONSE_BYTES = 8_000_000
MAX_CACHE_BYTES = 24_000_000
MAX_CELLS = 6
MAX_FEATURES = 2500
MAX_VERTICES = 150_000
CACHE_MAX_AGE = timedelta(days=7)
RETRY_DELAY = timedelta(hours=1)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise ValueError("Unexpected regional water redirect")


def water_cell(latitude: float, longitude: float) -> tuple[int, int] | None:
    """Return a coarse grid identity only; no exact coordinate is retained."""
    if any(
        isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)
        for value in (latitude, longitude)
    ):
        return None
    if not -80 < latitude < 80 or not -180 <= longitude < 180:
        return None
    return math.floor(latitude / CELL_DEGREES), math.floor(longitude / CELL_DEGREES)


def cell_query(cell: tuple[int, int]) -> dict[str, str]:
    if (
        len(cell) != 2
        or any(type(value) is not int for value in cell)
        or not -320 <= cell[0] < 320
        or not -720 <= cell[1] < 720
    ):
        raise ValueError("Invalid regional water cell")
    south, west = (value * CELL_DEGREES for value in cell)
    # Padding covers the near-shore shortcut even at a cell boundary. Whole
    # intersecting features are returned; clipped pieces must not become shores.
    padding = 0.025
    longitude_padding = padding / math.cos(math.radians(max(abs(south), abs(south + CELL_DEGREES))))
    bounds = {
        "xmin": max(-180, west - longitude_padding),
        "ymin": max(-80, south - padding),
        "xmax": min(180, west + CELL_DEGREES + longitude_padding),
        "ymax": min(80, south + CELL_DEGREES + padding),
        "spatialReference": {"wkid": 4326},
    }
    return {
        "f": "geojson",
        "where": "featuretype IN (1,2,3,4)",
        "geometry": json.dumps(bounds, separators=(",", ":")),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "outFields": "id3dhp,gnisidlabel,featuretype,featuredate",
        "returnZ": "false",
        "geometryPrecision": "5",
        "maxAllowableOffset": "0.00005",
        "resultRecordCount": str(MAX_FEATURES),
    }


def parse_public_polygons(
    payload: Any, *, id_field: str, name_field: str, prefix: str, type_field: str | None = None
) -> list[dict]:
    """Reject truncated or malformed collections instead of implying full coverage."""
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or payload.get("exceededTransferLimit")
        or not isinstance(payload.get("features"), list)
        or len(payload["features"]) >= MAX_FEATURES
    ):
        raise ValueError("Incomplete regional water collection")
    result, seen, vertices = [], set(), 0
    for feature in payload["features"]:
        if not isinstance(feature, dict):
            raise ValueError("Invalid regional water feature")
        properties, geometry = feature.get("properties"), feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise ValueError("Missing regional water geometry")
        identifier = properties.get(id_field)
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 100
            or identifier in seen
            or (type_field is not None and properties.get(type_field) not in {1, 2, 3, 4})
        ):
            raise ValueError("Invalid regional water identity")
        coordinates = geometry.get("coordinates")
        if geometry.get("type") == "Polygon":
            polygons = [coordinates]
        elif geometry.get("type") == "MultiPolygon":
            polygons = coordinates
        else:
            raise ValueError("Unsupported regional water geometry")
        if not isinstance(polygons, list) or not polygons:
            raise ValueError("Empty regional water geometry")
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("Empty regional water polygon")
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Unclosed regional water ring")
                vertices += len(ring)
                if vertices > MAX_VERTICES:
                    raise ValueError("Regional water geometry exceeds budget")
                for point in ring:
                    if (
                        not isinstance(point, list)
                        or len(point) != 2
                        or any(
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not math.isfinite(value)
                            for value in point
                        )
                        or not -180 <= point[0] <= 180
                        or not -90 <= point[1] <= 90
                    ):
                        raise ValueError("Invalid regional water coordinate")
                if any(abs(first[0] - second[0]) > 180 for first, second in zip(ring, ring[1:])):
                    raise ValueError("Dateline water geometry needs a supported split")
                area = sum(
                    first[0] * second[1] - second[0] * first[1]
                    for first, second in zip(ring, ring[1:])
                )
                if abs(area) < 1e-12:
                    raise ValueError("Degenerate regional water ring")
        seen.add(identifier)
        name = properties.get(name_field)
        result.append(
            {
                "id": prefix + identifier,
                "name": name[:160] if isinstance(name, str) else "Mapped water",
                "feature_type": properties.get(type_field) if type_field else None,
                "geometry": geometry,
            }
        )
    return result


def parse_waterbodies(payload: Any) -> list[dict]:
    return parse_public_polygons(
        payload,
        id_field="id3dhp",
        name_field="gnisidlabel",
        prefix="usgs3dhp:",
        type_field="featuretype",
    )


def fetch_water_cell(cell: tuple[int, int]) -> list[dict]:
    """Download public geometry with a fixed host, bounded body and no redirect."""
    url = WATERBODY_URL + "?" + urlencode(cell_query(cell))
    request = Request(
        url,
        headers={
            "Accept": "application/geo+json, application/json",
            "User-Agent": "WeatherIntelligence (regional water map beta)",
        },
    )
    with build_opener(_NoRedirect).open(request, timeout=12) as response:
        if response.geturl() != url:
            raise ValueError("Unexpected regional water response URL")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Regional water response exceeds budget")
    return parse_waterbodies(json.loads(body))


class RegionalWaterCache:
    """Short-lived, size-bounded public cells. No user/device IDs or GPS histories."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._cells: dict[str, dict] = {}
        self._retry_after: dict[str, datetime] = {}
        self._loaded = False
        self._lock = asyncio.Lock()
        self.generation = 0
        self.source_url = WATERBODY_URL
        self.fetcher = fetch_water_cell

    def parse_cached(self, bodies: list[dict]) -> list[dict]:
        features = [
            {
                "properties": {
                    "id3dhp": body["id"].removeprefix("usgs3dhp:"),
                    "gnisidlabel": body.get("name"),
                    "featuretype": body["feature_type"],
                },
                "geometry": body["geometry"],
            }
            for body in bodies
        ]
        if any(not body["id"].startswith("usgs3dhp:") for body in bodies):
            raise ValueError("Unexpected cached map identity")
        return parse_waterbodies({"type": "FeatureCollection", "features": features})

    @staticmethod
    def _key(cell: tuple[int, int]) -> str:
        cell_query(cell)
        return f"{cell[0]},{cell[1]}"

    def bodies(self, cell: tuple[int, int], now: datetime) -> list[dict] | None:
        item = self._cells.get(self._key(cell))
        if not item:
            return None
        try:
            age = now - datetime.fromisoformat(item["fetched_at"])
        except (KeyError, TypeError, ValueError):
            return None
        return item["bodies"] if timedelta(0) <= age < CACHE_MAX_AGE else None

    async def async_refresh(
        self, cells: tuple[tuple[int, int], ...], executor: Any, now: datetime | None = None
    ) -> None:
        """Call from a background task, never while waiting to deliver an alert."""
        now = now or datetime.now(timezone.utc)
        async with self._lock:
            previous = self._cells.copy()
            if not self._loaded:
                self._loaded = True
                try:
                    data = await self._store.async_load()
                    if isinstance(data, dict) and isinstance(data.get("cells"), dict):
                        for key, item in list(data["cells"].items())[:MAX_CELLS]:
                            cell = tuple(map(int, key.split(",")))
                            self._key(cell)
                            if isinstance(item, dict) and isinstance(item.get("bodies"), list):
                                bodies = self.parse_cached(item["bodies"])
                                self._cells[key] = {
                                    "fetched_at": item["fetched_at"],
                                    "bodies": bodies,
                                }
                except (OSError, KeyError, TypeError, ValueError):
                    self._cells = {}
            requested = tuple(dict.fromkeys(cells))[:MAX_CELLS]
            for cell in requested:
                key = self._key(cell)
                if self.bodies(cell, now) is not None or self._retry_after.get(key, now) > now:
                    continue
                self._retry_after[key] = now + RETRY_DELAY
                try:
                    bodies = await executor(self.fetcher, cell)
                except (OSError, TypeError, ValueError):
                    continue
                self._cells[key] = {"fetched_at": now.isoformat(), "bodies": bodies}
            # Retain only current requested regions, not a trail of visited cells.
            wanted = {self._key(cell) for cell in requested}
            self._cells = {
                key: value
                for key, value in self._cells.items()
                if key in wanted and self.bodies(tuple(map(int, key.split(","))), now) is not None
            }
            self._retry_after = {
                key: value for key, value in self._retry_after.items() if key in wanted
            }
            while len(json.dumps(self._cells).encode()) > MAX_CACHE_BYTES:
                self._cells.pop(next(iter(self._cells)))
            if self._cells != previous:
                self.generation += 1
            if self._cells != previous:
                try:
                    await self._store.async_save({"source": self.source_url, "cells": self._cells})
                except OSError:
                    pass  # Current in-memory maps remain usable; no false coverage claim.
