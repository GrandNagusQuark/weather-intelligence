"""Privacy-minimal household overview; no personal coordinates or device targets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import html
import re
from typing import Any
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

from .config import effective_entry_config, profiles_from_config
from .hazard_policy import classify_alert, family_enabled, alert_choices, briefing_item_enabled


def build_dashboard_snapshot(hass: Any, entry: Any) -> dict[str, Any]:
    coordinator = getattr(entry, "runtime_data", None)
    now = datetime.now(timezone.utc)
    core = getattr(coordinator, "core", None)
    records = tuple(getattr(core, "incident_records", ()))
    decisions = tuple(getattr(core, "notification_records", ()))
    active = {item.incident_key: item for item in records
              if item.phase.value == "active" and (
                  item.latest_alert.expires_at is None or now < item.latest_alert.expires_at)}
    status = getattr(coordinator, "data", None)
    health = status.source_health.value if status else "starting"
    generated = status.generated_at if status else None
    # A healthy-but-stopped coordinator must not keep looking current forever.
    if generated and (now - generated).total_seconds() > 600:
        health = "data_stale"
    profiles = profiles_from_config(effective_entry_config(entry))
    cards = []
    for profile in profiles:
        if not profile.enabled:
            continue
        presence = _presence(hass, profile.person_entity_id)
        subjects = set()
        if profile.receive_personal_alerts:
            subjects.add(profile.subject_id)
        if presence == "home" or profile.receive_home_while_away:
            subjects.add("designated_home")
        keys = {item.incident_key for item in decisions
                if item.subject_id in subjects and not item.resolved}
        alerts = []
        for key in keys:
            record = active.get(key)
            if record is None or not family_enabled(profile, classify_alert(record.latest_alert), record.latest_alert.event):
                continue
            policy = classify_alert(record.latest_alert)
            acknowledgement = getattr(coordinator, "acknowledgements", None)
            alerts.append({"incident_key": key, "event": record.latest_alert.event,
                           "action": policy.action, "priority": policy.behavior.value,
                           "report_id": _report_id("alert", key),
                           "expires_at": _iso(record.latest_alert.expires_at),
                           **(acknowledgement.status(profile.profile_id, record) if acknowledgement else
                              {"acknowledged": False, "acknowledged_at": None, "ack_available": False})})
        alerts.sort(key=lambda item: (item["priority"] != "critical", item["event"]))
        cards.append({"profile_id": profile.profile_id, "name": profile.name,
                      "presence": presence, "automatic_alerts": profile.automatic_notifications,
                      "critical_alerts": profile.critical_notifications,
                      "location_enabled": profile.receive_personal_alerts,
                      "coverage_current": health == "healthy" and (
                          presence == "home" or not profile.receive_personal_alerts or
                          getattr(getattr(core, "subject_location_freshness", {}).get(profile.subject_id),
                                  "value", "missing") in {"fresh", "last_known_grace"}),
                      "map_visible": _map_entity_visible(hass, profile.person_entity_id, profile.show_location_on_map),
                      "alerts": alerts})
    outlooks = []
    home = getattr(coordinator, "briefing", None)
    if home is not None:
        outlook = _outlook(home, "Home", "home")
        outlook["sun_times"] = _home_sun_times(hass,now)
        outlooks.append(outlook)
    personal = getattr(coordinator, "dashboard_briefings", {})
    for profile in profiles:
        if profile.enabled and profile.profile_id in personal:
            outlooks.append(_outlook(personal[profile.profile_id], profile.name, profile.profile_id,profile))
    lat = float(getattr(getattr(hass, "config", None), "latitude", 39.5))
    lon = float(getattr(getattr(hass, "config", None), "longitude", -98.0))
    return {"generated_at": _iso(generated), "source_health": health,
            "map_alert_events": _map_alert_events(profiles),
            "users": cards, "outlooks": outlooks,
            # An approximate HOME map view only. Never center or mark a person.
            "map_center": [round(lat, 1), round(lon, 1)],
            "home_marker": [lat, lon],
            "monitored_polygons": [{"type": "Feature", "geometry": item.latest_alert.geometry,
                                    "properties": {"event": item.latest_alert.event,"expiration":_iso(item.latest_alert.expires_at)}}
                                   for item in active.values() if item.latest_alert.geometry]}


def _map_alert_events(profiles: Any) -> list[str] | None:
    """Union of explicit household choices; retain prior broad map until legacy profiles opt in."""
    enabled = tuple(profile for profile in profiles if profile.enabled)
    if any(profile.alert_events is None for profile in enabled):
        return None
    choices = alert_choices()
    values = {value for profile in enabled for value in profile.alert_events} if enabled else {
        item["value"] for item in choices if item["default"]}
    return [item["official_event"] for item in choices if item["value"] in values and item["official_event"]]


def _presence(hass: Any, entity_id: str) -> str:
    get_state = getattr(getattr(hass, "states", None), "get", None)
    state = get_state(entity_id) if get_state else None
    value = str(getattr(state, "state", "unknown")).lower()
    if value in {"unknown", "unavailable", "none", ""}:
        return "unknown"
    return "home" if value == "home" else "away"


def _home_sun_times(hass: Any, now: datetime, event_getter: Any = None) -> dict[str, Any]:
    """Today's home solar events, including sunrise already passed, calculated locally."""
    try:
        zone_name = str(hass.config.time_zone)
        zone = ZoneInfo(zone_name)
        today = now.astimezone(zone).date()
        if event_getter is None:
            from homeassistant.helpers.sun import get_astral_event_date
            event_getter = get_astral_event_date
        result = {"local_date":today.isoformat(),"time_zone":zone_name}
        for event in ("sunrise","sunset"):
            result[event] = None
            # UTC-dated calculations can cross the local midnight boundary.
            for offset in (0,-1,1):
                value = event_getter(hass,event,today+timedelta(days=offset))
                if value is not None and value.astimezone(zone).date() == today:
                    result[event] = _iso(value)
                    break
        return result
    except (ImportError, AttributeError, ValueError, KeyError):
        return {}


