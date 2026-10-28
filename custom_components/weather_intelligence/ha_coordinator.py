"""Home Assistant polling and storage adapter around the pure coordinator."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from functools import partial
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .automatic_delivery import HouseholdDeliveryRouter
from .acknowledgements import Acknowledgements
from .briefing_receipts import briefing_tag, received_briefing_profile
from .briefing import (
    DailyBriefing,
    briefing_delivery_due,
    briefing_message,
    build_daily_briefing,
    incidents_for_subjects,
    points_within_miles,
)
from .const import (
    BRIEFING_LOCATION_BOTH,
    BRIEFING_LOCATION_HOME,
    BRIEFING_LOCATION_PERSON,
    CONF_MRMS_HAIL_ENABLED,
    DEFAULT_BRIEFING_TIME,
    DOMAIN,
    LAST_KNOWN_CRITICAL_ELIGIBILITY,
    NWS_POLL_INTERVAL,
)
from .coordinator import WeatherCoordinator
from .ha_location import location_fix_from_person_state
from .water_detection import WaterAssessment, current_water_state, invalid_water_fix
from .regional_water import RegionalWaterCache, water_cell
from .regional_water_assessment import assess_regional_water
from .regional_navigation import RegionalNavigationCache
from .marine_nearby_feed import MarineNearbyFeed
from .models import (
    BriefingDeliveryRecord,
    CoordinatorStatus,
    HouseholdProfile,
    LocationFix,
    LocationFreshness,
    SourceHealthState,
)
from .mobile_notification import MobileTargetError, async_send_profile_notification, cancel_profile_audio
from .mrms_hail import (
    MRMS_MAX_AGE_SECONDS,
    HailApproach,
    HailMotionTracker,
    MrmsHailClient,
    MrmsHailError,
)
from .nws_client import NwsAlertClient, NwsClientError, NwsResponse
from .normalization import AlertNormalizationError
from .persistence import (
    StoredStateError,
    deserialize_briefing_delivery_state,
    deserialize_full_runtime_state,
    serialize_runtime_state,
)
from .official_sources import (
    SupplementalSourceState,
    fetch_airnow_current,
    fetch_spc_mesoscale_discussions,
    fetch_spc_outlooks,
    fetch_wssi,
    normalize_airnow,
    normalize_nws_forecast,
    normalize_spc_mesoscale_discussions,
    normalize_spc_outlook,
    normalize_wssi,
)
from .hazard_policy import DeliveryBehavior, hail_enabled, briefing_item_enabled

_LOGGER = logging.getLogger(__name__)


class WeatherIntelligenceDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorStatus]):
    """Poll distinct home/person points, deduplicate alerts, and persist continuity."""

    def __init__(
        self,
        hass: Any,
        entry: Any,
        client: NwsAlertClient,
        core: WeatherCoordinator,
        store: Store[dict[str, Any]],
        home_point: tuple[float, float],
        profiles: tuple[HouseholdProfile, ...] = (),
        mobile_target_configured: bool = False,
        briefing_time: str = DEFAULT_BRIEFING_TIME,
        source_options: dict[str, Any] | None = None,
        hail_client: MrmsHailClient | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=NWS_POLL_INTERVAL,
            always_update=False,
        )
        self._client = client
        self._entry = entry
        self.core = core
        self._store = store
        self._home_point = home_point
        self._profiles = profiles
        self._enabled_profiles = tuple(item for item in profiles if item.enabled)
        self._profile_by_subject = {
            item.subject_id: item
            for item in profiles
            if item.enabled
            and (
                item.receive_personal_alerts
                or (
                    item.daily_briefing
                    and item.briefing_location
                    in {BRIEFING_LOCATION_PERSON, BRIEFING_LOCATION_BOTH}
                )
            )
        }
        self._mobile_target_configured = mobile_target_configured
        self._last_person_fixes: dict[str, LocationFix] = {}
        self.water_assessments: dict[str, WaterAssessment] = {}
        self._water_point_cache: dict[str, tuple[Any, WaterAssessment]] = {}
        self._regional_water = RegionalWaterCache(Store(hass, 1, f"{DOMAIN}.regional_water"))
        self._regional_water_task = None
        self._regional_navigation = RegionalNavigationCache(Store(hass, 1, f"{DOMAIN}.regional_navigation"))
        self._nearby_feed = MarineNearbyFeed(client, hass.async_add_executor_job)
        self.acknowledgements = Acknowledgements()
        self._delivery = HouseholdDeliveryRouter(hass, profiles, self.acknowledgements)
        self._ack_unsubscribe = None
        self._briefing_receipt_unsubscribe = None
        self._briefing_delivery_lock = asyncio.Lock()
        self._briefing_time = briefing_time
        self._source_options = dict(source_options or {})
        self._hail_client = hail_client
        self._hail_tracker = HailMotionTracker()
        self._hail_active_approaches: dict[str, HailApproach] = {}
        self._hail_clear_streaks: dict[str, int] = {}
        self.hail_tracking_state = (
            "initializing"
            if self._source_options.get(CONF_MRMS_HAIL_ENABLED) and hail_client
            else "unconfigured"
        )
        self.hail_last_observed_at: datetime | None = None
        self._briefing_records: dict[str, BriefingDeliveryRecord] = {}
        self.briefing: DailyBriefing = build_daily_briefing(
            datetime.now(timezone.utc), (), (), {"NWS alerts": SupplementalSourceState.DEGRADED}
        )
        self._last_supplemental_refresh: datetime | None = None
        self._supplemental_hazards: tuple[Any, ...] = ()
        self._supplemental_states: dict[str, SupplementalSourceState] = {}
        self._supplemental_cache: dict[
            tuple[float, float],
            tuple[datetime, tuple[Any, ...], dict[str, SupplementalSourceState]],
        ] = {}
        self._profile_briefings: dict[str, DailyBriefing] = {}
        self._profile_briefing_parts: dict[str, tuple[DailyBriefing, ...]] = {}
        self._profile_briefing_locations: dict[str, str] = {}
        self.dashboard_briefings: dict[str, DailyBriefing] = {}
        self._poll_attempts = 0
        self.nws_request_healthy = None
        self.nws_alert_observed_at = {}
        from .source_latency import SourceLatencyTracker
        self.source_latency = SourceLatencyTracker()

    async def async_restore_state(self) -> None:
        stored = await self._store.async_load()
        try:
            incidents, notifications, deliveries = deserialize_full_runtime_state(stored)
        except StoredStateError as error:
            _LOGGER.warning("Ignoring invalid weather-intelligence stored state: %s", error)
            return
        self.core.restore_runtime_state(incidents, notifications)
        self._delivery.restore(deliveries)
        self.acknowledgements.restore((stored or {}).get("acknowledgements", []),
                                     {profile.profile_id for profile in self._profiles})
        for item in deserialize_briefing_delivery_state(stored):
            if any(profile.profile_id == item.profile_id for profile in self._profiles):
                self._briefing_records[item.profile_id] = item

    def apply_marine_preferences(self, modes: dict[str, str]) -> None:
        """Apply the verified saved choice without a restart or new enrollment."""
        self._profiles = tuple(replace(profile, marine_warning_mode=modes.get(profile.profile_id, profile.marine_warning_mode))
                               for profile in self._profiles)
        self._enabled_profiles = tuple(profile for profile in self._profiles if profile.enabled)
        self._profile_by_subject = {key: replace(profile, marine_warning_mode=modes.get(profile.profile_id, profile.marine_warning_mode))
                                    for key, profile in self._profile_by_subject.items()}
        self._delivery.apply_marine_preferences(modes)

    async def async_save_state(self) -> None:
        self.acknowledgements.prune(self.core.incident_records,
                                   {p.profile_id for p in self._profiles if p.enabled},
                                   datetime.now(timezone.utc))
        document = serialize_runtime_state(
                self.core.incident_records,
                self.core.notification_records,
                self._delivery.records,
                tuple(self._briefing_records.values()),
            )
        document["acknowledgements"] = self.acknowledgements.serialize()
        await self._store.async_save(document)

    def async_listen_for_acknowledgements(self) -> None:
        bus = getattr(self.hass, "bus", None)
        if self._ack_unsubscribe is None and bus is not None:
            self._ack_unsubscribe = bus.async_listen(
                "mobile_app_notification_action", self._async_acknowledge)
        if self._briefing_receipt_unsubscribe is None and bus is not None:
            self._briefing_receipt_unsubscribe = bus.async_listen(
                "mobile_app_notification_received", self._async_briefing_received)

    async def _async_briefing_received(self, event: Any) -> None:
        profile_id = received_briefing_profile(self.hass, self._profiles, self._briefing_records, event.data)
        if profile_id is None:
            return
        self._briefing_records[profile_id] = replace(
            self._briefing_records[profile_id], confirmed_at=datetime.now(timezone.utc))
        await self.async_save_state()

    async def _async_acknowledge(self, event: Any) -> None:
        result = self.acknowledgements.consume(event.data.get("action"),
                                               self.core.incident_records,
                                               datetime.now(timezone.utc))
        if result is None:
            return
        for delivery in self._delivery.records:
            if (delivery.profile_id == result["profile_id"]
                    and delivery.incident_key == result["incident_key"]):
                cancel_profile_audio(self.hass, delivery.profile_id, delivery.stable_tag)
        await self.async_save_state()
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        await self._nearby_feed.async_shutdown()
        if self._regional_water_task is not None:
            self._regional_water_task.cancel()
            await asyncio.gather(self._regional_water_task, return_exceptions=True)
            self._regional_water_task = None
        if self._ack_unsubscribe is not None:
            self._ack_unsubscribe()
            self._ack_unsubscribe = None
        if self._briefing_receipt_unsubscribe is not None:
            self._briefing_receipt_unsubscribe()
            self._briefing_receipt_unsubscribe = None
        for profile in self._profiles:
            cancel_profile_audio(self.hass, profile.profile_id)
        await self.async_save_state()

    async def _async_update_data(self) -> CoordinatorStatus:
        self._poll_attempts += 1
        now = datetime.now(timezone.utc)
        if self._profiles and getattr(self._entry, "options", {}).get("onboarding_accounts"):
            from .onboarding_preferences import async_apply_saved_marine_preferences
            try:
                await async_apply_saved_marine_preferences(self.hass, self._entry)
            except ValueError:
                # A concurrently edited profile must not interrupt official-alert polling.
                _LOGGER.debug("Marine preference transfer deferred while profile settings change.")
        await self._async_refresh_water(now)
        profile_fixes = {
            profile.profile_id: self._person_fix(profile)
            for profile in self._enabled_profiles
        }
        queries: dict[tuple[float, float], set[str]] = {
            self._home_point: {"designated_home"}
        }
        eligible_person_points = 0
        for subject_id, profile in self._profile_by_subject.items():
            fix = profile_fixes.get(profile.profile_id)
            person_point = _eligible_point(fix, now)
            if person_point is not None:
                eligible_person_points += 1
                queries.setdefault(person_point, set()).add(subject_id)

        # Query distinct monitored points concurrently. A slow point must not make
        # another household member wait through multiple request timeouts before a
        # life-safety alert can be evaluated.
        query_items = tuple(queries.items())
        results = await asyncio.gather(
            *(
                self.hass.async_add_executor_job(
                    partial(self._client.fetch_active, point=point)
                )
                for point, _subjects in query_items
            ),
            return_exceptions=True,
        )
        successes: list[tuple[NwsResponse, set[str]]] = []
        failures = 0
        failure_details: set[str] = set()
        last_failure = None
        for (_point, subjects), result in zip(query_items, results, strict=True):
            if isinstance(result, (NwsClientError, AlertNormalizationError)):
                last_failure = result
                failures += 1
                failure_details.add(_safe_failure_detail(result))
                continue
            if isinstance(result, BaseException):
                raise result
            try:
                _feature_list(result.payload)
            except AlertNormalizationError as error:
                last_failure = error
                failures += 1
                continue
            successes.append((result, subjects))

        self.nws_request_healthy = bool(successes) and failures == 0

        if not successes:
            _LOGGER.error(
                "Every direct NWS active-alert request failed for this polling cycle (%s).",
                "; ".join(sorted(failure_details)) or "unknown error",
                extra={"wi_exception": last_failure},
            )
            status = self.core.record_source_failure(
                "All required NWS point requests failed.", now
            )
            await self._async_refresh_briefing(
                now, SupplementalSourceState.DEGRADED, profile_fixes, set()
            )
            await self._async_refresh_hail(now, profile_fixes)
            await self.async_save_state()
            return self._finalize_status(status, profile_fixes, now)

        try:
            payload, matches, received_at = _combine_point_responses(successes)
            successful_subjects = {
                subject_id
                for _response, subjects in successes
                for subject_id in subjects
            }
            self.core.process_official_payload(
                payload,
                received_at,
                now,
                location_updates={
                    subject_id: profile_fixes[profile.profile_id]
                    for subject_id, profile in self._profile_by_subject.items()
                    if profile_fixes.get(profile.profile_id) is not None
                },
                official_point_matches=matches,
                authoritative_subjects=successful_subjects,
                complete_active_snapshot=(
                    failures == 0
                    and eligible_person_points == len(self._profile_by_subject)
                ),
            )
            self.nws_alert_observed_at = {
                message_id: observed for message_id, observed in self.nws_alert_observed_at.items()
                if now - timedelta(hours=2) <= observed <= now
            }
            for message_id in list(matches)[:5000]:
                self.nws_alert_observed_at[message_id] = received_at
            if len(self.nws_alert_observed_at) > 5000:
                self.nws_alert_observed_at = dict(sorted(self.nws_alert_observed_at.items(),
                    key=lambda item: item[1], reverse=True)[:5000])
            from .source_latency import collection_messages
            for (point, _subjects), response in zip(query_items, results, strict=True):
                if not any(response is successful[0] for successful in successes):
                    continue
                messages, complete = collection_messages(response.payload)
                self.source_latency.observe(point, messages, response.received_at, response.server_time,
                                            complete=complete)
            # The core records a source decision before Home Assistant attempts the
            # mobile send. Re-offer the current decisions on every successful poll;
            # the delivery router suppresses only fingerprints it actually sent.
            # This keeps a temporary phone/service failure retryable instead of
            # letting the next duplicate NWS poll silently strand the alert.
            await self._delivery.async_route(
                self.core.notification_records,
                self.core.incident_records,
                now,
                water_assessments=self.water_assessments,
            )
            await self._delivery.async_clear_due(now)
            await self._async_route_nearby_water(now)
        except AlertNormalizationError:
            self.nws_request_healthy = False
            status = self.core.record_source_failure(
                "An NWS point response could not be normalized.", now
            )
            await self._async_refresh_hail(now, profile_fixes)
            await self.async_save_state()
            return self._finalize_status(status, profile_fixes, now)

        if failures:
            _LOGGER.error(
                "%d direct NWS active-alert request(s) failed while other monitored points succeeded (%s).",
                failures,
                "; ".join(sorted(failure_details)) or "unknown error",
                extra={"wi_exception": last_failure},
            )
            self.core.record_source_degraded(
                "At least one NWS point request failed; retained incidents were not cleared.",
                now,
            )
        await self._async_refresh_briefing(
            now,
            SupplementalSourceState.DEGRADED if failures else SupplementalSourceState.HEALTHY,
            profile_fixes,
            successful_subjects,
        )
        await self._async_refresh_hail(now, profile_fixes)
        await self.async_save_state()
        if self.core.status is None:
            raise RuntimeError("Weather coordinator did not produce a status")
        return self._finalize_status(self.core.status, profile_fixes, now)

    async def _async_refresh_hail(
        self,
        now: datetime,
        profile_fixes: dict[str, LocationFix | None],
    ) -> None:
        if not self._source_options.get(CONF_MRMS_HAIL_ENABLED):
            self.hail_tracking_state = "unconfigured"
            return
        if self._hail_client is None:
            self.hail_tracking_state = "degraded"
            return
        targets: dict[str, tuple[float, float]] = {}
        monitor_home = False
        for profile in self._enabled_profiles:
            if not (
                profile.automatic_notifications
                and hail_enabled(profile)
            ):
                continue
            if profile.receive_personal_alerts:
                point = _eligible_point(profile_fixes.get(profile.profile_id), now)
                if point is not None:
                    targets[profile.subject_id] = point
            if profile.receive_home_while_away:
                monitor_home = True
        if monitor_home:
            targets["designated_home"] = self._home_point
        if not targets:
            self.hail_tracking_state = "idle"
            return
        try:
            frame = await self.hass.async_add_executor_job(
                partial(self._hail_client.fetch_latest, targets)
            )
        except (MrmsHailError, OSError, ValueError, TypeError) as error:
            self.hail_tracking_state = "degraded"
            _LOGGER.error(
                "Direct NOAA MRMS hail request failed: %s", str(error) if isinstance(error, MrmsHailError) else type(error).__name__,
                extra={"wi_exception": error},
            )
            return
        if frame is None:
            if self.hail_last_observed_at is None or (now - self.hail_last_observed_at).total_seconds() > MRMS_MAX_AGE_SECONDS:
                self.hail_tracking_state = "stale"
            else:
                self.hail_tracking_state = "healthy"
            return
        age_seconds = (now - frame.observed_at).total_seconds()
        if age_seconds > MRMS_MAX_AGE_SECONDS or age_seconds < -60:
            self.hail_tracking_state = "stale"
            _LOGGER.error("NOAA MRMS hail frame is outside the freshness window")
            return
        self.hail_tracking_state = "healthy"
        self.hail_last_observed_at = frame.observed_at
        authoritative, approaches = self._hail_tracker.update(frame, targets)
        if not authoritative:
            return
        for target_id in tuple(self._hail_active_approaches):
            if target_id not in targets:
                self._hail_active_approaches.pop(target_id, None)
                self._hail_clear_streaks.pop(target_id, None)
        for target_id in targets:
            approach = approaches.get(target_id)
            if approach is not None:
                self._hail_active_approaches[target_id] = approach
                self._hail_clear_streaks[target_id] = 0
                continue
            if target_id not in self._hail_active_approaches:
                continue
            misses = self._hail_clear_streaks.get(target_id, 0) + 1
            self._hail_clear_streaks[target_id] = misses
            if misses >= 2:
                self._hail_active_approaches.pop(target_id, None)
                self._hail_clear_streaks.pop(target_id, None)
        await self._delivery.async_route_hail(
            {
                target_id: approach
                for target_id, approach in self._hail_active_approaches.items()
                if target_id in targets
            },
            source_healthy=True,
            now=now,
        )

    async def _async_refresh_briefing(
        self,
        now: datetime,
        alert_state: SupplementalSourceState,
        profile_fixes: dict[str, LocationFix | None],
        authoritative_subjects: set[str],
    ) -> None:
        self._supplemental_cache = {
            point: cached
            for point, cached in self._supplemental_cache.items()
            if now - cached[0] < timedelta(hours=1)
        }
        home_briefing_point = _briefing_point(self._home_point)
        points = {home_briefing_point}
        profile_points: dict[str, tuple[float, float]] = {}
        for profile in self._enabled_profiles:
            if not (
                profile.receive_personal_alerts or (
                    profile.daily_briefing and profile.briefing_location
                    in {BRIEFING_LOCATION_PERSON, BRIEFING_LOCATION_BOTH})
            ):
                continue
            point = _eligible_point(profile_fixes.get(profile.profile_id), now)
            if point is not None:
                point = _briefing_point(point)
                points.add(point)
                profile_points[profile.profile_id] = point

        point_results = await asyncio.gather(
            *(self._async_supplemental_at(point, now) for point in points)
        )
        supplemental_by_point = dict(zip(points, point_results, strict=True))
        home_hazards, home_source_states = supplemental_by_point[home_briefing_point]
        home_states = {
            "NWS alerts": (
                SupplementalSourceState.HEALTHY
                if "designated_home" in authoritative_subjects
                else alert_state
            ),
            **home_source_states,
        }
        home_incidents = incidents_for_subjects(
            self.core.incident_records,
            self.core.notification_records,
            {"designated_home"},
        )
        self._last_supplemental_refresh = now
        self._supplemental_hazards = home_hazards
        self._supplemental_states = home_source_states
        self.briefing = build_daily_briefing(
            now, home_incidents, home_hazards, home_states
        )

        self._profile_briefings = {}
        self._profile_briefing_parts = {}
        self._profile_briefing_locations = {}
        self.dashboard_briefings = {}
        for profile in self._enabled_profiles:
            point = profile_points.get(profile.profile_id)
            if point is None or points_within_miles(home_briefing_point, point, 25.0):
                continue
            hazards, source_states = supplemental_by_point[point]
            personal_incidents = incidents_for_subjects(
                self.core.incident_records, self.core.notification_records, {profile.subject_id})
            self.dashboard_briefings[profile.profile_id] = build_daily_briefing(
                now, personal_incidents, hazards,
                {"NWS alerts": SupplementalSourceState.HEALTHY
                 if profile.subject_id in authoritative_subjects else SupplementalSourceState.DEGRADED,
                 **source_states})
        for profile in self._enabled_profiles:
            if not profile.daily_briefing:
                continue
            location = profile.briefing_location
            personal_point = profile_points.get(profile.profile_id)
            if (
                personal_point is not None
                and location
                in {BRIEFING_LOCATION_PERSON, BRIEFING_LOCATION_BOTH}
                and points_within_miles(
                    home_briefing_point, personal_point, 25.0
                )
            ):
                location = BRIEFING_LOCATION_HOME
            self._profile_briefing_locations[profile.profile_id] = location
            if personal_point is None:
                personal_hazards: tuple[Any, ...] = ()
                personal_states = _unavailable_supplemental_states(
                    self._source_options
                )
            else:
                personal_hazards, personal_source_states = supplemental_by_point[
                    personal_point
                ]
                personal_states = {
                    "NWS alerts": (
                        SupplementalSourceState.HEALTHY
                        if profile.subject_id in authoritative_subjects
                        else SupplementalSourceState.DEGRADED
                    ),
                    **personal_source_states,
                }
            if location == BRIEFING_LOCATION_HOME:
                hazards = home_hazards
                states = home_states
                subject_ids = {"designated_home"}
            elif location == BRIEFING_LOCATION_PERSON:
                hazards = personal_hazards
                states = personal_states
                subject_ids = {profile.subject_id}
            else:
                hazards = _deduplicate_supplemental(
                    (*home_hazards, *personal_hazards)
                )
                states = _merge_source_states(home_states, personal_states)
                subject_ids = {"designated_home", profile.subject_id}
            incidents = incidents_for_subjects(
                self.core.incident_records,
                self.core.notification_records,
                subject_ids,
            )
            self._profile_briefings[profile.profile_id] = build_daily_briefing(
                now, incidents, hazards, states
            )
            if location == BRIEFING_LOCATION_BOTH:
                personal_incidents = incidents_for_subjects(
                    self.core.incident_records,
                    self.core.notification_records,
                    {profile.subject_id},
                )
                self._profile_briefing_parts[profile.profile_id] = (
                    build_daily_briefing(
                        now, home_incidents, home_hazards, home_states
                    ),
                    build_daily_briefing(
                        now,
                        personal_incidents,
                        personal_hazards,
                        personal_states,
                    ),
                )

        # Preemptive notices remain explicitly tied to designated home. Personal
        # travel forecasts are delivered only through that profile's briefing.
        await self._delivery.async_route_supplemental(
            home_hazards, home_states, now
        )
        await self._async_deliver_briefing(now)

    async def _async_supplemental_at(
        self, point: tuple[float, float], now: datetime
    ) -> tuple[tuple[Any, ...], dict[str, SupplementalSourceState]]:
        cached = self._supplemental_cache.get(point)
        # An unavailable forecast should not suppress recovery for fifteen minutes.
        cache_minutes = 15 if cached and cached[2].get("NWS forecast") == SupplementalSourceState.HEALTHY else 2
        if cached is not None and now - cached[0] < timedelta(minutes=cache_minutes):
            return cached[1], dict(cached[2])
        supplemental = []
        states: dict[str, SupplementalSourceState] = {}
        fetch_forecast = getattr(self._client, "fetch_point_forecast", None)
        if callable(fetch_forecast):
            try:
                response = await self.hass.async_add_executor_job(
                    partial(fetch_forecast, point)
                )
                forecast_items = normalize_nws_forecast(response.payload)
                supplemental.extend(forecast_items)
                states["NWS forecast"] = (SupplementalSourceState.HEALTHY
                    if any(item.forecast_summary for item in forecast_items)
                    else SupplementalSourceState.DEGRADED)
            except (NwsClientError, ValueError, TypeError) as error:
                _LOGGER.error("Direct NWS forecast request failed: %s", type(error).__name__,
                              extra={"wi_exception": error})
                states["NWS forecast"] = SupplementalSourceState.DEGRADED
        else:
            states["NWS forecast"] = SupplementalSourceState.DEGRADED

        if self._source_options.get("spc_outlooks_enabled"):
            try:
                payload = await self.hass.async_add_executor_job(
                    partial(fetch_spc_outlooks, point)
                )
                supplemental.extend(normalize_spc_outlook(payload))
                states["SPC outlook"] = SupplementalSourceState.HEALTHY
            except Exception as error:
                _LOGGER.error("Direct SPC outlook request failed: %s", type(error).__name__)
                states["SPC outlook"] = SupplementalSourceState.DEGRADED
            try:
                payload = await self.hass.async_add_executor_job(
                    partial(fetch_spc_mesoscale_discussions, point)
                )
                supplemental.extend(normalize_spc_mesoscale_discussions(payload))
                states["SPC mesoscale discussion"] = SupplementalSourceState.HEALTHY
            except Exception as error:
                _LOGGER.error(
                    "Direct SPC mesoscale-discussion request failed: %s",
                    type(error).__name__,
                )
                states["SPC mesoscale discussion"] = SupplementalSourceState.DEGRADED
        if self._source_options.get("wssi_enabled"):
            try:
                payload = await self.hass.async_add_executor_job(
                    partial(fetch_wssi, point)
                )
                supplemental.extend(normalize_wssi(payload))
                states["NWS WSSI"] = SupplementalSourceState.HEALTHY
            except Exception as error:
                _LOGGER.error("Direct NWS WSSI request failed: %s", type(error).__name__)
                states["NWS WSSI"] = SupplementalSourceState.DEGRADED
        if self._source_options.get("uv_enabled"):
            states["Official UV"] = SupplementalSourceState.UNCONFIGURED
        if self._source_options.get("airnow_enabled"):
            key = str(self._source_options.get("airnow_api_key", "")).strip()
            if not key:
                states["EPA AirNow"] = SupplementalSourceState.UNCONFIGURED
            else:
                try:
                    payload = await self.hass.async_add_executor_job(
                        partial(fetch_airnow_current, point, key)
                    )
                    supplemental.extend(normalize_airnow(payload))
                    states["EPA AirNow"] = SupplementalSourceState.HEALTHY
                except Exception as error:  # Network and provider failures are isolated to this source.
                    _LOGGER.error("Direct EPA AirNow request failed: %s", type(error).__name__)
                    states["EPA AirNow"] = SupplementalSourceState.DEGRADED

        result = (tuple(supplemental), dict(states))
        self._supplemental_cache[point] = (now, result[0], result[1])
        return result

    async def _async_deliver_briefing(self, now: datetime) -> None:
        async with self._briefing_delivery_lock:
            await self._async_deliver_scheduled_briefing(now)

    async def _async_deliver_scheduled_briefing(self, now: datetime) -> None:
        try:
            local_now = now.astimezone(ZoneInfo(str(self.hass.config.time_zone)))
        except (AttributeError, ValueError):
            local_now = now
        for profile in self._profiles:
            if not (profile.enabled and profile.daily_briefing):
                continue
            scoped_briefing = self._profile_briefings.get(
                profile.profile_id, self.briefing
            )
            effective_location = self._profile_briefing_locations.get(
                profile.profile_id, profile.briefing_location
            )
            required_briefings = (self._profile_briefing_parts.get(profile.profile_id, ())
                if effective_location == BRIEFING_LOCATION_BOTH else (scoped_briefing,))
            if not required_briefings or any(
                part.forecast is None
                or part.source_states.get("NWS forecast") != SupplementalSourceState.HEALTHY
                or (part.forecast.valid_to is not None and part.forecast.valid_to <= now)
                for part in required_briefings
            ):
                # No empty fallback and no daily claim: the next source refresh
                # can still deliver today's forecast. Separate hazard alerts continue.
                continue
            visible_items = tuple(
                item for item in scoped_briefing.items
                if briefing_item_enabled(profile,item) and _relevant_on_local_day(item, local_now)
            )
            profile_briefing = DailyBriefing(
                scoped_briefing.generated_at,
                visible_items[0].headline if visible_items else "No selected hazard concerns",
                (f"{len(visible_items)} safety item{'s' if len(visible_items) != 1 else ''}. {visible_items[0].headline}."
                 if visible_items else "No current concern in the selected hazard families."),
                visible_items, scoped_briefing.source_states,
                sha256("|".join(f"{item.source}:{item.headline}:{item.native_level}" for item in visible_items).encode()).hexdigest(),
                scoped_briefing.forecast,
            )
            title, message = briefing_message(profile_briefing)
            if effective_location == BRIEFING_LOCATION_BOTH:
                part_messages = []
                for label, part in zip(
                    ("Home", "Your location"),
                    self._profile_briefing_parts.get(profile.profile_id, ()),
                    strict=True,
                ):
                    part_items = tuple(
                        item
                        for item in part.items
                        if briefing_item_enabled(profile,item) and _relevant_on_local_day(item, local_now)
                    )
                    part_briefing = DailyBriefing(
                        part.generated_at,
                        part_items[0].headline
                        if part_items
                        else "No selected hazard concerns",
                        "",
                        part_items,
                        part.source_states,
                        _briefing_items_fingerprint(part_items),
                        part.forecast,
                    )
                    _part_title, part_message = briefing_message(part_briefing)
                    part_messages.append(f"{label}: {part_message}")
                if part_messages:
                    message = " ".join(part_messages)
            title += {
                BRIEFING_LOCATION_HOME: " — Home",
                BRIEFING_LOCATION_PERSON: " — Your Location",
                BRIEFING_LOCATION_BOTH: " — Home + Your Location",
            }.get(effective_location, " — Home")
            same_day_items = tuple(
                item for item in visible_items if _relevant_on_local_day(item, local_now)
            )
            same_day_briefing = DailyBriefing(
                profile_briefing.generated_at,
                profile_briefing.state,
                profile_briefing.summary,
                same_day_items,
                profile_briefing.source_states,
                _briefing_items_fingerprint((*same_day_items, profile_briefing.forecast)),
                profile_briefing.forecast,
            )
            urgency = _briefing_urgency(same_day_briefing)
            prior = self._briefing_records.get(profile.profile_id)
            today = local_now.date().isoformat()
            if not briefing_delivery_due(
                prior, local_now, profile.daily_outlook_time or self._briefing_time,
                same_day_briefing.fingerprint, urgency,
            ):
                continue
            midnight = (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            remaining = int((midnight.astimezone(timezone.utc) - local_now.astimezone(timezone.utc)).total_seconds())
            if remaining <= 0:
                continue
            # A durable pre-send claim prevents an uncertain send being repeated
            # after a crash. Definite failures are marked pending for retry.
            claim = BriefingDeliveryRecord(profile.profile_id, today,
                same_day_briefing.fingerprint, urgency, None, False, local_now)
            self._briefing_records[profile.profile_id] = claim
            try:
                await self.async_save_state()
            except Exception:
                if prior is None:
                    self._briefing_records.pop(profile.profile_id, None)
                else:
                    self._briefing_records[profile.profile_id] = prior
                _LOGGER.error("Daily briefing paused because its delivery record could not be saved.")
                continue
            try:
                await async_send_profile_notification(
                    self.hass, profile, title=title, message=message,
                    stable_tag=briefing_tag(profile.profile_id, today),
                    critical=False, behavior=DeliveryBehavior.BRIEFING_ONLY,
                    timeout_seconds=remaining, delivery_ttl_seconds=remaining,
                    delivery_expiration=int(midnight.timestamp()),
                    request_confirmation=profile.mobile_platform == "android",
                )
            except MobileTargetError as error:
                _LOGGER.error(
                    "Daily briefing delivery failed for one configured profile: %s",
                    error,
                )
                receipt = self._briefing_records[profile.profile_id].confirmed_at
                self._briefing_records[profile.profile_id] = BriefingDeliveryRecord(
                    profile.profile_id,
                    today,
                    same_day_briefing.fingerprint,
                    urgency,
                    local_now if receipt else prior.delivered_at if prior else None,
                    error.retry_safe and receipt is None,
                    local_now,
                    receipt,
                )
                await self.async_save_state()
                continue
            # Keep any receipt which arrived while the service call was awaiting.
            self._briefing_records[profile.profile_id] = replace(
                self._briefing_records[profile.profile_id], delivered_at=local_now)
            await self.async_save_state()

    async def _async_refresh_water(self, now: datetime) -> None:
        states = self.hass.states.async_all("person")
        fixes = {state.entity_id: location_fix_from_person_state(state) for state in states}
        # Map downloads are limited to explicitly enrolled on-water profiles and
        # run separately: a slow map server must not delay official warning polls.
        opted_people = {profile.person_entity_id for profile in self._enabled_profiles
                        if profile.automatic_notifications and profile.receive_personal_alerts
                        and (profile.marine_warning_mode == "on_water" or profile.marine_nearby_enabled
                             or (profile.critical_notifications and any(
                                 rule.startswith("water_wind:") for rule in profile.dnd_rule_ids or ())))}
        nearby_people = {profile.person_entity_id for profile in self._enabled_profiles
                         if profile.automatic_notifications and profile.receive_personal_alerts
                         and profile.marine_nearby_enabled}
        cells = tuple(dict.fromkeys(cell for entity_id, fix in fixes.items()
                      if entity_id in opted_people and not invalid_water_fix(fix, now)
                      and (cell := water_cell(fix.latitude, fix.longitude)) is not None))
        if self._regional_water_task is None or self._regional_water_task.done():
            navigation_cells = tuple(dict.fromkeys(cell for entity_id, fix in fixes.items()
                          if entity_id in nearby_people and not invalid_water_fix(fix, now)
                          and (cell := water_cell(fix.latitude, fix.longitude)) is not None))
            self._regional_water_task = asyncio.create_task(self._async_refresh_water_maps(cells, navigation_cells, now))
        results = await self.hass.async_add_executor_job(self._assess_water_fixes, fixes, now)
        if results != self.water_assessments:
            self.water_assessments = results
            self.async_update_listeners()

    async def _async_refresh_water_maps(self, cells: tuple, navigation_cells: tuple, now: datetime) -> None:
        await asyncio.gather(
            self._regional_water.async_refresh(cells, self.hass.async_add_executor_job, now),
            self._regional_navigation.async_refresh(navigation_cells, self.hass.async_add_executor_job, now),
        )

    async def _async_route_nearby_water(self, now: datetime) -> None:
        enabled = any(profile.enabled and profile.automatic_notifications
                      and profile.receive_personal_alerts and profile.marine_nearby_enabled
                      and current_water_state(self.water_assessments.get(profile.person_entity_id), now) is True
                      for profile in self._profiles)
        self._nearby_feed.request_refresh(enabled, now)
        alerts = self._nearby_feed.alerts(now)
        if alerts:
            await self._delivery.async_route_marine_nearby(
                alerts, self.water_assessments, self._regional_water,
                self._regional_navigation, now,
            )

    def _assess_water_fixes(self, fixes: dict[str, LocationFix | None], now: datetime) -> dict[str, WaterAssessment]:
        # Decode static geography off HA's event loop; retain only current in-memory results.
        self._water_point_cache = {key: value for key, value in self._water_point_cache.items() if key in fixes}
        results = {}
        for entity_id, fix in fixes.items():
            reason = invalid_water_fix(fix, now)
            if reason:
                results[entity_id] = WaterAssessment(None, reason, fix.observed_at if fix else None)
                continue
            assert fix is not None
            regional = getattr(self, "_regional_water", None)
            cell = water_cell(fix.latitude, fix.longitude)
            point = (fix.latitude, fix.longitude, fix.accuracy_meters,
                     regional.generation if regional is not None else None,
                     regional.bodies(cell, now) is not None if regional is not None and cell is not None else False)
            cached = self._water_point_cache.get(entity_id)
            if cached is None or cached[0] != point:
                assessment = assess_regional_water(regional, fix, now) if regional is not None else None
                if assessment is None:
                    assessment = WaterAssessment(None, "regional_water_unavailable", fix.observed_at)
                cached = (point, assessment)
                self._water_point_cache[entity_id] = cached
            results[entity_id] = replace(cached[1], observed_at=fix.observed_at)
        return results

    def _person_fix(self, profile: HouseholdProfile) -> LocationFix | None:
        parsed = location_fix_from_person_state(
            self.hass.states.get(profile.person_entity_id)
        )
        if (
            parsed is not None
            and parsed.observed_at is not None
            and parsed.latitude is not None
            and parsed.longitude is not None
        ):
            self._last_person_fixes[profile.profile_id] = parsed
            return parsed
        last_fix = self._last_person_fixes.get(profile.profile_id)
        if last_fix is not None:
            return replace(last_fix, reported_stale=True)
        return parsed or LocationFix(None, None, None, None)

    def _decorate_status(
        self,
        status: CoordinatorStatus,
        person_fixes: dict[str, LocationFix | None],
        now: datetime,
    ) -> CoordinatorStatus:
        freshnesses = [_status_freshness(item, now) for item in person_fixes.values()]
        enabled = [item for item in self._profiles if item.enabled]
        degraded_states = {
            LocationFreshness.DEGRADED,
            LocationFreshness.LAST_KNOWN_GRACE,
        }
        unknown_states = {
            LocationFreshness.UNKNOWN,
            LocationFreshness.MISSING,
            LocationFreshness.INTENTIONALLY_UNAVAILABLE,
        }
        decorated = replace(
            status,
            personal_tracking_configured=bool(self._profile_by_subject),
            mobile_test_target_configured=self._mobile_target_configured,
            person_location_freshness=_aggregate_freshness(freshnesses),
            configured_profile_count=len(self._profiles),
            enabled_profile_count=len(enabled),
            fresh_person_count=sum(item == LocationFreshness.FRESH for item in freshnesses),
            degraded_person_count=sum(item in degraded_states for item in freshnesses),
            unknown_person_count=sum(item in unknown_states for item in freshnesses),
            automatic_profile_count=sum(item.automatic_notifications for item in enabled),
            critical_profile_count=sum(item.critical_notifications for item in enabled),
            partial_source_degradation=(
                status.source_health.value == "source_degraded"
            ),
        )
        self.core.status = decorated
        return decorated

    def _finalize_status(
        self,
        status: CoordinatorStatus,
        person_fixes: dict[str, LocationFix | None],
        now: datetime,
    ) -> CoordinatorStatus:
        decorated = self._decorate_status(status, person_fixes, now)
        if (
            self._poll_attempts == 1
            and decorated.source_health != SourceHealthState.HEALTHY
        ):
            decorated = replace(
                decorated,
                source_health=SourceHealthState.INITIALIZING,
                partial_source_degradation=False,
            )
            self.core.status = decorated
        return decorated


def _aggregate_freshness(values: list[LocationFreshness]) -> LocationFreshness:
    if not values:
        return LocationFreshness.MISSING
    for value in (
        LocationFreshness.UNKNOWN,
        LocationFreshness.MISSING,
        LocationFreshness.DEGRADED,
        LocationFreshness.LAST_KNOWN_GRACE,
        LocationFreshness.FRESH,
    ):
        if value in values:
            return value
    return values[0]


def _briefing_urgency(briefing: DailyBriefing) -> int:
    order = {"immediate_life_safety": 0, "important_warning": 1,
             "health_or_behavior_notice": 2, "advance_awareness": 3,
             "briefing_only": 4}
    return min((order.get(item.behavior.value, 5) for item in briefing.items), default=5)


def _deduplicate_supplemental(items: tuple[Any, ...]) -> tuple[Any, ...]:
    seen = set()
    result = []
    for item in items:
        key = (
            item.source,
            item.family,
            item.headline,
            item.native_level,
            item.valid_from,
            item.valid_to,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


def _merge_source_states(
    first: dict[str, SupplementalSourceState],
    second: dict[str, SupplementalSourceState],
) -> dict[str, SupplementalSourceState]:
    rank = {
        SupplementalSourceState.HEALTHY: 0,
        SupplementalSourceState.UNCONFIGURED: 1,
        SupplementalSourceState.STALE: 2,
        SupplementalSourceState.DEGRADED: 3,
    }
    result = dict(first)
    for key, value in second.items():
        if key not in result or rank[value] > rank[result[key]]:
            result[key] = value
    return result


def _unavailable_supplemental_states(
    source_options: dict[str, Any],
) -> dict[str, SupplementalSourceState]:
    states = {
        "NWS alerts": SupplementalSourceState.DEGRADED,
        "NWS forecast": SupplementalSourceState.DEGRADED,
    }
    if source_options.get("spc_outlooks_enabled"):
        states["SPC outlook"] = SupplementalSourceState.DEGRADED
        states["SPC mesoscale discussion"] = SupplementalSourceState.DEGRADED
    if source_options.get("wssi_enabled"):
        states["NWS WSSI"] = SupplementalSourceState.DEGRADED
    if source_options.get("uv_enabled"):
        states["Official UV"] = SupplementalSourceState.UNCONFIGURED
    if source_options.get("airnow_enabled"):
        states["EPA AirNow"] = (
            SupplementalSourceState.DEGRADED
            if str(source_options.get("airnow_api_key", "")).strip()
            else SupplementalSourceState.UNCONFIGURED
        )
    return states


def _briefing_items_fingerprint(items: tuple[Any, ...]) -> str:
    return sha256(
        "|".join(
            f"{item.source}:{item.headline}:{item.native_level}:{item.valid_from}:{item.valid_to}"
            for item in items
        ).encode()
    ).hexdigest()


def _relevant_on_local_day(item: Any, local_now: datetime) -> bool:
    if item.valid_from is None and item.valid_to is None:
        return not item.routine_forecast
    zone = local_now.tzinfo or timezone.utc
    start = item.valid_from.astimezone(zone).date() if item.valid_from else None
    end = item.valid_to.astimezone(zone).date() if item.valid_to else None
    today = local_now.date()
    return (start is None or start <= today) and (end is None or today <= end)


def _explicit_severe_potential(item: Any) -> bool:
    if item.source in {"SPC outlook", "SPC mesoscale discussion"}:
        return True
    text = f"{item.headline} {item.detail}".casefold()
    return any(
        phrase in text
        for phrase in (
            "severe thunderstorm",
            "tornado",
            "large hail",
            "damaging wind",
        )
    )


def _eligible_point(fix: LocationFix | None, now: datetime) -> tuple[float, float] | None:
    if (
        fix is None
        or fix.latitude is None
        or fix.longitude is None
        or fix.observed_at is None
    ):
        return None
    age = max(0.0, (now - fix.observed_at).total_seconds())
    if age > LAST_KNOWN_CRITICAL_ELIGIBILITY.total_seconds():
        return None
    return fix.latitude, fix.longitude


def _briefing_point(point: tuple[float, float]) -> tuple[float, float]:
    """Keep small GPS jitter from bypassing the 15-minute source cache."""
    return round(point[0], 3), round(point[1], 3)


def _status_freshness(fix: LocationFix | None, now: datetime) -> LocationFreshness:
    if fix is None or fix.observed_at is None or fix.latitude is None or fix.longitude is None:
        return LocationFreshness.MISSING
    age = max(0.0, (now - fix.observed_at).total_seconds())
    if age > LAST_KNOWN_CRITICAL_ELIGIBILITY.total_seconds():
        return LocationFreshness.UNKNOWN
    if age >= 15 * 60:
        return LocationFreshness.DEGRADED
    if fix.reported_stale:
        return LocationFreshness.LAST_KNOWN_GRACE
    return LocationFreshness.FRESH


def _feature_list(payload: Any) -> list[dict[str, Any]]:
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise AlertNormalizationError("NWS response does not contain a features list")
    return features


def _safe_failure_detail(error: BaseException) -> str:
    """Return a bounded request failure reason without locations or request URLs."""
    text = str(error).casefold()
    if "http error 429" in text or "too many requests" in text:
        return "HTTP 429 rate limited"
    for status in (500, 502, 503, 504):
        if f"http error {status}" in text:
            return f"HTTP {status}"
    if "timed out" in text or "timeout" in text:
        return "request timed out"
    if isinstance(error, AlertNormalizationError):
        return "invalid alert response"
    return type(error).__name__


def _combine_point_responses(
    responses: list[tuple[NwsResponse, set[str]]],
) -> tuple[dict[str, Any], dict[str, set[str]], datetime]:
    features_by_id: dict[str, dict[str, Any]] = {}
    matches: dict[str, set[str]] = {}
    received_at = max(response.received_at for response, _subjects in responses)
    for response, subjects in responses:
        for feature in _feature_list(response.payload):
            properties = feature.get("properties") if isinstance(feature, dict) else None
            message_id = (
                properties.get("id") if isinstance(properties, dict) else None
            ) or (feature.get("id") if isinstance(feature, dict) else None)
            if not message_id:
                raise AlertNormalizationError("NWS feature has no official message identifier")
            message_id = str(message_id)
            features_by_id[message_id] = feature
            matches.setdefault(message_id, set()).update(subjects)
    return (
        {"type": "FeatureCollection", "features": list(features_by_id.values())},
        matches,
        received_at,
    )
