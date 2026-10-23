"""Authenticated onboarding plus separately admin-only household configuration."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

_LOGGER = logging.getLogger(__name__)

from .config import effective_entry_config, normalize_profiles, profile_to_dict, profiles_from_config
from .const import (
    CONF_AIRNOW_API_KEY, CONF_AIRNOW_ENABLED, CONF_BRIEFING_TIME, CONF_PROFILES,
    CONF_MQTT_ERROR_LOGGING, CONF_MQTT_ERROR_TOPIC, DEFAULT_MQTT_ERROR_TOPIC,
    CONF_MRMS_HAIL_ENABLED, CONF_SPC_ENABLED, CONF_UV_ENABLED, CONF_WSSI_ENABLED,
    DEFAULT_BRIEFING_TIME, DOMAIN,
)
from .hazard_policy import HazardFamily, alert_choices
from .dashboard import build_dashboard_snapshot, get_official_report
from .onboarding import ONBOARDING_KEY, onboarding_progress, onboarding_snapshot
from .admin_actions import async_commit_profile_update
from .profile_preferences import async_preferences_snapshot, async_save_alert_preferences, async_remove_profile, preference_pages
from .about import about_snapshot
from .profile_dnd import profile_dnd_catalog, profile_dnd_setup_status
from .onboarding_accounts import async_actor, async_onboarding_snapshot, async_save_account_progress, STAGES, ALERT_PATHS
from .saved_device_settings import SAVED_DEVICE_SETTINGS, async_manage_saved_settings, capture_profile_settings, library_from_config
from .onboarding_alerts import alert_source_note
from .onboarding_notifications import NOTIFICATION_ACTIONS, async_activate_saved_notifications, async_notification_action
from .mqtt_error_logging import mqtt_error_logging_status, validate_mqtt_topic
from .mobile_notification import (
    MobileTargetError,
    async_send_ios_setup_handoff,
    async_send_ios_spoken_alert_test,
    async_send_android_setup_handoff,
    async_send_android_tone_speech_test,
    async_send_android_silent_setup,
)

PANEL_URL = "weather-intelligence"
PANEL_ELEMENT = "weather-intelligence-panel"
PANEL_MODULE_URL = (
    "/weather_intelligence_static/weather-intelligence-panel.js?v=0.1.33-alpha-diagnostics-1"
)


def build_panel_snapshot(hass: Any, entry: Any) -> dict[str, Any]:
    """Return friendly UI data and never return a stored credential."""
    effective = effective_entry_config(entry)
    from .reporting_config import reporting_review_required
    onboarding = onboarding_snapshot(effective, testing=getattr(hass, "data", {}).get(DOMAIN, {}).get("onboarding_testing", False))
    return {
        "about": about_snapshot(effective),
        "reporting_consent_review_required": reporting_review_required(effective),
        "onboarding": onboarding,
        "profiles": [profile_to_dict(item) for item in profiles_from_config(effective)],
        "people": _entity_choices(hass, "person"),
        "notify_targets": _entity_choices(hass, "notify"),
        "legacy_targets": _legacy_choices(hass),
        "hazard_families": [
            {"value": item.value, "label": item.value.replace("_", " ").title()}
            for item in HazardFamily
        ],
        "alert_choices": [{**choice, "source_note": alert_source_note(choice["value"])} for choice in alert_choices()],
        "alert_pages": preference_pages(hass),
        "dnd_catalog": profile_dnd_catalog(hass),
        "dnd_setup": {profile.profile_id: profile_dnd_setup_status(hass, entry, profile_to_dict(profile)) for profile in profiles_from_config(effective)},
        "briefing_time": str(effective.get(CONF_BRIEFING_TIME, DEFAULT_BRIEFING_TIME)),
        "sources": {
            CONF_MRMS_HAIL_ENABLED: bool(
                effective.get(CONF_MRMS_HAIL_ENABLED, True)
            ),
            CONF_SPC_ENABLED: bool(effective.get(CONF_SPC_ENABLED, False)),
            CONF_WSSI_ENABLED: bool(effective.get(CONF_WSSI_ENABLED, False)),
            CONF_AIRNOW_ENABLED: bool(effective.get(CONF_AIRNOW_ENABLED, False)),
            CONF_UV_ENABLED: bool(effective.get(CONF_UV_ENABLED, False)),
            "airnow_api_key_configured": bool(str(effective.get(CONF_AIRNOW_API_KEY, "")).strip()),
        },
        "developer_logging": {
            **mqtt_error_logging_status(hass, entry),
            "configured": bool(effective.get(CONF_MQTT_ERROR_LOGGING, False)),
            "topic": str(effective.get(CONF_MQTT_ERROR_TOPIC, DEFAULT_MQTT_ERROR_TOPIC)),
        },
        "status": _status_snapshot(getattr(entry, "runtime_data", None)),
        "dashboard": build_dashboard_snapshot(hass, entry) if onboarding["dashboard_available"] else None,
    }


def normalize_single_profile_update(
    payload: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge only a wizard's explicitly saved profile; reject stale edits."""
    draft = payload.get("profile")
    expected = payload.get("expected_profile")
    if not isinstance(draft, Mapping):
        raise ValueError("A profile is required")
    profile_id = str(draft.get("profile_id", "")).strip()
    if not profile_id:
        raise ValueError("A profile ID is required")
    profiles = [profile_to_dict(item) for item in profiles_from_config(current)]
    saved = next((p for p in profiles if p["profile_id"] == profile_id), None)
    if draft.get("mobile_platform") != "android" or (saved and saved.get("mobile_platform") == "ios"):
        raise ValueError("This guided setup updates Android profiles only")
    if saved != expected:
        raise ValueError("This person's settings changed. Reopen onboarding before saving.")
    replacement = dict(draft)
    replacement.pop("android_confirmed", None)
    if saved is None:
        profiles.append(replacement)
    else:
        profiles = [replacement if p["profile_id"] == profile_id else p for p in profiles]
    return {CONF_PROFILES: [profile_to_dict(item) for item in normalize_profiles(profiles)]}


