"""Guarded household routing for real official-warning notifications."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .hazard_policy import DeliveryBehavior, classify_alert, family_enabled, hail_enabled
from .mobile_notification import (
    MobileTargetError,
    async_clear_profile_notification,
    async_send_profile_notification,
)
from .models import (
    HouseholdProfile,
    IncidentRecord,
    NotificationPayload,
    ProfileDeliveryRecord,
    SubjectKind,
)
from .reporting_device import mobile_report_context
from .mrms_hail import HailApproach
from .official_sources import SupplementalHazard, SupplementalSourceState
from .water_detection import WaterAssessment
from .marine_location import marine_location_eligible
from .device_activity import marine_travel_assessment
from .onboarding_dnd import profile_bypasses_dnd
from .ha_location import location_fix_from_person_state
from .marine_nearby import nearby_alert_matches
from .regional_water import water_cell
from .warning_details import TORNADO_SHELTER_ACTION, official_warning_details, warning_title_suffix

_LOGGER = logging.getLogger(__name__)


def _receipt_allowed(profile: HouseholdProfile, policy: Any, event: str, *, prior_delivery: bool) -> bool:
    if family_enabled(profile, policy, event):
        return True
    # An already delivered life-safety incident may weaken. Update its existing
    # notification and stop critical audio; do not start a new lower-tier alert.
    return bool(prior_delivery and event.casefold() in profile.life_safety_events
                and (profile.alert_events is None or event.casefold() in profile.alert_events))


def _marine_location_allowed(profile: HouseholdProfile | None, event: str, decision: NotificationPayload,
                             assessments: Mapping[str, WaterAssessment] | None, now: datetime, hass: Any) -> bool:
    if profile is None:
        return False
    if event.casefold() != "special marine warning" or profile.marine_warning_mode == "always":
        return True
    # A delivered alert can still be resolved/cleared after the person leaves water.
    if decision.resolved:
        return True
    if decision.subject_kind != SubjectKind.PERSON:
        return False
    travel = marine_travel_assessment(hass, profile.companion_device_id, now)
    return marine_location_eligible(
        (assessments or {}).get(profile.person_entity_id), now,
        person_state=hass.states.get(profile.person_entity_id),
        home_zone_state=hass.states.get("zone.home"),
        vehicle_travel=travel.vehicle_travel,
        car_connected=travel.car_connected,
    )


class HouseholdDeliveryRouter:
    """Route subject decisions without widening a configured recipient boundary."""

    def __init__(self, hass: Any, profiles: Iterable[HouseholdProfile], acknowledgements: Any = None) -> None:
        self._hass = hass
        self._profiles = {item.profile_id: item for item in profiles}
        self._records: dict[tuple[str, str], ProfileDeliveryRecord] = {}
        self._acknowledgements = acknowledgements

    @property
    def records(self) -> tuple[ProfileDeliveryRecord, ...]:
        return tuple(self._records.values())

    def restore(self, records: Iterable[ProfileDeliveryRecord]) -> None:
        """Restore only records for profiles which still exist."""
        self._records = {
            (item.profile_id, item.incident_key): item
            for item in records
            if item.profile_id in self._profiles
        }

    def apply_marine_preferences(self, modes: Mapping[str, str]) -> None:
        """Update only this field; recipient and all delivery opt-ins stay fixed."""
        self._profiles = {key: replace(profile, marine_warning_mode=modes.get(key, profile.marine_warning_mode))
                          for key, profile in self._profiles.items()}

    async def async_route(
        self,
        decisions: Iterable[NotificationPayload],
        incidents: Iterable[IncidentRecord],
        now: datetime | None = None,
        *, water_assessments: Mapping[str, WaterAssessment] | None = None,
    ) -> int:
        """Deliver coalesced per-profile updates; return a privacy-safe failure count."""
        now = now or datetime.now(timezone.utc)
        incidents = tuple(incidents)
        alerts = {item.incident_key: item.latest_alert for item in incidents}
        records = {item.incident_key: item for item in incidents}
        grouped: dict[tuple[str, str], list[NotificationPayload]] = defaultdict(list)
        for decision in decisions:
            alert = alerts.get(decision.incident_key)
            if alert is None:
                continue
            policy = classify_alert(alert)
            if not policy.automatic:
                continue
            if decision.subject_kind == SubjectKind.PERSON:
                profile_id = decision.subject_id.removeprefix("profile:")
                profile = self._profiles.get(profile_id)
                prior_delivery = (profile_id, decision.incident_key) in self._records
                if (
                    (not decision.resolved or prior_delivery)
                    and self._eligible_person(profile)
                    and _receipt_allowed(profile, policy, alert.event, prior_delivery=prior_delivery)
                    and _marine_location_allowed(profile, alert.event, decision, water_assessments, now, self._hass)
                ):
                    grouped[(profile_id, decision.incident_key)].append(decision)
            else:
                for profile in self._profiles.values():
                    prior_delivery = (
                        profile.profile_id,
                        decision.incident_key,
                    ) in self._records
                    if _receipt_allowed(profile, policy, alert.event, prior_delivery=prior_delivery) and _marine_location_allowed(profile, alert.event, decision, water_assessments, now, self._hass) and (self._eligible_home(profile) or (
                        decision.resolved
                        and prior_delivery
                        and profile.enabled
                        and profile.automatic_notifications
                    )):
                        grouped[(profile.profile_id, decision.incident_key)].append(decision)

        failures = 0
        for (profile_id, incident_key), items in grouped.items():
            profile = self._profiles[profile_id]
            alert = alerts[incident_key]
            policy = classify_alert(alert)
            title, message, resolved = _coalesced_wording(items, alert, policy.action)
            critical = not resolved and profile_bypasses_dnd(self._hass, profile, alert, now,
                water_assessment=(water_assessments or {}).get(profile.person_entity_id)
                if any(item.subject_kind == SubjectKind.PERSON for item in items) else None)
            stable_tag = _profile_tag(profile_id, incident_key)
            fingerprint = _fingerprint(title, message, critical, resolved)
            if self._acknowledgements is not None and not resolved:
                fingerprint += f":revision:{records[incident_key].revision}"
            prior = self._records.get((profile_id, incident_key))
            if prior is not None and prior.content_fingerprint == fingerprint:
                continue
            try:
                until = getattr(alert, "ends_at", None) or getattr(alert, "expires_at", None)
                timeout_seconds = (
                    3600 if resolved else
                    max(1, int((until - now).total_seconds())) if until is not None else None
                )
                await async_send_profile_notification(
                    self._hass,
                    profile,
                    title=title,
                    message=message,
                    stable_tag=stable_tag,
                    critical=critical,
                    behavior=policy.behavior,
                    resolved=resolved,
                    timeout_seconds=timeout_seconds,
                    actions=([self._acknowledgements.action(profile_id, records[incident_key], now)]
                             if self._acknowledgements and profile.legacy_notify_service and not resolved
                             else None),
                )
            except MobileTargetError as error:
                failures += 1
                _LOGGER.error(
                    "Eligible %s delivery failed for one configured profile: %s",
                    alert.event,
                    error,
                    extra={"wi_mobile_context": mobile_report_context(self._hass, profile.companion_device_id)},
                )
                continue
            self._records[(profile_id, incident_key)] = ProfileDeliveryRecord(
                profile_id=profile_id,
                incident_key=incident_key,
                content_fingerprint=fingerprint,
                stable_tag=stable_tag,
                resolved=resolved,
                clear_at=now + timedelta(hours=1) if resolved else None,
                cleared=False,
            )
        return failures

    async def async_route_marine_nearby(
        self, alerts: tuple, assessments: Mapping[str, WaterAssessment],
        water_cache: Any, navigation_cache: Any, now: datetime,
    ) -> int:
        """Send opted-in outside-polygon heads-ups, never critical notifications."""
        failures = 0
        for profile in self._profiles.values():
            if not self._eligible_person(profile) or not profile.marine_nearby_enabled:
                continue
            fix = location_fix_from_person_state(self._hass.states.get(profile.person_entity_id))
            if fix is None:
                continue
            cell = water_cell(fix.latitude, fix.longitude)
            if cell is None:
                continue
            assessment = assessments.get(profile.person_entity_id)
            matches = await self._hass.async_add_executor_job(
                nearby_alert_matches, profile, fix, assessment, alerts,
                water_cache.bodies(cell, now), navigation_cache.bodies(cell, now), now,
            )
            # The user may move while geometry runs in the executor. Do not send
            # an extra alert using a location which has since been replaced.
            current = location_fix_from_person_state(self._hass.states.get(profile.person_entity_id))
            if current != fix:
                continue
            for alert in matches:
                incident_key = "marine_nearby:" + alert.incident_key
                record_key = (profile.profile_id, incident_key)
                prior = self._records.get(record_key)
                # Direct delivery wins and uses its own official warning wording.
                if (profile.profile_id, alert.incident_key) in self._records:
                    continue
                title = f"Nearby-water heads-up — {alert.event}"
                message = (
                    f"Weather Intelligence found an NWS {alert.event} affecting mapped water "
                    f"within your {profile.marine_nearby_miles:g}-mile setting, on the same water "
                    "or a charted navigation connection. Your reported location is outside "
                    "the official warning area. Check official updates and local conditions. "
                    "This is not navigation guidance or confirmation that a lock is open."
                )
                fingerprint = _fingerprint(title, message, False, False)
                if prior is not None and prior.content_fingerprint == fingerprint:
                    continue
                until = alert.ends_at or alert.expires_at
                stable_tag = _profile_tag(profile.profile_id, incident_key)
                try:
                    await async_send_profile_notification(
                        self._hass, profile, title=title, message=message,
                        stable_tag=stable_tag, critical=False, behavior=DeliveryBehavior.AWARENESS,
                        timeout_seconds=max(1, min(1800, int((until - now).total_seconds()))),
                    )
                except MobileTargetError:
                    failures += 1
                    _LOGGER.warning("Nearby-water heads-up failed for one configured profile")
                    continue
                self._records[record_key] = ProfileDeliveryRecord(
                    profile_id=profile.profile_id, incident_key=incident_key,
                    content_fingerprint=fingerprint, stable_tag=stable_tag,
                    clear_at=until,
                )
        return failures

    async def async_clear_due(self, now: datetime | None = None) -> int:
        """Remove expired local messages, retaining failed work for a later retry."""
        now = now or datetime.now(timezone.utc)
        failures = 0
        for key, record in tuple(self._records.items()):
            is_nearby = record.incident_key.startswith("marine_nearby:")
            direct = self._records.get((record.profile_id, record.incident_key.removeprefix("marine_nearby:"))) if is_nearby else None
            superseded = direct is not None and not direct.resolved
            if (
                (not record.resolved and not is_nearby)
                or record.cleared
                or record.clear_at is None
                or (not superseded and now < record.clear_at)
            ):
                continue
            profile = self._profiles.get(record.profile_id)
            if profile is None:
                continue
            try:
                await async_clear_profile_notification(
                    self._hass, profile, stable_tag=record.stable_tag
                )
            except MobileTargetError as error:
                failures += 1
                _LOGGER.error(
                    "All-clear removal failed for one configured profile: %s", error
                )
                continue
            self._records[key] = replace(record, cleared=True)
        return failures

    async def async_route_supplemental(
        self,
        hazards: Iterable[SupplementalHazard],
        source_states: dict[str, SupplementalSourceState],
        now: datetime | None = None,
    ) -> int:
        """Send source-native home-area heads-ups without creating a second router."""
        now = now or datetime.now(timezone.utc)
        candidates: dict[str, SupplementalHazard] = {}
        for item in hazards:
            if _preemptive_behavior(item) is None:
                continue
            key = _supplemental_key(item)
            prior = candidates.get(key)
            if prior is None or _supplemental_rank(item) > _supplemental_rank(prior):
                candidates[key] = item

        failures = 0
        active_record_keys: set[tuple[str, str]] = set()
        for incident_key, item in candidates.items():
            behavior = _preemptive_behavior(item)
            if behavior is None:
                continue
            for profile in self._profiles.values():
                if not _eligible_supplemental(profile, item):
                    continue
                record_key = (profile.profile_id, incident_key)
                active_record_keys.add(record_key)
                rank = _supplemental_rank(item)
                title, message = _supplemental_wording(self._hass, item)
                stable_tag = _profile_tag(profile.profile_id, incident_key)
                fingerprint = _fingerprint(title, message, False, False)
                prior = self._records.get(record_key)
                if (
                    prior is not None
                    and not prior.resolved
                    and prior.content_fingerprint == fingerprint
                ):
                    continue
                try:
                    timeout_seconds = (
                        max(1, int((item.valid_to - now).total_seconds()))
                        if item.valid_to is not None
                        else None
                    )
                    await async_send_profile_notification(
                        self._hass,
                        profile,
                        title=title,
                        message=message,
                        stable_tag=stable_tag,
                        critical=False,
                        behavior=behavior,
                        timeout_seconds=timeout_seconds,
                    )
                except MobileTargetError as error:
                    failures += 1
                    _LOGGER.error(
                        "Preemptive %s delivery failed for one configured profile: %s",
                        item.family.value,
                        error,
                    )
                    continue
                self._records[record_key] = ProfileDeliveryRecord(
                    profile_id=profile.profile_id,
                    incident_key=incident_key,
                    content_fingerprint=fingerprint,
                    stable_tag=stable_tag,
                    severity_rank=rank,
                )

        # Resolve only from a healthy authoritative refresh. A missing item from
        # a failed source is unknown, never an all-clear.
        for record_key, prior in tuple(self._records.items()):
            profile_id, incident_key = record_key
            if not incident_key.startswith("supplemental|"):
                continue
            if record_key in active_record_keys or prior.resolved:
                continue
            _prefix, source, family = incident_key.split("|", 2)
            if source_states.get(source) != SupplementalSourceState.HEALTHY:
                continue
            profile = self._profiles.get(profile_id)
            if profile is None or not profile.enabled or not profile.automatic_notifications:
                continue
            if source == "NWS forecast":
                # v0.9.0 briefly treated ordinary thunderstorm forecasts as
                # heads-ups. Retire those records without sending another message.
                try:
                    await async_clear_profile_notification(
                        self._hass, profile, stable_tag=prior.stable_tag
                    )
                except MobileTargetError:
                    pass
                self._records[record_key] = replace(
                    prior, resolved=True, clear_at=None, cleared=True
                )
                continue
            title = f"Weather Heads-Up Cleared — {_family_label(family)}"
            message = (
                f"The earlier {source} potential is no longer indicated for your "
                "designated home area. Continue to monitor official updates."
            )
            fingerprint = _fingerprint(title, message, False, True)
            try:
                await async_send_profile_notification(
                    self._hass,
                    profile,
                    title=title,
                    message=message,
                    stable_tag=prior.stable_tag,
                    critical=False,
                    behavior=DeliveryBehavior.AWARENESS,
                    resolved=True,
                    timeout_seconds=3600,
                )
            except MobileTargetError as error:
                failures += 1
                _LOGGER.error(
                    "Preemptive weather all-clear failed for one configured profile: %s",
                    error,
                )
                continue
            self._records[record_key] = replace(
                prior,
                content_fingerprint=fingerprint,
                resolved=True,
                clear_at=now + timedelta(hours=1),
                cleared=False,
            )
        return failures

    async def async_route_hail(
        self,
        approaches: Mapping[str, HailApproach],
        *,
        source_healthy: bool,
        now: datetime | None = None,
    ) -> int:
        """Route radar-tracked hail through existing profile safety boundaries."""
        now = now or datetime.now(timezone.utc)
        candidates: dict[str, HailApproach] = {}
        for subject_id, approach in approaches.items():
            if subject_id.startswith("profile:"):
                profile_id = subject_id.removeprefix("profile:")
                profile = self._profiles.get(profile_id)
                if self._eligible_person(profile) and _hail_family_enabled(profile):
                    candidates[profile_id] = _stronger_hail_candidate(
                        candidates.get(profile_id), approach
                    )
                continue
            if subject_id != "designated_home":
                continue
            for profile in self._profiles.values():
                if self._eligible_home(profile) and _hail_family_enabled(profile):
                    candidates[profile.profile_id] = _stronger_hail_candidate(
                        candidates.get(profile.profile_id), approach
                    )

        failures = 0
        incident_key = "mrms_hail_motion"
        for profile_id, approach in candidates.items():
            profile = self._profiles[profile_id]
            record_key = (profile_id, incident_key)
            prior_hail = self._records.get(record_key)
            if ("radar_hail" in profile.life_safety_events and not approach.life_threatening
                    and (prior_hail is None or prior_hail.resolved)):
                continue
            critical = bool(
                (approach.life_threatening or approach.property_damaging)
                and profile.critical_notifications
            )
            if profile.dnd_rule_ids is not None:
                from types import SimpleNamespace
                critical = profile_bypasses_dnd(self._hass, profile, SimpleNamespace(event="radar_hail"), now,
                                                hail_destructive=approach.life_threatening)
            soft_critical = bool(
                approach.property_damaging and not approach.life_threatening
            )
            scope = (
                "your current location"
                if approach.target_id.startswith("profile:")
                else "your designated home"
            )
            if approach.life_threatening:
                title = "Critical Hail Alert — Destructive Hail Approaching"
                message = (
                    f"Radar repeatedly estimates destructive hail up to "
                    f"{approach.max_hail_inches:.1f} inches moving toward {scope}, "
                    f"with closest approach in about {approach.eta_minutes} minutes. "
                    "Move indoors and stay away from windows now."
                )
                behavior = DeliveryBehavior.CRITICAL
            elif approach.property_damaging:
                title = "Urgent Hail Alert — Damaging Hail Approaching"
                message = (
                    f"Radar repeatedly estimates property-damaging hail up to "
                    f"{approach.max_hail_inches:.1f} inches moving toward {scope}, "
                    f"with closest approach in about {approach.eta_minutes} minutes. "
                    "Protect vehicles only if it is safe, then move indoors."
                )
                behavior = DeliveryBehavior.CRITICAL
            else:
                title = "Hail Alert — Radar-Detected Hail Approaching"
                message = (
                    f"Radar detects a hail core moving toward {scope}, with closest "
                    f"approach in about {approach.eta_minutes} minutes and estimated "
                    f"hail up to {approach.max_hail_inches:.1f} inches. Protect vehicles "
                    "only if it is safe, then move indoors."
                )
                behavior = DeliveryBehavior.IMPORTANT
            stable_tag = _profile_tag(profile_id, incident_key)
            # Do not resend every two-minute radar adjustment. The title identifies
            # the hail tier, while a tier escalation still replaces the alert.
            fingerprint = _fingerprint(title, scope, critical, False)
            prior = self._records.get(record_key)
            if (
                prior is not None
                and not prior.resolved
                and prior.content_fingerprint == fingerprint
            ):
                continue
            try:
                await async_send_profile_notification(
                    self._hass,
                    profile,
                    title=title,
                    message=message,
                    stable_tag=stable_tag,
                    critical=critical,
                    behavior=behavior,
                    timeout_seconds=30 * 60,
                    channel="Weather Hail",
                    soft_critical=soft_critical,
                )
            except MobileTargetError as error:
                failures += 1
                _LOGGER.error(
                    "Tracked hail delivery failed for one configured profile: %s",
                    error,
                )
                continue
            self._records[record_key] = ProfileDeliveryRecord(
                profile_id=profile_id,
                incident_key=incident_key,
                content_fingerprint=fingerprint,
                stable_tag=stable_tag,
                severity_rank=round(approach.max_hail_inches * 100),
            )

        if not source_healthy:
            return failures
        for record_key, prior in tuple(self._records.items()):
            profile_id, prior_incident_key = record_key
            if (
                prior_incident_key != incident_key
                or profile_id in candidates
                or prior.resolved
            ):
                continue
            profile = self._profiles.get(profile_id)
            if profile is None or not profile.enabled or not profile.automatic_notifications:
                continue
            title = "Hail Alert Cleared"
            message = (
                "The radar-detected hail core is no longer projected to pass near "
                "your monitored location. Continue to monitor official warnings."
            )
            fingerprint = _fingerprint(title, message, False, True)
            try:
                await async_send_profile_notification(
                    self._hass,
                    profile,
                    title=title,
                    message=message,
                    stable_tag=prior.stable_tag,
                    critical=False,
                    behavior=DeliveryBehavior.AWARENESS,
                    resolved=True,
                    timeout_seconds=3600,
                    channel="Weather Hail",
                )
            except MobileTargetError as error:
                failures += 1
                _LOGGER.error(
                    "Tracked hail all-clear failed for one configured profile: %s",
                    error,
                )
                continue
            self._records[record_key] = replace(
                prior,
                content_fingerprint=fingerprint,
                resolved=True,
                clear_at=now + timedelta(hours=1),
                cleared=False,
            )
        return failures

    def _eligible_person(self, profile: HouseholdProfile | None) -> bool:
        return bool(
            profile
            and profile.enabled
            and profile.automatic_notifications
            and profile.receive_personal_alerts
        )

    def _eligible_home(self, profile: HouseholdProfile) -> bool:
        if not (
            profile.enabled
            and profile.automatic_notifications
            and profile.receive_home_while_away
        ):
            return False
        state = self._hass.states.get(profile.person_entity_id)
        value = str(getattr(state, "state", "")).casefold()
        return value not in {"", "home", "unknown", "unavailable", "none"}


def _coalesced_wording(
    items: list[NotificationPayload], alert: object, action: str
) -> tuple[str, str, bool]:
    event = str(getattr(alert, "event", "Official weather warning"))
    resolved = all(item.resolved for item in items)
    relevant_items = items if resolved else [item for item in items if not item.resolved]
    scopes = {item.subject_kind for item in relevant_items}
    last_known = any(item.subject_kind == SubjectKind.PERSON and item.location_is_last_known
                     for item in relevant_items)
    if scopes == {SubjectKind.PERSON, SubjectKind.DESIGNATED_HOME}:
        scope_sentence = ("your designated home and your last known location" if last_known
                          else "you and your designated home")
    elif SubjectKind.DESIGNATED_HOME in scopes:
        scope_sentence = "your designated home"
    else:
        scope_sentence = "your last known location" if last_known else "your location"
    if resolved:
        return (
            f"Weather All Clear — {event}",
            f"The official warning is no longer active for {scope_sentence}. Continue to monitor official updates.",
            True,
        )
    is_update = any(item.operation.value == "update" for item in relevant_items)
    title = f"Weather Alert{' Update' if is_update else ''} — {event}{warning_title_suffix(alert)}"
    if last_known:
        title += " — last known location" if SubjectKind.DESIGNATED_HOME in scopes else " at your last known location"
    until = getattr(alert, "ends_at", None) or getattr(alert, "expires_at", None)
    until_text = f" Until {until.isoformat()}." if until else ""
    uncertainty = " Your current location cannot be confirmed." if last_known else ""
    detail = official_warning_details(alert)
    if event.casefold() == "tornado warning":
        action = TORNADO_SHELTER_ACTION
    return (
        title,
        f"The official alert includes {scope_sentence}.{uncertainty}{until_text} {action}" + (f" {detail}" if detail else ""),
        False,
    )
def _profile_tag(profile_id: str, incident_key: str) -> str:
    token = sha256(f"{profile_id}|{incident_key}".encode()).hexdigest()[:24]
    return f"weather_intelligence_{token}"


def _fingerprint(title: str, message: str, critical: bool, resolved: bool) -> str:
    return sha256(f"{title}|{message}|{critical}|{resolved}".encode()).hexdigest()


def _eligible_supplemental(
    profile: HouseholdProfile, item: SupplementalHazard
) -> bool:
    selected = set(profile.hazard_families)
    return bool(
        profile.enabled
        and profile.automatic_notifications
        and (profile.alert_events is None or "severe_weather_awareness" in profile.alert_events)
        and (profile.alert_events is not None or not selected or item.family.value in selected)
    )


def _hail_family_enabled(profile: HouseholdProfile | None) -> bool:
    return hail_enabled(profile)


def _stronger_hail_candidate(
    first: HailApproach | None, second: HailApproach
) -> HailApproach:
    if first is None:
        return second
    return min(
        (first, second),
        key=lambda item: (
            not item.life_threatening,
            item.eta_minutes,
            -item.max_hail_inches,
        ),
    )


def _preemptive_behavior(
    item: SupplementalHazard,
) -> DeliveryBehavior | None:
    """Select only official short-term or explicitly severe potential."""
    if item.source == "SPC mesoscale discussion":
        return DeliveryBehavior.AWARENESS
    if (
        item.source == "SPC outlook"
        and item.family.value == "severe_convection"
        and _supplemental_rank(item) >= 1
    ):
        return DeliveryBehavior.AWARENESS
    if item.source == "NWS forecast":
        text = f"{item.headline} {item.detail}".casefold()
        if re.search(
            r"\b(?:severe thunderstorms?|tornado(?:es)?|large hail|damaging winds?)\b",
            text,
        ):
            return DeliveryBehavior.AWARENESS
    return None


def _supplemental_key(item: SupplementalHazard) -> str:
    return f"supplemental|{item.source}|{item.family.value}"


def _supplemental_rank(item: SupplementalHazard) -> int:
    value = item.native_level.strip().casefold()
    levels = {
        "tstm": 0,
        "marginal": 1,
        "mrgl": 1,
        "slight": 2,
        "slgt": 2,
        "enhanced": 3,
        "enh": 3,
        "moderate": 4,
        "mdt": 4,
        "high": 5,
        "elevated": 1,
        "critical": 3,
        "extreme": 5,
        "minor": 1,
        "major": 3,
    }
    if value in levels:
        return levels[value]
    numeric = re.search(r"\d+(?:\.\d+)?", value)
    return int(float(numeric.group(0))) if numeric else 1


def _supplemental_wording(
    hass: Any, item: SupplementalHazard
) -> tuple[str, str]:
    if item.source == "SPC mesoscale discussion":
        return (
            "Weather Heads-Up — Mesoscale Discussion",
            "Thunderstorms are predicted by the National Weather Service. "
            "Stay weather aware.",
        )
    if item.source == "SPC outlook" and item.family.value == "severe_convection":
        levels = {
            "mrgl": "Marginal",
            "slgt": "Slight",
            "enh": "Enhanced",
            "mdt": "Moderate",
            "high": "High",
        }
        level = levels.get(
            item.native_level.strip().casefold(), item.native_level.strip().title()
        )
        return (
            f"Weather Heads-Up — {level} Risk Outlook",
            "Thunderstorms are predicted by the National Weather Service. "
            "Stay weather aware.",
        )
    title = f"Weather Heads-Up — {item.headline}"
    window = _official_window(hass, item.valid_from, item.valid_to)
    message = (
        f"{item.source} indicates {item.headline} for your designated home area."
        f"{window} {item.action}"
    )
    return title, " ".join(message.split())


def _official_window(
    hass: Any, start: datetime | None, end: datetime | None
) -> str:
    try:
        zone = ZoneInfo(str(hass.config.time_zone))
    except (AttributeError, ValueError):
        zone = timezone.utc

    def label(value: datetime) -> str:
        return value.astimezone(zone).strftime("%a %b %d at %I:%M %p").replace(" 0", " ")

    if start is not None and end is not None:
        return f" Official window: {label(start)} through {label(end)}."
    if start is not None:
        return f" Expected from {label(start)}."
    if end is not None:
        return f" Expected through {label(end)}."
    return ""


def _family_label(value: str) -> str:
    return value.replace("_", " ").title()
