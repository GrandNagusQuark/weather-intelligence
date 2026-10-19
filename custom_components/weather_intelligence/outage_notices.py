"""Local hazard checks and restart safe deduplication of service notices."""

from datetime import datetime, timedelta, timezone

from .config import effective_entry_config, profiles_from_config
from .geometry import point_in_geometry, circle_overlaps_geometry
from .ha_location import location_fix_from_person_state
from .hazard_policy import DeliveryBehavior
from .mobile_notification import async_send_profile_notification

SEVERE_EVENTS = {"Tornado Warning", "Tornado Watch", "Severe Thunderstorm Warning", "Severe Thunderstorm Watch"}


def severe_weather_near_profile(hass, coordinator, profile, now):
    """Require recent official evidence and local geography, never a remote claim."""
    if not profile.outage_dnd_enabled or not profile.critical_notifications:
        return False
    fix = location_fix_from_person_state(hass.states.get(profile.person_entity_id))
    if (not profile.receive_personal_alerts or fix is None or fix.reported_stale
            or fix.latitude is None or fix.longitude is None or fix.observed_at is None
            or not -60 <= (now - fix.observed_at).total_seconds() <= 300
            or fix.accuracy_meters is None or fix.accuracy_meters > 1000):
        return False
    for record in getattr(getattr(coordinator, "core", None), "incident_records", ()):
        alert = record.latest_alert
        observed_at = getattr(coordinator, "nws_alert_observed_at", {}).get(
            getattr(alert, "official_message_id", ""), alert.received_at)
        if (getattr(record.phase, "value", "") != "active" or alert.source != "NWS"
                or alert.status != "Actual" or alert.event not in SEVERE_EVENTS
                or not -60 <= (now - observed_at).total_seconds() <= 7200
                or alert.expires_at is None or alert.expires_at <= now
                or alert.effective_at is None or alert.effective_at > now + timedelta(hours=2)
                or alert.onset_at is not None and alert.onset_at > now + timedelta(hours=2)
                or not alert.geometry):
            continue
        point = (fix.longitude, fix.latitude)
        if point_in_geometry(point, alert.geometry) or circle_overlaps_geometry(point, fix.accuracy_meters, alert.geometry):
            return True
    return False


class OutageNotices:
    def __init__(self, hass, entry, store):
        self.hass, self.entry, self.store = hass, entry, store
        self.delivered = {}
        self.open = False

    async def load(self):
        saved = await self.store.async_load()
        if isinstance(saved, dict):
            self.open = saved.get("open") is True
            rows = saved.get("delivered", {})
            if isinstance(rows, dict):
                self.delivered = {key: value for key, value in list(rows.items())[:500]
                                  if isinstance(key, str) and value in ("normal", "critical", "recovered")}

    async def save(self):
        await self.store.async_save({"open": self.open, "delivered": self.delivered})

    async def update(self, status):
        state = status.get("state")
        if state not in ("available", "corroborated_outage", "corroborated_delay"):
            return
        recovery = state == "available"
        if recovery and not self.open:
            return
        if not recovery:
            self.open = True
        now = datetime.now(timezone.utc)
        profiles = profiles_from_config(effective_entry_config(self.entry))
        active_ids = {profile.profile_id for profile in profiles if profile.enabled}
        self.delivered = {key: value for key, value in self.delivered.items() if key in active_ids}
        for profile in profiles:
            if not profile.enabled or not profile.automatic_notifications:
                continue
            previous = self.delivered.get(profile.profile_id)
            if recovery and previous not in ("normal", "critical"):
                continue
            critical = not recovery and severe_weather_near_profile(self.hass, self.entry.runtime_data, profile, now)
            level = "recovered" if recovery else "critical" if critical else "normal"
            if previous == level or previous == "critical" and not recovery:
                continue
            # Record intent first. A storage failure must never produce an untracked wakeup.
            self.delivered[profile.profile_id] = level
            try:
                await self.save()
            except Exception:
                if previous is None:
                    self.delivered.pop(profile.profile_id, None)
                else:
                    self.delivered[profile.profile_id] = previous
                raise
            message = ("The latest checks no longer corroborate a shared NWS service problem. This does not confirm every alert was delivered."
                       if recovery else "A shared NWS alert feed access problem has been corroborated. Weather Intelligence may miss or delay alerts. Use NOAA Weather Radio and other official warning sources.")
            if state == "corroborated_delay":
                message = "Shared reports and an independent source check indicate that newly observed NWS alerts are reaching the integration at least five minutes after their stated issue time. Use NOAA Weather Radio and other official warning sources."
            if critical:
                message += " The last available official severe weather watch or warning applies to your current location now or within two hours. Newer changes may be unavailable."
            try:
                await async_send_profile_notification(self.hass, profile,
                    title="Weather alert service update", message=message,
                    stable_tag="weather_intelligence_source_outage", critical=critical,
                    behavior=DeliveryBehavior.IMPORTANT, soft_critical=True)
            except Exception:
                if previous is None:
                    self.delivered.pop(profile.profile_id, None)
                else:
                    self.delivered[profile.profile_id] = previous
                await self.save()
        if recovery and all(value == "recovered" for value in self.delivered.values()):
            self.open = False
            self.delivered = {}
            await self.save()
