"""Plain-language alert pages and persisted, non-enrolling setup choices.

Issuing criteria are researched from official sources, not copied product text.
Regional criteria are described as regional, never substituted with one office's
numeric thresholds. Historical names remain separate because the existing
catalog accepts them. These pages do not change the production hazard policy.
"""
from __future__ import annotations

from typing import Any, Mapping

from .alert_sources import alert_source_note
from .hazard_policy import DeliveryBehavior, _POLICIES, alert_choices
from .onboarding_dnd import DND_FIELDS

# References for the numeric criteria and source-native distinctions below.
CRITERIA_SOURCES = (
    "https://www.weather.gov/lot/SevereThunderstormWarningsUpdate",
    "https://www.weather.gov/impacts/understanding",
    "https://www.weather.gov/box/criteria",
    "https://www.weather.gov/car/Warning_Criteria",
    "https://www.weather.gov/ind/criteria",
    "https://www.weather.gov/safety/winter-snow-squall",
    "https://www.weather.gov/safety/cold-ww",
    "https://www.weather.gov/lwx/heat",
    "https://www.weather.gov/safety/tsunami-alerts",
    "https://www.weather.gov/safety/airquality-volcanic-ash",
    "https://www.weather.gov/safety/wind-dust-storm",
    "https://www.nhc.noaa.gov/aboutgloss.shtml",
    "https://www.nhc.noaa.gov/surge/warning/",
)

