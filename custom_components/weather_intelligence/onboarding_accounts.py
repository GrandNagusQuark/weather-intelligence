"""Authenticated account-scoped onboarding, without broader dashboard access."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .avalanche_region import async_prepare_avalanche_regions
from .config import effective_entry_config
from .const import DOMAIN
from .onboarding import ONBOARDING_KEY, onboarding_snapshot
from .onboarding_alerts import alert_setup_snapshot, apply_alert_action, clear_alert_progress
from .onboarding_dnd import apply_home_context, clear_dnd_choices, dnd_snapshot
from .onboarding_notifications import NOTIFICATION_STAGES, notification_snapshot, progress_lock
from .saved_device_settings import SAVED_DEVICE_SETTINGS, capture_latest, capture_profile_settings, library_from_config, resolve_saved_preferences, saved_choices
from .onboarding_workflow import (
    CONFIGURATION_STAGES, FLOW_STAGES, apply_workflow_action, cache_choices,
    clear_choices, selected_ids, selection_stage,
)

ACCOUNT_PROGRESS = "onboarding_accounts"
LEGACY_OWNER = "onboarding_legacy_owner"
ALERT_STAGES = {"alert_choices", "alert_dnd", "notification_setup"}
STAGES = {"welcome", "choice", "device_setup", "accounts", "target_device_setup", "single_device", "single_device_setup", *ALERT_STAGES, *FLOW_STAGES, *NOTIFICATION_STAGES}
ALERT_PATHS = {"life_only", "life_plus", "all", "choose_all"}


def account_devices(hass: Any, user_id: str) -> list[dict[str, str]]:
    """Return push-capable Companion registrations owned by this HA account.

    Registration user_id is assigned by Home Assistant at authenticated app
    registration, not inferred from a Person, name or client-supplied owner.
    Do not expose webhook IDs, push tokens/URLs or registration payloads.
    """
    devices = []
    for entry in hass.config_entries.async_entries("mobile_app"):
        data = entry.data
        app_data = data.get("app_data") or {}
        loaded = getattr(entry.state, "value", entry.state) == "loaded"
        push = (bool(app_data.get("push_token")) and bool(app_data.get("push_url"))) or "push_websocket_channel" in app_data
        if data.get("user_id") != user_id or not loaded or not push:
            continue
        devices.append({
            "id": entry.entry_id,
            "name": data.get("device_name") or entry.title or "Companion device",
            "platform": str(data.get("os_name") or ""),
        })
    return sorted(devices, key=lambda item: (item["name"].casefold(), item["id"]))


def human_account(user: Any) -> bool:
    return bool(user and user.is_active and not user.system_generated)


def account_state(config: Mapping[str, Any], user_id: str) -> dict[str, Any]:
    state = deepcopy(config.get(ACCOUNT_PROGRESS, {}).get(user_id) or {
        "version": 1, "initiated": False, "completed": False,
        "endpoint": None, "revision": 0, "stage": "welcome",
        "target_user_id": user_id,
    })
    # The earlier Quick path contained the custom questionnaire. Preserve that
    # meaning for in-progress drafts rather than replacing their chosen alerts.
    if state.get("workflow_version") != 2 and state.get("setup_mode") == "quick" and (
            state.get("alert_path") or state.get("stage") == "single_device_setup"):
        state["setup_mode"] = "custom"
    return state


def normalize_account_progress(
    current: Mapping[str, Any], payload: Mapping[str, Any], actor: Any,
    active_user_ids: set[str], *, saved_preferences: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate every cross-account choice server-side; no device is enrolled."""
    if not human_account(actor):
        raise ValueError("An active Home Assistant user account is required.")
    if payload.get("expected_revision") != current.get("revision", 0):
        raise ValueError("Setup changed in another tab. Reopen onboarding and try again.")
    state = deepcopy(dict(current))
    mode = payload.get("mode", state.get("setup_mode"))
    stage = payload.get("stage", state.get("stage", "choice"))
    target = payload.get("target_user_id", state.get("target_user_id", actor.id))
    count = payload.get("device_count", state.get("device_count"))
    if mode not in {None, "quick", "guided", "custom"} or stage not in STAGES:
        raise ValueError("Unsupported onboarding step.")
    if stage in {"notification_review", "notification_complete"} and "stage" in payload:
        raise ValueError("Use the phone notification setup controls to review or finish.")
    if ("stage" in payload and stage in CONFIGURATION_STAGES and stage != current.get("stage")
            and not (stage == "single_device_setup" and current.get("stage") == "single_device")):
        raise ValueError("Continue using the controls on the current onboarding page.")
    if target != actor.id and not actor.is_admin:
        raise ValueError("Non-admin users can only set up their own devices.")
    if target not in active_user_ids:
        raise ValueError("Choose an active Home Assistant user.")
    if stage == "accounts" and not actor.is_admin:
        raise ValueError("Only administrators can select another user.")
    if stage not in {"welcome", "choice"} and mode is None:
        raise ValueError("Choose a setup mode before selecting devices.")
    if stage == "device_setup" and target != actor.id:
        raise ValueError("Use the selected user's device setup screen.")
    if stage == "target_device_setup" and (not actor.is_admin or target == actor.id):
        raise ValueError("Choose another user first.")
    if count not in {None, "single", "multiple"}:
        raise ValueError("Choose single or multiple devices.")
    if "device_count" in payload and stage not in {"device_setup", "target_device_setup", "single_device", "multiple_settings"}:
        raise ValueError("Choose devices from the device setup screen.")
    if mode != state.get("setup_mode"):
        clear_choices(state)
        state.pop("device_drafts", None)
    if target != state.get("target_user_id", actor.id):
        count = payload.get("device_count")
        state.pop("selected_device_id", None)
        state.pop("selected_device_ids", None)
        state.pop("multiple_settings", None)
        state.pop("device_drafts", None)
        state["active_device_index"] = 0
        clear_choices(state)
    if count != state.get("device_count"):
        state.pop("selected_device_id", None)
        state.pop("selected_device_ids", None)
        state.pop("multiple_settings", None)
        state.pop("device_drafts", None)
        state["active_device_index"] = 0
        clear_choices(state)
    if stage == "single_device" and count != "single":
        raise ValueError("Choose single-device setup first.")
    if stage in {"multiple_settings", "multiple_devices"} and count != "multiple":
        raise ValueError("Choose multiple-device setup first.")
    if stage in CONFIGURATION_STAGES and count not in {"single", "multiple"}:
        raise ValueError("Choose devices before continuing.")
    if "multiple_settings" in payload:
        setting = payload["multiple_settings"]
        if current.get("stage") != "multiple_settings" or stage != "multiple_devices" or setting not in {"shared", "individual"}:
            raise ValueError("Choose shared or individual settings on its setup page.")
        if setting != state.get("multiple_settings"):
            clear_choices(state)
            state.pop("device_drafts", None)
            state["active_device_index"] = 0
        state["multiple_settings"] = setting
    if "selected_device_ids" in payload:
        devices = payload["selected_device_ids"]
        if stage != "multiple_devices" or count != "multiple" or not isinstance(devices, list) or any(not isinstance(device, str) for device in devices) or len(set(devices)) != len(devices):
            raise ValueError("Choose distinct devices on the multiple-device page.")
        if devices != state.get("selected_device_ids", []):
            clear_choices(state)
            state.pop("device_drafts", None)
            state["active_device_index"] = 0
        state["selected_device_ids"] = list(devices)
        state["selected_device_id"] = devices[0] if devices else None
    if "alert_path" in payload:
        if stage != "single_device_setup" or payload["alert_path"] not in ALERT_PATHS:
            raise ValueError("Choose a supported alert setup path after selecting a device.")
        if payload["alert_path"] != state.get("alert_path"):
            clear_alert_progress(state)
        state["alert_path"] = payload["alert_path"]
    if "dnd_bypass" in payload:
        if stage != "alert_dnd" or current.get("stage") != "alert_dnd" or type(payload["dnd_bypass"]) is not bool:
            raise ValueError("Choose a Do Not Disturb preference on its setup page.")
        if state.get("dnd_bypass") != payload["dnd_bypass"]:
            clear_dnd_choices(state)
        state["dnd_bypass"] = payload["dnd_bypass"]
    if "home_avalanche_exposure" in payload:
        raise ValueError("Home avalanche exposure is no longer a manual setup choice. Reload onboarding.")
    state.update({
        "version": 1, "workflow_version": 2, "initiated": True, "setup_mode": mode,
        "stage": stage, "target_user_id": target, "device_count": count,
        "revision": int(current.get("revision", 0)) + 1,
    })
    previous_stage = current.get("stage", "choice")
    if not apply_workflow_action(state, payload, previous_stage, saved_preferences=saved_preferences):
        apply_alert_action(state, payload, previous_stage)
        if payload.get("alert_action") == "notification_setup" and state["stage"] == "notification_setup":
            # Older clients cannot skip the newly required DND review.
            state["stage"] = "alert_dnd"
            apply_workflow_action(state, {"workflow_action": "delivery_next"}, "alert_dnd")
        elif payload.get("alert_action") == "back_to_dnd" and state.get("dnd_bypass_confirmed"):
            state["stage"] = "dnd_confirm"
    cache_choices(state)
    # This workflow does not enroll delivery or mark onboarding complete.
    return state


