"""Durable notice acknowledgement, separate from actual phone verification."""
from __future__ import annotations

from .config import effective_entry_config
from .const import (
    ANDROID_SIREN_REVIEW_MESSAGE,
    ANDROID_SIREN_REVIEW_NOTIFICATION,
    ANDROID_SIREN_REVIEW_PENDING,
)

ANDROID_SIREN_REVIEW_ACKNOWLEDGED = "android_siren_review_acknowledged"


def async_setup_siren_review_notice(hass, entry) -> None:
    """Keep Dismiss dismissed across restarts without completing phone setup."""
    from homeassistant.components import persistent_notification
    from homeassistant.core import callback

    config = effective_entry_config(entry)
    profile_ids = {profile.get("profile_id") for profile in config.get("profiles", [])}
    pending = set(config.get(ANDROID_SIREN_REVIEW_PENDING, [])) & profile_ids
    acknowledged = set(config.get(ANDROID_SIREN_REVIEW_ACKNOWLEDGED, []))
    shown_profiles = pending - acknowledged
    if not shown_profiles:
        persistent_notification.async_dismiss(hass, ANDROID_SIREN_REVIEW_NOTIFICATION)
        return

    @callback
    def notification_updated(update_type, notifications) -> None:
        if (update_type != persistent_notification.UpdateType.REMOVED
                or ANDROID_SIREN_REVIEW_NOTIFICATION not in notifications):
            return
        latest = effective_entry_config(entry)
        # Only acknowledge the profiles covered by the displayed notice. A new
        # affected device must still get its own review prompt. A completed
        # review removes pending state and needs no dismissal acknowledgement.
        still_pending = shown_profiles & set(latest.get(ANDROID_SIREN_REVIEW_PENDING, []))
        previous = set(latest.get(ANDROID_SIREN_REVIEW_ACKNOWLEDGED, []))
        if still_pending - previous:
            hass.config_entries.async_update_entry(entry, options={
                **entry.options,
                ANDROID_SIREN_REVIEW_ACKNOWLEDGED: sorted(previous | still_pending),
            })

    entry.async_on_unload(persistent_notification.async_register_callback(
        hass, notification_updated))
    persistent_notification.async_create(
        hass, ANDROID_SIREN_REVIEW_MESSAGE,
        title="Weather Intelligence: review Android siren setup",
        notification_id=ANDROID_SIREN_REVIEW_NOTIFICATION,
    )
