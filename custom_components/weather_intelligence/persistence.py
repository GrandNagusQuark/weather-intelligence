"""Versioned JSON-safe persistence for incident and delivery continuity."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping

from .models import (
    BriefingDeliveryRecord,
    DeliveryOperation,
    DeliveryPriority,
    IncidentPhase,
    IncidentRecord,
    NotificationPayload,
    OfficialAlert,
    ProfileDeliveryRecord,
    SubjectKind,
)

HA_STORE_VERSION = 1
STORAGE_VERSION = 4
PROFILE_REFERENCE_KEY = "profile_references"
PROFILE_REFERENCE_INTERVAL = timedelta(minutes=1)
_LOGGER = logging.getLogger(__name__)


def _profile_reference(hass: Any, entry: Any) -> dict:
    """Keep preference fingerprints and verified ownership, not location history."""
    from .config import effective_entry_config, profiles_from_config, profile_to_dict
    from .onboarding_accounts import account_devices
    from .onboarding_preferences import profile_matches_device

    result = {}
    # Legacy entries may have a Person but no enrolled phone yet. Read them with
    # the same migration policy as the runtime; recording continuity is not a save.
    for profile in profiles_from_config(effective_entry_config(entry)):
        person = hass.states.get(profile.person_entity_id)
        owner_id = person.attributes.get("user_id") if person else None
        devices = []
        if owner_id:
            allowed = {device["id"] for device in account_devices(hass, owner_id)}
            devices = [
                device.entry_id
                for device in hass.config_entries.async_entries("mobile_app")
                if device.entry_id in allowed and profile_matches_device(hass, profile, device)
            ]
        preferences = profile_to_dict(profile)
        for field in ("hazard_families", "alert_events", "dnd_rule_ids", "life_safety_events"):
            if isinstance(preferences.get(field), list):
                preferences[field] = sorted(preferences[field])
        serialized = json.dumps(preferences, sort_keys=True, separators=(",", ":"))
        result[profile.profile_id] = {
            "fingerprint": sha256(serialized.encode()).hexdigest(),
            "owner_id": owner_id,
            "device_ids": sorted(devices),
        }
    return result


class ProfileReference:
    """Reconcile profile continuity with the last successfully recorded state."""

    def __init__(self, hass: Any, entry: Any, store: Any) -> None:
        self.hass, self.entry, self.store = hass, entry, store
        self.previous: dict | None = None
        self.loaded = False

    async def async_load(self) -> None:
        stored = await self.store.async_load()
        if stored is not None and (
            not isinstance(stored, dict) or not isinstance(stored.get("profiles"), dict)
        ):
            raise StoredStateError("Stored profile reference is not an object")
        self.previous = stored.get("profiles") if stored is not None else None
        self.loaded = True

    async def async_record(self) -> None:
        current = _profile_reference(self.hass, self.entry)
        await self.store.async_save({"profiles": current})
        self.previous = current

    async def async_reconcile(self) -> None:
        from .admin_actions import ADMIN_ACTION_NOTICES, queued_admin_notices
        from .config import effective_entry_config

        if not self.loaded:
            await self.async_load()
        current = _profile_reference(self.hass, self.entry)
        if self.previous is None:
            await self.async_record()
            return
        recipients: dict[str, set[str]] = {}
        changes = []
        for profile_id in self.previous.keys() | current.keys():
            before, after = self.previous.get(profile_id), current.get(profile_id)
            if before and after and before["fingerprint"] == after["fingerprint"]:
                if not after["owner_id"] and before["owner_id"]:
                    # A temporarily unavailable Person is not an ownership edit.
                    after["owner_id"] = before["owner_id"]
                if not before["owner_id"] or before["owner_id"] == after["owner_id"]:
                    after["device_ids"] = sorted(
                        set(before["device_ids"]) | set(after["device_ids"])
                    )
                    continue
            # Target registration availability can change without a preference edit.
            if (
                before
                and after
                and (before["fingerprint"], before["owner_id"])
                == (after["fingerprint"], after["owner_id"])
            ):
                continue
            changes.append([profile_id, before, after])
            for record in (before, after):
                if record and record.get("owner_id"):
                    recipients.setdefault(record["owner_id"], set()).update(
                        record.get("device_ids", [])
                    )
        # Persist the notice first. Stable ids prevent duplicate sends if reference
        # storage fails after queuing it and reconciliation runs again.
        config = effective_entry_config(self.entry)
        queued = config.get(ADMIN_ACTION_NOTICES, {})
        notices = {}
        signature = sha256(
            json.dumps(sorted(changes, key=lambda item: item[0]), sort_keys=True).encode()
        ).hexdigest()
        for owner_id, device_ids in recipients.items():
            notice_id = sha256((owner_id + signature).encode()).hexdigest()
            if queued.get(owner_id, {}).get("id") != notice_id:
                notices[owner_id] = {
                    "id": notice_id,
                    "kind": "settings_changed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "device_ids": sorted(device_ids),
                    "attempts": {},
                }
        if notices:
            self.hass.config_entries.async_update_entry(
                self.entry,
                options={
                    **self.entry.options,
                    ADMIN_ACTION_NOTICES: queued_admin_notices(config, notices),
                },
            )
        if current != self.previous:
            await self.store.async_save({"profiles": current})
            self.previous = deepcopy(current)


def _entry_profile_reference(hass: Any, entry: Any) -> ProfileReference | None:
    from .const import DOMAIN

    return (
        hass.data.get(DOMAIN, {})
        .get(PROFILE_REFERENCE_KEY, {})
        .get(getattr(entry, "entry_id", None))
    )


async def async_reconcile_profile_reference(hass: Any, entry: Any) -> None:
    """Called while holding the same lock as authenticated preference saves."""
    reference = _entry_profile_reference(hass, entry)
    if reference is not None:
        await reference.async_reconcile()


async def async_record_profile_reference(hass: Any, entry: Any) -> None:
    reference = _entry_profile_reference(hass, entry)
    if reference is not None:
        await reference.async_record()


async def async_start_profile_reference(hass: Any, entry: Any, store: Any) -> None:
    from homeassistant.helpers.event import async_track_time_interval

    from .admin_actions import async_deliver_admin_notices
    from .const import DOMAIN
    from .onboarding_notifications import progress_lock

    reference = ProfileReference(hass, entry, store)
    references = hass.data.setdefault(DOMAIN, {}).setdefault(PROFILE_REFERENCE_KEY, {})
    references[entry.entry_id] = reference
    try:
        await reference.async_load()
    except Exception:
        _LOGGER.warning("Profile continuity could not be loaded; it will be retried")

    async def reconcile(_now: Any = None) -> None:
        if not hass.is_running:
            return
        try:
            async with progress_lock(hass, entry):
                await reference.async_reconcile()
                await async_deliver_admin_notices(hass, entry)
        except Exception:
            _LOGGER.warning("Profile continuity could not be checked; it will be retried")

    # Account/Person ownership and Companion registration must be loaded first.
    if hass.is_running:
        await reconcile()
    else:
        entry.async_on_unload(hass.bus.async_listen_once("homeassistant_started", reconcile))
    entry.async_on_unload(async_track_time_interval(hass, reconcile, PROFILE_REFERENCE_INTERVAL))

    def remove_cached_reference() -> None:
        references.pop(entry.entry_id, None)

    entry.async_on_unload(remove_cached_reference)


class StoredStateError(ValueError):
    """Raised when persisted state cannot be safely restored."""


def serialize_runtime_state(
    incidents: tuple[IncidentRecord, ...],
    notifications: tuple[NotificationPayload, ...],
    profile_deliveries: tuple[ProfileDeliveryRecord, ...] = (),
    briefing_deliveries: tuple[BriefingDeliveryRecord, ...] = (),
) -> dict[str, Any]:
    return {
        "schema_version": STORAGE_VERSION,
        "incidents": [_serialize_incident(item) for item in incidents],
        "notifications": [_serialize_notification(item) for item in notifications],
        "profile_deliveries": [_serialize_profile_delivery(item) for item in profile_deliveries],
        "briefing_deliveries": [
            {
                "profile_id": item.profile_id,
                "local_date": item.local_date,
                "content_fingerprint": item.content_fingerprint,
                "urgency": item.urgency,
                "delivered_at": _iso(item.delivered_at),
                "pending": item.pending,
                "last_attempt_at": _iso(item.last_attempt_at),
            }
            for item in briefing_deliveries
        ],
    }


def deserialize_runtime_state(
    document: Mapping[str, Any] | None,
) -> tuple[list[IncidentRecord], list[NotificationPayload]]:
    if document is None:
        return [], []
    if not isinstance(document, Mapping):
        raise StoredStateError("Weather-intelligence stored state is not an object")
    if document.get("schema_version") not in {1, 2, 3, STORAGE_VERSION}:
        raise StoredStateError("Unsupported weather-intelligence stored-state version")
    try:
        incidents = [_deserialize_incident(item) for item in document.get("incidents", [])]
        notifications = [
            _deserialize_notification(item) for item in document.get("notifications", [])
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise StoredStateError("Weather-intelligence stored state is invalid") from error
    return incidents, notifications


def deserialize_full_runtime_state(
    document: Mapping[str, Any] | None,
) -> tuple[list[IncidentRecord], list[NotificationPayload], list[ProfileDeliveryRecord]]:
    incidents, notifications = deserialize_runtime_state(document)
    if document is None or document.get("schema_version") == 1:
        return incidents, notifications, []
    try:
        deliveries = [
            _deserialize_profile_delivery(item) for item in document.get("profile_deliveries", [])
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise StoredStateError("Weather-intelligence profile delivery state is invalid") from error
    return incidents, notifications, deliveries


def deserialize_briefing_delivery_state(
    document: Mapping[str, Any] | None,
) -> list[BriefingDeliveryRecord]:
    """Read v0.6 briefing state while accepting all earlier documents."""
    if document is None or document.get("schema_version") in {1, 2}:
        return []
    if document.get("schema_version") not in {3, STORAGE_VERSION}:
        raise StoredStateError("Unsupported weather-intelligence stored-state version")
    try:
        return [
            BriefingDeliveryRecord(
                profile_id=str(item["profile_id"]),
                local_date=str(item["local_date"]),
                content_fingerprint=str(item["content_fingerprint"]),
                urgency=int(item["urgency"]),
                delivered_at=_datetime(item.get("delivered_at")),
                pending=bool(item.get("pending", False)),
                last_attempt_at=_datetime(item.get("last_attempt_at")),
            )
            for item in document.get("briefing_deliveries", [])
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise StoredStateError("Weather-intelligence briefing delivery state is invalid") from error


def _serialize_profile_delivery(item: ProfileDeliveryRecord) -> dict[str, Any]:
    return {
        "profile_id": item.profile_id,
        "incident_key": item.incident_key,
        "content_fingerprint": item.content_fingerprint,
        "stable_tag": item.stable_tag,
        "resolved": item.resolved,
        "clear_at": _iso(item.clear_at),
        "cleared": item.cleared,
        "severity_rank": item.severity_rank,
    }


def _deserialize_profile_delivery(value: Mapping[str, Any]) -> ProfileDeliveryRecord:
    return ProfileDeliveryRecord(
        profile_id=str(value["profile_id"]),
        incident_key=str(value["incident_key"]),
        content_fingerprint=str(value["content_fingerprint"]),
        stable_tag=str(value["stable_tag"]),
        resolved=bool(value.get("resolved", False)),
        clear_at=_datetime(value.get("clear_at")),
        cleared=bool(value.get("cleared", False)),
        severity_rank=(
            int(value["severity_rank"]) if value.get("severity_rank") is not None else None
        ),
    )


def _serialize_incident(item: IncidentRecord) -> dict[str, Any]:
    return {
        "incident_key": item.incident_key,
        "phase": item.phase.value,
        "latest_alert": _serialize_alert(item.latest_alert),
        "seen_message_ids": sorted(item.seen_message_ids),
        "content_fingerprint": item.content_fingerprint,
        "revision": item.revision,
    }


def _deserialize_incident(value: Mapping[str, Any]) -> IncidentRecord:
    return IncidentRecord(
        incident_key=str(value["incident_key"]),
        phase=IncidentPhase(value["phase"]),
        latest_alert=_deserialize_alert(value["latest_alert"]),
        seen_message_ids={str(item) for item in value["seen_message_ids"]},
        content_fingerprint=str(value["content_fingerprint"]),
        revision=int(value["revision"]),
    )


def _serialize_alert(item: OfficialAlert) -> dict[str, Any]:
    return {
        "source": item.source,
        "official_message_id": item.official_message_id,
        "incident_key": item.incident_key,
        "sender": item.sender,
        "event": item.event,
        "message_type": item.message_type,
        "status": item.status,
        "category": item.category,
        "sent_at": _iso(item.sent_at),
        "effective_at": _iso(item.effective_at),
        "onset_at": _iso(item.onset_at),
        "expires_at": _iso(item.expires_at),
        "ends_at": _iso(item.ends_at),
        "severity": item.severity,
        "urgency": item.urgency,
        "certainty": item.certainty,
        "headline": item.headline,
        "description": item.description,
        "instruction": item.instruction,
        "area_description": item.area_description,
        "geometry": item.geometry,
        "affected_zones": list(item.affected_zones),
        "tornado_detection": item.tornado_detection,
        "tornado_damage_threat": item.tornado_damage_threat,
        "thunderstorm_damage_threat": item.thunderstorm_damage_threat,
        "flash_flood_damage_threat": item.flash_flood_damage_threat,
        "vtec_action": item.vtec_action,
        "replaced_message_ids": list(item.replaced_message_ids),
        "received_at": _iso(item.received_at),
        "raw_official_payload": item.raw_official_payload,
    }


def _deserialize_alert(value: Mapping[str, Any]) -> OfficialAlert:
    return OfficialAlert(
        source=str(value["source"]),
        official_message_id=str(value["official_message_id"]),
        incident_key=str(value["incident_key"]),
        sender=_optional_string(value.get("sender")),
        event=str(value["event"]),
        message_type=str(value["message_type"]),
        status=str(value["status"]),
        category=_optional_string(value.get("category")),
        sent_at=_datetime(value.get("sent_at")),
        effective_at=_datetime(value.get("effective_at")),
        onset_at=_datetime(value.get("onset_at")),
        expires_at=_datetime(value.get("expires_at")),
        ends_at=_datetime(value.get("ends_at")),
        severity=_optional_string(value.get("severity")),
        urgency=_optional_string(value.get("urgency")),
        certainty=_optional_string(value.get("certainty")),
        headline=_optional_string(value.get("headline")),
        description=_optional_string(value.get("description")),
        instruction=_optional_string(value.get("instruction")),
        area_description=_optional_string(value.get("area_description")),
        geometry=value.get("geometry") if isinstance(value.get("geometry"), Mapping) else None,
        affected_zones=tuple(str(item) for item in value.get("affected_zones", [])),
        tornado_detection=_optional_string(value.get("tornado_detection")),
        tornado_damage_threat=_optional_string(value.get("tornado_damage_threat")),
        thunderstorm_damage_threat=_optional_string(value.get("thunderstorm_damage_threat")),
        flash_flood_damage_threat=_optional_string(value.get("flash_flood_damage_threat")),
        vtec_action=_optional_string(value.get("vtec_action")),
        replaced_message_ids=tuple(str(item) for item in value.get("replaced_message_ids", [])),
        received_at=_required_datetime(value["received_at"]),
        raw_official_payload=_required_mapping(value["raw_official_payload"]),
    )


def _serialize_notification(item: NotificationPayload) -> dict[str, Any]:
    return {
        "operation": item.operation.value,
        "stable_tag": item.stable_tag,
        "title": item.title,
        "message": item.message,
        "priority": item.priority.value,
        "incident_key": item.incident_key,
        "subject_id": item.subject_id,
        "subject_kind": item.subject_kind.value,
        "resolved": item.resolved,
        "location_is_last_known": item.location_is_last_known,
    }


def _deserialize_notification(value: Mapping[str, Any]) -> NotificationPayload:
    return NotificationPayload(
        operation=DeliveryOperation(value["operation"]),
        stable_tag=str(value["stable_tag"]),
        title=str(value["title"]),
        message=str(value["message"]),
        priority=DeliveryPriority(value["priority"]),
        incident_key=str(value["incident_key"]),
        subject_id=str(value["subject_id"]),
        subject_kind=SubjectKind(value["subject_kind"]),
        resolved=bool(value.get("resolved", False)),
        # Earlier stored decisions already had this qualifier in their title.
        # Preserve it on migration until a fresh core decision replaces it.
        location_is_last_known=(value.get("location_is_last_known") is True
            or ("location_is_last_known" not in value
                and "at your last known location" in str(value.get("title", "")).casefold())),
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _required_datetime(value: Any) -> datetime:
    result = _datetime(value)
    if result is None:
        raise ValueError("Required stored timestamp is missing")
    return result


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _required_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("Stored official payload is not an object")
    return value
