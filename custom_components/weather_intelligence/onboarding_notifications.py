"""Persisted per-phone setup, owner-checked tests and explicit final enrollment."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping

from .config import effective_entry_config, normalize_profiles, profile_to_dict
from .const import DOMAIN, ANDROID_SIREN_CHANNEL, ANDROID_SETUP_CHANNEL, android_siren_channel
from .hazard_policy import alert_choices
from .models import HouseholdProfile
from .onboarding_dnd import apply_home_context, dnd_snapshot
from .saved_device_settings import portable_preferences
from .marine_preferences import marine_nearby_preferences

NOTIFICATION_STAGES = {"notification_setup", "notification_review", "notification_complete"}
NOTIFICATION_ACTIONS = {"prepare", "retry_prepare", "simplify_channel", "permissions", "test", "test_critical", "confirm_test", "confirm_critical", "next", "back", "finish"}


def progress_lock(hass: Any, entry: Any) -> asyncio.Lock:
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("onboarding_locks", {})
    return locks.setdefault(getattr(entry, "entry_id", "default"), asyncio.Lock())


def selected_devices(state: Mapping[str, Any]) -> list[str]:
    from .onboarding_workflow import selected_ids
    return selected_ids(state)


def device_preferences(state: Mapping[str, Any], device_id: str) -> dict[str, Any]:
    draft = state.get("device_drafts", {}).get(device_id, {})
    if draft.get("owner") != state.get("target_user_id") or not draft.get("alert_selection_complete"):
        raise ValueError("Finish this device's alert choices before notification setup.")
    if not draft.get("dnd_bypass_confirmed") or type(draft.get("daily_outlook_enabled")) is not bool:
        raise ValueError("Confirm this device's DND and daily outlook choices first.")
    return dict(draft)


def owned_people(hass: Any, owner_id: str) -> list[dict[str, str]]:
    if not hasattr(hass, "states"):
        return []
    return [{"id": person.entity_id, "name": person.attributes.get("friendly_name", person.entity_id)}
            for person in getattr(hass.states, "async_all", lambda domain: [])("person") if person.attributes.get("user_id") == owner_id]


def exact_target(hass: Any, mobile_entry: Any) -> str:
    """Resolve HA's registration mapping, never construct an action from a name."""
    notify = hass.data.get("mobile_app", {}).get("notify")
    webhook = mobile_entry.data.get("webhook_id")
    targets = getattr(notify, "registered_targets", {})
    if not hasattr(hass, "services"):
        raise ValueError("This phone's Companion notification action is unavailable.")
    matches = [name for name, target in targets.items() if webhook and target == webhook
               and name.startswith("mobile_app_") and hass.services.has_service("notify", name)]
    if len(matches) != 1:
        raise ValueError("This phone's Companion notification action is unavailable. Open its Home Assistant app and retry.")
    return "notify." + matches[0]


def _platform(mobile_entry: Any) -> str:
    os_name = str(mobile_entry.data.get("os_name", "")).casefold()
    if os_name == "android":
        return "android"
    return "ios" if os_name in {"ios", "ipados", "iphone os"} else "unsupported"


def _binding(state: Mapping[str, Any], device_id: str, target: str, platform: str, profiles: list[dict]) -> str:
    preferences = portable_preferences(device_preferences(state, device_id))
    encoded = json.dumps([state["target_user_id"], device_id, target, platform, preferences, profiles], sort_keys=True)
    return sha256(encoded.encode()).hexdigest()