_TRIGGERS = {
    "tornado warning": "A tornado has been reported, or radar indicates one may be developing or occurring.",
    "severe thunderstorm warning": "A thunderstorm is expected to produce wind gusts of at least 58 mph, hail at least 1 inch across, or both. The most destructive warnings describe winds of at least 80 mph or hail at least 2.75 inches across.",
    "radar_hail": "Weather Intelligence looks for radar-estimated hail at least 1 inch across moving toward your location. Two recent observations must agree on its approach, with an estimated closest approach within 18 minutes. Repeated estimates of at least 2.75 inches trigger the destructive-hail tier. This requires the radar hail source and is an estimate, not a separate official warning.",
    "flash flood warning": "Rapid flooding is occurring or expected soon, including from heavy rain, a failed dam, or an ice jam. There is no single rainfall amount that triggers it: drainage, terrain, and existing water levels matter. The highest-risk warnings identify an unusually dangerous or catastrophic threat.",
    "dense fog advisory": "Fog is expected to make travel difficult by sharply reducing visibility, commonly to a quarter mile or less on land. Local duration rules and marine visibility thresholds can differ.",
    "wind advisory": "Winds are strong enough to affect driving and loose objects but remain below the local high-wind warning threshold.",
    "high wind warning": "Damaging winds are occurring or expected. Common thresholds are sustained winds of at least 40 miles per hour for an hour, or gusts of at least 58 miles per hour.",
    "hurricane warning": "A tropical system is expected to bring sustained winds of at least 74 miles per hour to the affected area.",
    "hurricane force wind warning": "A non-tropical storm is expected to produce sustained winds or frequent gusts of at least 64 knots, about 74 mph, over marine waters.",
    "avalanche advisory": "An avalanche authority identifies unstable snow or another avalanche concern. It is not based on a fixed snowfall amount; slope, snow layers, and local conditions determine the risk.",
    "avalanche warning": "An avalanche authority expects or observes dangerous avalanche activity that could threaten people, roads, or buildings. Snowpack stability and terrain matter more than a universal snow-depth threshold.",
    "avalanche watch": "Avalanche forecasters expect changing snow or weather conditions that could make dangerous avalanches more likely.",
    "blizzard warning": "Winds of at least 35 mph combine with falling or blowing snow to reduce visibility to a quarter mile or less for at least three hours. New snowfall is not required if existing snow is blowing around.",
    "blowing snow advisory": "Wind lifts existing snow enough to make driving visibility hazardous, without meeting the full blizzard criteria. The local office considers visibility, duration, and travel impacts rather than new snowfall alone.",
    "cold weather advisory": "Cold air or wind chill reaches the area's advisory threshold and creates a health risk, but is below the extreme-cold warning level. The temperature cutoff depends on the local climate.",
    "extreme cold warning": "Air temperature or wind chill is expected to reach the area's extreme-cold threshold. Dangerous exposure can occur quickly; there is no single nationwide temperature cutoff.",
    "extreme cold watch": "Air temperature or wind chill may reach the area's extreme-cold warning threshold. The timing or severity is still uncertain.",
    "freeze warning": "Widespread temperatures at or below 32°F are expected during the locally defined growing season. This alert mainly concerns vulnerable plants and crops, not the same threshold as an extreme-cold health warning.",
    "freeze watch": "Widespread temperatures at or below 32°F are possible during the local growing season.",
    "freezing fog advisory": "Fog droplets can freeze onto roads and exposed surfaces when temperatures are at or below freezing. Even a thin glaze can make travel slippery; heavy snowfall is not necessary.",
    "freezing rain advisory": "Freezing rain or drizzle is expected to leave a slippery coating, but not enough ice to meet the local ice-storm warning criteria. A very small accumulation can affect untreated roads.",
    "frost advisory": "Weather conditions favor frost on plants during the growing season, often with clear skies, light winds, and temperatures in the mid-30s Fahrenheit. Frost can form even when the measured air temperature stays above freezing.",
    "hard freeze warning": "Temperatures are expected to stay cold enough for a damaging hard freeze, commonly around 28°F or lower during the growing season. The exact local criteria vary; some offices now use Freeze Warning instead.",
    "hard freeze watch": "A damaging hard freeze may develop, commonly with temperatures around 28°F or lower during the growing season. The expected duration and local crop vulnerability influence the decision.",
    "heavy freezing spray warning": "Sea spray is expected to build ice rapidly on boats and exposed equipment, generally at least about 0.8 inch per hour.",
    "heavy freezing spray watch": "Weather and sea conditions may produce rapid ice buildup on vessels, reaching the heavy-freezing-spray warning level.",
    "ice storm warning": "Freezing rain is expected to build enough ice to seriously affect travel, trees, and power lines. Local warning thresholds differ; many areas use a quarter inch, while others require more.",
    "lake effect snow warning": "A narrow band of snow produced by air moving over a lake is expected to reach the area's heavy-snow warning criteria. Snow amounts and travel impacts vary sharply over short distances.",
    "sleet advisory": "Accumulating ice pellets are expected to make roads slippery, but remain below local warning criteria.",
    "sleet warning": "A substantial accumulation of ice pellets is expected to seriously disrupt travel.",
    "sleet watch": "A significant accumulation of ice pellets may develop.",
    "snow advisory": "Snow is expected to create slippery travel and other disruptions below the local heavy-snow warning level.",
    "snow squall warning": "A brief, intense burst of snow and wind is expected to create sudden dangerous travel, such as near-whiteout visibility or rapidly freezing roads.",
    "wind chill advisory": "The combination of cold and wind reaches the area's advisory threshold for hazardous exposure.",
    "wind chill warning": "Cold and wind combine to make exposure extremely dangerous at the area's warning threshold.",
    "wind chill watch": "Cold and wind may combine to reach the area's extreme exposure threshold.",
    "winter storm warning": "Heavy snow, significant ice, sleet, or a combination is expected to cause serious winter-weather impacts. Snow and ice thresholds depend on local conditions; one nationwide accumulation number would be misleading.",
    "winter storm watch": "A storm may bring heavy snow, significant ice, or another combination that reaches local winter-storm warning criteria. The track, timing, or amount is still uncertain.",
    "winter weather advisory": "Snow, sleet, freezing rain, or a mix is expected to make travel hazardous without reaching the local warning level.",
    "air quality alert": "An air-quality authority expects or observes pollution high enough to warrant a health notice. Older adults and people with heart or lung conditions may be affected at lower pollution levels. As pollution worsens, it can also affect otherwise healthy people.",
    "air stagnation advisory": "Light winds and stable air are expected to trap pollution near the ground.",
    "ashfall advisory": "Volcanic ash is expected to fall in amounts that can affect breathing, visibility, and equipment.",
    "ashfall warning": "A significant amount of volcanic ash is expected to accumulate at the surface and cause serious impacts.",
    "beach hazards statement": "Dangerous beach conditions are expected, such as strong currents or other shoreline hazards.",
    "blowing dust advisory": "Windblown dust or sand is expected to reduce visibility enough to affect travel, but below the local warning level.",
    "blowing dust warning": "Widespread windblown dust or sand is expected to create dangerous visibility over an extended period.",
    "brisk wind advisory": "Strong winds threaten vessels in ice-covered waters.",
    "coastal flood advisory": "A rise in coastal water is expected to produce minor flooding, such as water on vulnerable shoreline roads.",
    "coastal flood statement": "Information about coastal water levels or limited shoreline flooding that may fall below advisory criteria.",
    "coastal flood warning": "Coastal water levels are expected to cause significant flooding that threatens roads, property, or people.",
    "coastal flood watch": "Coastal water levels may rise enough to cause significant flooding.",
    "dense smoke advisory": "Smoke is expected to reduce visibility enough to make travel hazardous, commonly to a quarter mile or less.",
    "dust advisory": "A short-lived dust event is expected to impair travel visibility without meeting dust-storm warning criteria.",
    "dust storm warning": "A moving wall or burst of dust is occurring or expected to cause sudden, severely reduced visibility.",
    "earthquake warning": "An official alert identifies an earthquake threat in the affected area.",
    "excessive heat warning": "Heat and humidity are expected to create a serious health risk at the area's warning level.",
    "excessive heat watch": "A dangerous heat episode may develop and reach the area's heat-warning level.",
    "extreme fire danger": "Dry vegetation and weather conditions, such as strong winds or low humidity, create exceptionally high fire danger.",
    "extreme heat warning": "Heat and humidity are expected to create a serious health risk at the area's warning level.",
    "extreme heat watch": "A dangerous heat episode may develop and reach the area's heat-warning level.",
    "extreme wind warning": "Exceptionally destructive winds, generally sustained at 115 miles per hour or higher, are occurring or about to begin.",
    "fire warning": "An official alert identifies a fire threatening people or property in the affected area.",
    "fire weather watch": "Dry vegetation and weather conditions, such as low humidity or strong winds, may allow fires to start or spread rapidly.",
    "flash flood watch": "Weather or other conditions may cause rapid flooding.",
    "flood advisory": "Rain or overflowing water is expected to cause limited flooding, such as in low spots or poorly drained streets, below the local warning level.",
    "flood statement": "An update on a flooding situation, including changes in water levels, timing, or whether the threat is ending.",
    "flood warning": "Flooding that can threaten people or property is occurring or expected.",
    "flood watch": "Conditions may cause flooding significant enough for a warning.",
    "freezing spray advisory": "Sea spray is expected to freeze onto a vessel and equipment at a lighter rate than the heavy-freezing-spray warning level.",
    "gale warning": "A non-tropical storm is expected to produce sustained winds or frequent gusts of 34–47 knots, about 39–54 mph, over marine waters.",
    "gale watch": "A non-tropical storm may produce sustained winds or frequent gusts of 34–47 knots, about 39–54 mph, over marine waters.",
    "hazardous seas warning": "Dangerous waves are expected to threaten vessels, even if wind criteria for another warning are not met.",
    "hazardous seas watch": "Wave conditions may reach the area's hazardous-seas warning level.",
    "heat advisory": "Heat and humidity are expected to create a health concern below the area's heat-warning level.",
    "high surf advisory": "Breaking waves are expected to make the shoreline dangerous.",
    "high surf warning": "Exceptionally large breaking waves are expected to cause severe shoreline hazards or damage.",
    "high wind watch": "Damaging winds may reach the area's High Wind Warning threshold.",
    "hurricane force wind watch": "A non-tropical marine storm may produce sustained winds or frequent gusts of at least 64 knots, about 74 mph.",
    "hurricane watch": "A tropical system may bring sustained winds of at least 74 miles per hour to the affected area.",
    "hydrologic outlook": "An early heads-up that flooding could develop, including from rising rivers, melting snow, or ice jams.",
    "lake wind advisory": "Winds are expected to create unsafe conditions on local lakes, particularly for smaller boats.",
    "lakeshore flood advisory": "Elevated lake water and waves are expected to produce minor flooding near shore.",
    "lakeshore flood statement": "Information or updates about lake water levels and possible shoreline flooding.",
    "lakeshore flood warning": "Lake water and waves are expected to produce significant shoreline flooding that threatens people or property.",
    "lakeshore flood watch": "Lake water and waves may cause significant shoreline flooding.",
    "low water advisory": "Water levels are expected to drop enough to make navigation hazardous or restrict access to harbors.",
    "red flag warning": "Dry vegetation and a combination of weather factors such as low humidity and strong winds are expected to allow fires to start or spread rapidly.",
    "rip current statement": "Conditions favor dangerous currents that can pull swimmers away from shore.",
    "river flood warning": "A river is expected to reach or exceed its locally established flood level.",
    "severe thunderstorm watch": "Conditions favor storms capable of wind gusts of at least 58 mph or hail at least 1 inch across.",
    "severe_weather_awareness": "An official severe-weather outlook or short-term storm discussion identifies a potential threat in your area.",
    "small craft advisory": "Winds or waves are expected to make conditions hazardous for smaller vessels.",
    "special marine warning": "A sudden marine hazard is occurring or expected, such as thunderstorm winds of at least 34 knots—about 39 miles per hour—hail at least three-quarters of an inch across, or a waterspout.",
    "storm surge warning": "Water pushed inland from the sea by a tropical system is expected to cause life-threatening flooding, generally within 36 hours.",
    "storm surge watch": "Water pushed inland from the sea by a tropical system may cause life-threatening flooding, generally within 48 hours.",
    "storm warning": "A non-tropical storm is expected to produce sustained winds or frequent gusts of 48–63 knots—about 55–73 miles per hour—over marine waters.",
    "storm watch": "A non-tropical marine storm may produce sustained winds or frequent gusts reaching those speeds.",
    "tornado watch": "Weather conditions favor storms that could produce tornadoes.",
    "tropical storm warning": "A tropical system is expected to bring sustained winds of 39–73 miles per hour to the affected area.",
    "tropical storm watch": "A tropical system may bring sustained winds of 39–73 miles per hour to the affected area.",
    "tsunami advisory": "A tsunami may create dangerous waves and currents for people in or near the water, even when widespread flooding inland is not expected.",
    "tsunami warning": "A tsunami capable of dangerous coastal flooding is expected or occurring.",
    "tsunami watch": "A distant earthquake or other event may have generated a tsunami that could later affect the area.",
    "typhoon warning": "A tropical system is expected to bring sustained winds of at least 74 miles per hour to the affected area.",
    "typhoon watch": "A tropical system may bring sustained winds of at least 74 miles per hour to the affected area.",
    "volcano warning": "An official alert identifies danger from a volcanic eruption in the affected area.",
}

