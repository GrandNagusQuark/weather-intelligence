"""Small typed records shared by the prototype's safety core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from .const import ANDROID_SIREN_CHANNEL


class LocationFreshness(str, Enum):
    FRESH = "fresh"
    LAST_KNOWN_GRACE = "last_known_grace"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    MISSING = "missing"
    INTENTIONALLY_UNAVAILABLE = "intentionally_unavailable"


class GeometryRelationship(str, Enum):
    INSIDE = "inside"
    ACCURACY_OVERLAP = "accuracy_overlap"
    OFFICIAL_POINT_MATCH = "official_point_match"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"
    NO_GEOMETRY = "no_geometry"


class SubjectKind(str, Enum):
    PERSON = "person"
    DESIGNATED_HOME = "designated_home"


class IncidentPhase(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TransitionKind(str, Enum):
    NEW = "new"
    UPDATE = "update"
    CANCEL = "cancel"
    EXPIRE = "expire"
    DUPLICATE = "duplicate"


class DeliveryOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"


class DeliveryPriority(str, Enum):
    NORMAL = "normal"
    CRITICAL = "critical"


class SourceHealthState(str, Enum):
    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DATA_UNAVAILABLE = "data_unavailable"
    DATA_STALE = "data_stale"
    DATA_DELAYED = "data_delayed"
    SOURCE_DEGRADED = "source_degraded"


@dataclass(frozen=True)
class OfficialAlert:
    source: str
    official_message_id: str
    incident_key: str
    sender: str | None
    event: str
    message_type: str
    status: str
    category: str | None
    sent_at: datetime | None
    effective_at: datetime | None
    onset_at: datetime | None
    expires_at: datetime | None
    ends_at: datetime | None
    severity: str | None
    urgency: str | None
    certainty: str | None
    headline: str | None
    description: str | None
    instruction: str | None
    area_description: str | None
    geometry: Mapping[str, Any] | None
    affected_zones: tuple[str, ...]
    tornado_detection: str | None
    tornado_damage_threat: str | None
    thunderstorm_damage_threat: str | None
    flash_flood_damage_threat: str | None
    vtec_action: str | None
    replaced_message_ids: tuple[str, ...]
    received_at: datetime
    raw_official_payload: Mapping[str, Any]


@dataclass(frozen=True)
class LocationFix:
    latitude: float | None
    longitude: float | None
    observed_at: datetime | None
    accuracy_meters: float | None
    reported_stale: bool = False
    intentionally_unavailable: bool = False


@dataclass(frozen=True)
class MonitoredSubject:
    subject_id: str
    display_name: str
    kind: SubjectKind
    location: LocationFix


@dataclass(frozen=True)
class LocationAssessment:
    freshness: LocationFreshness
    age_seconds: float | None
    fix: LocationFix | None
    last_known_fix: LocationFix | None = None
    refresh_attempted: bool = False


@dataclass(frozen=True)
class RelevanceResult:
    subject_id: str
    subject_kind: SubjectKind
    relationship: GeometryRelationship
    freshness: LocationFreshness
    accuracy_overlap: bool | None
    reason: str
    last_known_relationship: GeometryRelationship | None = None


@dataclass
class IncidentRecord:
    incident_key: str
    phase: IncidentPhase
    latest_alert: OfficialAlert
    seen_message_ids: set[str] = field(default_factory=set)
    content_fingerprint: str = ""
    revision: int = 1


@dataclass(frozen=True)
class IncidentTransition:
    kind: TransitionKind
    incident: IncidentRecord
    prior_phase: IncidentPhase | None = None


@dataclass(frozen=True)
class NotificationPayload:
    operation: DeliveryOperation
    stable_tag: str
    title: str
    message: str
    priority: DeliveryPriority
    incident_key: str
    subject_id: str
    subject_kind: SubjectKind
    resolved: bool = False
    location_is_last_known: bool = False


@dataclass(frozen=True)
class SourceHealth:
    state: SourceHealthState
    checked_at: datetime
    last_success_at: datetime | None
    detail: str
    received_feature_count: int | None = None


@dataclass(frozen=True)
class CoordinatorStatus:
    source_health: SourceHealthState
    active_incident_count: int
    person_relevant_count: int
    home_relevant_count: int
    generated_at: datetime
    personal_tracking_configured: bool = False
    mobile_test_target_configured: bool = False
    person_location_freshness: LocationFreshness = LocationFreshness.MISSING
    configured_profile_count: int = 0
    enabled_profile_count: int = 0
    fresh_person_count: int = 0
    degraded_person_count: int = 0
    unknown_person_count: int = 0
    automatic_profile_count: int = 0
    critical_profile_count: int = 0
    partial_source_degradation: bool = False


@dataclass(frozen=True)
class HouseholdProfile:
    """One explicitly configured person-to-device delivery boundary."""

    profile_id: str
    name: str
    person_entity_id: str
    notify_entity_id: str = ""
    legacy_notify_service: str = ""
    mobile_platform: str = "auto"
    enabled: bool = True
    receive_personal_alerts: bool = True
    receive_home_while_away: bool = False
    automatic_notifications: bool = False
    critical_notifications: bool = False
    hazard_families: tuple[str, ...] = ()
    daily_briefing: bool = False
    briefing_location: str = "designated_home"
    show_location_on_map: str = "inherit"
    # None preserves legacy family semantics; an explicit empty tuple selects none.
    alert_events: tuple[str, ...] | None = None
    marine_warning_mode: str = "always"
    companion_device_id: str = ""
    dnd_rule_ids: tuple[str, ...] | None = None
    urgent_channel: str = ANDROID_SIREN_CHANNEL
    daily_outlook_time: str = ""
    life_safety_events: tuple[str, ...] = ()
    marine_nearby_enabled: bool = False
    marine_nearby_miles: float = 10.0
    outage_dnd_enabled: bool = False

    @property
    def subject_id(self) -> str:
        return f"profile:{self.profile_id}"


@dataclass(frozen=True)
class ProfileDeliveryRecord:
    """Privacy-minimal restart state for one recipient and official incident."""

    profile_id: str
    incident_key: str
    content_fingerprint: str
    stable_tag: str
    resolved: bool = False
    clear_at: datetime | None = None
    cleared: bool = False
    severity_rank: int | None = None


@dataclass(frozen=True)
class BriefingDeliveryRecord:
    """Minimal scheduled daily-briefing dedup state for one profile."""

    profile_id: str
    local_date: str
    content_fingerprint: str
    urgency: int
    delivered_at: datetime | None = None
    pending: bool = False
    last_attempt_at: datetime | None = None
    confirmed_at: datetime | None = None
