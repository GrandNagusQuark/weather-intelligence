"""Per-Person local on-water inference, independent of enrollment or map display."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .water_detection import current_water_state


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    known: set[str] = set()

    def add_person(state: Any) -> None:
        if state.entity_id in known:
            return
        known.add(state.entity_id)
        async_add_entities([WeatherIntelligenceOnWaterSensor(
            entry.runtime_data, entry.entry_id, state.entity_id,
            state.attributes.get("friendly_name") or state.entity_id.split(".", 1)[1],
        )])

    for state in hass.states.async_all("person"):
        add_person(state)

    @callback
    def person_added(event: Any) -> None:
        entity_id = event.data.get("entity_id", "")
        state = event.data.get("new_state")
        if entity_id.startswith("person.") and state is not None:
            add_person(state)

    entry.async_on_unload(hass.bus.async_listen("state_changed", person_added))


class WeatherIntelligenceOnWaterSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_icon = "mdi:waves"
    _attr_has_entity_name = False

    def __init__(self, coordinator: Any, entry_id: str, person_id: str, name: str) -> None:
        super().__init__(coordinator)
        self._person_id = person_id
        self._attr_unique_id = f"{entry_id}_{person_id}_on_water"
        self._attr_name = f"Weather Intelligence {name} On water"

    @property
    def available(self) -> bool:
        return self.coordinator.hass.states.get(self._person_id) is not None and self.is_on is not None

    @property
    def is_on(self) -> bool | None:
        return current_water_state(self.coordinator.water_assessments.get(self._person_id))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        assessment = self.coordinator.water_assessments.get(self._person_id)
        reason = assessment.reason if assessment else "awaiting_location"
        if assessment and assessment.on_water is not None and self.is_on is None:
            reason = "location_stale_or_missing"
        return {"classification": "water" if self.is_on is True else "land" if self.is_on is False else "unknown",
                "reason": reason, "method": "local_regional_water_estimate",
                "shoreline_dataset": "USGS 3DHP regional water maps — Early state"}