_PLAIN_LABELS = {
    "severe thunderstorm warning": "Severe storms",
    "radar_hail": "Approaching hail",
    "severe_weather_awareness": "Severe-weather heads-ups",
}

SPECIAL_MARINE_EVENT = "special marine warning"
MARINE_WARNING_MODES = {"always", "on_water"}
ALERT_PAGES_VERSION = 3
AUTOMATIC_WATCH_WARNINGS = {"tornado warning", "severe thunderstorm warning"}


def alert_pages() -> list[dict[str, Any]]:
    """One individually explained page for every existing selectable event."""
    pages = []
    for choice in alert_choices():
        key = choice["value"]
        # Missing authored copy must fail visibly during development, not silently
        # substitute a generic warning or omit a selectable safety product.
        trigger = _TRIGGERS[key]
        policy = _POLICIES.get(key)
        pages.append({
            "id": key, "title": _PLAIN_LABELS.get(key, choice["label"]),
            "conditions": trigger, "action": choice["description"],
            "source_note": alert_source_note(key),
            "recommended": bool(choice["default"]),
            "always_life_safety": bool(policy and policy.behavior == DeliveryBehavior.CRITICAL),
            "includes_life_safety": key in {"severe thunderstorm warning", "flash flood warning", "radar_hail"},
        })
    return pages


