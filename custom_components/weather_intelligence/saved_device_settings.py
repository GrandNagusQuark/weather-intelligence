"""Local, owner-scoped copies of device preferences, never phone enrollment."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .config import effective_entry_config
from .const import BRIEFING_LOCATION_BOTH, BRIEFING_LOCATION_HOME, BRIEFING_LOCATION_PERSON
from .hazard_policy import alert_choices
from .marine_preferences import MARINE_NEARBY_FIELDS, marine_nearby_preferences

SAVED_DEVICE_SETTINGS = "saved_device_settings"
MAX_NAMED_VERSIONS = 50
ADDITIONAL_PREFERENCE_FIELDS = ("receive_personal_alerts", "receive_home_while_away", "show_location_on_map", "briefing_location")
PREFERENCE_FIELDS = ("alert_path", "alert_answers", "alert_selection_complete",
    "dnd_bypass", "dnd_bypass_mode", "dnd_bypass_rules", "marine_warning_mode",
    "guided_answers", "daily_outlook_enabled", "daily_outlook_time", *ADDITIONAL_PREFERENCE_FIELDS, *MARINE_NEARBY_FIELDS)


def portable_preferences(value: Mapping[str, Any]) -> dict[str, Any]:
    """An allowlist prevents copying ownership, locations, tokens or permissions."""
    if not isinstance(value, Mapping):
        raise ValueError("Saved preferences are invalid.")
    result = {key: deepcopy(value[key]) for key in PREFERENCE_FIELDS if key in value}
    if result.get("alert_path") not in {"all", "life_only", "life_plus", "choose_all"}:
        return {}
    for key in ("dnd_bypass", "daily_outlook_enabled", "alert_selection_complete", "receive_personal_alerts", "receive_home_while_away"):
        if key in result and type(result[key]) is not bool:
            raise ValueError("Saved settings contain an invalid choice.")
    events = {item["value"] for item in alert_choices()}
    answers = result.get("alert_answers", {})
    if not isinstance(answers, Mapping) or any(key not in events or type(answer) is not bool for key, answer in answers.items()):
        raise ValueError("Saved alert choices are not supported.")
    if "marine_warning_mode" in result and result["marine_warning_mode"] not in {"always", "on_water"}:
        raise ValueError("Saved marine preference is not supported.")
    if any(key in result for key in MARINE_NEARBY_FIELDS):
        result.update(marine_nearby_preferences(result))
    if "dnd_bypass_mode" in result and result["dnd_bypass_mode"] not in {"default", "custom"}:
        raise ValueError("Saved DND preference is not supported.")
    if "briefing_location" in result and result["briefing_location"] not in {BRIEFING_LOCATION_BOTH, BRIEFING_LOCATION_HOME, BRIEFING_LOCATION_PERSON}:
        raise ValueError("Saved outlook location is not supported.")
    if "show_location_on_map" in result and result["show_location_on_map"] not in {"inherit", "show", "hide"}:
        raise ValueError("Saved map display choice is not supported.")
    rules = result.get("dnd_bypass_rules", [])
    if not isinstance(rules, list) or len(rules) > 256 or any(not isinstance(rule, str) or len(rule) > 150 for rule in rules):
        raise ValueError("Saved DND choices are not supported.")
    if "daily_outlook_time" in result:
        value = result["daily_outlook_time"]
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":" or not value[:2].isdigit() or not value[3:].isdigit() or int(value[:2]) > 23 or int(value[3:]) > 59:
            raise ValueError("Saved outlook time is invalid.")
    guided = result.get("guided_answers", {})
    if not isinstance(guided, Mapping) or any(key not in {"marine", "shoreline", "avalanche", "volcanic"} or type(answer) is not bool for key, answer in guided.items()):
        raise ValueError("Saved guided choices are not supported.")
    return result


def library_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    value = config.get(SAVED_DEVICE_SETTINGS)
    return deepcopy(value) if isinstance(value, dict) and value.get("version") == 1 else {"version": 1, "revision": 0, "owners": {}}


def capture_latest(library: dict[str, Any], state: Mapping[str, Any], devices: list[dict[str, str]], actor_id: str, *, seed_only: bool = False, previous_drafts: Mapping[str, Any] | None = None) -> bool:
    """Capture only the owner's own valid drafts after an authenticated save."""
    if state.get("target_user_id", actor_id) != actor_id:
        return False  # A draft cannot replace another owner's saved versions.
    owner = library.setdefault("owners", {}).setdefault(actor_id, {"latest": {}, "named": {}})
    changed = False
    for device in devices:
        draft = state.get("device_drafts", {}).get(device["id"], {})
        if draft.get("owner") != actor_id:
            continue
        preferences = portable_preferences(draft)
        if not preferences:
            continue
        previous = owner["latest"].get(device["id"])
        if previous and seed_only:
            continue
        if previous and previous_drafts is not None and preferences == portable_preferences(previous_drafts.get(device["id"], {})):
            continue
        if previous and previous.get("preferences") == preferences and previous.get("source_device_name") == device["name"]:
            continue
        owner["latest"][device["id"]] = {"id": "latest:" + device["id"], "name": "Latest settings · " + device["name"],
            "source_device_name": device["name"], "updated_at": datetime.now(timezone.utc).isoformat(),
            "preferences": preferences, "automatic": True}
        changed = True
    if changed:
        library["revision"] = int(library.get("revision", 0)) + 1
    return changed