def _context(hass: Any, entry: Any, state: dict, device_id: str) -> tuple[Any, str, dict, str, list]:
    from .onboarding_accounts import account_devices
    allowed = {device["id"] for device in account_devices(hass, state["target_user_id"])}
    if device_id not in selected_devices(state) or device_id not in allowed:
        raise ValueError("This phone is no longer available to the selected account.")
    mobile_entry = next(item for item in hass.config_entries.async_entries("mobile_app") if item.entry_id == device_id)
    target = exact_target(hass, mobile_entry)
    platform = _platform(mobile_entry)
    config = effective_entry_config(entry)
    # Exact action identity and authenticated registration ownership were checked above.
    matches = [raw for raw in config.get("profiles", []) if raw.get("legacy_notify_service") == target
               or raw.get("companion_device_id") == device_id]
    if len(matches) > 1 or any(raw.get("legacy_notify_service") != target for raw in matches):
        raise ValueError("This phone has conflicting saved profiles. Resolve them in User settings before continuing.")
    for raw in matches:
        person = hass.states.get(raw.get("person_entity", ""))
        if person is None or person.attributes.get("user_id") != state["target_user_id"]:
            raise ValueError("The phone's existing profile belongs to a different account.")
    fingerprint = _binding(state, device_id, target, platform, matches)
    progress = state.get("notification_devices", {}).get(device_id, {})
    if progress.get("binding") != fingerprint:
        progress = {"binding": fingerprint, "urgent_channel": matches[0].get("urgent_channel", ANDROID_SIREN_CHANNEL) if matches
                    else ANDROID_SIREN_CHANNEL, "setup_channel": ANDROID_SETUP_CHANNEL, "returning": bool(matches)}
    if platform == "android":
        corrected = android_siren_channel(progress["urgent_channel"])
        if corrected != progress["urgent_channel"]:
            # Old test results cannot verify a different audio channel.
            progress = {"binding": fingerprint, "urgent_channel": corrected,
                        "setup_channel": ANDROID_SETUP_CHANNEL, "returning": bool(matches)}
        else:
            progress = {**progress, "setup_channel": ANDROID_SETUP_CHANNEL}
    return mobile_entry, target, progress, platform, matches


def notification_snapshot(hass: Any, entry: Any, state: dict, actor_id: str, *, actor_is_admin: bool = False) -> dict[str, Any]:
    ids = selected_devices(state)
    index = min(max(state.get("notification_device_index", 0), 0), max(len(ids) - 1, 0))
    result = {"index": index, "count": len(ids), "can_manage": state.get("target_user_id") == actor_id or actor_is_admin,
              "people": owned_people(hass, state.get("target_user_id", actor_id)), "devices": [],
              "activation": state.get("notification_activation", "pending")}
    for device_id in ids:
        try:
            mobile, _target, progress, platform, _matches = _context(hass, entry, state, device_id)
            preferences = device_preferences(state, device_id)
            dnd = dnd_snapshot(preferences)
            selected = set(dnd["selected"])
            result["devices"].append({"id": device_id, "name": mobile.data.get("device_name") or mobile.title,
                "platform": platform, "urgent_channel": progress["urgent_channel"],
                "setup_attempted": bool(progress.get("setup_attempted")), "setup_status": progress.get("setup_status", ""),
                "permissions": progress.get("permissions") is True,
                "test_sent": progress.get("test_status") == "sent", "test_confirmed": progress.get("test_confirmed") is True,
                "critical_sent": progress.get("critical_status") == "sent", "critical_confirmed": progress.get("critical_confirmed") is True,
                "test_status": progress.get("test_status", ""), "critical_status": progress.get("critical_status", ""),
                "dnd": [rule["title"] for rule in dnd["choices"] if rule["id"] in selected],
                "daily_outlook": preferences.get("daily_outlook_enabled") is True,
                "daily_time": preferences.get("daily_outlook_time", "07:00"),
                "ready": _ready(progress, bool(selected)), "error": ""})
        except (ValueError, StopIteration) as error:
            result["devices"].append({"id": device_id, "name": "Selected phone", "error": str(error), "ready": False})
    result["device"] = result["devices"][index] if result["devices"] else None
    result["person_id"] = state.get("notification_person_id") or (result["people"][0]["id"] if len(result["people"]) == 1 else "")
    return result


def _ready(progress: Mapping[str, Any], needs_critical: bool) -> bool:
    return bool(progress.get("permissions") and progress.get("test_confirmed")
                and (not needs_critical or progress.get("critical_confirmed")))


def _persist(hass: Any, entry: Any, actor_id: str, state: dict, **extra: Any) -> None:
    from .onboarding_accounts import ACCOUNT_PROGRESS
    accounts = deepcopy(effective_entry_config(entry).get(ACCOUNT_PROGRESS, {}))
    state["revision"] = state.get("revision", 0) + 1
    accounts[actor_id] = deepcopy(state)
    hass.config_entries.async_update_entry(entry, options={**entry.options, ACCOUNT_PROGRESS: accounts, **extra})