def _individual_pages(path: str | None) -> list[dict[str, Any]]:
    """Original page order, retained to interpret saved pre-pairing cursors."""
    if path == "life_plus":
        return [page for page in alert_pages() if not page["always_life_safety"] or page["id"] == SPECIAL_MARINE_EVENT]
    if path == "life_only":
        return [page for page in alert_pages() if page["id"] == SPECIAL_MARINE_EVENT]
    return alert_pages() if path == "choose_all" else []


def _paired_pages_v2(path: str | None) -> list[dict[str, Any]]:
    """Present matching warning/watch events together, retaining both event IDs."""
    if path not in {"choose_all", "life_plus", "life_only"}:
        return []
    catalog = alert_pages()
    by_id = {page["id"]: page for page in catalog}
    watch_for = {
        key: key.removesuffix(" warning") + " watch"
        for key in by_id if key.endswith(" warning")
        and key.removesuffix(" warning") + " watch" in by_id
    }
    # These source-native names describe the same fire-weather hazard.
    watch_for["red flag warning"] = "fire weather watch"
    paired_watches = set(watch_for.values())
    pages = []
    for original in catalog:
        if original["id"] in paired_watches:
            continue
        page = dict(original)
        watch_id = watch_for.get(page["id"])
        if watch_id:
            page["watch"] = dict(by_id[watch_id])
            page["title"] = ("Fire weather" if page["id"] == "red flag warning"
                             else page["title"].removesuffix(" Warning"))
            page["watch_automatic"] = page["id"] in AUTOMATIC_WATCH_WARNINGS
        if path == "life_only" and page["id"] != SPECIAL_MARINE_EVENT:
            continue
        if (path == "life_plus" and page["always_life_safety"]
                and page["id"] != SPECIAL_MARINE_EVENT
                and (not watch_id or page["watch_automatic"])):
            continue
        pages.append(page)
    return pages


