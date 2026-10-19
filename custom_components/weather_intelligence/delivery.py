"""Deterministic delivery decisions and concise user-facing wording."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from .warning_details import TORNADO_SHELTER_ACTION

from .models import (
    DeliveryOperation,
    DeliveryPriority,
    GeometryRelationship,
    IncidentPhase,
    IncidentTransition,
    LocationFreshness,
    NotificationPayload,
    RelevanceResult,
    SubjectKind,
    TransitionKind,
)


class NotificationAdapter(Protocol):
    """Deployment boundary for Home Assistant or another delivery platform."""

    def send_or_update(self, payload: NotificationPayload) -> None:
        """Deliver using payload.stable_tag as the update/replacement identifier."""


class MemoryNotificationAdapter:
    """Useful for tests and non-HA prototype runs."""

    def __init__(self) -> None:
        self.deliveries: list[NotificationPayload] = []

    def send_or_update(self, payload: NotificationPayload) -> None:
        self.deliveries.append(payload)


class DeliveryEngine:
    def __init__(self, adapter: NotificationAdapter | None = None) -> None:
        self._adapter = adapter
        self._current: dict[tuple[str, str], NotificationPayload] = {}

    def decide(
        self,
        transition: IncidentTransition,
        relevance: RelevanceResult,
    ) -> NotificationPayload | None:
        key = (transition.incident.incident_key, relevance.subject_id)
        previous = self._current.get(key)
        if transition.kind == TransitionKind.DUPLICATE and (
            previous is None or previous.resolved or transition.incident.phase != IncidentPhase.ACTIVE
        ):
            return None

        if transition.incident.phase != IncidentPhase.ACTIVE:
            if previous is None or previous.resolved:
                return None
            label = "cancelled" if transition.kind == TransitionKind.CANCEL else "expired"
            payload = replace(
                previous,
                operation=DeliveryOperation.UPDATE,
                title=f"{transition.incident.latest_alert.event} {label}",
                message=_resolution_message(transition.incident.latest_alert.event, relevance.subject_kind),
                priority=DeliveryPriority.NORMAL,
                resolved=True,
            )
            return self._record(payload)

        relevant = relevance.relationship in {
            GeometryRelationship.INSIDE,
            GeometryRelationship.ACCURACY_OVERLAP,
            GeometryRelationship.OFFICIAL_POINT_MATCH,
        }
        alert = transition.incident.latest_alert
        critical_life_safety = _is_critical_life_safety(alert)
        retained_last_known_match = relevance.last_known_relationship in {
            GeometryRelationship.INSIDE,
            GeometryRelationship.ACCURACY_OVERLAP,
        }
        location_is_last_known = relevance.subject_kind == SubjectKind.PERSON and (
            relevance.freshness != LocationFreshness.FRESH or retained_last_known_match
        )
        if (
            relevance.subject_kind == SubjectKind.PERSON
            and critical_life_safety
            and retained_last_known_match
        ):
            relevant = True
        if transition.kind == TransitionKind.DUPLICATE:
            # Source deduplication must not freeze a previously delivered alert's
            # location qualifier. This updates wording only, not eligibility.
            if previous.location_is_last_known == location_is_last_known or (
                not location_is_last_known and not relevant
            ):
                return None
            title, message = _active_wording(
                alert, relevance, previous.priority, is_update=False,
                location_is_last_known=location_is_last_known,
            )
            return self._record(replace(
                previous, operation=DeliveryOperation.UPDATE, title=title, message=message,
                location_is_last_known=location_is_last_known,
            ))
        if (
            relevance.relationship in {
                GeometryRelationship.UNKNOWN,
                GeometryRelationship.NO_GEOMETRY,
            }
            and previous is not None
            and not retained_last_known_match
        ):
            # Unknown/degraded inputs are not evidence that an alert moved away.
            # An already-confirmed critical alert remains active until official resolution.
            return None
        if not relevant:
            if previous is None or previous.resolved:
                return None
            payload = replace(
                previous,
                operation=DeliveryOperation.UPDATE,
                title=f"{transition.incident.latest_alert.event} update",
                message=_no_longer_affected_message(
                    transition.incident.latest_alert.event, relevance.subject_kind
                ),
                priority=DeliveryPriority.NORMAL,
                resolved=True,
            )
            return self._record(payload)

        priority = (
            DeliveryPriority.CRITICAL
            if relevance.subject_kind == SubjectKind.PERSON and critical_life_safety
            else DeliveryPriority.NORMAL
        )
        title, message = _active_wording(
            alert,
            relevance,
            priority,
            is_update=transition.kind == TransitionKind.UPDATE,
            location_is_last_known=location_is_last_known,
        )
        payload = NotificationPayload(
            operation=DeliveryOperation.CREATE if previous is None else DeliveryOperation.UPDATE,
            stable_tag=_stable_tag(transition.incident.incident_key, relevance),
            title=title,
            message=message,
            priority=priority,
            incident_key=transition.incident.incident_key,
            subject_id=relevance.subject_id,
            subject_kind=relevance.subject_kind,
            location_is_last_known=location_is_last_known,
        )
        if previous is not None and _same_user_visible_payload(previous, payload):
            return None
        return self._record(payload)

    def _record(self, payload: NotificationPayload) -> NotificationPayload:
        self._current[(payload.incident_key, payload.subject_id)] = payload
        if self._adapter is not None:
            self._adapter.send_or_update(payload)
        return payload

    @property
    def current_notifications(self) -> tuple[NotificationPayload, ...]:
        return tuple(self._current.values())

    def restore(self, notifications: list[NotificationPayload]) -> None:
        """Restore update-in-place identifiers before the first source poll."""
        self._current = {
            (item.incident_key, item.subject_id): item for item in notifications
        }


def is_automatic_warning(alert: object) -> bool:
    """Compatibility wrapper for the broad source-native hazard policy."""
    from .hazard_policy import classify_alert

    return classify_alert(alert).automatic


def _is_critical_life_safety(alert: object) -> bool:
    """Return true only for the policy's immediate life-safety subset."""
    from .hazard_policy import classify_alert

    return classify_alert(alert).critical_capable


