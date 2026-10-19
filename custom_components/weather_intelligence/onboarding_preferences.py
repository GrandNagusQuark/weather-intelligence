"""Transfer a saved marine choice only across a verified account/device boundary."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from .config import effective_entry_config, profiles_from_config
from .const import CONF_PROFILES, CONF_PROFILE_ID, CONF_MARINE_WARNING_MODE
from .models import HouseholdProfile
from .onboarding_accounts import ACCOUNT_PROGRESS, account_devices, human_account
from .onboarding_workflow import selected_ids


def profile_matches_device(hass: Any, profile: HouseholdProfile, mobile_entry: Any) -> bool:
    """Use registry/registered targets, never phone names, slugs, or inferred people."""
    person = hass.states.get(profile.person_entity_id)
    if person is None or person.attributes.get("user_id") != mobile_entry.data.get("user_id"):
        return False
    found = False
    if profile.notify_entity_id:
        from homeassistant.helpers import entity_registry as er
        registered = er.async_get(hass).async_get(profile.notify_entity_id)
        if registered is None or registered.platform != "mobile_app" or registered.config_entry_id != mobile_entry.entry_id:
            return False
        found = True
    if profile.legacy_notify_service:
        # HA's actual registered target mapping binds the action to its webhook.
        # These identifiers stay internal; no request or notification is sent.
        service = profile.legacy_notify_service.removeprefix("notify.")
        notify = hass.data.get("mobile_app", {}).get("notify")
        targets = getattr(notify, "registered_targets", {})
        webhook = mobile_entry.data.get("webhook_id")
        if not webhook or targets.get(service) != webhook or not hass.services.has_service("notify", service):
            return False
        found = True
    return found


async def async_apply_saved_marine_preferences(hass: Any, entry: Any,
                                              profiles: Iterable[HouseholdProfile] | None = None) -> tuple[HouseholdProfile, ...]:
    """Copy only this preference; never enroll, enable delivery, or complete setup.

    Other-account drafts apply only at final enrollment, when the preference
    change and its ADMIN ACTION notice can be saved together. Own-account
    choices can apply as soon as the verified target exists.
    """
    from .persistence import async_reconcile_profile_reference, async_record_profile_reference
    await async_reconcile_profile_reference(hass, entry)
    config = effective_entry_config(entry)
    profiles = tuple(profiles) if profiles is not None else profiles_from_config(config)
    if not profiles:
        return profiles
    saved = config.get(ACCOUNT_PROGRESS, {})
    if not isinstance(saved, Mapping):
        return profiles
    modes: dict[str, str] = {}
    proofs: dict[str, Mapping[str, Any]] = {}
    for actor_id, state in saved.items():
        if not isinstance(state, Mapping):
            continue
        if not state.get("initiated") or state.get("target_user_id") != actor_id:
            continue
        actor = await hass.auth.async_get_user(actor_id)
        if not human_account(actor):
            continue
        allowed = {device["id"] for device in account_devices(hass, actor_id)}
        for selected in selected_ids(state):
            draft = state.get("device_drafts", {}).get(selected)
            if isinstance(draft, Mapping):
                mode = draft.get("marine_warning_mode") if draft.get("owner") == actor_id else None
            else:
                mode = state.get("marine_warning_mode") if selected == state.get("selected_device_id") else None
            if selected not in allowed or mode not in {"always", "on_water"}:
                continue
            mobile_entry = next((item for item in hass.config_entries.async_entries("mobile_app") if item.entry_id == selected), None)
            if mobile_entry is None:
                continue
            matching = [profile for profile in profiles if profile_matches_device(hass, profile, mobile_entry)]
            if len(matching) == 1:
                modes[matching[0].profile_id] = mode
                proofs[actor_id] = state
    updated = tuple(replace(profile, marine_warning_mode=modes.get(profile.profile_id, profile.marine_warning_mode)) for profile in profiles)
    if updated != profiles:
        # Re-read after auth awaits. A concurrent wizard/settings save is not overwritten.
        latest_config = effective_entry_config(entry)
        latest = profiles_from_config(latest_config)
        if latest != profiles or any(latest_config.get(ACCOUNT_PROGRESS, {}).get(actor_id) != state for actor_id, state in proofs.items()):
            raise ValueError("Profile settings changed. Reopen onboarding before applying your marine preference.")
        raw_profiles = [{**raw, **({CONF_MARINE_WARNING_MODE: modes[raw.get(CONF_PROFILE_ID)]}
                                  if raw.get(CONF_PROFILE_ID) in modes else {})}
                        for raw in latest_config.get(CONF_PROFILES, [])]
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_PROFILES: raw_profiles})
        await async_record_profile_reference(hass, entry)
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            runtime.apply_marine_preferences(modes)
    return updated
