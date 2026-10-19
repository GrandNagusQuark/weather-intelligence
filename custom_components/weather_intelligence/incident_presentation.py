"""Compact, privacy-safe presentation of one primary official incident."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from .const import ALL_CLEAR_RETENTION

from .models import (
    CoordinatorStatus,
    IncidentPhase,
    IncidentRecord,
    NotificationPayload,
    SourceHealthState,
    SubjectKind,
)


@dataclass(frozen=True)
class PrimaryIncidentView:
    """Small HA-facing view that excludes raw alert text and private identifiers."""

    state: str
    event: str | None
    applies_to: str
    phase: str
    source_health: str
    official_status: str | None = None
    official_message_type: str | None = None
    official_category: str | None = None
    official_severity: str | None = None
    official_urgency: str | None = None
    official_certainty: str | None = None
    sent_at: str | None = None
    effective_at: str | None = None
    expires_at: str | None = None
    ends_at: str | None = None
    active_incident_count: int = 0
    additional_active_incidents: int = 0

    def attributes(self) -> dict[str, object]:
        """Return only compact official facts suitable for HA state attributes."""
        return {
            "applies_to": self.applies_to,
            "incident_phase": self.phase,
            "source_health": self.source_health,
            "official_status": self.official_status,
            "official_message_type": self.official_message_type,
            "official_category": self.official_category,
            "official_severity": self.official_severity,
            "official_urgency": self.official_urgency,
            "official_certainty": self.official_certainty,
            "sent_at": self.sent_at,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
            "ends_at": self.ends_at,
            "active_incidents": self.active_incident_count,
            "additional_active_incidents": self.additional_active_incidents,
        }


def build_primary_incident_view(
    status: CoordinatorStatus | None,
    incidents: Iterable[IncidentRecord],
    notifications: Iterable[NotificationPayload],
) -> PrimaryIncidentView:
    """Select the newest active incident, or show the latest resolution honestly."""
    now = status.generated_at if status else datetime.now(timezone.utc)
    records = tuple(
        item for item in incidents
        if item.phase == IncidentPhase.ACTIVE
        or now < _resolution_time(item) + ALL_CLEAR_RETENTION
    )
    source_health = (
        status.source_health if status is not None else SourceHealthState.INITIALIZING
    )
    active = tuple(item for item in records if item.phase == IncidentPhase.ACTIVE)
    if not records:
        state = (
            "No active official incidents"
            if source_health == SourceHealthState.HEALTHY
            else _unknown_state(source_health)
        )
        return PrimaryIncidentView(
            state=state,
            event=None,
            applies_to="none",
            phase="none",
            source_health=source_health.value,
            active_incident_count=status.active_incident_count if status else 0,
        )

    primary = max(active or records, key=_incident_recency)
    alert = primary.latest_alert
    scope = _incident_scope(primary, active, status, tuple(notifications))
    if primary.phase == IncidentPhase.ACTIVE:
        state = f"{alert.event} — {scope}"
        additional = max(0, len(active) - 1)
    else:
        state = f"No active incidents — {alert.event} {primary.phase.value}"
        additional = 0
    suffix = _source_suffix(source_health)
    if suffix:
        state = f"{state} ({suffix})"

    return PrimaryIncidentView(
        state=state,
        event=alert.event,
        applies_to=scope,
        phase=primary.phase.value,
        source_health=source_health.value,
        official_status=alert.status,
        official_message_type=alert.message_type,
        official_category=alert.category,
        official_severity=alert.severity,
        official_urgency=alert.urgency,
        official_certainty=alert.certainty,
        sent_at=_iso(alert.sent_at),
        effective_at=_iso(alert.effective_at),
        expires_at=_iso(alert.expires_at),
        ends_at=_iso(alert.ends_at),
        active_incident_count=status.active_incident_count if status else len(active),
        additional_active_incidents=additional,
    )


def _incident_scope(
    primary: IncidentRecord,
    active: tuple[IncidentRecord, ...],
    status: CoordinatorStatus | None,
    notifications: tuple[NotificationPayload, ...],
) -> str:
    if primary.phase == IncidentPhase.ACTIVE and len(active) == 1 and status is not None:
        kinds = set()
        if status.person_relevant_count:
            kinds.add(SubjectKind.PERSON)
        if status.home_relevant_count:
            kinds.add(SubjectKind.DESIGNATED_HOME)
    else:
        kinds = {
            item.subject_kind
            for item in notifications
            if item.incident_key == primary.incident_key
            and (primary.phase != IncidentPhase.ACTIVE or not item.resolved)
        }
    if kinds == {SubjectKind.PERSON, SubjectKind.DESIGNATED_HOME}:
        return "person and designated home"
    if SubjectKind.PERSON in kinds:
        return "protected person"
    if SubjectKind.DESIGNATED_HOME in kinds:
        return "designated home"
    return "relevance not currently confirmed"


def _incident_recency(incident: IncidentRecord) -> datetime:
    alert = incident.latest_alert
    return alert.sent_at or alert.effective_at or alert.received_at or datetime.min.replace(
        tzinfo=timezone.utc
    )


def _resolution_time(incident: IncidentRecord) -> datetime:
    alert = incident.latest_alert
    if incident.phase == IncidentPhase.EXPIRED:
        return alert.expires_at or alert.ends_at or _incident_recency(incident)
    return alert.sent_at or alert.received_at or _incident_recency(incident)


def _source_suffix(source_health: SourceHealthState) -> str:
    return {
        SourceHealthState.HEALTHY: "",
        SourceHealthState.INITIALIZING: "initial check in progress",
        SourceHealthState.SOURCE_DEGRADED: "source degraded",
        SourceHealthState.DATA_UNAVAILABLE: "source unavailable",
        SourceHealthState.DATA_STALE: "source stale",
        SourceHealthState.DATA_DELAYED: "source delayed",
    }[source_health]


def _unknown_state(source_health: SourceHealthState) -> str:
    if source_health == SourceHealthState.INITIALIZING:
        return "Checking official incidents"
    suffix = _source_suffix(source_health) or "source status unknown"
    return f"Current incidents unknown — {suffix}"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
