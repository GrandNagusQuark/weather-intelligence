"""Official NOAA MRMS hail-core extraction and short-horizon motion tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import gzip
import math
import struct
from typing import Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

MRMS_MESH_URL = (
    "https://mrms.ncep.noaa.gov/data/2D/MESH/"
    "MRMS_MESH.latest.grib2.gz"
)
MRMS_HAIL_THRESHOLD_MM = 12.7
MRMS_PROPERTY_DAMAGE_HAIL_MM = 25.4
MRMS_DESTRUCTIVE_HAIL_MM = 69.85
MRMS_SEARCH_RADIUS_MILES = 60.0
MRMS_MAX_AGE_SECONDS = 5 * 60


class MrmsHailError(ValueError):
    """Raised when the operational MRMS hail product cannot be trusted."""


@dataclass(frozen=True)
class HailDetection:
    latitude: float
    longitude: float
    max_hail_inches: float
    cell_count: int
    radius_miles: float


@dataclass(frozen=True)
class MrmsHailFrame:
    observed_at: datetime
    detections: Mapping[str, tuple[HailDetection, ...]]


@dataclass(frozen=True)
class HailApproach:
    target_id: str
    eta_minutes: int
    closest_distance_miles: float
    max_hail_inches: float
    speed_mph: float
    property_damaging: bool
    life_threatening: bool
    observed_at: datetime


class MrmsHailClient:
    """Fetch the latest small compressed MRMS MESH grid directly from NOAA."""

    def __init__(self, user_agent: str, timeout_seconds: float = 10.0) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._etag: str | None = None
        self._last_modified: str | None = None

    def fetch_latest(
        self, targets: Mapping[str, tuple[float, float]]
    ) -> MrmsHailFrame | None:
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/x-gzip, application/octet-stream",
        }
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
        request = Request(MRMS_MESH_URL, headers=headers)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read()
                self._etag = response.headers.get("ETag") or self._etag
                self._last_modified = (
                    response.headers.get("Last-Modified") or self._last_modified
                )
        except HTTPError as error:
            if error.code == 304:
                return None
            raise MrmsHailError(f"MRMS returned HTTP {error.code}") from error
        except OSError as error:
            raise MrmsHailError("MRMS hail data could not be downloaded") from error
        return decode_mrms_mesh(payload, targets)


class HailMotionTracker:
    """Match consecutive hail cores and project only a short closing path."""

    def __init__(self) -> None:
        self._previous: MrmsHailFrame | None = None

    def update(
        self,
        frame: MrmsHailFrame,
        targets: Mapping[str, tuple[float, float]],
    ) -> tuple[bool, dict[str, HailApproach]]:
        prior = self._previous
        if prior is not None and frame.observed_at <= prior.observed_at:
            return False, {}
        self._previous = frame
        if prior is None:
            return False, {}
        elapsed_minutes = (frame.observed_at - prior.observed_at).total_seconds() / 60
        if not 0.5 <= elapsed_minutes <= 6:
            return False, {}

        approaches: dict[str, HailApproach] = {}
        for target_id, target in targets.items():
            prior_items = prior.detections.get(target_id, ())
            current_items = frame.detections.get(target_id, ())
            candidates = []
            for current in current_items:
                previous = _nearest_detection(current, prior_items)
                if previous is None:
                    continue
                approach = _project_approach(
                    target_id,
                    target,
                    previous,
                    current,
                    frame.observed_at,
                    elapsed_minutes,
                )
                if approach is not None:
                    candidates.append(approach)
            if candidates:
                approaches[target_id] = min(
                    candidates,
                    key=lambda item: (
                        item.eta_minutes,
                        -item.max_hail_inches,
                    ),
                )
        return True, approaches


def decode_mrms_mesh(
    compressed: bytes,
    targets: Mapping[str, tuple[float, float]],
) -> MrmsHailFrame:
    """Decode the operational GRIB2 PNG packing only around monitored points."""
    try:
        grib = gzip.decompress(compressed)
    except (OSError, EOFError) as error:
        raise MrmsHailError("MRMS hail payload is not valid gzip data") from error
    if len(grib) < 20 or grib[:4] != b"GRIB" or grib[7] != 2:
        raise MrmsHailError("MRMS hail payload is not GRIB2")
    sections = _grib_sections(grib)
    try:
        section1 = sections[1]
        section3 = sections[3]
        section5 = sections[5]
        section7 = sections[7]
    except KeyError as error:
        raise MrmsHailError("MRMS hail payload is missing a required section") from error
    if _u16(section3, 12) != 0:
        raise MrmsHailError("Unsupported MRMS grid template")
    if _u16(section5, 9) != 41:
        raise MrmsHailError("Unsupported MRMS data packing")

    observed_at = datetime(
        _u16(section1, 12),
        section1[14],
        section1[15],
        section1[16],
        section1[17],
        section1[18],
        tzinfo=timezone.utc,
    )
    width = _u32(section3, 30)
    height = _u32(section3, 34)
    subdivisions = _u32(section3, 42) or 1_000_000
    latitude_first = _signed_u32(section3, 46) / subdivisions
    longitude_first = _signed_u32(section3, 50) / subdivisions
    latitude_step = _u32(section3, 67) / subdivisions
    longitude_step = _u32(section3, 63) / subdivisions
    scan_mode = section3[71]
    if scan_mode != 0 or not width or not height:
        raise MrmsHailError("Unsupported MRMS scan mode")

    reference = struct.unpack(">f", section5[11:15])[0]
    binary_scale = _signed_u16(section5, 15)
    decimal_scale = _signed_u16(section5, 17)
    bits = section5[19]
    if bits != 16:
        raise MrmsHailError("Unsupported MRMS PNG sample depth")
    factor = (2.0 ** binary_scale) / (10.0 ** decimal_scale)

    png = section7[5:]
    try:
        with Image.open(BytesIO(png)) as image:
            image.load()
            if image.size != (width, height):
                raise MrmsHailError("MRMS grid and PNG dimensions disagree")
            detections = {
                target_id: _detections_for_target(
                    image,
                    point,
                    width,
                    height,
                    latitude_first,
                    longitude_first,
                    latitude_step,
                    longitude_step,
                    reference,
                    factor,
                )
                for target_id, point in targets.items()
            }
    except MrmsHailError:
        raise
    except Exception as error:
        raise MrmsHailError("MRMS PNG hail grid could not be decoded") from error
    return MrmsHailFrame(observed_at, detections)


def _detections_for_target(
    image: Image.Image,
    target: tuple[float, float],
    width: int,
    height: int,
    latitude_first: float,
    longitude_first: float,
    latitude_step: float,
    longitude_step: float,
    reference: float,
    factor: float,
) -> tuple[HailDetection, ...]:
    target_latitude, target_longitude = target
    target_longitude_grid = (
        target_longitude + 360 if target_longitude < 0 else target_longitude
    )
    center_row = round((latitude_first - target_latitude) / latitude_step)
    center_column = round(
        (target_longitude_grid - longitude_first) / longitude_step
    )
    row_radius = math.ceil(MRMS_SEARCH_RADIUS_MILES / 69.0 / latitude_step)
    longitude_miles = max(20.0, 69.0 * math.cos(math.radians(target_latitude)))
    column_radius = math.ceil(
        MRMS_SEARCH_RADIUS_MILES / longitude_miles / longitude_step
    )
    left = max(0, center_column - column_radius)
    right = min(width, center_column + column_radius + 1)
    top = max(0, center_row - row_radius)
    bottom = min(height, center_row + row_radius + 1)
    if left >= right or top >= bottom:
        return ()

    crop = image.crop((left, top, right, bottom))
    active: dict[tuple[int, int], float] = {}
    crop_width, _crop_height = crop.size
    for index, packed in enumerate(crop.getdata()):
        value_mm = reference + int(packed) * factor
        if value_mm < MRMS_HAIL_THRESHOLD_MM:
            continue
        row, column = divmod(index, crop_width)
        active[(row, column)] = value_mm

    detections = []
    while active:
        seed = next(iter(active))
        stack = [seed]
        cells: list[tuple[int, int, float]] = []
        while stack:
            row, column = stack.pop()
            value = active.pop((row, column), None)
            if value is None:
                continue
            cells.append((row, column, value))
            for row_delta in (-1, 0, 1):
                for column_delta in (-1, 0, 1):
                    neighbor = (row + row_delta, column + column_delta)
                    if neighbor in active:
                        stack.append(neighbor)
        if len(cells) < 3:
            continue
        weight = sum(value for _row, _column, value in cells)
        centroid_row = sum(row * value for row, _column, value in cells) / weight
        centroid_column = (
            sum(column * value for _row, column, value in cells) / weight
        )
        latitude = latitude_first - (top + centroid_row) * latitude_step
        longitude_grid = longitude_first + (left + centroid_column) * longitude_step
        longitude = longitude_grid - 360 if longitude_grid > 180 else longitude_grid
        if _distance_miles(target, (latitude, longitude)) > MRMS_SEARCH_RADIUS_MILES:
            continue
        cell_area = (
            69.0
            * latitude_step
            * longitude_miles
            * longitude_step
        )
        radius = max(1.0, math.sqrt(len(cells) * cell_area / math.pi))
        detections.append(
            HailDetection(
                latitude,
                longitude,
                max(value for _row, _column, value in cells) / 25.4,
                len(cells),
                radius,
            )
        )
    return tuple(detections)


def _nearest_detection(
    current: HailDetection, prior: tuple[HailDetection, ...]
) -> HailDetection | None:
    if not prior:
        return None
    candidate = min(
        prior,
        key=lambda item: _distance_miles(
            (current.latitude, current.longitude),
            (item.latitude, item.longitude),
        ),
    )
    if _distance_miles(
        (current.latitude, current.longitude),
        (candidate.latitude, candidate.longitude),
    ) > 12:
        return None
    return candidate


def _project_approach(
    target_id: str,
    target: tuple[float, float],
    previous: HailDetection,
    current: HailDetection,
    observed_at: datetime,
    elapsed_minutes: float,
) -> HailApproach | None:
    previous_x, previous_y = _local_xy_miles(
        target, (previous.latitude, previous.longitude)
    )
    current_x, current_y = _local_xy_miles(
        target, (current.latitude, current.longitude)
    )
    velocity_x = (current_x - previous_x) / elapsed_minutes
    velocity_y = (current_y - previous_y) / elapsed_minutes
    speed_per_minute = math.hypot(velocity_x, velocity_y)
    speed_mph = speed_per_minute * 60
    if not 5 <= speed_mph <= 120:
        return None
    velocity_squared = velocity_x * velocity_x + velocity_y * velocity_y
    eta = -(
        current_x * velocity_x + current_y * velocity_y
    ) / velocity_squared
    if not 0 <= eta <= 18:
        return None
    current_distance = math.hypot(current_x, current_y)
    previous_distance = math.hypot(previous_x, previous_y)
    if current_distance >= previous_distance - 0.1:
        return None
    closest_x = current_x + velocity_x * eta
    closest_y = current_y + velocity_y * eta
    closest_distance = math.hypot(closest_x, closest_y)
    corridor = max(2.5, current.radius_miles + 1.0)
    if closest_distance > corridor:
        return None
    max_hail_inches = max(previous.max_hail_inches, current.max_hail_inches)
    life_threatening = (
        previous.max_hail_inches >= MRMS_DESTRUCTIVE_HAIL_MM / 25.4
        and current.max_hail_inches >= MRMS_DESTRUCTIVE_HAIL_MM / 25.4
    )
    property_damaging = (
        previous.max_hail_inches >= MRMS_PROPERTY_DAMAGE_HAIL_MM / 25.4
        and current.max_hail_inches >= MRMS_PROPERTY_DAMAGE_HAIL_MM / 25.4
    )
    return HailApproach(
        target_id,
        max(1, round(eta)),
        closest_distance,
        max_hail_inches,
        speed_mph,
        property_damaging,
        life_threatening,
        observed_at,
    )


def _grib_sections(grib: bytes) -> dict[int, bytes]:
    result = {}
    offset = 16
    while offset + 5 <= len(grib):
        if grib[offset:offset + 4] == b"7777":
            break
        length = _u32(grib, offset)
        if length < 5 or offset + length > len(grib):
            raise MrmsHailError("MRMS GRIB2 section length is invalid")
        section = grib[offset:offset + length]
        result[section[4]] = section
        offset += length
    return result


def _local_xy_miles(
    origin: tuple[float, float], point: tuple[float, float]
) -> tuple[float, float]:
    latitude_scale = 69.0
    longitude_scale = 69.0 * math.cos(math.radians(origin[0]))
    return (
        (point[1] - origin[1]) * longitude_scale,
        (point[0] - origin[0]) * latitude_scale,
    )


def _distance_miles(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    x, y = _local_xy_miles(first, second)
    return math.hypot(x, y)


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "big")


def _signed_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "big", signed=True)


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "big")


def _signed_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "big", signed=True)
