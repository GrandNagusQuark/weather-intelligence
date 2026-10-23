# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Weather Intelligence contributors.
"""Installable Home Assistant lifecycle for the provisional integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    """Register benign local and explicitly single-target mobile test actions."""
    import voluptuous as vol

    from homeassistant.components import persistent_notification
    from homeassistant.exceptions import ServiceValidationError

    from .config import effective_entry_config
    from .const import (
        SAFE_TEST_MESSAGE,
        SAFE_TEST_NOTIFICATION_ID,
        SAFE_TEST_TITLE,
        CONF_TEST_SCENARIO,
        SERVICE_TEST_MOBILE_SCENARIO,
        SERVICE_TEST_MOBILE_NOTIFICATION,
        SERVICE_TEST_NOTIFICATION,
        TEST_SCENARIOS,
    )
    from .manual_scenarios import build_manual_scenario_message
    from .mobile_notification import (
        MobileTargetError,
        async_send_manual_test_message,
        async_send_safe_mobile_test,
    )

    async def async_handle_test_notification(call: Any) -> None:
        persistent_notification.async_create(
            hass,
            SAFE_TEST_MESSAGE,
            title=SAFE_TEST_TITLE,
            notification_id=SAFE_TEST_NOTIFICATION_ID,
        )

    async def async_handle_mobile_test_notification(call: Any) -> None:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if getattr(entry, "runtime_data", None) is not None
        ]
        if len(entries) != 1:
            raise ServiceValidationError(
                "Weather Intelligence requires one configured entry for the mobile test"
            )
        try:
            await async_send_safe_mobile_test(
                hass, effective_entry_config(entries[0])
            )
        except MobileTargetError as error:
            raise ServiceValidationError(str(error)) from error

    async def async_handle_mobile_test_scenario(call: Any) -> None:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if getattr(entry, "runtime_data", None) is not None
        ]
        if len(entries) != 1:
            raise ServiceValidationError(
                "Weather Intelligence requires one configured entry for the scenario test"
            )
        try:
            scenario = build_manual_scenario_message(
                str(call.data.get(CONF_TEST_SCENARIO, ""))
            )
            await async_send_manual_test_message(
                hass,
                effective_entry_config(entries[0]),
                title=scenario.title,
                message=scenario.message,
            )
        except (MobileTargetError, ValueError) as error:
            raise ServiceValidationError(str(error)) from error

    if not hass.services.has_service(DOMAIN, SERVICE_TEST_NOTIFICATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TEST_NOTIFICATION,
            async_handle_test_notification,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_TEST_MOBILE_NOTIFICATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TEST_MOBILE_NOTIFICATION,
            async_handle_mobile_test_notification,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_TEST_MOBILE_SCENARIO):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TEST_MOBILE_SCENARIO,
            async_handle_mobile_test_scenario,
            schema=vol.Schema(
                {vol.Required(CONF_TEST_SCENARIO): vol.In(TEST_SCENARIOS)}
            ),
        )
    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Restore state, perform the first cautious poll, and load the sensor."""
    from homeassistant.helpers.storage import Store

    from .config import (
        build_nws_user_agent,
        effective_entry_config,
        has_mobile_test_target,
        migrate_android_siren_channels,
        profiles_from_config,
    )
    from .const import (
        BRIEFING_LOCATION_BOTH, BRIEFING_LOCATION_PERSON,
        CONF_AIRNOW_API_KEY, CONF_AIRNOW_ENABLED, CONF_BRIEFING_TIME,
        CONF_CONTACT, CONF_MONITOR_HOME, CONF_SPC_ENABLED, CONF_UV_ENABLED,
        CONF_WSSI_ENABLED, CONF_MRMS_HAIL_ENABLED, DEFAULT_BRIEFING_TIME,
    )
    from .coordinator import WeatherCoordinator
    from .ha_coordinator import WeatherIntelligenceDataUpdateCoordinator
    from .models import LocationFix, MonitoredSubject, SubjectKind
    from .nws_client import NwsAlertClient
    from .mrms_hail import MrmsHailClient
    from .persistence import HA_STORE_VERSION

    from .onboarding import TEST_RESET_PENDING, async_prepare_onboarding_test
    store = Store(hass, HA_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    onboarding_testing = await async_prepare_onboarding_test(hass, entry)
    from .onboarding_reset import async_apply_requested_reset
    reference_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.profiles")
    await async_apply_requested_reset(hass, entry, store,
        additional_stores=(Store(hass, 1, f"{DOMAIN}.avalanche_regions"), reference_store))
    # Restore the alarm route before runtime profiles/reference fingerprints load.
    migrate_android_siren_channels(hass, entry)
    from .const import (ANDROID_SIREN_REVIEW_PENDING, ANDROID_SIREN_REVIEW_NOTIFICATION,
                        ANDROID_SIREN_REVIEW_MESSAGE)
    if effective_entry_config(entry).get(ANDROID_SIREN_REVIEW_PENDING):
        from homeassistant.components import persistent_notification
        # One stable local notice, not a new phone push after every restart.
        persistent_notification.async_create(hass, ANDROID_SIREN_REVIEW_MESSAGE,
            title="Weather Intelligence: review Android siren setup",
            notification_id=ANDROID_SIREN_REVIEW_NOTIFICATION)
    from .persistence import async_start_profile_reference
    await async_start_profile_reference(hass, entry, reference_store)
    effective = effective_entry_config(entry)
    profiles = profiles_from_config(effective)
    from .onboarding_preferences import async_apply_saved_marine_preferences
    profiles = await async_apply_saved_marine_preferences(hass, entry, profiles)
    subjects: list[MonitoredSubject] = []
    if effective.get(CONF_MONITOR_HOME, True):
        subjects.append(
            MonitoredSubject(
                subject_id="designated_home",
                display_name="Designated home",
                kind=SubjectKind.DESIGNATED_HOME,
                location=LocationFix(
                    latitude=float(hass.config.latitude),
                    longitude=float(hass.config.longitude),
                    observed_at=None,
                    accuracy_meters=None,
                ),
            )
        )

    for profile in profiles:
        if not (
            profile.enabled
            and (
                profile.receive_personal_alerts
                or (
                    profile.daily_briefing
                    and profile.briefing_location
                    in {BRIEFING_LOCATION_PERSON, BRIEFING_LOCATION_BOTH}
                )
            )
        ):
            continue
        subjects.append(
            MonitoredSubject(
                subject_id=profile.subject_id,
                display_name="Protected person",
                kind=SubjectKind.PERSON,
                location=LocationFix(None, None, None, None),
            )
        )

    user_agent = build_nws_user_agent(effective[CONF_CONTACT])
    client = NwsAlertClient(user_agent)
    hail_enabled = bool(effective.get(CONF_MRMS_HAIL_ENABLED, True))
    hail_client = MrmsHailClient(user_agent) if hail_enabled else None
    core = WeatherCoordinator(subjects)
    if onboarding_testing and entry.data.get(TEST_RESET_PENDING, False):
        await store.async_remove()
        data = dict(entry.data)
        data.pop(TEST_RESET_PENDING, None)
        hass.config_entries.async_update_entry(entry, data=data)
    coordinator = WeatherIntelligenceDataUpdateCoordinator(
        hass,
        entry,
        client,
        core,
        store,
        (float(hass.config.latitude), float(hass.config.longitude)),
        profiles=profiles,
        mobile_target_configured=has_mobile_test_target(effective),
        briefing_time=str(effective.get(CONF_BRIEFING_TIME, DEFAULT_BRIEFING_TIME)),
        source_options={
            CONF_MRMS_HAIL_ENABLED: hail_enabled,
            CONF_SPC_ENABLED: bool(effective.get(CONF_SPC_ENABLED, False)),
            CONF_WSSI_ENABLED: bool(effective.get(CONF_WSSI_ENABLED, False)),
            CONF_AIRNOW_ENABLED: bool(effective.get(CONF_AIRNOW_ENABLED, False)),
            CONF_UV_ENABLED: bool(effective.get(CONF_UV_ENABLED, False)),
            CONF_AIRNOW_API_KEY: str(effective.get(CONF_AIRNOW_API_KEY, "")),
        },
        hail_client=hail_client,
    )
    from .mqtt_error_logging import setup_mqtt_error_logging
    setup_mqtt_error_logging(hass, entry, effective)
    await coordinator.async_restore_state()
    coordinator.async_listen_for_acknowledgements()
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])
    from .panel import async_register_admin_panel
    await async_register_admin_panel(hass)
    from .maintainer_reporting import async_setup_reporting
    await async_setup_reporting(hass, entry)
    from .outage_reporting import async_setup_outages
    try:
        await async_setup_outages(hass, entry)
    except Exception:
        # Optional reporting must not prevent the weather integration from loading.
        hass.data.setdefault(DOMAIN, {}).setdefault("outage_setup_errors", {})[entry.entry_id] = "Outage reporting could not start"
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])
    if unloaded:
        await entry.runtime_data.async_shutdown()
        from .mqtt_error_logging import remove_mqtt_error_logging
        remove_mqtt_error_logging(hass, entry.entry_id)
        from .maintainer_reporting import async_stop_reporting
        await async_stop_reporting(hass, entry.entry_id)
        from .outage_reporting import async_stop_outages
        await async_stop_outages(hass, entry.entry_id)
        hass.data.get(DOMAIN, {}).get("feedback", {}).pop(entry.entry_id, None)
        entry.runtime_data = None
        from .panel import async_remove_admin_panel
        await async_remove_admin_panel(hass)
    return unloaded


