"""Small, testable configuration helpers for the HA-facing shell."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from uuid import uuid4
from .marine_preferences import MARINE_NEARBY_FIELDS, marine_nearby_preferences

from .const import (
    BRIEFING_LOCATION_HOME,
    BRIEFING_LOCATIONS,
    CONF_CONTACT,
    CONF_AUTOMATIC_NOTIFICATIONS,
    CONF_BRIEFING_ENABLED,
    CONF_BRIEFING_LOCATION,
    CONF_CRITICAL_NOTIFICATIONS,
    CONF_HAZARD_FAMILIES,
    CONF_ALERT_EVENTS,
    CONF_MARINE_WARNING_MODE,
    CONF_LEGACY_NOTIFY_SERVICE,
    CONF_MOBILE_PLATFORM,
    CONF_SHOW_LOCATION_ON_MAP,
    CONF_MONITOR_HOME,
    CONF_NOTIFY_ENTITY,
    CONF_PERSON_ENTITY,
    CONF_PROFILES,
    CONF_PROFILE_ENABLED,
    CONF_PROFILE_ID,
    CONF_PROFILE_NAME,
    CONF_RECEIVE_HOME_AWAY,
    CONF_RECEIVE_PERSONAL,
    PROTOTYPE_VERSION,
    MOBILE_PLATFORM_AUTO,
    MOBILE_PLATFORMS,
)
from .hazard_policy import ALL_HAZARD_FAMILIES, alert_choices
from .models import HouseholdProfile


def normalize_config_input(
    user_input: Mapping[str, Any], *, require_person_and_target: bool = True
) -> dict[str, Any]:
    """Normalize beginner-facing input and lock hazardous delivery off."""
    contact = str(user_input.get(CONF_CONTACT, "")).strip()
    if not contact:
        raise ValueError("A contact email address or website is required by the NWS client")
    person_entity = str(user_input.get(CONF_PERSON_ENTITY, "")).strip()
    notify_entity = str(user_input.get(CONF_NOTIFY_ENTITY, "")).strip()
    legacy_service = str(user_input.get(CONF_LEGACY_NOTIFY_SERVICE, "")).strip()
    if person_entity and not _is_single_entity(person_entity, "person"):
        raise ValueError("The protected person must be one person entity")
    if notify_entity and not _is_single_entity(notify_entity, "notify"):
        raise ValueError("The mobile target must be one notify entity")
    if legacy_service and not _is_safe_legacy_mobile_service(legacy_service):
        raise ValueError("Legacy target must be one phone-specific mobile_app notify action")
    if notify_entity and legacy_service:
        raise ValueError("Choose one mobile notification target, not both")
    if require_person_and_target and not person_entity:
        raise ValueError("Select one protected Person entity")
    if require_person_and_target and not (notify_entity or legacy_service):
        raise ValueError("Select one Companion notification target")
    return {
        CONF_CONTACT: contact,
        CONF_MONITOR_HOME: True,
        CONF_CRITICAL_NOTIFICATIONS: False,
        CONF_PERSON_ENTITY: person_entity,
        CONF_NOTIFY_ENTITY: notify_entity,
        CONF_LEGACY_NOTIFY_SERVICE: legacy_service,
    }


def build_nws_user_agent(contact: str) -> str:
    contact = contact.strip()
    if not contact:
        raise ValueError("NWS User-Agent contact cannot be empty")
    return f"HomeAssistant-WeatherIntelligence/{PROTOTYPE_VERSION} ({contact})"


def effective_entry_config(entry: Any) -> dict[str, Any]:
    """Options override migrated entry data without mutating either mapping."""
    effective = {**dict(entry.data), **dict(getattr(entry, "options", {}) or {})}
    # Retained only as a v0.4 compatibility flag. Real delivery is exclusively
    # controlled by each explicitly confirmed profile.
    effective[CONF_CRITICAL_NOTIFICATIONS] = False
    effective[CONF_MONITOR_HOME] = True
    if CONF_PROFILES not in effective:
        migrated = migrate_single_profile(effective)
        effective[CONF_PROFILES] = [profile_to_dict(migrated)] if migrated else []
    return effective


def normalize_profile_input(
    user_input: Mapping[str, Any], *, existing_id: str | None = None,
    allow_missing_target: bool = False,
) -> HouseholdProfile:
    """Validate one explicit profile; no entity or device is inferred."""
    name = str(user_input.get(CONF_PROFILE_NAME, "")).strip()
    person = str(user_input.get(CONF_PERSON_ENTITY, "")).strip()
    notify = str(user_input.get(CONF_NOTIFY_ENTITY, "")).strip()
    legacy = str(user_input.get(CONF_LEGACY_NOTIFY_SERVICE, "")).strip()
    mobile_platform = str(
        user_input.get(CONF_MOBILE_PLATFORM, MOBILE_PLATFORM_AUTO)
    ).strip().casefold()
    if not name:
        raise ValueError("Profile name is required")
    if not _is_single_entity(person, "person"):
        raise ValueError("Select exactly one Person entity")
    if not allow_missing_target and not (notify or legacy):
        raise ValueError("Select exactly one Companion notification target")
    if notify and not _is_single_entity(notify, "notify"):
        raise ValueError("The mobile target must be one notify entity")
    if legacy and not _is_safe_legacy_mobile_service(legacy):
        raise ValueError("Legacy target must be one phone-specific mobile_app action")
    if mobile_platform not in MOBILE_PLATFORMS:
        raise ValueError("Unknown mobile platform")
    automatic = bool(user_input.get(CONF_AUTOMATIC_NOTIFICATIONS, False))
    critical = bool(user_input.get(CONF_CRITICAL_NOTIFICATIONS, False))
    raw_families = user_input.get(CONF_HAZARD_FAMILIES, ALL_HAZARD_FAMILIES)
    if not isinstance(raw_families, (list, tuple, set)):
        raise ValueError("Hazard families must be a collection")
    families = tuple(dict.fromkeys(str(item) for item in raw_families))
    if any(item not in ALL_HAZARD_FAMILIES for item in families):
        raise ValueError("Unknown hazard family")
    raw_events = user_input.get(CONF_ALERT_EVENTS)
    events = None
    if raw_events is not None:
        if not isinstance(raw_events,(list,tuple,set)):
            raise ValueError("Alert choices must be a collection")
        events = tuple(dict.fromkeys(str(item).strip().casefold() for item in raw_events))
        allowed = {item["value"] for item in alert_choices()}
        if any(item not in allowed for item in events):
            raise ValueError("Unknown individual alert choice")
    if critical and not automatic:
        raise ValueError("Critical delivery requires automatic delivery")
    marine_mode = user_input.get(CONF_MARINE_WARNING_MODE, "always")
    if not isinstance(marine_mode, str) or marine_mode not in {"always", "on_water"}:
        raise ValueError("Unknown Special Marine Warning location preference")
    if critical and not legacy:
        raise ValueError(
            "Critical delivery requires the phone-specific Companion action"
        )
    device_id = user_input.get("companion_device_id", "")
    urgent_channel = user_input.get("urgent_channel", "Weather Siren")
    outlook_time = user_input.get("daily_outlook_time", "")
    rule_ids = user_input.get("dnd_rule_ids")
    life_events = user_input.get("life_safety_events", [])
    if not isinstance(life_events, (list, tuple)) or any(not isinstance(event, str) or event not in {"severe thunderstorm warning", "flash flood warning", "radar_hail"} for event in life_events):
        raise ValueError("Invalid life-safety alert scope")
    if not isinstance(device_id, str) or len(device_id) > 128:
        raise ValueError("Invalid Companion registration")
    if not isinstance(urgent_channel, str) or not urgent_channel.strip() or len(urgent_channel) > 100:
        raise ValueError("Invalid notification category")
    if not isinstance(outlook_time, str) or (outlook_time and (len(outlook_time) != 5 or
                         outlook_time[2] != ":" or not outlook_time[:2].isdigit() or
                         not outlook_time[3:].isdigit() or int(outlook_time[:2]) > 23 or int(outlook_time[3:]) > 59)):
        raise ValueError("Invalid daily outlook time")
    if rule_ids is not None:
        from .onboarding_dnd import valid_rule_ids
        if not isinstance(rule_ids, (list, tuple)) or any(not isinstance(rule_id, str) or rule_id not in valid_rule_ids() for rule_id in rule_ids):
            raise ValueError("Invalid DND alert choices")
    briefing_location = str(
        user_input.get(CONF_BRIEFING_LOCATION, BRIEFING_LOCATION_HOME)
    ).strip()
    if briefing_location not in BRIEFING_LOCATIONS:
        raise ValueError("Unknown daily briefing location")
    return HouseholdProfile(
        profile_id=existing_id or str(user_input.get(CONF_PROFILE_ID, "")).strip() or uuid4().hex,
        name=name,
        person_entity_id=person,
        notify_entity_id=notify,
        legacy_notify_service=legacy,
        mobile_platform=mobile_platform,
        show_location_on_map=_map_display_choice(user_input.get(CONF_SHOW_LOCATION_ON_MAP, "inherit")),
        enabled=bool(user_input.get(CONF_PROFILE_ENABLED, True)),
        receive_personal_alerts=bool(user_input.get(CONF_RECEIVE_PERSONAL, True)),
        receive_home_while_away=bool(user_input.get(CONF_RECEIVE_HOME_AWAY, False)),
        automatic_notifications=automatic,
        critical_notifications=critical,
        outage_dnd_enabled=user_input.get("outage_dnd_enabled") is True,
        hazard_families=families,
        alert_events=events,
        marine_warning_mode=marine_mode,
        **marine_nearby_preferences(user_input),
        daily_briefing=bool(user_input.get(CONF_BRIEFING_ENABLED, False)),
        briefing_location=briefing_location,
        companion_device_id=device_id,
        dnd_rule_ids=tuple(dict.fromkeys(rule_ids)) if rule_ids is not None else None,
        urgent_channel=urgent_channel,
        daily_outlook_time=outlook_time,
        life_safety_events=tuple(life_events),
    )


def profile_input_with_saved_choices(
    user_input: Mapping[str,Any], current: HouseholdProfile | None = None,
) -> dict[str,Any]:
    """Native HA profile forms do not overwrite the panel's finer choices."""
    value = dict(user_input)
    if current is not None:
        value.setdefault(CONF_ALERT_EVENTS,current.alert_events)
        value.setdefault(CONF_HAZARD_FAMILIES,current.hazard_families)
        value.setdefault(CONF_MARINE_WARNING_MODE,current.marine_warning_mode)
        for key in ("companion_device_id", "dnd_rule_ids", "urgent_channel", "daily_outlook_time", "life_safety_events", "outage_dnd_enabled", *MARINE_NEARBY_FIELDS):
            value.setdefault(key, getattr(current, key))
    elif CONF_ALERT_EVENTS not in value and CONF_HAZARD_FAMILIES not in value:
        value[CONF_ALERT_EVENTS] = [item["value"] for item in alert_choices() if item["default"]]
    return value


