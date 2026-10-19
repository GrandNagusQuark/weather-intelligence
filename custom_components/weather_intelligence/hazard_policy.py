"""Explicit, source-native NWS safety policy without a universal score."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class HazardFamily(str, Enum):
    CONVECTION = "severe_convection"
    FLOOD = "flooding"
    WINTER = "winter"
    HEAT = "heat"
    COLD = "cold"
    WIND = "wind"
    FIRE = "fire_weather"
    VISIBILITY = "visibility"
    TROPICAL_COASTAL = "tropical_coastal"
    MARINE = "marine"
    GEOLOGIC = "geologic"
    AIR_QUALITY = "air_quality_uv"
    OTHER_SAFETY = "other_official_safety"


ALL_HAZARD_FAMILIES = tuple(item.value for item in HazardFamily)


class DeliveryBehavior(str, Enum):
    CRITICAL = "immediate_life_safety"
    IMPORTANT = "important_warning"
    NOTICE = "health_or_behavior_notice"
    AWARENESS = "advance_awareness"
    BRIEFING_ONLY = "briefing_only"
    IGNORE = "ignore"


@dataclass(frozen=True)
class HazardPolicy:
    family: HazardFamily
    behavior: DeliveryBehavior
    action: str
    known_event: bool = True

    @property
    def automatic(self) -> bool:
        return self.behavior not in {DeliveryBehavior.BRIEFING_ONLY, DeliveryBehavior.IGNORE}

    @property
    def critical_capable(self) -> bool:
        return self.behavior == DeliveryBehavior.CRITICAL


def _entries(family: HazardFamily, behavior: DeliveryBehavior, action: str, names: str):
    return {name.strip().casefold(): HazardPolicy(family, behavior, action) for name in names.split("|")}


_POLICIES: dict[str, HazardPolicy] = {}
_EVENT_NAMES: dict[str, str] = {}


def _add(family: HazardFamily, behavior: DeliveryBehavior, action: str, names: str) -> None:
    _POLICIES.update(_entries(family, behavior, action, names))
    _EVENT_NAMES.update({name.strip().casefold():name.strip() for name in names.split("|")})


_add(HazardFamily.CONVECTION, DeliveryBehavior.CRITICAL, "Take protective action now and follow official instructions.",
     "Tornado Warning")
_add(HazardFamily.CONVECTION, DeliveryBehavior.IMPORTANT, "Move indoors and monitor official updates.",
     "Severe Thunderstorm Warning")
_add(HazardFamily.CONVECTION, DeliveryBehavior.AWARENESS, "Review shelter plans and monitor conditions.",
     "Tornado Watch|Severe Thunderstorm Watch")

_add(HazardFamily.FLOOD, DeliveryBehavior.IMPORTANT, "Avoid flooded roads and move to higher ground if instructed.",
     "Flash Flood Warning|Flood Warning|River Flood Warning|Coastal Flood Warning|Lakeshore Flood Warning")
_add(HazardFamily.FLOOD, DeliveryBehavior.AWARENESS, "Be ready to change plans in flood-prone areas.",
     "Flash Flood Watch|Flood Watch|Coastal Flood Watch|Lakeshore Flood Watch|Hydrologic Outlook")
_add(HazardFamily.FLOOD, DeliveryBehavior.NOTICE, "Avoid flooded roads and low-lying areas.",
     "Flood Advisory|Coastal Flood Advisory|Lakeshore Flood Advisory|Flood Statement|Coastal Flood Statement|Lakeshore Flood Statement")

_add(HazardFamily.WINTER, DeliveryBehavior.CRITICAL, "Delay travel or slow down immediately for sudden whiteout and ice.",
     "Snow Squall Warning")
_add(HazardFamily.WINTER, DeliveryBehavior.IMPORTANT, "Avoid unnecessary travel and prepare for dangerous winter conditions.",
     "Blizzard Warning|Ice Storm Warning|Winter Storm Warning|Lake Effect Snow Warning|Heavy Freezing Spray Warning|Avalanche Warning|Sleet Warning")
_add(HazardFamily.WINTER, DeliveryBehavior.AWARENESS, "Prepare for possible travel and power impacts.",
     "Winter Storm Watch|Avalanche Watch|Heavy Freezing Spray Watch|Sleet Watch")
_add(HazardFamily.WINTER, DeliveryBehavior.NOTICE, "Use extra caution while traveling and protect against cold exposure.",
     "Winter Weather Advisory|Freezing Rain Advisory|Freezing Fog Advisory|Freezing Spray Advisory|Avalanche Advisory|Sleet Advisory|Snow Advisory|Blowing Snow Advisory")

_add(HazardFamily.HEAT, DeliveryBehavior.IMPORTANT, "Limit outdoor activity, stay cool and hydrated, and check vulnerable people.",
     "Extreme Heat Warning|Excessive Heat Warning")
_add(HazardFamily.HEAT, DeliveryBehavior.NOTICE, "Reduce heat exposure, hydrate, and check vulnerable people.",
     "Heat Advisory")
_add(HazardFamily.HEAT, DeliveryBehavior.AWARENESS, "Plan cooling and reschedule strenuous outdoor activity if needed.",
     "Extreme Heat Watch|Excessive Heat Watch")

_add(HazardFamily.COLD, DeliveryBehavior.IMPORTANT, "Limit exposure and protect people, pets, and plumbing from dangerous cold.",
     "Extreme Cold Warning|Freeze Warning|Hard Freeze Warning|Wind Chill Warning")
_add(HazardFamily.COLD, DeliveryBehavior.AWARENESS, "Prepare people, pets, and plumbing for dangerous cold.",
     "Extreme Cold Watch|Freeze Watch|Hard Freeze Watch|Wind Chill Watch")
_add(HazardFamily.COLD, DeliveryBehavior.NOTICE, "Limit exposure and dress for dangerous cold.",
     "Cold Weather Advisory|Frost Advisory|Wind Chill Advisory")

_add(HazardFamily.WIND, DeliveryBehavior.CRITICAL, "Shelter now in an interior part of a well-built structure.",
     "Extreme Wind Warning")
_add(HazardFamily.WIND, DeliveryBehavior.IMPORTANT, "Go indoors and stay clear of trees and windows.",
     "High Wind Warning")
_add(HazardFamily.WIND, DeliveryBehavior.AWARENESS, "Secure loose objects and prepare for outages.",
     "High Wind Watch")
_add(HazardFamily.WIND, DeliveryBehavior.NOTICE, "Use caution outdoors and while driving high-profile vehicles.",
     "Wind Advisory|Lake Wind Advisory")

_add(HazardFamily.FIRE, DeliveryBehavior.CRITICAL, "Follow evacuation or shelter instructions immediately.",
     "Fire Warning")
_add(HazardFamily.FIRE, DeliveryBehavior.IMPORTANT, "Avoid ignition sources and be ready to act if fire develops.",
     "Red Flag Warning|Extreme Fire Danger")
_add(HazardFamily.FIRE, DeliveryBehavior.AWARENESS, "Avoid ignition sources and review wildfire plans.",
     "Fire Weather Watch")

_add(HazardFamily.VISIBILITY, DeliveryBehavior.CRITICAL, "Pull off the road safely or delay travel until visibility improves.",
     "Dust Storm Warning")
_add(HazardFamily.VISIBILITY, DeliveryBehavior.IMPORTANT, "Avoid travel until dangerous visibility improves.",
     "Blowing Dust Warning")
_add(HazardFamily.VISIBILITY, DeliveryBehavior.NOTICE, "Slow down, use low beams, and allow extra stopping distance.",
     "Dust Advisory|Blowing Dust Advisory|Dense Fog Advisory|Dense Smoke Advisory")

_add(HazardFamily.TROPICAL_COASTAL, DeliveryBehavior.CRITICAL, "Follow evacuation and shelter instructions immediately.",
     "Hurricane Warning|Typhoon Warning|Storm Surge Warning")
_add(HazardFamily.TROPICAL_COASTAL, DeliveryBehavior.IMPORTANT, "Complete preparations and follow local official instructions.",
     "Tropical Storm Warning|Hurricane Force Wind Warning|High Surf Warning")
_add(HazardFamily.TROPICAL_COASTAL, DeliveryBehavior.AWARENESS, "Review evacuation plans and prepare for changing coastal conditions.",
     "Hurricane Watch|Typhoon Watch|Storm Surge Watch|Tropical Storm Watch|Hurricane Force Wind Watch")
_add(HazardFamily.TROPICAL_COASTAL, DeliveryBehavior.NOTICE, "Stay out of dangerous surf and follow beach officials.",
     "High Surf Advisory|Rip Current Statement|Beach Hazards Statement")

_add(HazardFamily.MARINE, DeliveryBehavior.CRITICAL, "Seek safe harbor immediately and follow marine warnings.",
     "Special Marine Warning")
_add(HazardFamily.MARINE, DeliveryBehavior.IMPORTANT, "Remain in safe harbor and monitor marine warnings.",
     "Storm Warning|Hurricane Force Wind Warning|Hazardous Seas Warning|Gale Warning")
_add(HazardFamily.MARINE, DeliveryBehavior.AWARENESS, "Review marine plans and monitor updated forecasts.",
     "Storm Watch|Hurricane Force Wind Watch|Hazardous Seas Watch|Gale Watch")
_add(HazardFamily.MARINE, DeliveryBehavior.NOTICE, "Use caution on the water and check current marine conditions.",
     "Small Craft Advisory|Brisk Wind Advisory|Low Water Advisory|Freezing Spray Advisory")

_add(HazardFamily.GEOLOGIC, DeliveryBehavior.CRITICAL, "Move to safety now and follow official evacuation instructions.",
     "Tsunami Warning")
_add(HazardFamily.GEOLOGIC, DeliveryBehavior.IMPORTANT, "Move away from the coast or other threatened area and follow officials.",
     "Tsunami Advisory|Volcano Warning|Earthquake Warning")
_add(HazardFamily.GEOLOGIC, DeliveryBehavior.AWARENESS, "Prepare to act and monitor official updates.",
     "Tsunami Watch")
_add(HazardFamily.GEOLOGIC, DeliveryBehavior.NOTICE, "Limit exposure and follow official health guidance.",
     "Ashfall Warning|Ashfall Advisory")

_add(HazardFamily.AIR_QUALITY, DeliveryBehavior.NOTICE, "Reduce outdoor exertion as advised, especially for sensitive people.",
     "Air Quality Alert|Air Stagnation Advisory")
_add(HazardFamily.OTHER_SAFETY, DeliveryBehavior.BRIEFING_ONLY, "Review the official outlook and monitor updates.",
     "Hazardous Weather Outlook|Special Weather Statement|Marine Weather Statement|Short Term Forecast|Tropical Cyclone Local Statement")

_ADMINISTRATIVE = {
    "administrative message", "test", "911 telephone outage", "child abduction emergency",
    "blue alert", "law enforcement warning", "civil emergency message",
}


def classify_alert(alert: Any) -> HazardPolicy:
    """Classify one official event, retaining safe fallbacks for new event names."""
    event = str(getattr(alert, "event", "") or "").strip()
    key = event.casefold()
    base = _POLICIES.get(key)
    if key == "severe thunderstorm warning":
        tag = str(getattr(alert, "thunderstorm_damage_threat", "") or "").casefold()
        if tag == "destructive":
            return HazardPolicy(HazardFamily.CONVECTION, DeliveryBehavior.CRITICAL,
                                "Move indoors now and stay away from windows.")
    if key == "flash flood warning":
        tag = str(getattr(alert, "flash_flood_damage_threat", "") or "").casefold()
        if tag in {"considerable", "catastrophic"}:
            return HazardPolicy(HazardFamily.FLOOD, DeliveryBehavior.CRITICAL,
                                "Move to higher ground now. Never drive through floodwater.")
    if base is not None:
        return base
    if key in _ADMINISTRATIVE or not event:
        return HazardPolicy(HazardFamily.OTHER_SAFETY, DeliveryBehavior.IGNORE, "", False)
    if key.endswith("warning"):
        return HazardPolicy(
            HazardFamily.OTHER_SAFETY,
            DeliveryBehavior.IMPORTANT,
            "Review the official warning and follow local safety instructions.",
            False,
        )
    if key.endswith("watch"):
        return HazardPolicy(
            HazardFamily.OTHER_SAFETY,
            DeliveryBehavior.AWARENESS,
            "Prepare to act and monitor official updates.",
            False,
        )
    if key.endswith("advisory") or key.endswith("statement") or key.endswith("alert"):
        return HazardPolicy(
            HazardFamily.OTHER_SAFETY,
            DeliveryBehavior.NOTICE,
            "Review the official notice and adjust plans if needed.",
            False,
        )
    return HazardPolicy(HazardFamily.OTHER_SAFETY, DeliveryBehavior.IGNORE, "", False)


def family_enabled(profile: Any, policy: HazardPolicy, event: str | None = None) -> bool:
    if event and event.strip().casefold() in getattr(profile, "life_safety_events", ()) and not policy.critical_capable:
        return False
    events = getattr(profile, "alert_events", None)
    if events is not None and event is not None:
        return event.strip().casefold() in events
    selected = tuple(getattr(profile, "hazard_families", ()) or ())
    return not selected or policy.family.value in selected


def alert_choices() -> list[dict[str, Any]]:
    """Individual source-native choices; policy families are not enrollment bundles."""
    default_names = {"tornado warning", "severe thunderstorm warning", "flash flood warning",
                     "dense fog advisory", "wind advisory", "high wind warning",
                     "hurricane warning", "hurricane force wind warning"}
    choices = [{"value":key,"label":_EVENT_NAMES[key],"family":policy.family.value,
                "default":key in default_names or policy.family in {HazardFamily.WINTER,HazardFamily.COLD},
                "description":policy.action,"official_event":_EVENT_NAMES[key]}
               for key,policy in _POLICIES.items() if policy.automatic]
    choices.append({"value":"radar_hail","label":"Radar hail alerts","family":HazardFamily.CONVECTION.value,
                    "default":True,"description":"Radar-estimated hail approaching your location. Requires the enabled NOAA MRMS hail source; this is not a separate NWS warning polygon.","official_event":None})
    choices.append({"value":"severe_weather_awareness","label":"Severe weather heads-ups","family":HazardFamily.CONVECTION.value,
                    "default":False,"description":"Short-term SPC discussions and severe-weather forecast heads-ups from enabled sources. These are not warnings.","official_event":None})
    common = ("tornado warning","severe thunderstorm warning","radar_hail","flash flood warning",
              "dense fog advisory","wind advisory","high wind warning","hurricane warning",
              "hurricane force wind warning")
    return sorted(choices,key=lambda item:(common.index(item["value"]) if item["value"] in common else len(common),
                                           not item["default"],item["label"]))


def hail_enabled(profile: Any) -> bool:
    if profile is None:
        return False
    events = getattr(profile,"alert_events",None)
    if events is not None:
        return "radar_hail" in events
    selected = tuple(getattr(profile,"hazard_families",()) or ())
    return not selected or HazardFamily.CONVECTION.value in selected


def briefing_item_enabled(profile: Any, item: Any) -> bool:
    if item.routine_forecast:
        return True
    events = getattr(profile,"alert_events",None)
    if events is None:
        families = tuple(getattr(profile,"hazard_families",()) or ())
        return not families or item.family in families
    native = str(item.native_level).casefold()
    if native in _POLICIES:
        return native in events
    if item.source in {"SPC outlook","SPC mesoscale discussion","NWS forecast"}:
        return "severe_weather_awareness" in events
    if "MRMS" in item.source:
        return "radar_hail" in events
    families = {_POLICIES[key].family.value for key in events if key in _POLICIES}
    return item.family in families
