"""Honest adapters for official supplemental safety products.

Adapters preserve each source's native category/value.  They deliberately do
not manufacture a cross-source severity score.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .hazard_policy import DeliveryBehavior, HazardFamily


class SupplementalSourceState(str, Enum):
    HEALTHY = "healthy"
    UNCONFIGURED = "unconfigured"
    DEGRADED = "degraded"
    STALE = "stale"


@dataclass(frozen=True)
class SupplementalHazard:
    source: str
    family: HazardFamily
    headline: str
    detail: str
    action: str
    native_level: str
    behavior: DeliveryBehavior = DeliveryBehavior.NOTICE
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    routine_forecast: bool = False
    forecast_summary: str | None = None
    forecast_details: tuple[str, ...] = ()


def fetch_airnow_current(
    point: tuple[float, float], api_key: str, timeout_seconds: float = 10.0
) -> Any:
    """Fetch the official current AirNow point observations."""
    if not api_key.strip():
        raise ValueError("AirNow API key is required")
    query = urlencode({"format": "application/json", "latitude": point[0],
                       "longitude": point[1], "distance": 25, "API_KEY": api_key.strip()})
    request = Request(f"https://www.airnowapi.org/aq/observation/latLong/current/?{query}",
                      headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


def fetch_spc_outlooks(point: tuple[float, float]) -> Mapping[str, Any]:
    """Fetch official NOAA GIS point intersections for SPC outlooks."""
    features = []
    convective = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/FeatureServer"
    fire = "https://mapservices.weather.noaa.gov/vector/rest/services/fire_weather/SPC_firewx/MapServer"
    for layer in (1, 9, 17):
        features.extend(_arcgis_point_query(f"{convective}/{layer}", point).get("features", []))
    for layer in (1, 2, 4, 5):
        for feature in _arcgis_point_query(f"{fire}/{layer}", point).get("features", []):
            if isinstance(feature, Mapping):
                feature = dict(feature)
                props = dict(_mapping(feature.get("properties")))
                props["hazard"] = "fire weather"
                feature["properties"] = props
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def fetch_spc_mesoscale_discussions(point: tuple[float, float]) -> Mapping[str, Any]:
    """Fetch active SPC mesoscale-discussion polygons intersecting one point."""
    url = (
        "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/"
        "spc_mesoscale_discussion/MapServer/0"
    )
    return _arcgis_point_query(url, point)


def fetch_wssi(point: tuple[float, float]) -> Mapping[str, Any]:
    """Fetch the official NWS/WPC overall Days 1–3 WSSI at one point."""
    url = "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/wpc_wssi/MapServer/4"
    return _arcgis_point_query(url, point)


def _arcgis_point_query(layer_url: str, point: tuple[float, float]) -> Mapping[str, Any]:
    latitude, longitude = point
    query = urlencode({"where": "1=1", "geometry": f"{longitude},{latitude}",
                       "geometryType": "esriGeometryPoint", "inSR": 4326,
                       "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
                       "returnGeometry": "false", "f": "geojson"})
    request = Request(f"{layer_url}/query?{query}", headers={"Accept": "application/geo+json"})
    with urlopen(request, timeout=10.0) as response:
        payload = json.load(response)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("features"), list):
        raise ValueError("Official GIS response is not a feature collection")
    return payload


def normalize_nws_forecast(payload: Mapping[str, Any]) -> tuple[SupplementalHazard, ...]:
    """Extract one glanceable current period plus safety-relevant later periods."""
    periods = _mapping(payload.get("properties")).get("periods", [])
    keywords = ("tornado", "severe", "thunderstorm", "flood", "snow", "ice", "blizzard",
                "freezing", "extreme heat", "heat", "extreme cold", "wind", "fog", "smoke")
    results = []
    forecast_summary = compact_current_forecast(payload)
    period = _current_forecast_period(payload)
    wind_detail, _speed = _forecast_wind(period or {})
    for index, period in enumerate(periods if isinstance(periods, list) else []):
        if not isinstance(period, Mapping):
            continue
        text = str(period.get("detailedForecast") or period.get("shortForecast") or "").strip()
        safety_relevant = bool(text) and any(word in text.casefold() for word in keywords)
        if not text or (index != 0 and not safety_relevant):
            continue
        short = str(period.get("shortForecast") or "Weather concern")
        results.append(SupplementalHazard(
            "NWS forecast", _family_from_text(short + " " + text),
            f"{period.get('name', 'Forecast')}: {short}", text,
            "Check the latest official forecast before outdoor activity or travel.",
            _temperature_label(period), DeliveryBehavior.BRIEFING_ONLY,
            _time(period.get("startTime")), _time(period.get("endTime")),
            not safety_relevant,
            forecast_summary if index == 0 else None,
            (wind_detail,) if index == 0 and wind_detail else (),
        ))
    return tuple(results)


def compact_current_forecast(payload: Mapping[str, Any]) -> str | None:
    """One current day/night summary from supplied NWS values, not prose guesses."""
    periods = _mapping(payload.get("properties")).get("periods", [])
    usable = [p for p in periods if isinstance(p, Mapping)] if isinstance(periods,list) else []
    period = _current_forecast_period(payload)
    if period is None:
        return None
    parts = [f"Today's forecast: {str(period.get('shortForecast') or 'Conditions unavailable').strip().rstrip('.')}."]
    temperature = period.get("temperature")
    unit = period.get("temperatureUnit")
    if isinstance(temperature,(int,float)) and not isinstance(temperature,bool) and unit in {"F","C"}:
        label = "Low" if period.get("isDaytime") is False else "High"
        parts.append(f"{label} near {temperature:g}°{unit}.")
    if period.get("isDaytime") is True:
        position = usable.index(period)
        night = usable[position+1] if position+1<len(usable) else None
        if night is not None and night.get("isDaytime") is False:
            low = night.get("temperature")
            low_unit = night.get("temperatureUnit")
            if isinstance(low,(int,float)) and not isinstance(low,bool) and low_unit in {"F","C"}:
                parts.append(f"Low near {low:g}°{low_unit}.")
    chance = _mapping(period.get("probabilityOfPrecipitation")).get("value")
    if isinstance(chance,(int,float)) and not isinstance(chance,bool) and 0<=chance<=100:
        label = "Rain or snow chance" if any(word in str(period.get("shortForecast","")).casefold() for word in ("snow","ice","sleet","freezing")) else "Rain chance"
        parts.append(f"{label} {chance:g}%.")
    wind, speed = _forecast_wind(period)
    if wind and speed >= 15:
        parts.append(wind)
    return " ".join(parts)


def _current_forecast_period(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    periods = _mapping(payload.get("properties")).get("periods", [])
    usable = [p for p in periods if isinstance(p, Mapping)] if isinstance(periods,list) else []
    if not usable:
        return None
    period = usable[0]
    # An overnight period can precede today's day; do not promote tomorrow's day.
    first_start = _time(period.get("startTime"))
    if period.get("isDaytime") is False and first_start is not None:
        day = next((p for p in usable[1:3] if p.get("isDaytime") is True and
                    (start := _time(p.get("startTime"))) is not None and start.date() == first_start.date()),None)
        if day is not None:
            period = day
    return period


def _forecast_wind(period: Mapping[str, Any]) -> tuple[str | None, float]:
    speed = str(period.get("windSpeed") or "").strip()
    if speed.casefold() == "calm":
        return "Calm winds.", 0
    import re
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s+to\s+(\d+(?:\.\d+)?))?\s+mph",speed,re.I)
    if match is None:
        return None, 0
    directions={"N":"north","NNE":"north-northeast","NE":"northeast","ENE":"east-northeast",
        "E":"east","ESE":"east-southeast","SE":"southeast","SSE":"south-southeast",
        "S":"south","SSW":"south-southwest","SW":"southwest","WSW":"west-southwest",
        "W":"west","WNW":"west-northwest","NW":"northwest","NNW":"north-northwest"}
    direction = str(period.get("windDirection") or "").upper()
    prefix = "Variable winds" if direction in {"VRB","VARIABLE"} else f"Winds from the {directions[direction]}" if direction in directions else "Winds"
    return f"{prefix} at {speed}.", max(float(match.group(1)),float(match.group(2) or match.group(1)))


def normalize_spc_outlook(payload: Mapping[str, Any]) -> tuple[SupplementalHazard, ...]:
    """Normalize point-selected SPC convective and fire outlook features."""
    results = []
    for feature in _features(payload):
        item = _feature_hazard(feature, "SPC outlook")
        if item is not None:
            results.append(item)
    return tuple(results)


def normalize_spc_mesoscale_discussions(
    payload: Mapping[str, Any],
) -> tuple[SupplementalHazard, ...]:
    """Normalize point-intersecting SPC short-term mesoscale discussions."""
    results = []
    for feature in _features(payload):
        props = _mapping(feature.get("properties"))
        number = _first(props, "name", "NAME", "discussion")
        if not number:
            continue
        results.append(
            SupplementalHazard(
                "SPC mesoscale discussion",
                HazardFamily.CONVECTION,
                f"SPC Mesoscale Discussion {number}",
                "The official SPC discussion polygon includes the designated home.",
                "Monitor for rapidly changing conditions and later watches or warnings.",
                str(number),
                DeliveryBehavior.BRIEFING_ONLY,
                _time(_first(props, "idp_filedate", "validFrom")),
                None,
            )
        )
    return tuple(results)


def normalize_wssi(payload: Mapping[str, Any]) -> tuple[SupplementalHazard, ...]:
    """Normalize point-selected WSSI features while retaining impact names."""
    results = []
    for feature in _features(payload):
        props = _mapping(feature.get("properties"))
        level = _first(props, "impact", "IMPACT", "category", "Category", "WSSI")
        if not level:
            continue
        component = _first(props, "component", "COMPONENT", "hazard") or "winter weather"
        results.append(SupplementalHazard(
            "NWS WSSI", HazardFamily.WINTER, f"{level} winter-storm impacts",
            f"Official WSSI component: {component}.",
            "Review travel plans and the latest official winter forecast.", level,
            DeliveryBehavior.BRIEFING_ONLY,
            _time(_first(props, "validFrom", "start_time")),
            _time(_first(props, "validTo", "end_time")),
        ))
    return tuple(results)


def normalize_airnow(payload: Any) -> tuple[SupplementalHazard, ...]:
    """Normalize official AirNow observations/forecasts without hiding AQI."""
    rows = payload if isinstance(payload, list) else _mapping(payload).get("observations", [])
    candidates = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        try:
            aqi = int(row.get("AQI"))
        except (TypeError, ValueError):
            continue
        if aqi < 51:
            continue
        category = row.get("Category")
        if isinstance(category, Mapping):
            category = category.get("Name")
        category = str(category or _aqi_category(aqi))
        pollutant = str(row.get("ParameterName") or row.get("Parameter") or "air pollution")
        candidates.append((aqi, SupplementalHazard(
            "EPA AirNow", HazardFamily.AIR_QUALITY, f"Air quality: {category}",
            f"AQI {aqi}; primary pollutant {pollutant}.",
            "Use the official AQI guidance, especially for sensitive people.",
            f"AQI {aqi} — {category}", DeliveryBehavior.NOTICE,
        )))
    return (max(candidates, key=lambda item: item[0])[1],) if candidates else ()


def normalize_uv(payload: Mapping[str, Any]) -> tuple[SupplementalHazard, ...]:
    """Normalize an official UV product when a deployment supplies one."""
    raw = payload.get("uv_index", payload.get("value"))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return ()
    if value < 3:
        return ()
    category = str(payload.get("category") or _uv_category(value))
    return (SupplementalHazard(
        "Official UV", HazardFamily.AIR_QUALITY, f"UV exposure: {category}",
        f"UV index {value:g}.", "Use shade, protective clothing, and sunscreen.",
        f"UV index {value:g} — {category}", DeliveryBehavior.NOTICE,
    ),)


def _feature_hazard(feature: Mapping[str, Any], source: str) -> SupplementalHazard | None:
    props = _mapping(feature.get("properties"))
    label = _first(props, "LABEL", "label", "category", "risk") or _spc_dn_label(props)
    if not label:
        return None
    text = " ".join(str(value) for value in props.values() if value is not None)
    family = HazardFamily.FIRE if "fire" in text.casefold() else HazardFamily.CONVECTION
    kind = "fire-weather" if family == HazardFamily.FIRE else "convective"
    return SupplementalHazard(
        source, family, f"{label} SPC {kind} outlook",
        "Official outlook category for this point.",
        "Review plans and monitor later official watches and warnings.", label,
        DeliveryBehavior.BRIEFING_ONLY,
        _time(_first(props, "VALID", "valid", "validFrom")),
        _time(_first(props, "EXPIRE", "expire", "validTo")),
    )


def _features(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = payload.get("features", [])
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(values: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = values.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _temperature_label(period: Mapping[str, Any]) -> str:
    value, unit = period.get("temperature"), period.get("temperatureUnit")
    return f"{value}°{unit}" if value is not None and unit else str(period.get("shortForecast") or "forecast")


def _family_from_text(text: str) -> HazardFamily:
    value = text.casefold()
    for words, family in ((("snow", "ice", "blizzard", "freezing"), HazardFamily.WINTER),
                          (("flood",), HazardFamily.FLOOD), (("heat",), HazardFamily.HEAT),
                          (("cold",), HazardFamily.COLD), (("wind",), HazardFamily.WIND)):
        if any(word in value for word in words):
            return family
    return HazardFamily.CONVECTION


def _aqi_category(value: int) -> str:
    return "Moderate" if value <= 100 else "Unhealthy for Sensitive Groups" if value <= 150 else "Unhealthy" if value <= 200 else "Very Unhealthy" if value <= 300 else "Hazardous"


def _uv_category(value: float) -> str:
    return "Moderate" if value < 6 else "High" if value < 8 else "Very High" if value < 11 else "Extreme"


def _spc_dn_label(props: Mapping[str, Any]) -> str:
    value = str(props.get("DN", props.get("dn", "")))
    if "fire" in " ".join(str(item) for item in props.values()).casefold():
        return {"5": "Elevated", "8": "Critical", "10": "Extremely Critical"}.get(value, value)
    return {"2": "Thunderstorm", "3": "Marginal", "4": "Slight", "5": "Enhanced",
            "6": "Moderate", "8": "High"}.get(value, value)
