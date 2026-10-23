"""One normalized daily safety picture shared by entity and delivery."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import math
import re
from typing import Iterable, Mapping

from .hazard_policy import DeliveryBehavior, classify_alert
from .models import BriefingDeliveryRecord, IncidentPhase, IncidentRecord
from .official_sources import SupplementalHazard, SupplementalSourceState


@dataclass(frozen=True)
class BriefingItem:
    source: str
    family: str
    headline: str
    detail: str
    action: str
    native_level: str
    behavior: DeliveryBehavior
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    routine_forecast: bool = False
    forecast_summary: str | None = None
    forecast_details: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyBriefing:
    generated_at: datetime
    state: str
    summary: str
    items: tuple[BriefingItem, ...]
    source_states: Mapping[str, SupplementalSourceState]
    fingerprint: str

    @property
    def incomplete(self) -> bool:
        return any(value != SupplementalSourceState.HEALTHY for value in self.source_states.values())


def build_daily_briefing(
    now: datetime,
    incidents: Iterable[IncidentRecord],
    supplemental: Iterable[SupplementalHazard] = (),
    source_states: Mapping[str, SupplementalSourceState] | None = None,
) -> DailyBriefing:
    """Build a compact picture without inventing a universal severity scale."""
    items = []
    for record in incidents:
        if record.phase != IncidentPhase.ACTIVE:
            continue
        alert = record.latest_alert
        policy = classify_alert(alert)
        if policy.behavior == DeliveryBehavior.IGNORE:
            continue
        items.append(BriefingItem(
            alert.source, policy.family.value, alert.headline or alert.event,
            alert.area_description or "Official alert relevant to a monitored point.",
            policy.action, alert.event, policy.behavior, alert.effective_at,
            alert.ends_at or alert.expires_at, False,
        ))
    items.extend(BriefingItem(
        item.source, item.family.value, item.headline, item.detail, item.action,
        item.native_level, item.behavior, item.valid_from, item.valid_to,
        item.routine_forecast,
        item.forecast_summary,
        item.forecast_details,
    ) for item in supplemental)
    # Ordering is presentation priority only; the native labels remain authoritative.
    order = {DeliveryBehavior.CRITICAL: 0, DeliveryBehavior.IMPORTANT: 1,
             DeliveryBehavior.NOTICE: 2, DeliveryBehavior.AWARENESS: 3,
             DeliveryBehavior.BRIEFING_ONLY: 4, DeliveryBehavior.IGNORE: 5}
    compact = tuple(
        item for _index, item in sorted(
            enumerate(items), key=lambda pair: (order[pair[1].behavior], pair[0])
        )[:5]
    )
    states = dict(source_states or {"NWS alerts": SupplementalSourceState.HEALTHY})
    incomplete = any(value != SupplementalSourceState.HEALTHY for value in states.values())
    safety_items = tuple(item for item in compact if not item.routine_forecast)
    if safety_items:
        state = safety_items[0].headline
        summary = f"{len(safety_items)} safety item{'s' if len(safety_items) != 1 else ''}. {safety_items[0].headline}."
        if incomplete:
            summary += " Some optional sources are unavailable."
    elif incomplete:
        state = "Safety picture incomplete"
        summary = "No current concern was found, but one or more configured sources are unavailable."
    else:
        state = "No significant safety concerns"
        summary = "Official sources show no significant safety concern for the monitored points."
    token_source = "|".join(f"{item.source}:{item.headline}:{item.native_level}:{item.valid_to}" for item in compact)
    token_source += "|" + "|".join(f"{key}:{value.value}" for key, value in sorted(states.items()))
    token = sha256(token_source.encode()).hexdigest()
    return DailyBriefing(now, state, summary, compact, states, token)


def briefing_message(briefing: DailyBriefing) -> tuple[str, str]:
    """Return a one-glance briefing; include only a source-stated severe ETA."""
    forecast = next(
        (
            item
            for item in briefing.items
            if item.source == "NWS forecast" and item.routine_forecast
        ),
        next((item for item in briefing.items if item.source == "NWS forecast"), None),
    )
    sentences = []
    if forecast is not None:
        condition = forecast.headline.split(":", 1)[-1].strip()
        temperature = (
            f", near {forecast.native_level}"
            if "°" in forecast.native_level else ""
        )
        sentences.append(f"Today expect {condition}{temperature}.")
    elif briefing.incomplete:
        sentences.append("Today's weather picture is incomplete.")
    else:
        sentences.append("Today, no significant weather hazards are expected.")

    safety_items = tuple(item for item in briefing.items if not item.routine_forecast)
    severe = next(
        (item for item in safety_items if item.family == "severe_convection"), None
    )
    if severe is not None:
        arrival = _explicit_arrival(severe.detail)
        if arrival:
            sentences.append(f"Severe weather is forecast to arrive {arrival}.")
        elif forecast is None or severe is not forecast:
            sentences.append("Severe weather is possible today.")
    elif safety_items:
        concern = safety_items[0].native_level or safety_items[0].headline
        sentences.append(f"{concern} is expected today.")
    return "Daily Weather Briefing", " ".join(sentences)


def _explicit_arrival(text: str) -> str | None:
    """Use a single time only when the official forecast states one."""
    match = re.search(
        r"\b(after|around|near|before)\s+((?:1[0-2]|[1-9])(?::[0-5][0-9])?\s*(?:a\.?m\.?|p\.?m\.?)|noon|midnight)\b",
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(match.group(0).split()) if match else None


def briefing_delivery_due(
    prior: BriefingDeliveryRecord | None,
    local_now: datetime,
    scheduled_time: str,
    fingerprint: str,
    urgency: int,
    *,
    allow_same_day_worsening: bool = False,
) -> bool:
    """Retry today's scheduled briefing until accepted, never send a second one.

    The legacy worsening argument remains for callers from older test tools.
    Worsening weather uses the separate hazard delivery path, not a second daily.
    """
    try:
        hour, minute = (int(value) for value in scheduled_time.split(":", 1))
    except (AttributeError, ValueError):
        hour, minute = 7, 0
    if hour not in range(24) or minute not in range(60):
        hour, minute = 7, 0
    scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    today = local_now.date().isoformat()
    if local_now < scheduled:
        return False
    if prior is not None and prior.local_date == today and prior.pending:
        return (
            prior.last_attempt_at is None
            or local_now - prior.last_attempt_at >= timedelta(minutes=15)
        )
    return prior is None or prior.local_date != today


def incidents_for_subjects(
    incidents: tuple[object, ...],
    notifications: tuple[object, ...],
    subject_ids: set[str],
) -> tuple[object, ...]:
    """Limit active incident context to the selected briefing subjects."""
    incident_keys = {
        item.incident_key
        for item in notifications
        if item.subject_id in subject_ids and not item.resolved
    }
    return tuple(item for item in incidents if item.incident_key in incident_keys)


def points_within_miles(
    first: tuple[float, float],
    second: tuple[float, float],
    miles: float,
) -> bool:
    """Return whether two coordinates are within the requested radius."""
    lat1, lon1 = (math.radians(value) for value in first)
    lat2, lon2 = (math.radians(value) for value in second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    distance = 3958.7613 * 2 * math.asin(min(1.0, math.sqrt(haversine)))
    return distance <= miles