async def async_actor(hass: Any, connection: Any) -> Any:
    user = await hass.auth.async_get_user(connection.user.id)
    if not human_account(user):
        raise ValueError("An active Home Assistant user account is required.")
    return user


async def async_onboarding_snapshot(hass: Any, entry: Any, actor: Any, progress_user_id: str | None = None) -> dict[str, Any]:
    """Expose account names to admins only; no household settings or locations."""
    if not human_account(actor):
        raise ValueError("An active Home Assistant user account is required.")
    from .setup_resume import progress_owner
    source_id = progress_owner(actor, progress_user_id)
    if source_id != actor.id:
        source = await hass.auth.async_get_user(source_id)
        fresh = await hass.auth.async_get_user(actor.id)
        if not human_account(source) or not human_account(fresh) or not fresh.is_admin:
            raise ValueError("Only an active administrator can resume this setup.")
    config = effective_entry_config(entry)
    from .admin_actions import account_notice
    from .profile_preferences import own_preferences_available
    # Bind the earlier admin-only prototype's progress once. No ordinary user
    # ever inherits that global state or anyone else's selected account.
    legacy = config.get(ONBOARDING_KEY, {})
    if actor.is_admin and not config.get(LEGACY_OWNER) and legacy.get("initiated"):
        states = dict(config.get(ACCOUNT_PROGRESS, {}))
        states.setdefault(actor.id, {**legacy, "stage": "device_setup" if legacy.get("setup_mode") == "quick" else "choice", "target_user_id": actor.id, "revision": 0})
        hass.config_entries.async_update_entry(entry, options={**entry.options, ACCOUNT_PROGRESS: states, LEGACY_OWNER: actor.id})
        config = effective_entry_config(entry)
    accounts = await hass.auth.async_get_users() if actor.is_admin else [actor]
    accounts = [user for user in accounts if human_account(user)]
    state = account_state(config, source_id)
    await async_prepare_avalanche_regions(hass, state)
    config = effective_entry_config(entry)
    state = account_state(config, source_id)
    apply_home_context(state, hass)
    target = next((user for user in accounts if user.id == state.get("target_user_id", actor.id)), None)
    if target is None or (target.id != actor.id and not actor.is_admin):
        # Deleted accounts/revoked admin rights cannot revive an old grant.
        state.update({"target_user_id": actor.id, "stage": "device_setup" if state.get("setup_mode") == "quick" else "choice", "device_count": None})
        state.pop("selected_device_id", None)
        state.pop("selected_device_ids", None)
        state.pop("device_drafts", None)
        clear_choices(state)
        target = actor
    devices = account_devices(hass, target.id)
    selected_device = state.get("selected_device_id")
    allowed = {device["id"] for device in devices}
    device_available = bool(selected_device and selected_device in allowed)
    selection_available = bool(selected_ids(state)) and all(device in allowed for device in selected_ids(state))
    if state.get("stage") in CONFIGURATION_STAGES and not selection_available:
        state["stage"] = selection_stage(state)
    snapshot = onboarding_snapshot({**config, ONBOARDING_KEY: state}, testing=hass.data.get(DOMAIN, {}).get("onboarding_testing", False))
    snapshot.update({"stage": state.get("stage", "choice" if state.get("initiated") else "welcome"), "revision": state.get("revision", 0), "target_user_id": target.id, "device_count": state.get("device_count"), "selected_device_id": selected_device if device_available else None, "selected_device_unavailable": bool(selected_device and not device_available), "alert_path": state.get("alert_path") if state.get("alert_path") in ALERT_PATHS else None})
    snapshot["alert_setup"] = alert_setup_snapshot(state)
    snapshot["progress_user_id"] = source_id
    page = snapshot["alert_setup"].get("page")
    if page and page["id"] == "hurricane warning":
        page["title"] = "Typhoon" if state.get("regional_tropical_event") == "typhoon" else "Hurricane"
    snapshot["dnd_setup"] = dnd_snapshot(state)
    library = library_from_config(config)
    capture_latest(library, state, devices, actor.id, seed_only=True)
    if config.get("profiles"):
        capture_profile_settings(library, hass, config, actor.id, seed_only=True)
    snapshot["saved_device_settings"] = saved_choices(library, target.id)
    snapshot["saved_settings_revision"] = library["revision"]
    if state.get("stage") in NOTIFICATION_STAGES:
        snapshot["notification_setup"] = notification_snapshot(hass, entry, state, actor.id, actor_is_admin=actor.is_admin)
    snapshot.update({
        "selected_device_ids": [device for device in selected_ids(state) if device in allowed],
        "multiple_settings": state.get("multiple_settings"),
        "active_device_index": state.get("active_device_index", 0),
        "guided_index": state.get("guided_index", 0),
        "guided_answers": deepcopy(state.get("guided_answers", {})),
        "daily_outlook_enabled": state.get("daily_outlook_enabled"),
        "daily_outlook_time": state.get("daily_outlook_time", "07:00"),
        "home_timezone": str(getattr(getattr(hass, "config", None), "time_zone", "Home Assistant local time")),
    })
    # Regular-user dashboard/alert access remains separate from onboarding.
    if not actor.is_admin:
        snapshot["dashboard_available"] = False
    from .about import about_snapshot
    return {
        "about": about_snapshot(config),
        "admin_notice": account_notice(config, actor.id),
        "own_preferences_available": bool(actor.is_admin and config.get("profiles")) or own_preferences_available(hass, config, actor.id),
        "onboarding": snapshot,
        "actor": {"id": actor.id, "name": actor.name or "Home Assistant user", "is_admin": bool(actor.is_admin)},
        "target_user": {"id": target.id, "name": target.name or "Home Assistant user"},
        "setup_devices": devices,
        "setup_users": sorted([{"id": user.id, "name": user.name or "Home Assistant user"} for user in accounts if user.id != actor.id], key=lambda item: item["name"].casefold()) if actor.is_admin else [],
        "profiles": [], "dashboard": None,
    }


