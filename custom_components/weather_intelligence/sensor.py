"""Compact Home Assistant status surface for a wired coordinator."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    async_add_entities(
        [
            WeatherIntelligenceStatusSensor(entry.runtime_data, entry.entry_id),
            WeatherIntelligencePrimaryIncidentSensor(
                entry.runtime_data,
                entry.entry_id,
            ),
            WeatherIntelligenceDailyBriefingSensor(entry.runtime_data, entry.entry_id),
        ]
    )


class WeatherIntelligenceStatusSensor(CoordinatorEntity, SensorEntity):
    """One compact state with small, useful diagnostic attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "protection_status"
    _attr_icon = "mdi:weather-lightning"

    def __init__(self, coordinator: Any, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_protection_status"

    @property
    def native_value(self) -> str:
        status = self.coordinator.data
        return status.source_health.value if status else "initializing"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.data
        if status is None:
            return {"detail": "Weather Intelligence is awaiting its first source check."}
        return {
            "active_incidents": status.active_incident_count,
            "person_relevant_incidents": status.person_relevant_count,
            "home_relevant_incidents": status.home_relevant_count,
            "monitoring_scope": (
                "designated_home_and_person"
                if status.personal_tracking_configured
                else "designated_home_only"
            ),
            "personal_tracking_configured": status.personal_tracking_configured,
            "mobile_test_target_configured": status.mobile_test_target_configured,
            "person_location_status": status.person_location_freshness.value,
            "configured_profiles": status.configured_profile_count,
            "enabled_profiles": status.enabled_profile_count,
            "fresh_people": status.fresh_person_count,
            "degraded_people": status.degraded_person_count,
            "unknown_people": status.unknown_person_count,
            "automatic_notification_profiles": status.automatic_profile_count,
            "critical_notification_profiles": status.critical_profile_count,
            "partial_source_degradation": status.partial_source_degradation,
            "critical_mobile_delivery": status.critical_profile_count > 0,
            "hail_tracking_status": self.coordinator.hail_tracking_state,
            "hail_last_observed_at": (
                self.coordinator.hail_last_observed_at.isoformat()
                if self.coordinator.hail_last_observed_at
                else None
            ),
            "generated_at": status.generated_at.isoformat(),
        }


class WeatherIntelligencePrimaryIncidentSensor(CoordinatorEntity, SensorEntity):
    """Plain-language primary incident with a bounded set of official facts."""

    _attr_has_entity_name = True
    _attr_translation_key = "primary_incident"
    _attr_icon = "mdi:alert-outline"

    def __init__(self, coordinator: Any, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_primary_incident"

    @property
    def _view(self) -> Any:
        from .incident_presentation import build_primary_incident_view

        return build_primary_incident_view(
            self.coordinator.data,
            self.coordinator.core.incident_records,
            self.coordinator.core.notification_records,
        )

    @property
    def native_value(self) -> str:
        return self._view.state

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return self._view.attributes()


class WeatherIntelligenceDailyBriefingSensor(CoordinatorEntity, SensorEntity):
    """Compact shared daily safety picture with bounded source-native facts."""

    _attr_has_entity_name = True
    _attr_translation_key = "daily_briefing"
    _attr_icon = "mdi:weather-partly-cloudy"

    def __init__(self, coordinator: Any, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_daily_briefing"

    @property
    def native_value(self) -> str:
        return self.coordinator.briefing.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        briefing = self.coordinator.briefing
        return {
            "summary": briefing.summary,
            "item_count": len(briefing.items),
            "items": [
                {"source": item.source, "family": item.family,
                 "headline": item.headline, "native_level": item.native_level,
                 "valid_to": item.valid_to.isoformat() if item.valid_to else None}
                for item in briefing.items
            ],
            "source_states": {key: value.value for key, value in briefing.source_states.items()},
            "picture_incomplete": briefing.incomplete,
            "generated_at": briefing.generated_at.isoformat(),
        }