def _map_entity_visible(hass: Any, entity_id: str, choice: str) -> bool:
    """Inherit HA entity visibility; a hidden entity needs an explicit show choice."""
    if choice == "hide":
        return False
    try:
        from homeassistant.helpers import entity_registry
        entry = entity_registry.async_get(hass).async_get(entity_id)
        return entry is not None and not entry.disabled_by and (not entry.hidden_by or choice == "show")
    except (ImportError, AttributeError):
        return False


def _outlook(briefing: Any, name: str, scope: str, profile: Any = None) -> dict[str, Any]:
    # One current-day forecast, then relevant safety details; no extended periods.
    items = tuple(item for item in briefing.items if not item.routine_forecast and item.source != "NWS forecast"
                  and (profile is None or briefing_item_enabled(profile,item)))
    forecast = next((getattr(item,"forecast_summary",None) for item in briefing.items
                     if getattr(item,"forecast_summary",None)),None)
    forecast_item = next((item for item in briefing.items if item.source == "NWS forecast"),None)
    if not forecast and forecast_item is not None:
        forecast = "Today's forecast: " + forecast_item.headline.split(":",1)[-1].strip().rstrip(".") + "."
    summary = " ".join(part for part in (forecast,_short_headline(items[0]) if items else "No current weather concerns." if forecast else None) if part) or "Today's forecast is not available yet."
    if len(items) > 1:
        summary += f" · {len(items) - 1} more weather concern{'s' if len(items) > 2 else ''}."
    return {"name": name, "scope": scope, "summary": summary,
            "weather_details": list(getattr(forecast_item,"forecast_details",())),
            "generated_at": _iso(briefing.generated_at), "incomplete": briefing.incomplete,
            "sources": {key: value.value for key, value in briefing.source_states.items()},
            "items": [{"headline": _short_headline(item), "detail": item.detail,
                       "action": item.action, "source": item.source,
                       "valid_to": _iso(item.valid_to),
                       "report_id": _report_id(scope, f"{item.source}|{item.headline}|{item.native_level}")}
                      for item in items]}


def _short_headline(item: Any) -> str:
    if "mesoscale" in item.source.lower():
        return "Mesoscale Discussion"
    return item.headline


def get_official_report(entry: Any, report_id: str) -> dict[str, Any]:
    """Resolve only reports already in this instance, never an arbitrary URL."""
    coordinator = getattr(entry, "runtime_data", None)
    for record in getattr(getattr(coordinator, "core", None), "incident_records", ()):
        if _report_id("alert", record.incident_key) == report_id:
            alert = record.latest_alert
            return {"title": alert.event, "source": "National Weather Service",
                    "text": "\n\n".join(part for part in (alert.headline, alert.description, alert.instruction) if part),
                    "url": "https://www.weather.gov/", "issued_at": _iso(alert.sent_at),
                    "complete": True}
    briefings = {"home": getattr(coordinator, "briefing", None),
                 **getattr(coordinator, "dashboard_briefings", {})}
    for scope, briefing in briefings.items():
        for item in getattr(briefing, "items", ()):
            if _report_id(scope, f"{item.source}|{item.headline}|{item.native_level}") != report_id:
                continue
            if "mesoscale" in item.source.lower():
                number = re.search(r"\b\d{1,4}\b", item.native_level)
                if number is not None:
                    url = f"https://www.spc.noaa.gov/products/md/md{int(number.group()):04d}.html"
                    request = Request(url, headers={"User-Agent": "WeatherIntelligence/0.11 (Home Assistant report viewer)"})
                    with urlopen(request, timeout=10) as response:
                        page = response.read(131073)
                    if len(page) > 131072:
                        raise ValueError("The official discussion is too large")
                    blocks = re.findall(r"<pre\b[^>]*>(.*?)</pre>", page.decode("utf-8", errors="replace"), re.I | re.S)
                    text = html.unescape(re.sub(r"<[^>]+>", "", "\n\n".join(blocks))).strip()
                    if not text:
                        raise ValueError("The official discussion is not available as text")
                    if item.valid_from and str(item.valid_from.year) not in text:
                        raise ValueError("The source discussion date does not match this outlook")
                    return {"title": item.headline, "source": item.source, "text": text,
                            "url": url, "issued_at": _iso(item.valid_from), "complete": True}
            return {"title": item.headline, "source": item.source,
                    "text": item.detail + "\n\n" + item.action,
                    "url": "https://www.weather.gov/", "issued_at": _iso(item.valid_from),
                    "complete": item.source == "NWS forecast"}
    raise ValueError("This report is no longer in the current weather picture")


def _report_id(scope: str, key: str) -> str:
    return sha256(f"{scope}|{key}".encode()).hexdigest()[:24]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
