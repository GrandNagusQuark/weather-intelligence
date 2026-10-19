"""Account/device-scoped DND choices; no phone permissions or sends here."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import re
from typing import Any, Mapping

from .avalanche_region import home_avalanche_region, valid_home_point
from .alert_sources import alert_source_note
from .hazard_policy import DeliveryBehavior, _POLICIES, alert_choices, classify_alert

DND_FIELDS = ("dnd_bypass_mode", "dnd_bypass_rules", "dnd_bypass_confirmed", "home_avalanche_exposure", "home_avalanche_location", "regional_tropical_event", "home_avalanche_region")
DND_STAGES = {"dnd_options", "dnd_customize", "dnd_confirm"}
_CONDITIONAL = {
    "severe thunderstorm warning": [
        ("life", "Severe Thunderstorm Warning — destructive", "Only warnings marked destructive by NWS.", "life_safety"),
        ("water_wind", "Severe Thunderstorm Warning — on water", "Weather Intelligence requires fresh GPS confidently inside mapped water and an NWS maximum-wind-gust tag of at least 34 knots (about 39 mph). Near-shore proximity alone does not qualify; bridges can remain ambiguous.", "on_water_wind")],
    "flash flood warning": [
        ("catastrophic", "Flash Flood Warning — catastrophic", "Only warnings marked catastrophic by NWS, including Flash Flood Emergencies.", "catastrophic"),
        ("barrier", "Flash Flood Warning — dam or levee emergency", "Imminent or occurring failure, breach, or overtopping of a dam, levee, or other water-retaining structure identified in the NWS warning.", "barrier_failure")],
    "radar_hail": [("life", "Approaching hail — destructive", "Weather Intelligence uses repeated NOAA MRMS radar estimates of hail at least 2.75 inches across.", "life_safety")],
    "blizzard warning": [("driving", "Blizzard Warning — while driving", "NWS warning; Weather Intelligence also requires recent, confident vehicle travel reported by this phone's Companion app.", "driving")],
    "ice storm warning": [("driving", "Ice Storm Warning — while driving", "NWS warning; Weather Intelligence also requires recent, confident vehicle travel reported by this phone's Companion app.", "driving")],
    **{event: [("water_wind", event.title() + " — on water",
               "NWS wind warning; Weather Intelligence also requires fresh GPS confidently inside mapped water and winds of at least 34 knots (about 39 mph), established by the product's threshold or an explicit NWS wind tag. This is an estimated on-water condition, not proof of boating or safe navigation.", "on_water_wind")]
       for event in ("high wind warning", "gale warning", "storm warning",
                     "hurricane force wind warning", "tropical storm warning")},
}


def clear_dnd_choices(state: dict[str, Any]) -> None:
    for field in DND_FIELDS[:3]:
        state.pop(field, None)


def dnd_choices(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Offer only received alerts, preserving narrower life-safety conditions."""
    path, answers = state.get("alert_path"), state.get("alert_answers") or {}
    life_preset = path in {"life_only", "life_plus"}
    regional = state.get("regional_tropical_event", "hurricane")
    result = []
    for item in alert_choices():
        event = item["value"]
        if event.startswith("typhoon ") and regional != "typhoon":
            continue
        if event in {"hurricane warning", "hurricane watch"} and regional == "typhoon":
            continue
        policy = _POLICIES.get(event)
        critical = bool(policy and policy.behavior == DeliveryBehavior.CRITICAL)
        selected = (path == "all" or (life_preset and critical)
                    or bool(answers.get(event, item["default"] if path != "life_only" else False)))
        conditional = event in _CONDITIONAL and (selected or (life_preset and event in {"severe thunderstorm warning", "flash flood warning", "radar_hail"}))
        if conditional:
            for prefix, title, detail, scope in _CONDITIONAL[event]:
                result.append({"id": prefix + ":" + event, "event": event, "title": title,
                               "detail": detail, "scope": scope, "default": True})
        if selected:
            default = critical or event == "tsunami advisory" or (event == "avalanche warning" and state.get("home_avalanche_region") is True)
            title = item["label"] + (" — all selected conditions" if conditional else "")
            detail = "" if not conditional else "Also allows the other conditions you chose to receive."
            if event == "special marine warning" and state.get("marine_warning_mode") == "on_water":
                detail = "Only when your current location is identified as being on water."
            if event == "avalanche warning" and default:
                detail = "Your home is within an Avalanche.org forecast region."
            result.append({"id": "event:" + event, "event": event, "title": title,
                           "detail": detail, "scope": "all", "default": default})
            if event in {"hurricane warning", "typhoon warning", "hurricane watch", "typhoon watch"}:
                tier = event.rsplit(" ", 1)[1]
                result[-1]["events"] = ["hurricane " + tier, "typhoon " + tier]
    for rule in result:
        rule["source_note"] = alert_source_note(rule["event"])
    return result


