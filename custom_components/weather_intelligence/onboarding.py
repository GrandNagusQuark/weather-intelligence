"""Onboarding gate and an explicitly local, backup-first testing override."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .const import (
    CONF_CONTACT, CONF_CRITICAL_NOTIFICATIONS, CONF_LEGACY_NOTIFY_SERVICE,
    CONF_NOTIFY_ENTITY, CONF_PERSON_ENTITY, CONF_PROFILES,
)

ONBOARDING_KEY = "onboarding"
TEST_MARKER = Path(__file__).parent / ".onboarding-test.json"
TEST_INITIALIZED = "onboarding_test_initialized"
TEST_RESET_PENDING = "onboarding_test_reset_pending"


def testing_enabled(entry_id: str) -> bool:
    """Only a locally deployed, matching-entry marker enables destructive resets."""
    try:
        marker = json.loads(TEST_MARKER.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(marker, dict)
        and marker.get("entry_id") == entry_id
        and marker.get("testing_enabled") is True
        and bool(marker.get("verified_backup_sha256"))
    )


def fresh_install_preferences(values: Mapping[str, Any]) -> dict[str, Any]:
    """Clear all app preferences; retain only NWS's required install contact."""
    return {
        **({CONF_CONTACT: values[CONF_CONTACT]} if CONF_CONTACT in values else {}),
        CONF_PROFILES: [],
        CONF_PERSON_ENTITY: "",
        CONF_NOTIFY_ENTITY: "",
        CONF_LEGACY_NOTIFY_SERVICE: "",
        CONF_CRITICAL_NOTIFICATIONS: False,
        ONBOARDING_KEY: {"version": 1, "initiated": False, "completed": False, "endpoint": None},
    }


fresh_test_preferences = fresh_install_preferences


def onboarding_snapshot(config: Mapping[str, Any], *, testing: bool = False) -> dict[str, Any]:
    """Track initiation separately from completion and never infer a new endpoint."""
    profiles = config.get(CONF_PROFILES, [])
    selected = any(p.get(CONF_NOTIFY_ENTITY) or p.get(CONF_LEGACY_NOTIFY_SERVICE) for p in profiles)
    saved = config.get(ONBOARDING_KEY)
    # Compatibility only: do not strand existing enrolled installations on upgrade.
    legacy = saved is None and selected
    saved = saved if isinstance(saved, Mapping) else {}
    initiated = bool(saved.get("initiated", legacy))
    completed = bool(saved.get("completed", legacy))
    return {
        "version": 1, "initiated": initiated, "completed": completed,
        "endpoint": saved.get("endpoint", "legacy" if legacy else None) if completed else None,
        "setup_mode": saved.get("setup_mode") if saved.get("setup_mode") in {"quick", "guided", "custom"} else None,
        "device_selected": selected, "testing": testing,
        # Automation-only is intentionally not an implemented bypass yet.
        "dashboard_available": initiated and selected,
    }


def onboarding_progress(config: Mapping[str, Any], mode: str | None = None) -> dict[str, Any]:
    """Beginning persists progress without selecting a default path or completing."""
    if mode is not None and mode not in {"quick", "guided", "custom"}:
        raise ValueError("Unsupported onboarding path")
    state = dict(config.get(ONBOARDING_KEY) or {})
    state.update({"version": 1, "initiated": True})
    if mode is not None:
        state["setup_mode"] = mode
    return state


async def async_prepare_onboarding_test(hass: Any, entry: Any) -> bool:
    """Initialize testing once; subsequent restarts preserve real saved choices."""
    testing = await hass.async_add_executor_job(testing_enabled, entry.entry_id)
    hass.data.setdefault("weather_intelligence", {})["onboarding_testing"] = testing
    if testing and not entry.data.get(TEST_INITIALIZED, False):
        reset_test_entry(hass, entry)
    return testing


def reset_test_entry(hass: Any, entry: Any) -> None:
    """Clear app preferences and request a safe integration-store reset."""
    data = {**fresh_test_preferences(entry.data), TEST_INITIALIZED: True, TEST_RESET_PENDING: True}
    hass.config_entries.async_update_entry(entry, data=data, options=fresh_test_preferences(entry.options))