async def async_migrate_entry(hass: Any, entry: Any) -> bool:
    """Upgrade installed entries without deletion or recreation."""
    from .config import effective_entry_config, migrate_single_profile, profile_to_dict
    from .const import (
        CONF_CRITICAL_NOTIFICATIONS,
        CONF_LEGACY_NOTIFY_SERVICE,
        CONF_NOTIFY_ENTITY,
        CONF_PERSON_ENTITY,
        CONF_PROFILES,
        CONF_BRIEFING_TIME,
    )

    if entry.version != 1:
        return False
    if entry.minor_version < 2:
        data = dict(entry.data)
        data.setdefault(CONF_PERSON_ENTITY, "")
        data.setdefault(CONF_NOTIFY_ENTITY, "")
        data.setdefault(CONF_LEGACY_NOTIFY_SERVICE, "")
        data[CONF_CRITICAL_NOTIFICATIONS] = False
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            version=1,
            minor_version=2,
        )
    if entry.minor_version < 3:
        effective = effective_entry_config(entry)
        profile = migrate_single_profile(effective)
        data = dict(entry.data)
        data[CONF_PROFILES] = [profile_to_dict(profile)] if profile else []
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            version=1,
            minor_version=3,
        )
    if entry.minor_version < 4:
        # New briefing participation remains off on every migrated profile;
        # existing automatic/critical choices are preserved exactly.
        effective = effective_entry_config(entry)
        profiles = []
        for profile in effective.get(CONF_PROFILES, []):
            item = dict(profile)
            item.setdefault("daily_briefing_enabled", False)
            # Preserve the v0.5 automatic-delivery scope until the owner
            # explicitly broadens this migrated profile in the new panel.
            item["hazard_families"] = ["severe_convection"]
            profiles.append(item)
        data = dict(entry.data)
        data[CONF_PROFILES] = profiles
        data.setdefault(CONF_BRIEFING_TIME, "07:00")
        hass.config_entries.async_update_entry(
            entry, data=data, version=1, minor_version=4
        )
    return True
