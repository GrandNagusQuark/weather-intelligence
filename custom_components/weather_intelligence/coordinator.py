"""Thin lifecycle conductor for source, incidents, relevance, and delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .delivery import DeliveryEngine
from .geometry import evaluate_home_relevance, evaluate_person_relevance
from .incidents import IncidentTracker
from .location import LocationMonitor, LocationRefreshHook
from .models import (
    CoordinatorStatus,
    GeometryRelationship,
    IncidentPhase,
    IncidentTransition,
    LocationFix,
    LocationFreshness,
    MonitoredSubject,
    NotificationPayload,
    IncidentRecord,
    RelevanceResult,
    SourceHealthState,
    SubjectKind,
    TransitionKind,
)
from .normalization import parse_feature_collection
from .source_health import SourceHealthMonitor


class WeatherCoordinator:
    """Coordinate focused modules without embedding their decisions."""

    def __init__(
        self,
        subjects: Sequence[MonitoredSubject],
        delivery: DeliveryEngine | None = None,
        refresh_hook: LocationRefreshHook | None = None,
    ) -> None:
        self._subjects = {subject.subject_id: subject for subject in subjects}
        self._tracker = IncidentTracker()
        self._delivery = delivery or DeliveryEngine()
        self._locations = LocationMonitor(refresh_hook)
        self._source_health = SourceHealthMonitor()
        self._latest_location_freshness: dict[str, LocationFreshness] = {}
        self._current_relevant_keys: set[tuple[str, str]] = set()
        self.status: CoordinatorStatus | None = None

    def process_official_payload(
        self,
        payload: Mapping[str, Any],
        received_at: datetime,
        now: datetime,
        location_updates: Mapping[str, LocationFix] | None = None,
        official_point_matches: Mapping[str, set[str]] | None = None,
        authoritative_subjects: set[str] | None = None,
        complete_active_snapshot: bool = True,
    ) -> list[NotificationPayload]:
        alerts = parse_feature_collection(payload, received_at)
        self._source_health.record_success(received_at, len(alerts))
        subjects = self._updated_subjects(location_updates or {})
        assessments = {
            item.subject_id: self._locations.assess(item.subject_id, item.location, now)
            for item in subjects
            if item.kind == SubjectKind.PERSON
        }
        self._latest_location_freshness = {
            subject_id: assessment.freshness
            for subject_id, assessment in assessments.items()
        }

        notifications: list[NotificationPayload] = []
        relevant_person_keys: set[tuple[str, str]] = set()
        relevant_home_keys: set[tuple[str, str]] = set()
        # Direct feed transitions are authoritative only for the subjects whose
        # point response contained that official message. Reconciliation and
        # time-based expiry are authoritative across the complete snapshot.
        transitions = [
            (self._tracker.apply(alert, now), True) for alert in alerts
        ]
        active_snapshot_keys = {
            transition.incident.incident_key
            for transition, _restrict_to_point_matches in transitions
            if transition.incident.phase == IncidentPhase.ACTIVE
        }
        if complete_active_snapshot:
            transitions.extend(
                (transition, False)
                for transition in self._tracker.reconcile_active_snapshot(
                    active_snapshot_keys
                )
            )
        transitions.extend(
            (transition, False) for transition in self._tracker.expire_due(now)
        )
        for transition, restrict_to_point_matches in transitions:
            alert = transition.incident.latest_alert
            for subject in subjects:
                matched_subjects = (official_point_matches or {}).get(
                    alert.official_message_id,
                    set(),
                )
                if (
                    official_point_matches is not None
                    and restrict_to_point_matches
                    and subject.subject_id not in matched_subjects
                ):
                    continue
                if subject.kind == SubjectKind.PERSON:
                    relevance = evaluate_person_relevance(
                        subject.subject_id, assessments[subject.subject_id], alert.geometry
                    )
                else:
                    relevance = evaluate_home_relevance(
                        subject.subject_id,
                        subject.location.latitude,
                        subject.location.longitude,
                        alert.geometry,
                    )
                if (
                    relevance.relationship == GeometryRelationship.NO_GEOMETRY
                    and subject.subject_id
                    in (official_point_matches or {}).get(alert.official_message_id, set())
                ):
                    relevance = RelevanceResult(
                        subject_id=subject.subject_id,
                        subject_kind=subject.kind,
                        relationship=GeometryRelationship.OFFICIAL_POINT_MATCH,
                        freshness=relevance.freshness,
                        accuracy_overlap=None,
                        reason=(
                            "The official NWS point-filter response identifies this alert "
                            "as active for the evaluated point."
                        ),
                    )
                if (
                    transition.incident.phase == IncidentPhase.ACTIVE
                    and relevance.relationship
                    in {
                        GeometryRelationship.INSIDE,
                        GeometryRelationship.ACCURACY_OVERLAP,
                        GeometryRelationship.OFFICIAL_POINT_MATCH,
                    }
                ):
                    key = (transition.incident.incident_key, subject.subject_id)
                    if subject.kind == SubjectKind.PERSON:
                        relevant_person_keys.add(key)
                    else:
                        relevant_home_keys.add(key)
                decision = self._delivery.decide(transition, relevance)
                if decision is not None:
                    notifications.append(decision)

        # A successful point-filter request is authoritative only for the
        # subjects attached to that point. During a partial poll, resolve an
        # absent subject relationship without cancelling the shared incident or
        # touching subjects whose requests failed.
        if official_point_matches is not None and authoritative_subjects:
            matched_incidents: dict[str, set[str]] = {
                subject_id: set() for subject_id in authoritative_subjects
            }
            alert_incident_by_message = {
                alert.official_message_id: alert.incident_key for alert in alerts
            }
            for message_id, subject_ids in official_point_matches.items():
                incident_key = alert_incident_by_message.get(message_id)
                if incident_key is None:
                    continue
                for subject_id in subject_ids & authoritative_subjects:
                    matched_incidents.setdefault(subject_id, set()).add(incident_key)
            for incident in self._tracker.active_incidents():
                for subject_id in authoritative_subjects:
                    subject = self._subjects.get(subject_id)
                    if (
                        subject is None
                        or incident.incident_key in matched_incidents.get(subject_id, set())
                    ):
                        continue
                    prior = next(
                        (
                            item
                            for item in self._delivery.current_notifications
                            if item.incident_key == incident.incident_key
                            and item.subject_id == subject_id
                            and not item.resolved
                        ),
                        None,
                    )
                    if prior is None:
                        continue
                    relevance = RelevanceResult(
                        subject_id=subject_id,
                        subject_kind=subject.kind,
                        relationship=GeometryRelationship.OUTSIDE,
                        freshness=self._latest_location_freshness.get(
                            subject_id, LocationFreshness.FRESH
                        ),
                        accuracy_overlap=False,
                        reason="The successful official point response no longer lists this incident.",
                    )
                    decision = self._delivery.decide(
                        IncidentTransition(TransitionKind.UPDATE, incident), relevance
                    )
                    if decision is not None:
                        notifications.append(decision)

        active_keys = {item.incident_key for item in self._tracker.active_incidents()}
        direct_relevant = relevant_person_keys | relevant_home_keys
        if official_point_matches is None or complete_active_snapshot:
            self._current_relevant_keys = direct_relevant
        else:
            authoritative = authoritative_subjects or set()
            self._current_relevant_keys = {
                key
                for key in self._current_relevant_keys
                if key[0] in active_keys and key[1] not in authoritative
            } | direct_relevant
        self._current_relevant_keys = {
            key for key in self._current_relevant_keys if key[0] in active_keys
        }

        self.status = CoordinatorStatus(
            source_health=SourceHealthState.HEALTHY,
            active_incident_count=len(self._tracker.active_incidents()),
            person_relevant_count=sum(
                self._subjects[subject_id].kind == SubjectKind.PERSON
                for _incident_key, subject_id in self._current_relevant_keys
            ),
            home_relevant_count=sum(
                self._subjects[subject_id].kind == SubjectKind.DESIGNATED_HOME
                for _incident_key, subject_id in self._current_relevant_keys
            ),
            generated_at=now,
            personal_tracking_configured=bool(assessments),
            person_location_freshness=(
                next(iter(self._latest_location_freshness.values()))
                if assessments
                else LocationFreshness.MISSING
            ),
        )
        return notifications

    def record_source_failure(self, detail: str, now: datetime) -> CoordinatorStatus:
        """Record feed failure without erasing the last known active incident state."""
        health = self._source_health.record_failure(now, detail)
        prior = self.status
        self.status = CoordinatorStatus(
            source_health=health.state,
            active_incident_count=len(self._tracker.active_incidents()),
            person_relevant_count=prior.person_relevant_count if prior else 0,
            home_relevant_count=prior.home_relevant_count if prior else 0,
            generated_at=now,
            personal_tracking_configured=(
                prior.personal_tracking_configured if prior else bool(self._latest_location_freshness)
            ),
            mobile_test_target_configured=(
                prior.mobile_test_target_configured if prior else False
            ),
            person_location_freshness=(
                prior.person_location_freshness
                if prior
                else next(
                    iter(self._latest_location_freshness.values()),
                    LocationFreshness.MISSING,
                )
            ),
        )
        return self.status

    def record_source_degraded(self, detail: str, now: datetime) -> CoordinatorStatus:
        """Record a partial successful poll without clearing retained incident state."""
        health = self._source_health.record_degraded(now, detail)
        prior = self.status
        self.status = CoordinatorStatus(
            source_health=health.state,
            active_incident_count=len(self._tracker.active_incidents()),
            person_relevant_count=prior.person_relevant_count if prior else 0,
            home_relevant_count=prior.home_relevant_count if prior else 0,
            generated_at=now,
            personal_tracking_configured=(
                prior.personal_tracking_configured if prior else bool(self._latest_location_freshness)
            ),
            mobile_test_target_configured=(
                prior.mobile_test_target_configured if prior else False
            ),
            person_location_freshness=(
                prior.person_location_freshness
                if prior
                else next(
                    iter(self._latest_location_freshness.values()),
                    LocationFreshness.MISSING,
                )
            ),
        )
        return self.status

    @property
    def incident_records(self) -> tuple[IncidentRecord, ...]:
        return self._tracker.incidents

    @property
    def subject_location_freshness(self) -> dict[str, LocationFreshness]:
        """Expose coverage status for presentation, never the underlying fixes."""
        return dict(self._latest_location_freshness)

    @property
    def notification_records(self) -> tuple[NotificationPayload, ...]:
        return self._delivery.current_notifications

    def restore_runtime_state(
        self,
        incidents: list[IncidentRecord],
        notifications: list[NotificationPayload],
    ) -> None:
        """Restore state before polling so active messages are not replayed as new."""
        self._tracker.restore(incidents)
        self._delivery.restore(notifications)

    def _updated_subjects(self, updates: Mapping[str, LocationFix]) -> tuple[MonitoredSubject, ...]:
        result: list[MonitoredSubject] = []
        for subject in self._subjects.values():
            fix = updates.get(subject.subject_id, subject.location)
            updated = MonitoredSubject(subject.subject_id, subject.display_name, subject.kind, fix)
            result.append(updated)
            if subject.subject_id in updates:
                self._subjects[subject.subject_id] = updated
        return tuple(result)