def capture_profile_settings(library: dict[str, Any], hass: Any, config: Mapping[str, Any], actor_id: str, *, seed_only: bool = False) -> bool:
    """Read only profiles bound to this owner's actual Companion registration."""
    from .config import profiles_from_config
    from .const import CONF_BRIEFING_TIME, DEFAULT_BRIEFING_TIME
    from .onboarding_accounts import account_devices
    from .onboarding_preferences import profile_matches_device
    devices = account_devices(hass, actor_id)
    registrations = {entry.entry_id: entry for entry in hass.config_entries.async_entries("mobile_app")}
    drafts = {}
    for device in devices:
        profiles = [profile for profile in profiles_from_config(config) if profile_matches_device(hass, profile, registrations[device["id"]])]
        if len(profiles) != 1:
            continue
        profile = profiles[0]
        answers = {choice["value"]: choice["value"] in profile.alert_events if profile.alert_events is not None
                   else choice["family"] in profile.hazard_families for choice in alert_choices()}
        drafts[device["id"]] = {"owner": actor_id, "alert_path": "choose_all", "alert_answers": answers,
            "alert_selection_complete": True, "dnd_bypass": profile.critical_notifications,
            "marine_warning_mode": profile.marine_warning_mode, "daily_outlook_enabled": profile.daily_briefing,
            **{key: getattr(profile, key) for key in MARINE_NEARBY_FIELDS},
            "daily_outlook_time": profile.daily_outlook_time or str(config.get(CONF_BRIEFING_TIME, DEFAULT_BRIEFING_TIME)),
            "receive_personal_alerts": profile.receive_personal_alerts, "receive_home_while_away": profile.receive_home_while_away,
            "show_location_on_map": profile.show_location_on_map, "briefing_location": profile.briefing_location}
        if profile.dnd_rule_ids is not None:
            drafts[device["id"]].update(dnd_bypass_mode="custom", dnd_bypass_rules=list(profile.dnd_rule_ids))
        if profile.life_safety_events:
            drafts[device["id"]]["alert_path"] = "life_plus"
            for event in profile.life_safety_events:
                answers[event] = False
    return capture_latest(library, {"target_user_id": actor_id, "device_drafts": drafts}, devices, actor_id, seed_only=seed_only)


def saved_choices(library: Mapping[str, Any], owner_id: str) -> list[dict[str, Any]]:
    owner = library.get("owners", {}).get(owner_id, {})
    values = [*owner.get("latest", {}).values(), *owner.get("named", {}).values()]
    return sorted([{key: value.get(key) for key in ("id", "name", "source_device_name", "updated_at", "automatic")}
                   for value in values], key=lambda item: (not item["automatic"], item["name"].casefold()))


def resolve_saved_preferences(library: Mapping[str, Any], owner_id: str, settings_id: Any) -> dict[str, Any]:
    owner = library.get("owners", {}).get(owner_id, {})
    snapshot = next((value for value in [*owner.get("latest", {}).values(), *owner.get("named", {}).values()]
                     if value.get("id") == settings_id), None)
    if snapshot is None:
        raise ValueError("These saved settings are no longer available for this account.")
    preferences = portable_preferences(snapshot.get("preferences", {}))
    if not preferences:
        raise ValueError("These saved settings have no alert preferences to copy.")
    return preferences