def _map_display_choice(value: Any) -> str:
    if isinstance(value, bool):
        return "show" if value else "hide"
    if not isinstance(value, str) or value not in {"inherit", "show", "hide"}:
        raise ValueError("Unknown map location display choice")
    return str(value)


def normalize_profiles(values: Sequence[Mapping[str, Any]]) -> tuple[HouseholdProfile, ...]:
    profiles = tuple(
        normalize_profile_input(value, existing_id=str(value.get(CONF_PROFILE_ID, "")).strip() or None)
        for value in values
    )
    _validate_profile_boundaries(profiles)
    names = [item.name.casefold() for item in profiles]
    if len(names) != len(set(names)):
        raise ValueError("Profile names must be unique")
    return profiles


def profiles_from_config(config: Mapping[str, Any]) -> tuple[HouseholdProfile, ...]:
    raw = config.get(CONF_PROFILES, [])
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Profiles must be a collection")
    profiles = tuple(
        normalize_profile_input(
            value,
            existing_id=str(value.get(CONF_PROFILE_ID, "")).strip() or None,
            allow_missing_target=True,
        )
        for value in raw
    )
    _validate_profile_boundaries(profiles)
    return profiles


def _validate_profile_boundaries(profiles: tuple[HouseholdProfile, ...]) -> None:
    """Multiple phones may share a person, never the same registered target."""
    grouped: dict[str, list[HouseholdProfile]] = {}
    device_ids = [profile.companion_device_id for profile in profiles if profile.companion_device_id]
    if len(device_ids) != len(set(device_ids)):
        raise ValueError("A Companion registration can belong to only one profile")
    targets: dict[str, HouseholdProfile] = {}
    for profile in profiles:
        target = profile.legacy_notify_service
        if target in targets and (profile.companion_device_id or targets[target].companion_device_id):
            raise ValueError("A phone notification target can belong to only one enrolled device profile")
        if target:
            targets[target] = profile
    for profile in profiles:
        grouped.setdefault(profile.person_entity_id, []).append(profile)
    for group in grouped.values():
        if len(group) > 1 and any(not profile.companion_device_id for profile in group):
            raise ValueError("A Person entity can belong to only one profile unless each phone has a distinct Companion registration")