APP_DEFINED_EVENTS = {"radar_hail", "severe_weather_awareness"}
INTEGRATION_TRANSITION = "_weather_intelligence_alerts_intro"
OPTIONAL_TIERS = ("advisory", "watch", "statement")


def _event_ids(item: Mapping[str, Any]) -> list[str]:
    return item.get("event_ids", [item["id"]])


def page_event_ids(page: Mapping[str, Any]) -> list[str]:
    """All canonical identities represented by a hazard; intros have none."""
    if page.get("kind") == "transition":
        return []
    return _event_ids(page) + [event for tier in OPTIONAL_TIERS if page.get(tier)
                              for event in _event_ids(page[tier])]


def selectable_pages(path: str | None) -> list[dict[str, Any]]:
    """Group related tiers without merging or deleting their saved event IDs."""
    if path not in {"choose_all", "life_plus", "life_only"}:
        return []
    catalog = alert_pages()
    by_id = {page["id"]: page for page in catalog}
    # Explicit cross-name relationships; other matching stems are paired below.
    groups = {
        "hurricane warning": {"aliases": ["typhoon warning"], "watch": ["hurricane watch", "typhoon watch"], "title": "Hurricane / Typhoon"},
        "extreme heat warning": {"aliases": ["excessive heat warning"], "watch": ["extreme heat watch", "excessive heat watch"], "advisory": ["heat advisory"], "title": "Extreme / Excessive Heat"},
        "extreme cold warning": {"advisory": ["cold weather advisory"]},
        "high wind warning": {"advisory": ["wind advisory"]},
        "winter storm warning": {"advisory": ["winter weather advisory"]},
        "freeze warning": {"advisory": ["frost advisory"]},
        "heavy freezing spray warning": {"advisory": ["freezing spray advisory"]},
        "dust storm warning": {"advisory": ["dust advisory"]},
        "red flag warning": {"watch": ["fire weather watch"], "title": "Fire weather"},
    }
    for key in by_id:
        if not key.endswith(" warning"):
            continue
        group = groups.setdefault(key, {})
        stem = key.removesuffix(" warning")
        for tier in OPTIONAL_TIERS:
            candidate = stem + " " + tier
            if candidate in by_id:
                group.setdefault(tier, [candidate])
    absorbed = {event for group in groups.values()
                for tier in ("aliases", *OPTIONAL_TIERS) for event in group.get(tier, [])}
    pages = []
    for original in catalog:
        if original["id"] in absorbed:
            continue
        page = dict(original)
        group = groups.get(page["id"], {})
        page["event_ids"] = [page["id"], *group.get("aliases", [])]
        for tier in OPTIONAL_TIERS:
            if ids := group.get(tier):
                page[tier] = {**by_id[ids[0]], "event_ids": ids}
        if any(page.get(tier) for tier in OPTIONAL_TIERS):
            page["title"] = group.get("title", page["title"].removesuffix(" Warning"))
        page["watch_automatic"] = page["id"] in AUTOMATIC_WATCH_WARNINGS
        if page["id"] == "tornado warning":
            page["evidence"] = "Radar Indicated, or Observed (confirmed by radar or reliable reports)."
            page["damage_threat"] = "Base (standard warning), Considerable (PDS—Particularly Dangerous Situation), or Catastrophic (Tornado Emergency)."
        if path == "life_only" and page["id"] != SPECIAL_MARINE_EVENT:
            continue
        if (path == "life_plus" and page["always_life_safety"]
                and page["id"] != SPECIAL_MARINE_EVENT
                and not any(page.get(tier) and not (tier == "watch" and page["watch_automatic"])
                            for tier in OPTIONAL_TIERS)):
            continue
        pages.append(page)
    official = [page for page in pages if page["id"] not in APP_DEFINED_EVENTS]
    specific = [page for page in pages if page["id"] in APP_DEFINED_EVENTS]
    if specific:
        official.append({"id": INTEGRATION_TRANSITION, "kind": "transition",
                         "title": "Weather Intelligence alerts",
                         "conditions": "The following notifications are specific to Weather Intelligence. They may use official weather data, but they are not official warnings.",
                         "recommended": False, "always_life_safety": False, "includes_life_safety": False})
    return official + specific