def _active_wording(
    alert: object,
    relevance: RelevanceResult,
    priority: DeliveryPriority,
    *,
    is_update: bool,
    location_is_last_known: bool,
) -> tuple[str, str]:
    event = str(getattr(alert, "event", "Official weather alert"))
    if relevance.subject_kind == SubjectKind.DESIGNATED_HOME:
        title = (
            f"{event} update affects your designated home"
            if is_update
            else f"{event} affects your designated home"
        )
        relationship = "The official warning includes your designated home."
    elif location_is_last_known:
        title = (
            f"{event} update at your last known location"
            if is_update
            else f"{event} at your last known location"
        )
        relationship = "Your current location has not recently updated and cannot be confirmed."
    else:
        title = (
            f"{event} update for your location"
            if is_update
            else f"{event} for your location"
        )
        relationship = "The official warning includes your location."

    official_update = _official_update_summary(alert) if is_update else ""
    action = _concise_action(
        event,
        getattr(alert, "instruction", None),
        priority,
    )
    return title, " ".join(part for part in (relationship, official_update, action) if part)


def _official_update_summary(alert: object) -> str:
    if str(getattr(alert, "event", "")).casefold() != "tornado warning":
        return "This is an official update to the warning."
    detection = str(getattr(alert, "tornado_detection", "") or "").strip()
    if detection.casefold() == "observed":
        return "The official update reports an observed tornado."
    if detection.casefold() == "radar indicated":
        return "The official update reports radar-indicated rotation."
    if detection:
        return f"Official tornado detection: {detection}."
    return "This is an official update to the warning."


def _concise_action(
    event: str, official_instruction: str | None, priority: DeliveryPriority
) -> str:
    event_lower = event.casefold()
    if event_lower == "tornado warning":
        return TORNADO_SHELTER_ACTION
    if event_lower == "severe thunderstorm warning" and priority == DeliveryPriority.CRITICAL:
        return "Move indoors now and stay away from windows."
    if official_instruction:
        first = official_instruction.replace("\n", " ").strip().split(". ", 1)[0].strip()
        if first:
            return first.rstrip(".") + "."
    return "Follow official safety instructions and monitor updates."


def _resolution_message(event: str, subject_kind: SubjectKind) -> str:
    target = "your designated home" if subject_kind == SubjectKind.DESIGNATED_HOME else "your location"
    return f"The {event} for {target} is no longer active. Continue to monitor official updates."


def _no_longer_affected_message(event: str, subject_kind: SubjectKind) -> str:
    target = "your designated home" if subject_kind == SubjectKind.DESIGNATED_HOME else "your location"
    return f"The {event} no longer includes {target}. Continue to monitor official updates."


def _stable_tag(incident_key: str, relevance: RelevanceResult) -> str:
    safe_incident = incident_key.replace(":", "_").replace("/", "_")
    return f"weather_intelligence_{safe_incident}_{relevance.subject_kind.value}_{relevance.subject_id}"


def _same_user_visible_payload(
    previous: NotificationPayload, current: NotificationPayload
) -> bool:
    return (
        previous.title,
        previous.message,
        previous.priority,
        previous.resolved,
    ) == (
        current.title,
        current.message,
        current.priority,
        current.resolved,
    )