def profile_to_dict(profile: HouseholdProfile) -> dict[str, Any]:
    return {
        CONF_PROFILE_ID: profile.profile_id,
        CONF_PROFILE_NAME: profile.name,
        CONF_PERSON_ENTITY: profile.person_entity_id,
        CONF_NOTIFY_ENTITY: profile.notify_entity_id,
        CONF_LEGACY_NOTIFY_SERVICE: profile.legacy_notify_service,
        CONF_MOBILE_PLATFORM: profile.mobile_platform,
        CONF_SHOW_LOCATION_ON_MAP: profile.show_location_on_map,
        CONF_PROFILE_ENABLED: profile.enabled,
        CONF_RECEIVE_PERSONAL: profile.receive_personal_alerts,
        CONF_RECEIVE_HOME_AWAY: profile.receive_home_while_away,
        CONF_AUTOMATIC_NOTIFICATIONS: profile.automatic_notifications,
        CONF_CRITICAL_NOTIFICATIONS: profile.critical_notifications,
        "outage_dnd_enabled": profile.outage_dnd_enabled,
        CONF_HAZARD_FAMILIES: list(profile.hazard_families),
        CONF_ALERT_EVENTS: list(profile.alert_events) if profile.alert_events is not None else None,
        CONF_MARINE_WARNING_MODE: profile.marine_warning_mode,
        **{key: getattr(profile, key) for key in MARINE_NEARBY_FIELDS},
        CONF_BRIEFING_ENABLED: profile.daily_briefing,
        CONF_BRIEFING_LOCATION: profile.briefing_location,
        "companion_device_id": profile.companion_device_id,
        "dnd_rule_ids": list(profile.dnd_rule_ids) if profile.dnd_rule_ids is not None else None,
        "urgent_channel": profile.urgent_channel,
        "daily_outlook_time": profile.daily_outlook_time,
        "life_safety_events": list(profile.life_safety_events),
    }