def _page_cursor(state: Mapping[str, Any], pages: list[dict[str, Any]]) -> int:
    cursor = max(int(state.get("alert_cursor", 0)), 0)
    if state.get("alert_pages_version") != ALERT_PAGES_VERSION:
        old_pages = (_paired_pages_v2(state.get("alert_path")) if state.get("alert_pages_version") == 2
                     else _individual_pages(state.get("alert_path")))
        if old_pages:
            old_id = old_pages[min(cursor, len(old_pages) - 1)]["id"]
            for index, page in enumerate(pages):
                if old_id in page_event_ids(page):
                    return index
    return min(cursor, max(len(pages) - 1, 0))


def _save_cursor(state: dict[str, Any], index: int) -> None:
    state.update(alert_cursor=index, alert_pages_version=ALERT_PAGES_VERSION)


def _preset_watches(state: dict[str, Any]) -> None:
    if state.get("alert_path") in {"life_only", "life_plus", "all"}:
        answers = state.setdefault("alert_answers", {})
        for warning in AUTOMATIC_WATCH_WARNINGS:
            answers[warning.removesuffix(" warning") + " watch"] = True


def clear_alert_progress(state: dict[str, Any], *, clear_path: bool = True) -> None:
    for key in ("alert_answers", "alert_cursor", "alert_pages_version", "alert_selection_complete", "dnd_bypass", "marine_warning_mode", "marine_nearby_enabled", "marine_nearby_miles", *DND_FIELDS):
        state.pop(key, None)
    if clear_path:
        state.pop("alert_path", None)


