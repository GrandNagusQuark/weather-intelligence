"""DND choices for existing profiles, reusing onboarding's scoped rule catalog."""

from __future__ import annotations

from typing import Any, Mapping

from .config import normalize_profile_input
from .onboarding_accounts import account_devices
from .onboarding_dnd import apply_home_context, dnd_snapshot
from .onboarding_preferences import profile_matches_device

DND_EDIT_FIELDS = {"dnd_bypass", "dnd_rule_ids", "dnd_confirmed"}


def profile_dnd_catalog(hass: Any) -> list[dict]:
    """Public rule descriptions/defaults; no profile mutation or permission changes."""
    state = {"alert_path": "all", "dnd_bypass": True}
    apply_home_context(state, hass)
    return dnd_snapshot(state)["choices"]


def profile_dnd_setup_status(hass: Any, entry: Any, profile: Mapping[str, Any]) -> str:
    """Report recorded test evidence, never infer current OS permission from enrollment."""
    from .config import effective_entry_config
    from .onboarding_accounts import ACCOUNT_PROGRESS
    from .onboarding_notifications import _binding

    device_id = profile.get("companion_device_id")
    if not device_id:
        return "unverified"
    person = hass.states.get(profile.get("person_entity"))
    owner_id = person.attributes.get("user_id") if person else None
    for state in effective_entry_config(entry).get(ACCOUNT_PROGRESS, {}).values():
        if (
            not owner_id
            or state.get("target_user_id") != owner_id
            or state.get("notification_person_id") != profile.get("person_entity")
        ):
            continue
        progress = state.get("notification_devices", {}).get(device_id, {})
        try:
            binding = _binding(
                state,
                device_id,
                profile.get("legacy_notify_service", ""),
                profile.get("mobile_platform", "auto"),
                [dict(profile)],
            )
        except (KeyError, ValueError):
            continue
        if progress.get("binding") != binding:
            continue
        return (
            "user_confirmed"
            if progress.get("permissions") is True and progress.get("critical_confirmed") is True
            else "incomplete"
        )
    return "unverified"


def apply_profile_dnd_changes(
    hass: Any, profile: Mapping[str, Any], selected_events: set[str], payload: Mapping[str, Any]
) -> dict:
    """Validate one explicitly reviewed edit without enabling ordinary delivery."""
    if not DND_EDIT_FIELDS.intersection(payload):
        return dict(profile)
    if (
        not DND_EDIT_FIELDS.issubset(payload)
        or type(payload.get("dnd_bypass")) is not bool
        or payload.get("dnd_confirmed") is not True
    ):
        raise ValueError("Review and confirm your Do Not Disturb choices before saving.")
    rules = payload.get("dnd_rule_ids")
    allowed = {
        rule["id"]
        for rule in profile_dnd_catalog(hass)
        if selected_events.intersection(rule.get("events", [rule["event"]]))
    }
    if not isinstance(rules, list) or any(
        not isinstance(rule, str) or rule not in allowed for rule in rules
    ):
        raise ValueError("Choose bypass rules only for alerts this device receives.")
    enabled = payload["dnd_bypass"]
    outage_enabled = payload.get("outage_dnd_enabled", profile.get("outage_dnd_enabled", False))
    if type(outage_enabled) is not bool or outage_enabled and not enabled:
        raise ValueError("Enable and review Do Not Disturb bypass before allowing outage notices to interrupt it.")
    if enabled:
        if not profile.get("automatic_official_warning_notifications"):
            raise ValueError("Complete notification setup before enabling Do Not Disturb bypass.")
        normalized = normalize_profile_input({**profile, "critical_notifications_enabled": True})
        person = hass.states.get(normalized.person_entity_id)
        owner_id = person.attributes.get("user_id") if person else None
        allowed_devices = (
            {device["id"] for device in account_devices(hass, owner_id)} if owner_id else set()
        )
        verified = any(
            device.entry_id in allowed_devices
            and (
                not normalized.companion_device_id
                or normalized.companion_device_id == device.entry_id
            )
            and profile_matches_device(hass, normalized, device)
            for device in hass.config_entries.async_entries("mobile_app")
        )
        if not verified:
            raise ValueError(
                "Reopen notification setup to verify this device before enabling bypass."
            )
    return {
        **profile,
        "critical_notifications_enabled": enabled,
        "dnd_rule_ids": list(dict.fromkeys(rules)),
        "outage_dnd_enabled": outage_enabled,
    }