async def async_manage_saved_settings(hass: Any, entry: Any, actor: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    from .onboarding_accounts import ACCOUNT_PROGRESS, account_devices, account_state, human_account, async_onboarding_snapshot
    from .onboarding_workflow import cache_choices, load_saved_preferences
    from .onboarding_dnd import apply_home_context
    if not human_account(actor):
        raise ValueError("An active Home Assistant account is required.")
    action = payload.get("action", "list")
    if action not in {"list", "save_named", "rename", "delete", "restore"}:
        raise ValueError("Choose a supported saved-settings action.")
    config = effective_entry_config(entry)
    library = library_from_config(config)
    devices = account_devices(hass, actor.id)
    # Existing durable drafts seed the automatic versions on first use.
    changed = capture_latest(library, account_state(config, actor.id), devices, actor.id, seed_only=True)
    if config.get("profiles"):
        changed = capture_profile_settings(library, hass, config, actor.id, seed_only=True) or changed
    if action != "list" and payload.get("expected_revision") != config.get(SAVED_DEVICE_SETTINGS, {}).get("revision", 0):
        raise ValueError("Saved settings changed in another tab. Reopen this page.")
    owner = library.setdefault("owners", {}).setdefault(actor.id, {"latest": {}, "named": {}})
    settings_id = payload.get("settings_id")
    if action == "restore":
        device_id = payload.get("device_id")
        if device_id not in {device["id"] for device in devices}:
            raise ValueError("Choose one of your available devices.")
        preferences = resolve_saved_preferences(library, actor.id, settings_id)
        state = account_state(config, actor.id)
        if payload.get("expected_onboarding_revision") != state.get("revision", 0):
            raise ValueError("Onboarding changed in another tab. Reopen saved settings.")
        state.update(target_user_id=actor.id, setup_mode="custom", device_count="single",
            selected_device_id=device_id, selected_device_ids=[device_id], active_device_index=0,
            initiated=True, workflow_version=2, revision=int(state.get("revision", 0)) + 1)
        state.pop("multiple_settings", None)
        state.pop("device_drafts", None)
        load_saved_preferences(state, preferences, include_intro=True)
        apply_home_context(state, hass)
        cache_choices(state)
        states = dict(config.get(ACCOUNT_PROGRESS, {}))
        states[actor.id] = state
        capture_latest(library, state, devices, actor.id)
        hass.config_entries.async_update_entry(entry, options={**entry.options, ACCOUNT_PROGRESS: states, SAVED_DEVICE_SETTINGS: library})
        return {"onboarding_snapshot": await async_onboarding_snapshot(hass, entry, actor)}
    if action in {"save_named", "rename"}:
        name = payload.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(character) < 32 for character in name):
            raise ValueError("Enter a name between 1 and 80 characters.")
    if action == "save_named":
        if len(owner["named"]) >= MAX_NAMED_VERSIONS:
            raise ValueError("You have 50 named versions. Remove one before saving another.")
        preferences = resolve_saved_preferences(library, actor.id, settings_id)
        identifier = uuid4().hex
        source = next(value for value in [*owner["latest"].values(), *owner["named"].values()] if value["id"] == settings_id)
        owner["named"][identifier] = {"id": identifier, "name": name.strip(), "source_device_name": source["source_device_name"],
            "updated_at": datetime.now(timezone.utc).isoformat(), "preferences": preferences, "automatic": False}
        changed = True
    elif action in {"rename", "delete"}:
        group = owner["latest"] if isinstance(settings_id, str) and settings_id.startswith("latest:") else owner["named"]
        key = settings_id.removeprefix("latest:") if group is owner["latest"] else settings_id
        if key not in group:
            raise ValueError("These saved settings are no longer available.")
        if group is owner["latest"]:
            raise ValueError("Automatic latest settings are maintained for each device. Save a named version to manage it separately.")
        if action == "rename":
            group[key]["name"] = name.strip()
        else:
            del group[key]
        changed = True
    if changed:
        library["revision"] = int(library.get("revision", 0)) + 1
        hass.config_entries.async_update_entry(entry, options={**entry.options, SAVED_DEVICE_SETTINGS: library})
    return {"revision": library["revision"], "settings": saved_choices(library, actor.id), "devices": devices,
            "onboarding_revision": account_state(effective_entry_config(entry), actor.id).get("revision", 0)}