def alert_setup_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    path = state.get("alert_path")
    pages = selectable_pages(path)
    answers = state.get("alert_answers") or {}
    cursor = _page_cursor(state, pages)
    page = pages[cursor] if pages else None
    inclusion_fixed = bool(page and page["always_life_safety"] and path in {"life_only", "life_plus"})
    enabled = True if inclusion_fixed else answers.get(page["id"], page["recommended"]) if page else None
    watch = (page or {}).get("watch")
    life_included = bool(page and path in {"life_only", "life_plus"}
                         and (page["always_life_safety"] or page["includes_life_safety"]))
    automatic_watch = bool(watch and page.get("watch_automatic"))
    watch_enabled = (bool(enabled or life_included) if automatic_watch else
                     bool(answers.get(watch["id"], watch["recommended"])) if watch else False)
    # Alias choices must be confirmed, but each tier is independently selectable.
    def values(item):
        return [bool(answers.get(event, by_id[event]["recommended"])) for event in _event_ids(item)]
    by_id = {item["id"]: item for item in alert_pages()}
    primary_values = values(page) if page and page.get("kind") != "transition" else []
    confirm_pair = bool(page and not inclusion_fixed and not life_included and
                        len(set(primary_values)) > 1)
    confirm_tiers = [tier for tier in OPTIONAL_TIERS if page and page.get(tier)
                     and not (tier == "watch" and automatic_watch)
                     and len(set(values(page[tier]))) > 1]
    optional = {tier + "_enabled": bool(answers.get(page[tier]["id"], page[tier]["recommended"]))
                if page and page.get(tier) else False
                for tier in ("advisory", "statement")}
    return {
        "page": page, "page_index": cursor, "page_count": len(pages),
        "enabled": enabled,
        "inclusion_fixed": inclusion_fixed,
        "watch_enabled": watch_enabled, "watch_automatic": automatic_watch,
        "confirm_pair": confirm_pair,
        "confirm_tiers": confirm_tiers, **optional,
        "marine_warning_mode": state.get("marine_warning_mode") if state.get("marine_warning_mode") in MARINE_WARNING_MODES else None,
        "marine_nearby_enabled": state.get("marine_nearby_enabled", False),
        "marine_nearby_miles": state.get("marine_nearby_miles", 10.0),
        "selection_complete": bool(state.get("alert_selection_complete")),
        "dnd_bypass": state.get("dnd_bypass"),
        "life_safety_included": path in {"life_only", "life_plus", "all"},
    }