def migrate_single_profile(config: Mapping[str, Any]) -> HouseholdProfile | None:
    """Convert the v0.4 single person/target into one equivalent, safe profile."""
    person = str(config.get(CONF_PERSON_ENTITY, "")).strip()
    notify = str(config.get(CONF_NOTIFY_ENTITY, "")).strip()
    legacy = str(config.get(CONF_LEGACY_NOTIFY_SERVICE, "")).strip()
    if not person:
        return None
    return normalize_profile_input(
        {
            CONF_PROFILE_NAME: "Primary profile",
            CONF_PERSON_ENTITY: person,
            CONF_NOTIFY_ENTITY: notify,
            CONF_LEGACY_NOTIFY_SERVICE: legacy,
            CONF_PROFILE_ENABLED: True,
            CONF_RECEIVE_PERSONAL: True,
            CONF_RECEIVE_HOME_AWAY: False,
            CONF_AUTOMATIC_NOTIFICATIONS: False,
            CONF_CRITICAL_NOTIFICATIONS: False,
        },
        allow_missing_target=True,
    )


def has_mobile_test_target(config: Mapping[str, Any]) -> bool:
    profiles = profiles_from_config(config)
    if profiles:
        return any(
            item.enabled and bool(item.notify_entity_id or item.legacy_notify_service)
            for item in profiles
        )
    notify_entity = str(config.get(CONF_NOTIFY_ENTITY, "")).strip()
    legacy_service = str(config.get(CONF_LEGACY_NOTIFY_SERVICE, "")).strip()
    return (
        bool(notify_entity) != bool(legacy_service)
        and (
            _is_single_entity(notify_entity, "notify")
            if notify_entity
            else _is_safe_legacy_mobile_service(legacy_service)
        )
    )


def _is_single_entity(value: str, domain: str) -> bool:
    return value.startswith(f"{domain}.") and "," not in value and " " not in value


def _is_safe_legacy_mobile_service(value: str) -> bool:
    return (
        value.startswith("notify.mobile_app_")
        and "," not in value
        and " " not in value
        and value.count(".") == 1
    )
