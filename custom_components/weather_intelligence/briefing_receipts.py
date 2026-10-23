"""Local Companion receipt matching. Registration secrets never leave HA."""

from __future__ import annotations

from hmac import compare_digest
from typing import Any, Mapping


def briefing_tag(profile_id: str, local_date: str) -> str:
    return f"weather_intelligence_daily_{profile_id}_{local_date}"


def received_briefing_profile(hass: Any, profiles: tuple, records: Mapping, event_data: Mapping) -> str | None:
    """Correlate the day's tag with HA's exact registered phone action."""
    tag, webhook = event_data.get("tag"), event_data.get("webhook_id")
    if not isinstance(tag, str) or not isinstance(webhook, str) or not webhook:
        return None
    notify = hass.data.get("mobile_app", {}).get("notify")
    targets = getattr(notify, "registered_targets", {})
    for profile in profiles:
        record = records.get(profile.profile_id)
        if record is None or record.confirmed_at is not None or not profile.enabled:
            continue
        expected = targets.get(profile.legacy_notify_service.removeprefix("notify."))
        if (isinstance(expected, str) and expected
                and compare_digest(webhook, expected)
                and tag == briefing_tag(profile.profile_id, record.local_date)):
            return profile.profile_id
    return None
