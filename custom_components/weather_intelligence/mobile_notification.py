"""Manual-only, exactly-one-target Companion notification delivery."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Mapping

from .const import (
    ALL_CLEAR_RETENTION,
    ANDROID_SETUP_CHANNEL,
    android_siren_channel,
    CONF_LEGACY_NOTIFY_SERVICE,
    CONF_NOTIFY_ENTITY,
    DOMAIN,
    MOBILE_PLATFORM_ANDROID,
    MOBILE_PLATFORM_AUTO,
    MOBILE_PLATFORM_IOS,
    SAFE_MOBILE_TEST_MESSAGE,
    SAFE_MOBILE_TEST_TITLE,
    WEATHER_NOTIFICATION_ICON,
)
from .hazard_policy import DeliveryBehavior
from .models import HouseholdProfile
from .reporting_device import mobile_report_context


_LOGGER = logging.getLogger(__name__)
_CRITICAL_AUDIO_TASKS = "critical_audio_tasks"
_CRITICAL_REPEAT_COUNT = 3
_TONE_LEAD_SECONDS = 2.5
_MIN_SPEECH_SECONDS = 5.0
_MAX_SPEECH_SECONDS = 18.0
_IOS_SETUP_TITLE = "Finish spoken weather-alert setup"
_IOS_SETUP_MESSAGE = (
    "Tap to enable Siri announcements for Home Assistant, then run a safe test."
)
_IOS_TEST_TITLE = "TEST ONLY — Spoken weather alert"
_IOS_TEST_MESSAGE = (
    "TEST ONLY. Tornado warning. Take shelter now. This is only a test."
)
_ANDROID_SETUP_TITLE = "Finish weather-alert sound setup"
_ANDROID_SETUP_MESSAGE = (
    "Tap to choose the Weather Siren sound and run a safe tone-and-speech test."
)
_ANDROID_TEST_TITLE = "TEST ONLY — Weather critical alert"
_ANDROID_TEST_MESSAGE = (
    "TEST ONLY. Tornado warning. Take shelter now. This is only a test."
)


class MobileTargetError(ValueError):
    def __init__(self, message: str, *, retry_safe: bool = True) -> None:
        super().__init__(message)
        self.retry_safe = retry_safe


async def async_send_onboarding_notification(hass: Any, profile: HouseholdProfile, *, kind: str, returning: bool = False, setup_channel: str = "") -> str:
    """One exact registered phone; never enroll or start repeating alert audio."""
    if kind == "prepare":
        # Android callers must ask explicitly: a restored channel retains sound
        # settings. Never generate a fresh category to pretend this is silent.
        channel = android_siren_channel(profile.urgent_channel) if profile.mobile_platform == MOBILE_PLATFORM_ANDROID else ANDROID_SETUP_CHANNEL
        return await _async_send_to_target(hass, notify_entity="", legacy_action=profile.legacy_notify_service,
            title="SETUP ONLY — Weather Intelligence",
            message="Notification setup is ready. Return to Weather Intelligence to choose your phone settings.",
            companion_data={"channel": channel, "importance": "high" if profile.mobile_platform == MOBILE_PLATFORM_ANDROID else "low", "vibrationPattern": "", "tag": "wi_setup_" + profile.profile_id,
                "ttl": 0, "priority": "high", "push": {"interruption-level": "passive", "sound": "none"}})
    if kind == "critical" and profile.mobile_platform == "android":
        return await async_send_android_tone_speech_test(hass, profile)
    if kind == "critical" and profile.mobile_platform == "ios":
        return await async_send_ios_spoken_alert_test(hass, profile)
    if kind != "normal":
        raise MobileTargetError("Unknown notification setup test")
    return await _async_send_to_target(hass, notify_entity="", legacy_action=profile.legacy_notify_service,
        title="TEST ONLY — Weather Intelligence", message="This is a notification setup test. No weather emergency is being reported.",
        companion_data={"channel": "Weather Alerts", "importance": "high", "tag": "wi_test_" + profile.profile_id,
            "ttl": 0, "priority": "high", "push": {"interruption-level": "active", "sound": "default"}})


async def async_send_ios_setup_handoff(
    hass: Any, profile: HouseholdProfile, *, setup_url: str
) -> str:
    """Send one user-requested setup link to exactly one configured iPhone."""
    _validate_ios_setup_profile(profile)
    if not setup_url.startswith("/weather-intelligence"):
        raise MobileTargetError("The iPhone setup link is invalid")
    return await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title=_IOS_SETUP_TITLE,
        message=_IOS_SETUP_MESSAGE,
        companion_data={
            "url": setup_url,
            "clickAction": setup_url,
            "push": {"interruption-level": "active", "sound": "default"},
        },
    )


async def async_send_ios_spoken_alert_test(
    hass: Any, profile: HouseholdProfile
) -> str:
    """Send one unmistakable, manually requested iPhone critical-alert test."""
    _validate_ios_setup_profile(profile)
    return await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title=_IOS_TEST_TITLE,
        message=_IOS_TEST_MESSAGE,
        companion_data={
            "tag": f"weather_intelligence_ios_setup_{profile.profile_id}",
            "ttl": 0,
            "priority": "high",
            "push": {
                "interruption-level": "critical",
                "sound": {
                    "name": "default",
                    "critical": 1,
                    "volume": 1.0,
                },
            },
        },
    )


def _validate_ios_setup_profile(profile: HouseholdProfile) -> None:
    if not profile.enabled:
        raise MobileTargetError("This profile is disabled")
    if profile.mobile_platform != MOBILE_PLATFORM_IOS:
        raise MobileTargetError("Choose iPhone as this profile's mobile platform first")
    if not profile.legacy_notify_service:
        raise MobileTargetError(
            "iPhone setup requires the phone-specific Companion action"
        )


async def async_send_android_setup_handoff(
    hass: Any, profile: HouseholdProfile, *, setup_url: str
) -> str:
    """Send one user-requested setup link to exactly one configured Android phone."""
    _validate_android_setup_profile(profile)
    if not setup_url.startswith("/weather-intelligence"):
        raise MobileTargetError("The Android setup link is invalid")
    return await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title=_ANDROID_SETUP_TITLE,
        message=_ANDROID_SETUP_MESSAGE,
        companion_data={
            "url": setup_url,
            "clickAction": setup_url,
            "ttl": 0,
            "priority": "high",
            "channel": ANDROID_SETUP_CHANNEL,
        },
    )


async def async_send_android_silent_setup(hass: Any, profile: HouseholdProfile) -> str:
    """Create one explicitly requested siren category; its saved sound may play."""
    _validate_android_setup_profile(profile)
    return await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title="SETUP ONLY — Weather Siren",
        message=("Open this notification's settings, choose alarm_stream, select Alert "
                 "and your sound. Popup and lock-screen content are optional."),
        companion_data={
            "channel": android_siren_channel(profile.urgent_channel),
            "importance": "high",
            "ttl": 0,
            "priority": "high",
            "tag": f"weather_intelligence_siren_setup_{profile.profile_id}",
            "timeout": 300,
        },
    )


async def async_send_android_tone_speech_test(
    hass: Any, profile: HouseholdProfile
) -> str:
    """Send one unmistakable Android tone-then-speech setup test."""
    _validate_android_setup_profile(profile)
    path = await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title=_ANDROID_TEST_TITLE,
        message=_ANDROID_TEST_MESSAGE,
        companion_data={
            "tag": f"weather_intelligence_android_setup_{profile.profile_id}",
            "ttl": 0,
            "priority": "high",
            "channel": android_siren_channel(profile.urgent_channel),
            "importance": "max",
            "vibrationPattern": "100,1000,500,1000",
        },
    )
    await asyncio.sleep(_TONE_LEAD_SECONDS)
    await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title=_ANDROID_TEST_TITLE,
        message="TTS",
        companion_data={
            "ttl": 0,
            "priority": "high",
            "media_stream": "alarm_stream_max",
            "tts_text": _ANDROID_TEST_MESSAGE,
        },
    )
    return path


def _validate_android_setup_profile(profile: HouseholdProfile) -> None:
    if not profile.enabled:
        raise MobileTargetError("This profile is disabled")
    if profile.mobile_platform != MOBILE_PLATFORM_ANDROID:
        raise MobileTargetError("Choose Android as this profile's mobile platform first")
    if not profile.legacy_notify_service:
        raise MobileTargetError(
            "Android sound setup requires the phone-specific Companion action"
        )


async def async_send_profile_notification(
    hass: Any,
    profile: HouseholdProfile,
    *,
    title: str,
    message: str,
    stable_tag: str,
    critical: bool,
    behavior: DeliveryBehavior = DeliveryBehavior.NOTICE,
    resolved: bool = False,
    timeout_seconds: int | None = None,
    channel: str | None = None,
    soft_critical: bool = False,
    actions: list[dict[str, str]] | None = None,
    request_confirmation: bool = False,
    delivery_ttl_seconds: int | None = None,
    delivery_expiration: int | None = None,
) -> str:
    """Send one guarded official message to exactly one profile target."""
    if not profile.enabled or not profile.automatic_notifications:
        raise MobileTargetError("Automatic delivery is disabled for this profile")
    platform = _profile_mobile_platform(hass, profile)
    companion_data: dict[str, Any] = {
        "tag": stable_tag,
        "notification_icon": WEATHER_NOTIFICATION_ICON,
    }
    if actions and not resolved:
        companion_data["actions"] = actions
    if timeout_seconds is not None:
        companion_data["timeout"] = max(1, int(timeout_seconds))
    if critical:
        # Documented iOS and Android Companion fields coexist safely: each app
        # ignores fields belonging to the other platform.
        companion_data.update(
            {
                "ttl": 0,
                "priority": "high",
                "channel": android_siren_channel(profile.urgent_channel) if platform == MOBILE_PLATFORM_ANDROID else profile.urgent_channel,
                "importance": "max",
                "alert_once": soft_critical,
                "push": {
                    "interruption-level": "critical",
                    "sound": {
                        "name": "default",
                        "critical": 1,
                        "volume": 0.35 if soft_critical else 1.0,
                    }
                },
            }
        )
    elif resolved:
        companion_data.update({
            "channel": "Weather All Clear",
            "importance": "low",
            "alert_once": True,
            "timeout": int(ALL_CLEAR_RETENTION.total_seconds()),
            "push": {"interruption-level": "passive"},
        })
    elif behavior == DeliveryBehavior.IMPORTANT:
        companion_data.update({
            "ttl": 0,
            "priority": "high",
            "channel": "Weather Alerts",
            "importance": "high",
            "alert_once": True,
            "push": {"sound": "default", "interruption-level": "active"},
        })
    elif behavior in {DeliveryBehavior.NOTICE, DeliveryBehavior.AWARENESS}:
        companion_data.update({
            "channel": "Weather Awareness",
            "importance": "low",
            "alert_once": True,
            "push": {"interruption-level": "passive"},
        })
    elif behavior == DeliveryBehavior.BRIEFING_ONLY:
        companion_data.update({
            "channel": "Weather Briefing",
            "importance": "low",
            "alert_once": True,
            "push": {"interruption-level": "passive"},
        })
    if channel and not critical:
        companion_data["channel"] = channel
    if request_confirmation:
        companion_data["confirmation"] = True
    if delivery_ttl_seconds is not None:
        companion_data["ttl"] = max(0, int(delivery_ttl_seconds))
        companion_data["priority"] = "high"
    if delivery_expiration is not None:
        companion_data["apns_headers"] = {"apns-expiration": str(delivery_expiration)}
    delivery_path = await _async_send_to_target(
        hass,
        notify_entity=profile.notify_entity_id,
        legacy_action=profile.legacy_notify_service,
        title=title,
        message=message,
        companion_data=companion_data,
    )
    if critical and not soft_critical and platform in {
        MOBILE_PLATFORM_ANDROID,
        MOBILE_PLATFORM_IOS,
    }:
        _schedule_life_safety_sequence(
            hass,
            profile,
            platform=platform,
            title=title,
            message=message,
            stable_tag=stable_tag,
            companion_data=companion_data,
        )
    else:
        _cancel_life_safety_sequence(hass, profile, stable_tag)
    return delivery_path


def _schedule_life_safety_sequence(
    hass: Any,
    profile: HouseholdProfile,
    *,
    platform: str,
    title: str,
    message: str,
    stable_tag: str,
    companion_data: Mapping[str, Any],
) -> None:
    """Repeat the platform-appropriate life-safety pattern in the background."""
    data = getattr(hass, "data", None)
    if data is None:
        return
    tasks = data.setdefault(DOMAIN, {}).setdefault(_CRITICAL_AUDIO_TASKS, {})
    key = (profile.profile_id, stable_tag)
    prior = tasks.pop(key, None)
    if prior is not None and not prior.done():
        prior.cancel()
    if platform == MOBILE_PLATFORM_ANDROID:
        coro = _async_android_life_safety_sequence(
            hass,
            profile,
            title=title,
            message=message,
            companion_data=companion_data,
        )
    else:
        coro = _async_ios_life_safety_sequence(
            hass,
            profile,
            title=title,
            message=message,
            companion_data=companion_data,
        )
    create_task = getattr(hass, "async_create_task", None)
    task = (
        create_task(coro, f"{DOMAIN} life-safety audio")
        if create_task is not None
        else asyncio.create_task(coro)
    )
    tasks[key] = task

    def _remove(completed: asyncio.Task[Any]) -> None:
        if tasks.get(key) is completed:
            tasks.pop(key, None)

    task.add_done_callback(_remove)


def _cancel_life_safety_sequence(
    hass: Any, profile: HouseholdProfile, stable_tag: str
) -> None:
    data = getattr(hass, "data", None)
    if not isinstance(data, dict):
        return
    tasks = data.get(DOMAIN, {}).get(_CRITICAL_AUDIO_TASKS, {})
    task = tasks.pop((profile.profile_id, stable_tag), None)
    if task is not None and not task.done():
        task.cancel()


def cancel_profile_audio(hass: Any, profile_id: str, stable_tag: str | None = None) -> None:
    """Stop remaining repeats after acknowledgement or integration unload."""
    tasks = getattr(hass, "data", {}).get(DOMAIN, {}).get(_CRITICAL_AUDIO_TASKS, {})
    for key, task in tuple(tasks.items()):
        if key[0] == profile_id and (stable_tag is None or key[1] == stable_tag):
            tasks.pop(key, None)
            if not task.done():
                task.cancel()


async def _async_android_life_safety_sequence(
    hass: Any,
    profile: HouseholdProfile,
    *,
    title: str,
    message: str,
    companion_data: Mapping[str, Any],
) -> None:
    """Complete the Android tone/speech pattern after the first tone was sent."""
    try:
        for cycle in range(_CRITICAL_REPEAT_COUNT):
            if cycle:
                await _async_send_to_target(
                    hass,
                    notify_entity=profile.notify_entity_id,
                    legacy_action=profile.legacy_notify_service,
                    title=title,
                    message=message,
                    companion_data=companion_data,
                )
            await asyncio.sleep(_TONE_LEAD_SECONDS)
            await _async_send_to_target(
                hass,
                notify_entity=profile.notify_entity_id,
                legacy_action=profile.legacy_notify_service,
                title=title,
                message="TTS",
                companion_data={
                    "ttl": 0,
                    "priority": "high",
                    "media_stream": "alarm_stream_max",
                    "tts_text": message,
                },
            )
            if cycle + 1 < _CRITICAL_REPEAT_COUNT:
                await asyncio.sleep(_speech_playback_seconds(message))
    except asyncio.CancelledError:
        raise
    except MobileTargetError as error:
        _LOGGER.error("Android life-safety audio sequence failed: %s", error,
            extra={"wi_mobile_context": mobile_report_context(hass, profile.companion_device_id)})


async def _async_ios_life_safety_sequence(
    hass: Any,
    profile: HouseholdProfile,
    *,
    title: str,
    message: str,
    companion_data: Mapping[str, Any],
) -> None:
    """Repeat the critical alert; Siri announces each cycle when the user enables it."""
    try:
        for _cycle in range(1, _CRITICAL_REPEAT_COUNT):
            await asyncio.sleep(_speech_playback_seconds(message) + _TONE_LEAD_SECONDS)
            await _async_send_to_target(
                hass,
                notify_entity=profile.notify_entity_id,
                legacy_action=profile.legacy_notify_service,
                title=title,
                message=message,
                companion_data=companion_data,
            )
    except asyncio.CancelledError:
        raise
    except MobileTargetError as error:
        _LOGGER.error("iPhone life-safety alert sequence failed: %s", error,
            extra={"wi_mobile_context": mobile_report_context(hass, profile.companion_device_id)})


def _speech_playback_seconds(message: str) -> float:
    """Leave enough time for Android TTS before starting the next tone."""
    estimated = len(message.split()) / 2.3 + 1.5
    return min(_MAX_SPEECH_SECONDS, max(_MIN_SPEECH_SECONDS, estimated))


def _profile_mobile_platform(hass: Any, profile: HouseholdProfile) -> str:
    """Use the explicit choice, then cautiously infer an existing mobile_app entry."""
    configured = profile.mobile_platform
    if configured in {MOBILE_PLATFORM_ANDROID, MOBILE_PLATFORM_IOS}:
        return configured
    if configured != MOBILE_PLATFORM_AUTO:
        return MOBILE_PLATFORM_AUTO
    config_entries = getattr(hass, "config_entries", None)
    async_entries = getattr(config_entries, "async_entries", None)
    if async_entries is None:
        return MOBILE_PLATFORM_AUTO
    service = profile.legacy_notify_service.removeprefix("notify.mobile_app_")
    if not service:
        return MOBILE_PLATFORM_AUTO
    for entry in async_entries("mobile_app"):
        entry_data = dict(getattr(entry, "data", {}) or {})
        names = (
            getattr(entry, "title", ""),
            entry_data.get("device_name", ""),
        )
        if service not in {_slug_device_name(str(name)) for name in names if name}:
            continue
        os_name = str(entry_data.get("os_name", "")).casefold()
        manufacturer = str(entry_data.get("manufacturer", "")).casefold()
        if "android" in os_name:
            return MOBILE_PLATFORM_ANDROID
        if "ios" in os_name or "iphone" in os_name or manufacturer == "apple":
            return MOBILE_PLATFORM_IOS
    return MOBILE_PLATFORM_AUTO


def _slug_device_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


async def async_clear_profile_notification(
    hass: Any, profile: HouseholdProfile, *, stable_tag: str
) -> str:
    """Clear one tagged Companion notification without creating a new notice."""
    cancel_profile_audio(hass, profile.profile_id, stable_tag)
    legacy_action = profile.legacy_notify_service
    if (
        not legacy_action.startswith("notify.mobile_app_")
        or legacy_action.count(".") != 1
        or not hass.services.has_service(*legacy_action.split(".", 1))
    ):
        raise MobileTargetError(
            "Clearing a notification requires the phone-specific Companion action"
        )
    domain, service = legacy_action.split(".", 1)
    try:
        await hass.services.async_call(
            domain,
            service,
            {"message": "clear_notification", "data": {"tag": stable_tag}},
            blocking=True,
        )
    except Exception as error:
        raise MobileTargetError(
            "The configured Companion action could not clear the notification"
        ) from error
    return "legacy_mobile_action"


async def async_send_safe_mobile_test(hass: Any, config: Mapping[str, Any]) -> str:
    """Send the fixed test text to one configured target and nowhere else."""
    return await async_send_manual_test_message(
        hass,
        config,
        title=SAFE_MOBILE_TEST_TITLE,
        message=SAFE_MOBILE_TEST_MESSAGE,
    )


async def async_send_manual_test_message(
    hass: Any,
    config: Mapping[str, Any],
    *,
    title: str,
    message: str,
) -> str:
    """Send fixed/generated TEST ONLY text through the one validated target path."""
    if not title.startswith("TEST ONLY") or not message.startswith("TEST ONLY"):
        raise MobileTargetError(
            "Manual mobile test title and message must both be labeled TEST ONLY"
        )
    notify_entity = str(config.get(CONF_NOTIFY_ENTITY, "")).strip()
    legacy_action = str(config.get(CONF_LEGACY_NOTIFY_SERVICE, "")).strip()
    if config.get("profiles") is not None:
        from .config import profiles_from_config

        enabled = [profile for profile in profiles_from_config(config) if profile.enabled]
        if len(enabled) != 1:
            raise MobileTargetError(
                "Manual mobile tests require exactly one enabled profile"
            )
        notify_entity = enabled[0].notify_entity_id
        legacy_action = enabled[0].legacy_notify_service
    return await _async_send_to_target(
        hass,
        notify_entity=notify_entity,
        legacy_action=legacy_action,
        title=title,
        message=message,
    )


async def _async_send_to_target(
    hass: Any,
    *,
    notify_entity: str,
    legacy_action: str,
    title: str,
    message: str,
    companion_data: Mapping[str, Any] | None = None,
) -> str:
    if not notify_entity and not legacy_action:
        raise MobileTargetError("Exactly one mobile notification target must be configured")

    # One selected Companion phone handles both basic and advanced messages.
    # A basic notify entity is used only when no Companion action is configured.
    # Never silently switch to another target after a delivery failure.
    use_legacy = bool(legacy_action)
    if notify_entity and not use_legacy:
        if (
            not notify_entity.startswith("notify.")
            or "," in notify_entity
            or " " in notify_entity
            or hass.states.get(notify_entity) is None
        ):
            raise MobileTargetError("The configured notify entity is unavailable")
        if not hass.services.has_service("notify", "send_message"):
            raise MobileTargetError("The notify.send_message action is unavailable")
        service_data: dict[str, Any] = {"message": message, "title": title}
        try:
            await hass.services.async_call(
                "notify",
                "send_message",
                service_data,
                target={"entity_id": notify_entity},
                blocking=True,
            )
        except Exception as error:
            raise MobileTargetError("The configured notify entity could not receive the message", retry_safe=False) from error
        return "notify_entity"

    if (
        not legacy_action.startswith("notify.mobile_app_")
        or legacy_action.count(".") != 1
        or "," in legacy_action
        or " " in legacy_action
    ):
        raise MobileTargetError("The configured legacy mobile action is invalid")
    domain, service = legacy_action.split(".", 1)
    if not hass.services.has_service(domain, service):
        raise MobileTargetError("The configured legacy mobile action is unavailable")
    service_data = {"message": message, "title": title}
    if companion_data:
        service_data["data"] = dict(companion_data)
    try:
        await hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
        )
    except Exception as error:
        raise MobileTargetError("The configured Companion action could not receive the message", retry_safe=False) from error
    return "legacy_mobile_action"