def apply_alert_action(state: dict[str, Any], payload: Mapping[str, Any], previous_stage: str) -> None:
    """Persist one workflow action; no profile or notification is touched."""
    action = payload.get("alert_action")
    stage = state["stage"]
    if action == "start":
        if stage != "single_device_setup" or previous_stage != "single_device_setup" or not state.get("alert_path"):
            raise ValueError("Choose an alert setup path first.")
        pages = selectable_pages(state["alert_path"])
        if state["alert_path"] == "all":
            state["marine_warning_mode"] = "always"
        state["stage"] = "alert_choices" if pages else "alert_dnd"
        state["alert_selection_complete"] = not pages
        state.setdefault("alert_answers", {})
        # New combined cards use their representative defaults consistently.
        # Existing explicit alias differences still require confirmation.
        for page in pages:
            if page.get("kind") == "transition":
                continue
            for item in [page, *(page[tier] for tier in OPTIONAL_TIERS if page.get(tier))]:
                events = _event_ids(item)
                if len(events) > 1 and not any(event in state["alert_answers"] for event in events):
                    state["alert_answers"].update({event: bool(item["recommended"]) for event in events})
        _save_cursor(state, _page_cursor(state, pages))
        _preset_watches(state)
        return
    if action in {"answer", "watch_answer", "advisory_answer", "statement_answer", "marine_mode", "next", "previous"}:
        if stage != "alert_choices" or previous_stage != "alert_choices":
            raise ValueError("Open the individual alert page first.")
        view = alert_setup_snapshot(state)
        page = view["page"]
        if not page or payload.get("alert_event") != page["id"]:
            raise ValueError("This alert page changed. Reopen onboarding and try again.")
        if page.get("kind") == "transition" and action not in {"next", "previous"}:
            raise ValueError("Continue past the information page before choosing alerts.")
        if action == "answer":
            state.pop("dnd_bypass_confirmed", None)
            if view["inclusion_fixed"]:
                raise ValueError("This alert is included in the life-threatening preset. Choose when to receive it.")
            value = payload.get("alert_enabled")
            if type(value) is not bool:
                raise ValueError("Choose whether to include this alert.")
            answers = state.setdefault("alert_answers", {})
            for event in _event_ids(page):
                answers[event] = value
            for tier in OPTIONAL_TIERS:
                if not page.get(tier):
                    continue
                for event in _event_ids(page[tier]):
                    if tier == "watch" and view["watch_automatic"]:
                        answers[event] = bool(value or state["alert_path"] == "life_plus")
            _save_cursor(state, view["page_index"])
            return
        if action in {"watch_answer", "advisory_answer", "statement_answer"}:
            state.pop("dnd_bypass_confirmed", None)
            tier = action.removesuffix("_answer")
            item = page.get(tier)
            value = payload.get(tier + "_enabled")
            if not item or (tier == "watch" and view["watch_automatic"]) or type(value) is not bool:
                raise ValueError("Choose an available alert tier on its hazard page.")
            for event in _event_ids(item):
                state.setdefault("alert_answers", {})[event] = value
            _save_cursor(state, view["page_index"])
            return
        if action == "marine_mode":
            mode = payload.get("marine_warning_mode")
            if page["id"] != SPECIAL_MARINE_EVENT or mode not in MARINE_WARNING_MODES:
                raise ValueError("Choose a Special Marine Warning location preference on its setup page.")
            state["marine_warning_mode"] = mode
            from .marine_preferences import MARINE_NEARBY_FIELDS, marine_nearby_preferences
            state.update(marine_nearby_preferences({**state, **{key: payload[key] for key in MARINE_NEARBY_FIELDS if key in payload}}))
            _save_cursor(state, view["page_index"])
            return
        if action == "previous":
            if view["page_index"] == 0:
                state["stage"] = "single_device_setup"
            else:
                _save_cursor(state, view["page_index"] - 1)
            return
        # Next explicitly accepts either the saved answer or this page's default.
        if page["id"] == SPECIAL_MARINE_EVENT and view["enabled"] and state.get("marine_warning_mode") not in MARINE_WARNING_MODES:
            raise ValueError("Choose when to receive Special Marine Warnings before continuing.")
        if view["confirm_pair"] or view["confirm_tiers"]:
            raise ValueError("Confirm this combined hazard's choices before continuing.")
        if page.get("kind") != "transition":
            answers = state.setdefault("alert_answers", {})
            for event in _event_ids(page):
                answers.setdefault(event, view["enabled"])
            for tier in OPTIONAL_TIERS:
                if page.get(tier):
                    for event in _event_ids(page[tier]):
                        answers[event] = view[tier + "_enabled"]
        _save_cursor(state, view["page_index"])
        if view["page_index"] + 1 == view["page_count"]:
            state["alert_selection_complete"] = True
            state["stage"] = "alert_dnd"
        else:
            _save_cursor(state, view["page_index"] + 1)
        return
    if action == "back_to_alerts":
        if previous_stage != "alert_dnd" or stage != "alert_dnd":
            raise ValueError("Open alert delivery preferences first.")
        pages = selectable_pages(state.get("alert_path"))
        state["stage"] = "alert_choices" if pages else "single_device_setup"
        if pages:
            _save_cursor(state, len(pages) - 1)
        return
    if action == "notification_setup":
        if stage != "alert_dnd" or previous_stage != "alert_dnd" or type(state.get("dnd_bypass")) is not bool:
            raise ValueError("Choose a Do Not Disturb preference first.")
        # Old saved drafts may already be at DND from before the marine question.
        # Do not let those drafts silently bypass the new required preference.
        if state.get("marine_warning_mode") not in MARINE_WARNING_MODES:
            if state.get("alert_path") == "all":
                state["marine_warning_mode"] = "always"
            else:
                pages = selectable_pages(state.get("alert_path"))
                _save_cursor(state, next(i for i, page in enumerate(pages) if page["id"] == SPECIAL_MARINE_EVENT))
                state["stage"] = "alert_choices"
                return
        state["stage"] = "notification_setup"
        _preset_watches(state)
        return
    if action == "back_to_dnd":
        if stage != "notification_setup" or previous_stage != "notification_setup":
            raise ValueError("Open notification setup first.")
        state["stage"] = "alert_dnd"
        return
    if action is not None:
        raise ValueError("Unsupported alert setup action.")
    if "marine_warning_mode" in payload:
        raise ValueError("Choose a marine preference using its page controls.")
    if any(tier + "_enabled" in payload for tier in OPTIONAL_TIERS):
        raise ValueError("Choose optional tiers using the current alert page controls.")
    if stage in {"alert_choices", "alert_dnd", "notification_setup"} and stage != previous_stage:
        raise ValueError("Continue using the onboarding page controls.")