def dnd_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    choices = dnd_choices(state)
    defaults = [item for item in choices if item["default"]]
    allowed = {item["id"] for item in choices}
    saved = state.get("dnd_bypass_rules")
    selected = ([item for item in saved if isinstance(item, str) and item in allowed] if isinstance(saved, list)
                else [item["id"] for item in defaults])
    if state.get("dnd_bypass_mode") == "default" and state.get("home_avalanche_region") is not True:
        selected = [rule_id for rule_id in selected if rule_id != "event:avalanche warning"]
    if state.get("dnd_bypass") is False:
        selected = []
    return {"choices": choices, "defaults": defaults, "selected": selected,
            "mode": state.get("dnd_bypass_mode"),
            "confirmed": state.get("dnd_bypass_confirmed") is True}


def home_context(hass: Any) -> tuple[str, str]:
    """Keep home coordinates internal. Region only labels setup aliases."""
    config = getattr(hass, "config", None)
    latitude, longitude = getattr(config, "latitude", None), getattr(config, "longitude", None)
    valid = valid_home_point(latitude, longitude)
    key = f"{latitude:.5f},{longitude:.5f}" if valid else ""
    regional = "typhoon" if valid and 0 <= latitude <= 45 and 100 <= longitude <= 180 else "hurricane"
    return key, regional


def apply_home_context(state: dict[str, Any], hass: Any) -> None:
    _, regional = home_context(hass)
    in_region = home_avalanche_region(hass) is True
    drafts = state.get("device_drafts") or {}
    for choices in [state, *drafts.values()]:
        choices.pop("home_avalanche_exposure", None)
        choices.pop("home_avalanche_location", None)
        choices["regional_tropical_event"] = regional
        choices["home_avalanche_region"] = in_region
        rules = choices.get("dnd_bypass_rules")
        if choices.get("dnd_bypass_mode") != "default" or not isinstance(rules, list):
            continue
        wants_avalanche = (choices.get("dnd_bypass") is True and any(
            item["event"] == "avalanche warning" and item["default"] for item in dnd_choices(choices)))
        if ("event:avalanche warning" in rules) != wants_avalanche:
            choices["dnd_bypass_rules"] = [rule_id for rule_id in rules if rule_id != "event:avalanche warning"]
            if wants_avalanche:
                choices["dnd_bypass_rules"].append("event:avalanche warning")
            choices["dnd_bypass_confirmed"] = False
            if choices.get("stage") in {"daily_outlook", "notification_setup"}:
                choices["stage"] = "dnd_confirm"


def enter_dnd_review(state: dict[str, Any]) -> None:
    state["dnd_bypass_confirmed"] = False
    if state.get("dnd_bypass") is True:
        state["stage"] = "dnd_options"
    else:
        state.update(stage="dnd_confirm", dnd_bypass_rules=[])
        state.pop("dnd_bypass_mode", None)


def apply_dnd_action(state: dict[str, Any], payload: Mapping[str, Any]) -> bool:
    action = payload.get("workflow_action")
    if action not in {"dnd_default", "dnd_custom", "dnd_toggle", "dnd_customize_next", "dnd_back"}:
        return False
    state["dnd_bypass_confirmed"] = False
    if action == "dnd_default":
        state.update(dnd_bypass_mode="default", dnd_bypass_rules=[item["id"] for item in dnd_snapshot(state)["defaults"]], stage="dnd_confirm")
    elif action == "dnd_custom":
        state["dnd_bypass_rules"] = dnd_snapshot(state)["selected"]
        state.update(dnd_bypass_mode="custom", stage="dnd_customize")
    elif action == "dnd_toggle":
        view = dnd_snapshot(state)
        rule = next((item for item in view["choices"] if item["id"] == payload.get("dnd_rule")), None)
        if rule is None:
            raise ValueError("Choose one of your available alert types on this page.")
        selected = set(view["selected"])
        if rule["id"] in selected:
            selected.remove(rule["id"])
        else:
            # Narrow scopes can coexist; all conditions replaces narrower rules.
            selected.difference_update(item["id"] for item in view["choices"] if item["event"] == rule["event"] and (rule["scope"] == "all" or item["scope"] == "all"))
            selected.add(rule["id"])
        state["dnd_bypass_rules"] = [item["id"] for item in view["choices"] if item["id"] in selected]
    elif action == "dnd_customize_next":
        state["dnd_bypass_rules"] = dnd_snapshot(state)["selected"]
        state["stage"] = "dnd_confirm"
    else:
        previous = state["stage"]
        if previous == "dnd_confirm" and state.get("dnd_bypass"):
            state["stage"] = "dnd_customize" if state.get("dnd_bypass_mode") == "custom" else "dnd_options"
        else:
            state["stage"] = "dnd_options" if previous == "dnd_customize" else "alert_dnd"
    return True


