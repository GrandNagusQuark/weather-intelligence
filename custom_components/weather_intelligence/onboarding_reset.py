"""Consume an explicit, entry-bound local request for a fresh installation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import effective_entry_config

RESET_REQUEST_PATH = Path(__file__).parent / ".onboarding-reset-request.json"
RESET_REQUEST_ID = "onboarding_reset_request_id"
RESET_PENDING = "onboarding_reset_pending"
_LOGGER = logging.getLogger(__name__)


def read_reset_request(entry_id: str) -> dict | None:
    try:
        request = json.loads(RESET_REQUEST_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(request, dict)
        or request.get("entry_id") != entry_id
        or not isinstance(request.get("request_id"), str)
        or len(request["request_id"]) != 32
        or any(character not in "0123456789abcdef" for character in request["request_id"])
        or request.get("scope") != "integration"
    ):
        return None
    return request


def remove_reset_request() -> None:
    RESET_REQUEST_PATH.unlink(missing_ok=True)


async def async_apply_requested_reset(
    hass: Any, entry: Any, store: Any, *, additional_stores: tuple = ()
) -> bool:
    """Clear WI preferences and continuity, never unrelated HA configuration.

    The required NWS installation contact remains so the installed integration
    can start. Persist a pending flag before clearing history; if interrupted,
    startup finishes that reset instead of restoring the old alert records.
    """
    from .onboarding import fresh_install_preferences

    request = await hass.async_add_executor_job(read_reset_request, entry.entry_id)
    pending = entry.data.get(RESET_PENDING) is True
    if request is None and not pending:
        return False
    if request and entry.data.get(RESET_REQUEST_ID) != request["request_id"]:
        fresh = fresh_install_preferences(effective_entry_config(entry))
        hass.config_entries.async_update_entry(
            entry,
            data={**fresh, RESET_REQUEST_ID: request["request_id"], RESET_PENDING: True},
            options={},
        )
        pending = True
    if pending:
        await store.async_remove()
        for additional_store in additional_stores:
            await additional_store.async_remove()
        data = dict(entry.data)
        data.pop(RESET_PENDING, None)
        hass.config_entries.async_update_entry(entry, data=data)
    try:
        await hass.async_add_executor_job(remove_reset_request)
    except OSError:
        _LOGGER.warning(
            "Installation reset completed; the consumed local request could not be removed"
        )
    return pending
