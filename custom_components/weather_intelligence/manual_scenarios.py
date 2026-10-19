"""Isolated, manual-only notification scenarios using the real safety core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import (
    TEST_SCENARIO_CANCEL,
    TEST_SCENARIO_NEW,
    TEST_SCENARIO_UPDATE,
    TEST_SCENARIOS,
)
from .coordinator import WeatherCoordinator
from .incident_presentation import build_primary_incident_view
from .models import LocationFix, MonitoredSubject, NotificationPayload, SubjectKind
from .scenario_data import tornado_scenario_features


@dataclass(frozen=True)
class ManualScenarioMessage:
    title: str
    message: str


def build_manual_scenario_message(scenario: str) -> ManualScenarioMessage:
    """Run one throwaway recorded lifecycle and return one safe review message."""
    if scenario not in TEST_SCENARIOS:
        raise ValueError("Unknown manual weather review scenario")

    features = tornado_scenario_features()
    step_count = {
        TEST_SCENARIO_NEW: 1,
        TEST_SCENARIO_UPDATE: 2,
        TEST_SCENARIO_CANCEL: 3,
    }[scenario]
    initial_time = _official_time(features[0])
    coordinator = WeatherCoordinator(
        [
            MonitoredSubject(
                "designated_home",
                "Designated home",
                SubjectKind.DESIGNATED_HOME,
                LocationFix(35.5, -97.5, None, None),
            ),
            MonitoredSubject(
                "protected_person",
                "Protected person",
                SubjectKind.PERSON,
                LocationFix(35.5, -97.5, initial_time, 25),
            ),
        ]
    )

    generated: list[NotificationPayload] = []
    for feature in features[:step_count]:
        official_time = _official_time(feature)
        generated = coordinator.process_official_payload(
            {"type": "FeatureCollection", "features": [feature]},
            official_time + timedelta(seconds=2),
            official_time + timedelta(minutes=1),
            location_updates={
                "protected_person": LocationFix(35.5, -97.5, official_time, 25)
            },
        )

    if coordinator.status is None or not generated:
        raise RuntimeError("Manual scenario did not produce review wording")
    view = build_primary_incident_view(
        coordinator.status,
        coordinator.incident_records,
        coordinator.notification_records,
    )
    representative = next(
        (item for item in generated if item.subject_kind == SubjectKind.PERSON),
        generated[0],
    )
    label = {
        TEST_SCENARIO_NEW: "new-warning",
        TEST_SCENARIO_UPDATE: "meaningful-update",
        TEST_SCENARIO_CANCEL: "cancellation/resolution",
    }[scenario]
    return ManualScenarioMessage(
        title=f"TEST ONLY — {representative.title}",
        message=(
            f"TEST ONLY — Recorded-data {label} scenario for {view.applies_to}. "
            f"{representative.message} This manual review did not change live weather state."
        ),
    )


def _official_time(feature: dict[str, object]) -> datetime:
    properties = feature["properties"]
    if not isinstance(properties, dict):
        raise ValueError("Scenario feature has no properties")
    return datetime.fromisoformat(str(properties["sent"]))