_FAILURE_TAG = re.compile(r"(?im)^\s*(?:DAM|LEVEE)\s+FAILURE\s*\.{2,}\s*(?:IMMINENT|OCCURRING)\b")
_STRUCTURE = re.compile(r"\b(?:dams?|levees?|dikes?|dykes?|floodwalls?|spillways?|embankments?|(?:water[ -])?retaining (?:walls?|structures?))\b", re.I)
_NEGATED = re.compile(r"\b(?:no|not|never|unlikely|historical|previously|yesterday|last (?:year|month|week)|routine|controlled release)\b", re.I)
_FAILURE = re.compile(r"\bimminent\s+(?:failure|breach|overtopping)\b|\b(?:failure|breach|overtopping)(?:\s+of\b[^.;\n]{1,120}?)?\s+(?:is\s+)?(?:imminent|occurring|ongoing|underway)|\b(?:is|are|has|have)\s+(?:(?:now|already|currently|actively|being|been)\s+)*(?:failing|failed|breaching|breached|overtopping|overtopped)\b", re.I)


def barrier_emergency(alert: Any) -> bool:
    """Affirmative official evidence only, not a dam name or river crest."""
    text = "\n".join(str(getattr(alert, key, "") or "") for key in ("headline", "description"))
    if _FAILURE_TAG.search(text):
        return True
    raw = getattr(alert, "raw_official_payload", {}) or {}
    properties = raw.get("properties", {}) if isinstance(raw, Mapping) else {}
    parameters = properties.get("parameters", {}) if isinstance(properties, Mapping) else {}
    for key in ("damFailure", "leveeFailure"):
        values = parameters.get(key, []) if isinstance(parameters, Mapping) else []
        values = [values] if isinstance(values, str) else values
        if isinstance(values, (list, tuple)) and any(str(value).upper().strip() in {"IMMINENT", "OCCURRING"} for value in values):
            return True
    for sentence in re.split(r"[.!?\n]+", text):
        if len(sentence) <= 600 and _STRUCTURE.search(sentence) and not _NEGATED.search(sentence) and _FAILURE.search(sentence):
            return True
    return False


def driving_assessment(hass: Any, mobile_entry_id: str, now: datetime) -> bool | None:
    """Compatibility entry point for the shared, registration-scoped activity reader."""
    from .device_activity import driving_assessment as read_driving_assessment

    return read_driving_assessment(hass, mobile_entry_id, now)


def rule_matches(rule: Mapping[str, Any], alert: Any, *, driving: bool | None = None,
                 hail_destructive: bool = False, on_water_wind: bool = False) -> bool:
    """Call after the existing subscription, active-alert and location checks."""
    if str(getattr(alert, "event", "")).casefold() not in rule.get("events", [rule["event"]]):
        return False
    scope = rule["scope"]
    if scope == "catastrophic":
        return str(getattr(alert, "flash_flood_damage_threat", "")).casefold() == "catastrophic"
    if scope == "barrier_failure":
        return barrier_emergency(alert)
    if scope == "driving":
        return driving is True
    if scope == "on_water_wind":
        return on_water_wind is True
    if scope == "life_safety":
        return hail_destructive if rule["event"] == "radar_hail" else classify_alert(alert).critical_capable
    return scope == "all"


@lru_cache(maxsize=1)
def delivery_rules() -> dict[str, dict[str, Any]]:
    """Canonical scopes, independent of an onboarding screen's regional defaults."""
    rules = {}
    for choice in alert_choices():
        event = choice["value"]
        rules["event:" + event] = {"event": event, "scope": "all"}
        if event in {"hurricane warning", "typhoon warning", "hurricane watch", "typhoon watch"}:
            tier = event.rsplit(" ", 1)[1]
            rules["event:" + event]["events"] = ["hurricane " + tier, "typhoon " + tier]
    for event, conditions in _CONDITIONAL.items():
        for prefix, _title, _detail, scope in conditions:
            rules[prefix + ":" + event] = {"event": event, "scope": scope}
    return rules


def valid_rule_ids() -> set[str]:
    return set(delivery_rules())


def profile_bypasses_dnd(hass: Any, profile: Any, alert: Any, now: datetime, *, hail_destructive: bool = False,
                        water_assessment: Any = None) -> bool:
    if not profile.critical_notifications:
        return False
    if profile.dnd_rule_ids is None:
        return hail_destructive or classify_alert(alert).critical_capable
    rules = delivery_rules()
    selected = [rules[rule_id] for rule_id in profile.dnd_rule_ids if rule_id in rules]
    driving = None
    if any(rule["scope"] == "driving" and rule["event"] == str(alert.event).casefold() for rule in selected):
        try:
            driving = driving_assessment(hass, profile.companion_device_id, now)
        except (ImportError, AttributeError, KeyError):
            driving = None
    from .marine_wind import on_water_wind_qualifies
    on_water_wind = on_water_wind_qualifies(alert, water_assessment, now) if any(
        rule["scope"] == "on_water_wind" and rule["event"] == str(alert.event).casefold() for rule in selected) else False
    return any(rule_matches(rule, alert, driving=driving, hail_destructive=hail_destructive,
                           on_water_wind=on_water_wind) for rule in selected)
