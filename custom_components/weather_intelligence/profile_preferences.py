"""Account-scoped edits to existing device alert choices, outside onboarding."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from .admin_actions import async_commit_profile_update
from .config import effective_entry_config, normalize_profiles, profile_to_dict
from .hazard_policy import alert_choices
from .onboarding_accounts import human_account
from .onboarding_alerts import APP_DEFINED_EVENTS, OPTIONAL_TIERS, page_event_ids, selectable_pages
from .onboarding_dnd import home_context
from .profile_dnd import apply_profile_dnd_changes, profile_dnd_catalog, profile_dnd_setup_status
from .marine_preferences import MARINE_NEARBY_FIELDS, marine_nearby_preferences


def _owner_id(hass: Any, profile: Mapping[str, Any]) -> str | None:
    person = hass.states.get(profile.get("person_entity"))
    return person.attributes.get("user_id") if person else None


def own_preferences_available(hass: Any, config: Mapping[str, Any], actor_id: str) -> bool:
    return any(_owner_id(hass, profile) == actor_id for profile in config.get("profiles", []))


def preference_pages(hass: Any) -> list[dict]:
    """Reuse the reviewed onboarding groups and criteria without their cursor."""
    pages = deepcopy(selectable_pages("choose_all"))
    regional = home_context(hass)[1]
    result = []
    for page in pages:
        if page.get("kind") == "transition":
            continue
        if page["id"] == "hurricane warning":
            page["title"] = "Typhoon" if regional == "typhoon" else "Hurricane"
        page["group_label"] = re.sub(
            r"\s+(warning|advisory|watch|statement|alert)$", "", page["title"], flags=re.IGNORECASE
        )
        page["section"] = "weather_intelligence" if page["id"] in APP_DEFINED_EVENTS else "official"
        for item in [page, *(page[tier] for tier in OPTIONAL_TIERS if page.get(tier))]:
            item.pop("action", None)
        result.append(page)
    return result


async def _active_actor(hass: Any, actor: Any) -> Any:
    fresh_actor = await hass.auth.async_get_user(actor.id)
    if not human_account(fresh_actor):
        raise ValueError("Sign in again before editing notification settings.")
    return fresh_actor


async def async_preferences_snapshot(hass: Any, entry: Any, actor: Any) -> dict:
    actor = await _active_actor(hass, actor)
    profiles = [
        profile_to_dict(profile)
        for profile in normalize_profiles(effective_entry_config(entry).get("profiles", []))
    ]
    visible = [
        profile for profile in profiles if actor.is_admin or _owner_id(hass, profile) == actor.id
    ]
    return {
        "profiles": visible,
        "pages": preference_pages(hass),
        "choices": alert_choices(),
        "dnd_catalog": profile_dnd_catalog(hass),
        "dnd_setup": {
            profile["profile_id"]: profile_dnd_setup_status(hass, entry, profile)
            for profile in visible
        },
        "notice_profile_ids": [
            profile["profile_id"] for profile in visible if _owner_id(hass, profile) != actor.id
        ],
    }


async def async_save_alert_preferences(
    hass: Any, entry: Any, actor: Any, payload: Mapping[str, Any]
) -> dict:
    actor = await _active_actor(hass, actor)
    config = effective_entry_config(entry)
    profiles = [
        profile_to_dict(profile) for profile in normalize_profiles(config.get("profiles", []))
    ]
    profile_id = payload.get("profile_id")
    previous = next((profile for profile in profiles if profile["profile_id"] == profile_id), None)
    if previous is None or (not actor.is_admin and _owner_id(hass, previous) != actor.id):
        raise ValueError("These notification settings are not available to this account.")
    if previous != payload.get("expected_profile"):
        raise ValueError("These settings changed. Reopen notification settings before saving.")
    choices = alert_choices()
    allowed = {choice["value"] for choice in choices}
    events, reviewed = payload.get("alert_events"), payload.get("reviewed_event_ids", [])
    if any(
        not isinstance(values, list)
        or any(not isinstance(event, str) or event not in allowed for event in values)
        for values in (events, reviewed)
    ):
        raise ValueError("Choose valid alert types from the notification editor.")
    selected, touched = set(events), set(reviewed)
    previous_events = (
        set(previous["alert_events"])
        if previous.get("alert_events") is not None
        else {
            choice["value"]
            for choice in choices
            if not previous.get("hazard_families")
            or choice["family"] in previous["hazard_families"]
        }
    )
    changed_events = touched | selected.symmetric_difference(previous_events)
    for page in preference_pages(hass):
        if page.get("watch_automatic") and changed_events.intersection(page_event_ids(page)):
            if selected.intersection(page.get("event_ids", [page["id"]])):
                selected.update(page["watch"].get("event_ids", [page["watch"]["id"]]))
    replacement = dict(previous)
    if selected != previous_events or touched.intersection(previous.get("life_safety_events", [])):
        replacement.update(
            {
                "alert_events": [
                    choice["value"] for choice in choices if choice["value"] in selected
                ],
                "hazard_families": sorted(
                    {choice["family"] for choice in choices if choice["value"] in selected}
                ),
                "life_safety_events": [
                    event
                    for event in previous.get("life_safety_events", [])
                    if event not in touched
                ],
            }
        )
    if "marine_warning_mode" in payload:
        if payload["marine_warning_mode"] not in {"always", "on_water"}:
            raise ValueError("Choose a valid marine notification preference.")
        replacement["marine_warning_mode"] = payload["marine_warning_mode"]
    replacement = apply_profile_dnd_changes(hass, replacement, selected, payload)
    if any(key in payload for key in MARINE_NEARBY_FIELDS):
        replacement.update(marine_nearby_preferences({**replacement, **{key: payload[key] for key in MARINE_NEARBY_FIELDS if key in payload}}))
    if replacement == previous:
        return previous
    updated = [
        replacement if profile["profile_id"] == profile_id else profile for profile in profiles
    ]
    updated = [profile_to_dict(profile) for profile in normalize_profiles(updated)]
    from .saved_device_settings import (
        SAVED_DEVICE_SETTINGS,
        capture_profile_settings,
        library_from_config,
    )

    updates = {"profiles": updated}
    library = library_from_config(config)
    if capture_profile_settings(library, hass, {**config, **updates}, actor.id):
        updates[SAVED_DEVICE_SETTINGS] = library
    await async_commit_profile_update(
        hass, entry, actor, updates, expected_profiles=config.get("profiles", [])
    )
    return next(profile for profile in updated if profile["profile_id"] == profile_id)
