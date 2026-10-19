"""Deterministic NWS incident lifecycle and duplicate suppression."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .models import (
    IncidentPhase,
    IncidentRecord,
    IncidentTransition,
    OfficialAlert,
    TransitionKind,
)

_CANCEL_ACTIONS = {"CAN"}
_EXPIRE_ACTIONS = {"EXP"}


class IncidentTracker:
    def __init__(self) -> None:
        self._incidents: dict[str, IncidentRecord] = {}
        self._message_to_incident: dict[str, str] = {}

    @property
    def incidents(self) -> tuple[IncidentRecord, ...]:
        return tuple(self._incidents.values())

    def apply(self, alert: OfficialAlert, now: datetime) -> IncidentTransition:
        incident_key = self._resolve_incident_key(alert)
        existing = self._incidents.get(incident_key)
        fingerprint = _content_fingerprint(alert)
        target_phase = _phase_for_alert(alert, now)

        if existing is None:
            record = IncidentRecord(
                incident_key=incident_key,
                phase=target_phase,
                latest_alert=alert,
                seen_message_ids={alert.official_message_id},
                content_fingerprint=fingerprint,
            )
            self._incidents[incident_key] = record
            self._message_to_incident[alert.official_message_id] = incident_key
            return IncidentTransition(_transition_for_phase(target_phase, is_new=True), record)

        prior_phase = existing.phase
        is_duplicate = (
            alert.official_message_id in existing.seen_message_ids
            and fingerprint == existing.content_fingerprint
            and target_phase == existing.phase
        )
        existing.seen_message_ids.add(alert.official_message_id)
        self._message_to_incident[alert.official_message_id] = incident_key
        if is_duplicate:
            return IncidentTransition(TransitionKind.DUPLICATE, existing, prior_phase)

        existing.latest_alert = alert
        existing.content_fingerprint = fingerprint
        existing.phase = target_phase
        existing.revision += 1
        return IncidentTransition(_transition_for_phase(target_phase), existing, prior_phase)

    def expire_due(self, now: datetime) -> list[IncidentTransition]:
        transitions: list[IncidentTransition] = []
        for incident in self._incidents.values():
            expires_at = incident.latest_alert.expires_at
            if (
                incident.phase == IncidentPhase.ACTIVE
                and expires_at is not None
                and now >= expires_at
            ):
                incident.phase = IncidentPhase.EXPIRED
                incident.revision += 1
                transitions.append(
                    IncidentTransition(TransitionKind.EXPIRE, incident, IncidentPhase.ACTIVE)
                )
        return transitions

    def reconcile_active_snapshot(
        self, active_incident_keys: set[str]
    ) -> list[IncidentTransition]:
        """Resolve incidents absent from a successfully parsed complete active feed."""
        transitions: list[IncidentTransition] = []
        for incident in self._incidents.values():
            if (
                incident.phase == IncidentPhase.ACTIVE
                and incident.incident_key not in active_incident_keys
            ):
                incident.phase = IncidentPhase.EXPIRED
                incident.revision += 1
                transitions.append(
                    IncidentTransition(TransitionKind.EXPIRE, incident, IncidentPhase.ACTIVE)
                )
        return transitions

    def active_incidents(self) -> tuple[IncidentRecord, ...]:
        return tuple(item for item in self._incidents.values() if item.phase == IncidentPhase.ACTIVE)

    def restore(self, incidents: list[IncidentRecord]) -> None:
        """Restore trusted, version-validated incident records from HA storage."""
        self._incidents = {item.incident_key: item for item in incidents}
        self._message_to_incident = {
            message_id: item.incident_key
            for item in incidents
            for message_id in item.seen_message_ids
        }

    def _resolve_incident_key(self, alert: OfficialAlert) -> str:
        if not alert.incident_key.startswith("nws-reference:"):
            return alert.incident_key
        for reference in alert.replaced_message_ids:
            known = self._message_to_incident.get(reference)
            if known:
                return known
        return alert.incident_key


def _phase_for_alert(alert: OfficialAlert, now: datetime) -> IncidentPhase:
    action = (alert.vtec_action or "").upper()
    if alert.message_type.lower() == "cancel" or action in _CANCEL_ACTIONS:
        return IncidentPhase.CANCELLED
    if action in _EXPIRE_ACTIONS or (alert.expires_at is not None and now >= alert.expires_at):
        return IncidentPhase.EXPIRED
    return IncidentPhase.ACTIVE


def _transition_for_phase(phase: IncidentPhase, is_new: bool = False) -> TransitionKind:
    if phase == IncidentPhase.CANCELLED:
        return TransitionKind.CANCEL
    if phase == IncidentPhase.EXPIRED:
        return TransitionKind.EXPIRE
    return TransitionKind.NEW if is_new else TransitionKind.UPDATE


def _content_fingerprint(alert: OfficialAlert) -> str:
    meaningful = {
        "message_id": alert.official_message_id,
        "message_type": alert.message_type,
        "status": alert.status,
        "event": alert.event,
        "sent": _iso(alert.sent_at),
        "effective": _iso(alert.effective_at),
        "expires": _iso(alert.expires_at),
        "severity": alert.severity,
        "urgency": alert.urgency,
        "certainty": alert.certainty,
        "headline": alert.headline,
        "description": alert.description,
        "instruction": alert.instruction,
        "geometry": alert.geometry,
        "tornado_detection": alert.tornado_detection,
        "tornado_damage_threat": alert.tornado_damage_threat,
        "thunderstorm_damage_threat": alert.thunderstorm_damage_threat,
        "vtec_action": alert.vtec_action,
    }
    encoded = json.dumps(meaningful, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