def normalize_panel_update(payload: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an admin save and preserve an existing secret when left blank."""
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("Profiles must be a list")
    profiles = normalize_profiles(raw_profiles)
    value = {CONF_PROFILES: [profile_to_dict(item) for item in profiles]}
    time_value = str(payload.get(CONF_BRIEFING_TIME, DEFAULT_BRIEFING_TIME)).strip()
    parts = time_value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("Briefing time must be HH:MM")
    hour, minute = (int(part) for part in parts)
    if hour not in range(24) or minute not in range(60):
        raise ValueError("Briefing time is outside the day")
    value[CONF_BRIEFING_TIME] = f"{hour:02d}:{minute:02d}"
    sources = payload.get("sources", {})
    if not isinstance(sources, Mapping):
        raise ValueError("Sources must be an object")
    for key in (
        CONF_MRMS_HAIL_ENABLED,
        CONF_SPC_ENABLED,
        CONF_WSSI_ENABLED,
        CONF_AIRNOW_ENABLED,
        CONF_UV_ENABLED,
    ):
        value[key] = bool(sources.get(key, False))
    new_key = str(sources.get(CONF_AIRNOW_API_KEY, "")).strip()
    value[CONF_AIRNOW_API_KEY] = new_key or str(current.get(CONF_AIRNOW_API_KEY, ""))
    developer_logging = payload.get("developer_logging", {})
    if not isinstance(developer_logging, Mapping):
        raise ValueError("Developer logging must be an object")
    value[CONF_MQTT_ERROR_LOGGING] = bool(
        developer_logging.get(CONF_MQTT_ERROR_LOGGING, False)
    )
    value[CONF_MQTT_ERROR_TOPIC] = validate_mqtt_topic(
        developer_logging.get(CONF_MQTT_ERROR_TOPIC, DEFAULT_MQTT_ERROR_TOPIC)
    )
    return value


async def async_register_admin_panel(hass: Any) -> bool:
    """Register one authenticated panel plus admin-only websocket commands."""
    try:
        import voluptuous as vol
        from homeassistant.components import frontend, panel_custom, websocket_api
        from homeassistant.components.http import StaticPathConfig
    except ImportError:
        return False
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("panel_static"):
        path = str(Path(__file__).parent / "frontend")
        await hass.http.async_register_static_paths([
            StaticPathConfig("/weather_intelligence_static", path, False)
        ])
        data["panel_static"] = True

    if not data.get("panel_commands"):
        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/account_notice/dismiss",
            vol.Required("notice_id"): str,
        })
        @websocket_api.async_response
        async def dismiss_account_notice(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            from .admin_actions import async_dismiss_account_notice
            try:
                actor = await async_actor(hass, connection)
                await async_dismiss_account_notice(hass, _single_entry(hass), actor, msg["notice_id"])
            except ValueError as error:
                connection.send_error(msg["id"], "notice_not_dismissed", str(error))
                return
            connection.send_result(msg["id"], {"dismissed":True})

        @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/preferences/get"})
        @websocket_api.async_response
        async def get_preferences(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                actor = await async_actor(hass, connection)
                snapshot = await async_preferences_snapshot(hass, _single_entry(hass), actor)
            except ValueError as error:
                connection.send_error(msg["id"], "preferences_unavailable", str(error))
                return
            connection.send_result(msg["id"], snapshot)

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/preferences/update",
            vol.Required("profile_id"): str,
            vol.Required("expected_profile"): dict,
            vol.Required("alert_events"): [str],
            vol.Optional("reviewed_event_ids", default=[]): [str],
            vol.Optional("marine_warning_mode"): vol.In(["always", "on_water"]),
            vol.Optional("marine_nearby_enabled"): bool,
            vol.Optional("marine_nearby_miles"): vol.Any(int, float),
            vol.Optional("dnd_bypass"): bool,
            vol.Optional("dnd_rule_ids"): [str],
            vol.Optional("dnd_confirmed"): bool,
            vol.Optional("outage_dnd_enabled"): bool,
        })
        @websocket_api.async_response
        async def update_preferences(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            try:
                actor = await async_actor(hass, connection)
                saved = await async_save_alert_preferences(hass, entry, actor, msg)
            except ValueError as error:
                connection.send_error(msg["id"], "invalid_preferences", str(error))
                return
            if not await async_reload_preserving_panel(hass, entry):
                connection.send_error(msg["id"], "activation_failed", "Your choices were saved, but activation failed. Restart Home Assistant before relying on the changed settings.")
                return
            connection.send_result(msg["id"], {"saved": True, "profile": saved})

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/preferences/remove",
            vol.Required("profile_id"): str,
            vol.Required("expected_profile"): dict,
        })
        @websocket_api.async_response
        async def remove_profile(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            try:
                actor = await async_actor(hass, connection)
                await async_remove_profile(hass, entry, actor, msg)
            except ValueError as error:
                connection.send_error(msg["id"], "invalid_preferences", str(error))
                return
            if not await async_reload_preserving_panel(hass, entry):
                connection.send_error(msg["id"], "activation_failed", "Your choices were saved, but activation failed. Restart Home Assistant before relying on the changed settings.")
                return
            connection.send_result(msg["id"], {"saved": True})

        @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/onboarding/get", vol.Optional("progress_user_id"): str})
        @websocket_api.async_response
        async def get_onboarding(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                actor = await async_actor(hass, connection)
                snapshot = await async_onboarding_snapshot(hass, _single_entry(hass), actor, msg.get("progress_user_id"))
            except ValueError as error:
                connection.send_error(msg["id"], "onboarding_unavailable", str(error))
                return
            connection.send_result(msg["id"], snapshot)

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/onboarding/update",
            vol.Optional("progress_user_id"): str,
            vol.Required("expected_revision"): int,
            vol.Optional("mode"): vol.In(["quick", "guided", "custom"]),
            vol.Optional("stage"): vol.In(sorted(STAGES)),
            vol.Optional("target_user_id"): str,
            vol.Optional("device_count"): vol.In(["single", "multiple"]),
            vol.Optional("selected_device_id"): str,
            vol.Optional("selected_device_ids"): [str],
            vol.Optional("multiple_settings"): vol.In(["shared", "individual"]),
            vol.Optional("workflow_action"): vol.In(["configure_devices", "saved_settings_fresh", "saved_settings_apply", "saved_settings_back", "back_to_devices", "intro_next", "intro_back", "guided_answer", "guided_next", "guided_back", "recommendations_next", "recommendations_back", "marine_answer", "marine_next", "marine_back", "delivery_next", "delivery_back", "dnd_default", "dnd_custom", "dnd_toggle", "dnd_customize_next", "dnd_back", "dnd_confirm_next", "daily_answer", "daily_next", "daily_back", "notification_back"]),
            vol.Optional("saved_settings_id"): str,
            vol.Optional("saved_settings_revision"): int,
            vol.Optional("dnd_rule"): str,
            vol.Optional("daily_outlook_enabled"): bool,
            vol.Optional("daily_outlook_time"): str,
            vol.Optional("guided_question"): vol.In(["marine", "shoreline", "avalanche", "volcanic"]),
            vol.Optional("guided_answer"): bool,
            vol.Optional("alert_path"): vol.In(sorted(ALERT_PATHS)),
            vol.Optional("alert_action"): vol.In(["start", "answer", "advisory_answer", "watch_answer", "statement_answer", "marine_mode", "next", "previous", "back_to_alerts", "notification_setup", "back_to_dnd"]),
            vol.Optional("alert_event"): str,
            vol.Optional("alert_enabled"): bool,
            vol.Optional("watch_enabled"): bool,
            vol.Optional("advisory_enabled"): bool,
            vol.Optional("statement_enabled"): bool,
            vol.Optional("marine_warning_mode"): vol.In(["always", "on_water"]),
            vol.Optional("marine_nearby_enabled"): bool,
            vol.Optional("marine_nearby_miles"): vol.Any(int, float),
            vol.Optional("dnd_bypass"): bool,
        })
        @websocket_api.async_response
        async def update_onboarding(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                actor = await async_actor(hass, connection)
                snapshot = await async_save_account_progress(hass, _single_entry(hass), actor, msg)
            except ValueError as error:
                connection.send_error(msg["id"], "invalid_onboarding", str(error))
                return
            connection.send_result(msg["id"], snapshot)

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/onboarding/notifications",
            vol.Optional("progress_user_id"): str,
            vol.Required("expected_revision"): int,
            vol.Required("request_id"): str,
            vol.Required("device_id"): str,
            vol.Required("action"): vol.In(sorted(NOTIFICATION_ACTIONS)),
            vol.Optional("value"): bool,
            vol.Optional("person_id"): str,
        })
        @websocket_api.async_response
        async def notification_setup(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                actor = await async_actor(hass, connection)
                entry = _single_entry(hass)
                from .onboarding_accounts import account_state
                from .setup_resume import progress_owner
                source_id = progress_owner(actor, msg.get("progress_user_id"))
                was_complete = account_state(effective_entry_config(entry), source_id).get("stage") == "notification_complete"
                snapshot = await async_notification_action(hass, entry, actor, msg)
                if msg["action"] == "finish" and not was_complete:
                    snapshot = await async_activate_saved_notifications(hass, entry, actor, source_id)
            except ValueError as error:
                connection.send_error(msg["id"], "notification_setup_failed", str(error))
                return
            connection.send_result(msg["id"], snapshot)

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/device_settings",
            vol.Optional("action"): vol.In(["list", "save_named", "rename", "delete", "restore"]),
            vol.Optional("expected_revision"): int,
            vol.Optional("expected_onboarding_revision"): int,
            vol.Optional("settings_id"): str,
            vol.Optional("device_id"): str,
            vol.Optional("name"): str,
        })
        @websocket_api.async_response
        async def device_settings(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                actor = await async_actor(hass, connection)
                result = await async_manage_saved_settings(hass, _single_entry(hass), actor, msg)
            except ValueError as error:
                connection.send_error(msg["id"], "invalid_saved_settings", str(error))
                return
            connection.send_result(msg["id"], result)

        @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/dashboard/get"})
        @websocket_api.require_admin
        @websocket_api.async_response
        async def get_dashboard(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            gate = onboarding_snapshot(effective_entry_config(entry), testing=hass.data.get(DOMAIN, {}).get("onboarding_testing", False))
            connection.send_result(msg["id"], build_dashboard_snapshot(hass, entry) if gate["dashboard_available"] else None)

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/dashboard/report", vol.Required("report_id"): str,
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def get_report(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                report = await hass.async_add_executor_job(
                    get_official_report, _single_entry(hass), msg["report_id"])
            except (ValueError, OSError):
                connection.send_error(msg["id"], "report_unavailable", "Official report unavailable. Try again later.")
                return
            connection.send_result(msg["id"], report)

        @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config/get"})
        @websocket_api.require_admin
        @websocket_api.async_response
        async def get_config(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            connection.send_result(msg["id"], build_panel_snapshot(hass, entry))

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/onboarding/mode",
            vol.Optional("mode"): vol.In(["quick", "custom"]),
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def set_onboarding_mode(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            state = onboarding_progress(effective_entry_config(entry), msg.get("mode"))
            hass.config_entries.async_update_entry(entry, options={**entry.options, ONBOARDING_KEY: state})
            connection.send_result(msg["id"], onboarding_snapshot(effective_entry_config(entry), testing=hass.data.get(DOMAIN, {}).get("onboarding_testing", False)))

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/config/update",
            vol.Required("config"): dict,
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def update_config(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            try:
                actor = await async_actor(hass, connection)
                original_config = effective_entry_config(entry)
                options = normalize_panel_update(msg["config"], original_config)
                library = library_from_config(original_config)
                if capture_profile_settings(library, hass, {**original_config, **options}, actor.id):
                    options[SAVED_DEVICE_SETTINGS] = library
                await async_commit_profile_update(hass, entry, actor, options,
                    expected_profiles=original_config.get(CONF_PROFILES, []))
            except ValueError as error:
                connection.send_error(msg["id"], "invalid_config", str(error))
                return
            if not await async_reload_preserving_panel(hass, entry):
                connection.send_error(msg["id"], "activation_failed", "Your choices were saved, but activation failed. Restart Home Assistant before relying on the changed settings.")
                return
            connection.send_result(msg["id"], {"saved": True})

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/config/profile/update",
            vol.Required("profile"): dict,
            vol.Required("expected_profile"): vol.Any(dict, None),
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def update_profile(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            entry = _single_entry(hass)
            try:
                actor = await async_actor(hass, connection)
                original_config = effective_entry_config(entry)
                update = normalize_single_profile_update(msg, original_config)
                library = library_from_config(original_config)
                if capture_profile_settings(library, hass, {**original_config, **update}, actor.id):
                    update[SAVED_DEVICE_SETTINGS] = library
                await async_commit_profile_update(hass, entry, actor, update,
                    expected_profiles=original_config.get(CONF_PROFILES, []))
            except ValueError as error:
                connection.send_error(msg["id"], "invalid_profile", str(error))
                return
            if not await async_reload_preserving_panel(hass, entry):
                connection.send_error(msg["id"], "activation_failed", "Your choices were saved, but activation failed. Restart Home Assistant before relying on the changed settings.")
                return
            profile = _profile_by_id(entry, msg["profile"]["profile_id"])
            connection.send_result(msg["id"], {"saved": True, "profile": profile_to_dict(profile)})

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/mobile_setup/send_ios_handoff",
            vol.Required("profile_id"): str,
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def send_ios_handoff(
            hass: Any, connection: Any, msg: dict[str, Any]
        ) -> None:
            entry = _single_entry(hass)
            try:
                profile = _profile_by_id(entry, msg["profile_id"])
                setup_url = (
                    "/weather-intelligence?mobile_setup="
                    f"{quote(profile.profile_id, safe='')}"
                )
                await async_send_ios_setup_handoff(
                    hass, profile, setup_url=setup_url
                )
            except (ValueError, MobileTargetError) as error:
                connection.send_error(msg["id"], "mobile_setup_failed", str(error))
                return
            connection.send_result(msg["id"], {"sent": True, "url": setup_url})

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/mobile_setup/test_ios_speech",
            vol.Required("profile_id"): str,
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def test_ios_speech(
            hass: Any, connection: Any, msg: dict[str, Any]
        ) -> None:
            entry = _single_entry(hass)
            try:
                profile = _profile_by_id(entry, msg["profile_id"])
                await async_send_ios_spoken_alert_test(hass, profile)
            except (ValueError, MobileTargetError) as error:
                connection.send_error(msg["id"], "mobile_test_failed", str(error))
                return
            connection.send_result(msg["id"], {"sent": True})

        @websocket_api.websocket_command({
            vol.Required("type"): f"{DOMAIN}/mobile_setup/android",
            vol.Required("profile_id"): str,
            vol.Required("action"): vol.In(["handoff", "test", "prepare"]),
            vol.Optional("expected_profile"): dict,
        })
        @websocket_api.require_admin
        @websocket_api.async_response
        async def android_setup(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
            try:
                profile = _profile_by_id(_single_entry(hass), msg["profile_id"])
                if "expected_profile" in msg and profile_to_dict(profile) != msg["expected_profile"]:
                    raise ValueError("This person's saved setup changed. Reopen onboarding before testing.")
                if msg["action"] == "handoff":
                    await async_send_android_setup_handoff(
                        hass, profile, setup_url=f"/weather-intelligence?mobile_setup={quote(profile.profile_id, safe='')}"
                    )
                elif msg["action"] == "prepare":
                    await async_send_android_silent_setup(hass, profile)
                else:
                    await async_send_android_tone_speech_test(hass, profile)
            except ValueError as error:
                connection.send_error(msg["id"], "mobile_setup_failed", str(error))
                return
            connection.send_result(msg["id"], {"sent": True})

        websocket_api.async_register_command(hass, dismiss_account_notice)
        websocket_api.async_register_command(hass, android_setup)
        websocket_api.async_register_command(hass, get_preferences)
        websocket_api.async_register_command(hass, update_preferences)
        websocket_api.async_register_command(hass, remove_profile)
        websocket_api.async_register_command(hass, get_onboarding)
        websocket_api.async_register_command(hass, notification_setup)
        websocket_api.async_register_command(hass, update_onboarding)
        websocket_api.async_register_command(hass, device_settings)
        websocket_api.async_register_command(hass, set_onboarding_mode)
        websocket_api.async_register_command(hass, update_profile)
        websocket_api.async_register_command(hass, get_dashboard)
        websocket_api.async_register_command(hass, get_report)
        websocket_api.async_register_command(hass, get_config)
        websocket_api.async_register_command(hass, update_config)
        websocket_api.async_register_command(hass, send_ios_handoff)
        websocket_api.async_register_command(hass, test_ios_speech)
        from .reporting_api import register_reporting_commands
        register_reporting_commands(hass, _single_entry)
        from .feedback_api import register_feedback_commands
        register_feedback_commands(hass, _single_entry)
        data["panel_commands"] = True

    if not data.get("panel_registered"):
        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title="Weather Intelligence",
            sidebar_icon="mdi:weather-lightning",
            module_url=PANEL_MODULE_URL,
            embed_iframe=False,
            require_admin=False,
            config_panel_domain=DOMAIN,
        )
        data["panel_registered"] = True
    return True


async def async_reload_preserving_panel(hass: Any, entry: Any) -> bool:
    """Activate a settings save without removing the route or sidebar item.

    Serializing saves keeps one reload from clearing another reload's guard.
    Actual unload/removal still removes the panel normally.
    """
    data = hass.data.setdefault(DOMAIN, {})
    lock = data.setdefault("panel_reload_locks", {}).setdefault(entry.entry_id, asyncio.Lock())
    async with lock:
        previous = data.get("panel_reset_reload")
        data["panel_reset_reload"] = entry.entry_id
        try:
            return bool(await hass.config_entries.async_reload(entry.entry_id))
        except Exception:
            _LOGGER.warning("Saved Weather Intelligence settings could not be activated")
            return False
        finally:
            if previous is None:
                data.pop("panel_reset_reload", None)
            else:
                data["panel_reset_reload"] = previous


async def async_remove_admin_panel(hass: Any) -> None:
    data = getattr(hass, "data", {}).get(DOMAIN, {})
    if data.get("panel_reset_reload"):
        return
    if data.get("panel_registered"):
        try:
            from homeassistant.components import frontend
            frontend.async_remove_panel(hass, PANEL_URL)
        except ImportError:
            pass
        data["panel_registered"] = False


def _single_entry(hass: Any) -> Any:
    entries = hass.config_entries.async_entries(DOMAIN)
    if len(entries) != 1:
        raise ValueError("Weather Intelligence requires exactly one entry")
    return entries[0]


def _profile_by_id(entry: Any, profile_id: str):
    profile_id = str(profile_id).strip()
    for profile in profiles_from_config(effective_entry_config(entry)):
        if profile.profile_id == profile_id:
            return profile
    raise ValueError("That household profile no longer exists")


def _entity_choices(hass: Any, domain: str) -> list[dict[str, str]]:
    try:
        states = hass.states.async_all(domain)
    except AttributeError:
        states = []
    result = []
    for state in states:
        entity_id = str(getattr(state, "entity_id", ""))
        attributes = getattr(state, "attributes", {}) or {}
        name = str(attributes.get("friendly_name") or entity_id.split(".", 1)[-1].replace("_", " ").title())
        result.append({"value": entity_id, "label": name})
    return sorted(result, key=lambda item: item["label"].casefold())


def _legacy_choices(hass: Any) -> list[dict[str, str]]:
    try:
        services = hass.services.async_services().get("notify", {})
    except AttributeError:
        services = {}
    return [
        {"value": f"notify.{name}",
         "label": name.removeprefix("mobile_app_").replace("_", " ").title()}
        for name in sorted(services) if name.startswith("mobile_app_")
    ]


def _status_snapshot(coordinator: Any) -> dict[str, Any]:
    if coordinator is None or coordinator.data is None:
        return {"state": "starting", "active_incidents": 0}
    return {"state": coordinator.data.source_health.value,
            "active_incidents": coordinator.data.active_incident_count,
            "briefing": coordinator.briefing.state}