async def async_save_account_progress(hass: Any, entry: Any, actor: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    async with progress_lock(hass, entry):
        return await _async_save_account_progress(hass, entry, actor, payload)


async def _async_save_account_progress(hass: Any, entry: Any, actor: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    from .setup_resume import progress_owner
    source_id = progress_owner(actor, payload.get("progress_user_id"))
    if source_id != actor.id:
        actor = await hass.auth.async_get_user(actor.id)
        source = await hass.auth.async_get_user(source_id)
        if not human_account(actor) or not human_account(source):
            raise ValueError("Sign in again before changing setup.")
        progress_owner(actor, source_id)
    accounts = await hass.auth.async_get_users() if actor.is_admin else [actor]
    active_ids = {user.id for user in accounts if human_account(user)}
    current = account_state(effective_entry_config(entry), source_id)
    await async_prepare_avalanche_regions(hass, current)
    # The optional boundary download can yield while another tab saves.
    # Validate the client's revision against the latest state, not that old read.
    current = account_state(effective_entry_config(entry), source_id)
    apply_home_context(current, hass)
    if current.get("target_user_id", actor.id) not in active_ids or (not actor.is_admin and current.get("target_user_id", actor.id) != actor.id):
        current.update({"target_user_id": actor.id, "device_count": None, "stage": "device_setup" if current.get("setup_mode") == "quick" else "choice"})
        current.pop("selected_device_id", None)
        current.pop("selected_device_ids", None)
        current.pop("device_drafts", None)
        clear_choices(current)
    library = library_from_config(effective_entry_config(entry))
    capture_latest(library, current, account_devices(hass, actor.id), actor.id, seed_only=True)
    if effective_entry_config(entry).get("profiles"):
        capture_profile_settings(library, hass, effective_entry_config(entry), actor.id, seed_only=True)
    copied_preferences = None
    if payload.get("workflow_action") == "saved_settings_apply":
        if payload.get("saved_settings_revision") != library["revision"]:
            raise ValueError("Saved settings changed. Reopen this setup step before copying.")
        copied_preferences = resolve_saved_preferences(library, current.get("target_user_id", actor.id), payload.get("saved_settings_id"))
    state = normalize_account_progress(current, payload, actor, active_ids, saved_preferences=copied_preferences)
    apply_home_context(state, hass)
    cache_choices(state)
    if "selected_device_id" in payload:
        if state["stage"] != "single_device" or state["device_count"] != "single":
            raise ValueError("Select a device from single-device setup.")
        selected = payload["selected_device_id"]
        allowed = {device["id"] for device in account_devices(hass, state["target_user_id"])}
        if selected not in allowed:
            raise ValueError("This device is no longer available for this account. Reopen device setup.")
        if selected != current.get("selected_device_id"):
            clear_choices(state)
            state.pop("device_drafts", None)
        state["selected_device_id"] = selected
    allowed = {device["id"] for device in account_devices(hass, state["target_user_id"])}
    if any(device not in allowed for device in selected_ids(state)):
        raise ValueError("A selected device is no longer available for this account. Reopen device setup.")
    if state["stage"] in CONFIGURATION_STAGES:
        chosen = selected_ids(state)
        if not chosen or (state.get("device_count") == "multiple" and len(chosen) < 2):
            raise ValueError("Choose an available device before continuing.")
    # Read/merge at write time. Saving actor A's workflow cannot overwrite B.
    states = dict(effective_entry_config(entry).get(ACCOUNT_PROGRESS, {}))
    states[source_id] = state
    capture_latest(library, state, account_devices(hass, actor.id), actor.id, previous_drafts=current.get("device_drafts", {}))
    hass.config_entries.async_update_entry(entry, options={**entry.options, ACCOUNT_PROGRESS: states, SAVED_DEVICE_SETTINGS: library})
    if state.get("marine_warning_mode") in {"always", "on_water"}:
        from .onboarding_preferences import async_apply_saved_marine_preferences
        await async_apply_saved_marine_preferences(hass, entry)
    return await async_onboarding_snapshot(hass, entry, actor, source_id)
