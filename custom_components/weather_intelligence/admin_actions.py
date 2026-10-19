"""Account-private notices attached to successful administrator profile saves."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .config import effective_entry_config, normalize_profiles

ADMIN_ACTION_NOTICES = "admin_action_notices"
ADMIN_ACTION_TITLE = "ADMIN ACTION"
ADMIN_ACTION_MESSAGE = "An admin has modified your profile preferences for Weather Intelligence"


def notice_message(record: Mapping[str, Any]) -> str:
    """Use server-authenticated attribution, with a neutral legacy fallback."""
    admin_name = record.get("admin_name")
    if record.get("kind") == "settings_changed" and not admin_name:
        return "Your Weather Intelligence notification settings have changed."
    if not admin_name:
        return ADMIN_ACTION_MESSAGE
    if record.get("kind") == "enrollment":
        return f"You have been enrolled in Weather Intelligence notifications by {admin_name}."
    return f"Your Weather Intelligence notification settings were changed by {admin_name}."


def account_notice(config: Mapping[str, Any], owner_id: str) -> dict | None:
    record = config.get(ADMIN_ACTION_NOTICES, {}).get(owner_id)
    if not record:
        return None
    return {
        "id": record["id"],
        "title": ADMIN_ACTION_TITLE,
        "message": notice_message(record),
        "created_at": record["created_at"],
    }


async def async_prepare_admin_notices(
    hass: Any,
    actor: Any,
    before_profiles: list,
    after_profiles: list,
    *,
    enrollment_owner_id: str | None = None,
) -> dict:
    """Determine recipients from HA ownership, never a supplied name or target."""
    from .onboarding_accounts import account_devices, human_account
    from .onboarding_preferences import profile_matches_device

    fresh_actor = await hass.auth.async_get_user(actor.id)
    if not human_account(fresh_actor):
        raise ValueError("Sign in again before saving profile preferences.")
    before = {profile.profile_id: profile for profile in normalize_profiles(before_profiles)}
    after = {profile.profile_id: profile for profile in normalize_profiles(after_profiles)}
    recipients: dict[str, set[str]] = {}
    enrolled_owners = set()
    for profile in before.values():
        person = hass.states.get(profile.person_entity_id)
        if person and profile.enabled and profile.automatic_notifications:
            enrolled_owners.add(person.attributes.get("user_id"))
    for profile_id in before.keys() | after.keys():
        previous, replacement = before.get(profile_id), after.get(profile_id)
        if previous == replacement:
            continue
        for profile in (previous, replacement):
            if profile is None:
                continue
            person = hass.states.get(profile.person_entity_id)
            owner_id = person.attributes.get("user_id") if person else None
            if owner_id == fresh_actor.id:
                continue
            if not fresh_actor.is_admin:
                raise ValueError("Only an administrator can change another account's profile.")
            owner = await hass.auth.async_get_user(owner_id) if owner_id else None
            if not human_account(owner):
                raise ValueError(
                    "Link the affected Person to an active HA account before changing their preferences."
                )
            allowed = {device["id"] for device in account_devices(hass, owner_id)}
            targets = recipients.setdefault(owner_id, set())
            for mobile in hass.config_entries.async_entries("mobile_app"):
                if mobile.entry_id in allowed and profile_matches_device(hass, profile, mobile):
                    targets.add(mobile.entry_id)
    fresh_actor = await hass.auth.async_get_user(actor.id)
    if not human_account(fresh_actor) or (recipients and not fresh_actor.is_admin):
        raise ValueError(
            "Sign in with an active administrator account before saving these changes."
        )
    admin_name = (
        " ".join(str(getattr(fresh_actor, "name", None) or "").split())[:128] or "Administrator"
    )
    return {
        owner_id: {
            "id": uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "admin_name": admin_name,
            "kind": "enrollment"
            if owner_id == enrollment_owner_id and owner_id not in enrolled_owners
            else "settings_changed",
            "device_ids": sorted(device_ids),
            "attempts": {},
        }
        for owner_id, device_ids in recipients.items()
    }


def queued_admin_notices(config: Mapping[str, Any], notices: dict) -> dict:
    return {**deepcopy(config.get(ADMIN_ACTION_NOTICES, {})), **deepcopy(notices)}


async def async_deliver_admin_notices(hass: Any, entry: Any) -> None:
    """Best-effort normal push plus a durable, owner-only in-app notice.

    Mark attempts before awaiting delivery. A crash or uncertain push response
    must not cause the same account notice to be resent after every restart.
    """
    from .mobile_notification import _async_send_to_target
    from .onboarding_accounts import account_devices, human_account
    from .onboarding_notifications import exact_target

    notices = deepcopy(effective_entry_config(entry).get(ADMIN_ACTION_NOTICES, {}))
    for owner_id, record in notices.items():
        owner = await hass.auth.async_get_user(owner_id)
        if not human_account(owner):
            continue
        for device_id in record["device_ids"]:
            latest = deepcopy(effective_entry_config(entry).get(ADMIN_ACTION_NOTICES, {}))
            current = latest.get(owner_id, {})
            if current.get("id") != record["id"] or device_id in current.get("attempts", {}):
                continue
            allowed = {device["id"] for device in account_devices(hass, owner_id)}
            mobile = next(
                (
                    device
                    for device in hass.config_entries.async_entries("mobile_app")
                    if device.entry_id == device_id and device_id in allowed
                ),
                None,
            )
            try:
                target = exact_target(hass, mobile) if mobile else None
            except ValueError:
                target = None
            current.setdefault("attempts", {})[device_id] = "attempted" if target else "unavailable"
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, ADMIN_ACTION_NOTICES: latest}
            )
            if not target:
                continue
            outcome = "sent"
            try:
                await _async_send_to_target(
                    hass,
                    notify_entity="",
                    legacy_action=target,
                    title=ADMIN_ACTION_TITLE,
                    message=notice_message(record),
                    companion_data={
                        "channel": "Weather Intelligence account notices",
                        "importance": "default",
                        "tag": "wi_admin_" + record["id"],
                        "url": "/weather-intelligence",
                        "push": {"interruption-level": "active"},
                    },
                )
            except Exception:
                outcome = "uncertain"
            latest = deepcopy(effective_entry_config(entry).get(ADMIN_ACTION_NOTICES, {}))
            if latest.get(owner_id, {}).get("id") == record["id"]:
                latest[owner_id]["attempts"][device_id] = outcome
                hass.config_entries.async_update_entry(
                    entry, options={**entry.options, ADMIN_ACTION_NOTICES: latest}
                )


async def async_commit_profile_update(
    hass: Any, entry: Any, actor: Any, updates: dict, *, expected_profiles: list | None = None
) -> None:
    """Commit preferences and their required notices in the same options write."""
    from .onboarding_notifications import progress_lock

    async with progress_lock(hass, entry):
        from .persistence import async_reconcile_profile_reference, async_record_profile_reference

        await async_reconcile_profile_reference(hass, entry)
        previous = deepcopy(effective_entry_config(entry).get("profiles", []))
        if expected_profiles is not None and previous != expected_profiles:
            raise ValueError("Profile preferences changed. Reopen settings before saving.")
        proposed = updates.get("profiles", previous)
        notices = await async_prepare_admin_notices(hass, actor, previous, proposed)
        config = effective_entry_config(entry)
        if config.get("profiles", []) != previous:
            raise ValueError(
                "Profile preferences changed while saving. Reopen settings and try again."
            )
        options = {**entry.options, **updates}
        if notices:
            options[ADMIN_ACTION_NOTICES] = queued_admin_notices(config, notices)
        hass.config_entries.async_update_entry(entry, options=options)
        await async_record_profile_reference(hass, entry)
        await async_deliver_admin_notices(hass, entry)