async def async_notification_action(hass: Any, entry: Any, actor: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    from .onboarding_accounts import account_state, async_onboarding_snapshot, human_account
    from .setup_resume import progress_owner
    actor = await hass.auth.async_get_user(actor.id)
    if not human_account(actor):
        raise ValueError("An active Home Assistant account is required.")
    source_id = progress_owner(actor, payload.get("progress_user_id"))
    action = payload.get("action")
    request_id = payload.get("request_id")
    if action not in NOTIFICATION_ACTIONS or not isinstance(request_id, str) or not 8 <= len(request_id) <= 80:
        raise ValueError("Use the notification setup controls.")
    async with progress_lock(hass, entry):
        state = account_state(effective_entry_config(entry), source_id)
        command = [action, payload.get("device_id"), payload.get("value"), payload.get("person_id")]
        previous = state.get("notification_request", {})
        if previous.get("id") == request_id:
            if previous.get("command") != command:
                raise ValueError("This setup request was already used for another action.")
            return await async_onboarding_snapshot(hass, entry, actor, source_id)
        if state.get("revision", 0) != payload.get("expected_revision"):
            raise ValueError("Setup changed in another tab. Reopen onboarding before continuing.")
        if state.get("stage") not in {"notification_setup", "notification_review"}:
            raise ValueError("Finish alert preferences before setting up notifications.")
        apply_home_context(state, hass)
        if state.get("target_user_id") != actor.id:
            fresh_actor = await hass.auth.async_get_user(actor.id)
            target_user = await hass.auth.async_get_user(state.get("target_user_id"))
            if not human_account(fresh_actor) or not fresh_actor.is_admin or not human_account(target_user):
                raise ValueError("Only an active administrator can set up another active account's phone.")
            if account_state(effective_entry_config(entry), source_id).get("revision", 0) != state["revision"]:
                raise ValueError("Setup changed in another tab. Reopen onboarding before continuing.")
        ids = selected_devices(state)
        index = state.get("notification_device_index", 0)
        if not ids or index not in range(len(ids)):
            raise ValueError("Choose available phones before continuing.")
        device_id = ids[index]
        if payload.get("device_id") != device_id:
            raise ValueError("Use the controls for the phone currently shown.")
        mobile, target, progress, platform, _matches = _context(hass, entry, state, device_id)
        if platform == "unsupported":
            raise ValueError("Notification setup currently supports Android phones and iPhones.")
        preferences = device_preferences(state, device_id)
        needs_critical = bool(dnd_snapshot(preferences)["selected"])
        state.setdefault("notification_devices", {})[device_id] = progress
        if action == "finish":
            if state["stage"] != "notification_review":
                raise ValueError("Review every phone before enabling notifications.")
            await _async_finish(hass, entry, actor, state, payload)
        else:
            if state["stage"] == "notification_review" and action != "back":
                raise ValueError("Return to phone setup before testing or changing its permissions.")
            if action in {"prepare", "retry_prepare", "test", "test_critical"}:
                if action == "prepare" and progress.get("setup_attempted"):
                    return await async_onboarding_snapshot(hass, entry, actor, source_id)
                if action.startswith("test") and not progress.get("permissions"):
                    raise ValueError("Confirm the phone's notification settings before testing.")
                if action == "test_critical" and not needs_critical:
                    raise ValueError("This phone is set to respect Do Not Disturb.")
                status_key = "setup_status" if action in {"prepare", "retry_prepare"} else "critical_status" if action == "test_critical" else "test_status"
                progress[status_key] = "attempted"
                if status_key == "setup_status":
                    progress["setup_attempted"] = True
                else:
                    progress["critical_confirmed" if status_key == "critical_status" else "test_confirmed"] = False
                state["notification_request"] = {"id": request_id, "command": command}
                _persist(hass, entry, source_id, state)
                profile = HouseholdProfile(profile_id="setup_" + device_id, name="Phone setup", person_entity_id="person.setup",
                    legacy_notify_service=target, mobile_platform=platform, urgent_channel=progress["urgent_channel"])
                from .mobile_notification import async_send_onboarding_notification
                try:
                    if action == "prepare" and platform == "android":
                        # Reused channels can retain an audible sound. Opening
                        # setup must not ring a phone or create random channels.
                        progress[status_key] = "manual_required"
                    else:
                        await async_send_onboarding_notification(hass, profile,
                            kind="prepare" if status_key == "setup_status" else "critical" if action == "test_critical" else "normal",
                            returning=progress.get("returning", False), setup_channel=progress["setup_channel"])
                        progress[status_key] = "sent"
                except Exception:
                    # A delivery exception is not proof it never reached the phone.
                    progress[status_key] = "uncertain"
                if account_state(effective_entry_config(entry), source_id).get("revision", 0) != state["revision"]:
                    raise ValueError("Setup changed while the notification was being sent. Reopen onboarding before continuing.")
            elif action == "simplify_channel":
                if platform != "android":
                    raise ValueError("Notification categories apply only to Android phones.")
                progress = {"binding": progress["binding"], "urgent_channel": ANDROID_SIREN_CHANNEL,
                            "setup_channel": ANDROID_SETUP_CHANNEL, "returning": bool(_matches)}
                state["notification_devices"][device_id] = progress
            elif action == "permissions":
                if type(payload.get("value")) is not bool:
                    raise ValueError("Confirm the notification settings on this phone.")
                progress["permissions"] = payload["value"]
                progress["test_confirmed"] = progress["critical_confirmed"] = False
                progress.pop("test_status", None)
                progress.pop("critical_status", None)
            elif action in {"confirm_test", "confirm_critical"}:
                critical = action == "confirm_critical"
                if progress.get("critical_status" if critical else "test_status") != "sent" or not progress.get("permissions"):
                    raise ValueError("Send this phone's test before confirming the result.")
                if type(payload.get("value")) is not bool:
                    raise ValueError("Confirm what happened on the phone.")
                progress["critical_confirmed" if critical else "test_confirmed"] = payload["value"]
            elif action == "next":
                if not _ready(progress, needs_critical):
                    raise ValueError("Confirm the settings and test results on this phone first.")
                if index + 1 < len(ids):
                    state["notification_device_index"] = index + 1
                else:
                    state["stage"] = "notification_review"
            elif action == "back":
                if state["stage"] == "notification_review":
                    state["stage"] = "notification_setup"
                elif index:
                    state["notification_device_index"] = index - 1
                else:
                    state["stage"] = "daily_outlook"
            state["notification_request"] = {"id": request_id, "command": command}
            _persist(hass, entry, source_id, state)
    return await async_onboarding_snapshot(hass, entry, actor, source_id)


async def _async_finish(hass: Any, entry: Any, actor: Any, state: dict, payload: Mapping[str, Any]) -> None:
    from .onboarding import ONBOARDING_KEY
    from .onboarding_accounts import account_state, human_account
    from .setup_resume import progress_owner
    source_id = progress_owner(actor, payload.get("progress_user_id"))
    from .persistence import async_reconcile_profile_reference, async_record_profile_reference
    await async_reconcile_profile_reference(hass, entry)
    fresh_actor = await hass.auth.async_get_user(actor.id)
    if not human_account(fresh_actor):
        raise ValueError("Sign in again before enabling notifications.")
    if account_state(effective_entry_config(entry), source_id).get("revision", 0) != state["revision"]:
        raise ValueError("Setup changed before enrollment. Reopen onboarding.")
    target_user_id = state["target_user_id"]
    target_user = await hass.auth.async_get_user(target_user_id)
    if not human_account(target_user) or (target_user_id != actor.id and not fresh_actor.is_admin):
        raise ValueError("An active administrator is required to save another account's preferences.")
    people = owned_people(hass, target_user_id)
    person_id = payload.get("person_id") or (people[0]["id"] if len(people) == 1 else "")
    if person_id not in {person["id"] for person in people}:
        raise ValueError("Choose a Home Assistant Person linked to the selected account. An administrator can link one under People.")
    config = effective_entry_config(entry)
    raw_profiles = deepcopy(config.get("profiles", []))
    for device_id in selected_devices(state):
        mobile, target, progress, platform, matches = _context(hass, entry, state, device_id)
        preferences = device_preferences(state, device_id)
        dnd = dnd_snapshot(preferences)
        if not _ready(progress, bool(dnd["selected"])):
            raise ValueError("A phone's settings changed. Review and test it again before enabling notifications.")
        selected_rules = set(dnd["selected"])
        received = {event for rule in dnd["choices"] for event in rule.get("events", [rule["event"]])}
        # Conditional life-only entries still subscribe to the corresponding product.
        events = [choice["value"] for choice in alert_choices() if choice["value"] in received]
        previous = matches[0] if matches else {}
        replacement = {**previous,
            "profile_id": previous.get("profile_id") or "device_" + sha256((target_user_id + ":" + device_id).encode()).hexdigest()[:24],
            "name": previous.get("name") or (target_user.name or "Weather alerts") + " · " + (mobile.data.get("device_name") or mobile.title) + " · " + device_id[:6],
            "person_entity": person_id, "notify_entity": "", "legacy_notify_service": target,
            "companion_device_id": device_id, "mobile_platform": platform, "enabled": True,
            "automatic_official_warning_notifications": True,
            "critical_notifications_enabled": bool(selected_rules), "dnd_rule_ids": list(dnd["selected"]),
            **marine_nearby_preferences(preferences),
            "urgent_channel": progress["urgent_channel"], "alert_events": events,
            "life_safety_events": [event for event in ("severe thunderstorm warning", "flash flood warning", "radar_hail")
                if preferences.get("alert_path") in {"life_only", "life_plus"} and not preferences.get("alert_answers", {}).get(event, False)],
            "receive_personal_location_alerts": preferences.get("receive_personal_alerts", True),
            "receive_designated_home_alerts_while_away": preferences.get("receive_home_while_away", False),
            "show_location_on_map": preferences.get("show_location_on_map", "inherit"),
            "marine_warning_mode": preferences.get("marine_warning_mode", "always"),
            "daily_briefing_enabled": preferences.get("daily_outlook_enabled", False),
            "daily_outlook_time": preferences.get("daily_outlook_time", "07:00"),
            "daily_briefing_location": preferences.get("briefing_location", "designated_home")}
        if previous:
            raw_profiles = [replacement if raw.get("profile_id") == previous.get("profile_id") else raw for raw in raw_profiles]
        else:
            raw_profiles.append(replacement)
    normalized = [profile_to_dict(profile) for profile in normalize_profiles(raw_profiles)]
    from .admin_actions import ADMIN_ACTION_NOTICES, async_prepare_admin_notices, queued_admin_notices
    notices = await async_prepare_admin_notices(hass, fresh_actor, config.get("profiles", []), normalized,
                                               enrollment_owner_id=target_user_id)
    if (account_state(effective_entry_config(entry), source_id).get("revision", 0) != state["revision"]
            or effective_entry_config(entry).get("profiles", []) != config.get("profiles", [])):
        raise ValueError("Setup or profiles changed before enrollment. Reopen onboarding.")
    for device_id in selected_devices(state):
        enrolled = next(profile for profile in normalized if profile.get("companion_device_id") == device_id)
        state["notification_devices"][device_id]["binding"] = _binding(state, device_id,
            enrolled["legacy_notify_service"], enrolled["mobile_platform"], [enrolled])
    state.update(completed=True, endpoint="notifications", stage="notification_complete", notification_person_id=person_id)
    state["notification_activation"] = "pending"
    state["notification_request"] = {"id": payload["request_id"], "command": ["finish", payload.get("device_id"), payload.get("value"), payload.get("person_id")]}
    extra = {ONBOARDING_KEY: {**config.get(ONBOARDING_KEY, {}), "initiated": True, "completed": True, "endpoint": "notifications"}}
    if notices:
        extra[ADMIN_ACTION_NOTICES] = queued_admin_notices(effective_entry_config(entry), notices)
    from .const import ANDROID_SIREN_REVIEW_PENDING, ANDROID_SIREN_REVIEW_NOTIFICATION
    pending = set(config.get(ANDROID_SIREN_REVIEW_PENDING, []))
    completed_profiles = {profile["profile_id"] for profile in normalized
                          if profile.get("companion_device_id") in selected_devices(state)}
    if pending:
        extra[ANDROID_SIREN_REVIEW_PENDING] = sorted(pending - completed_profiles)
    _persist(hass, entry, source_id, state, profiles=normalized, **extra)
    if pending and not extra[ANDROID_SIREN_REVIEW_PENDING]:
        from homeassistant.components import persistent_notification
        persistent_notification.async_dismiss(hass, ANDROID_SIREN_REVIEW_NOTIFICATION)
    await async_record_profile_reference(hass, entry)
    # The websocket handler verifies integration activation before returning.


async def async_activate_saved_notifications(hass: Any, entry: Any, actor: Any, progress_user_id: str | None = None) -> dict[str, Any]:
    from .onboarding_accounts import account_state, async_onboarding_snapshot
    from .admin_actions import async_deliver_admin_notices
    from .setup_resume import progress_owner
    source_id = progress_owner(actor, progress_user_id)
    await async_deliver_admin_notices(hass, entry)
    from .panel import async_reload_preserving_panel
    activated = await async_reload_preserving_panel(hass, entry)
    async with progress_lock(hass, entry):
        state = account_state(effective_entry_config(entry), source_id)
        if state.get("stage") == "notification_complete":
            state["notification_activation"] = "active" if activated else "failed"
            _persist(hass, entry, source_id, state)
    return await async_onboarding_snapshot(hass, entry, actor, source_id)
