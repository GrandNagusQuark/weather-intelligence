"""Administrator controls for reporting, separate from household profile saves."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .config import effective_entry_config
from .const import DOMAIN
from .maintainer_reporting import async_setup_reporting, async_stop_reporting, reporting_snapshot
from .reporting_config import REPORTING_KEY, reporting_config, reporting_update
from .reporting_audit import async_reporting_audit


async def async_save_reporting(hass: Any, entry: Any, payload: dict[str, Any]) -> dict[str, Any]:
    locks = hass.data.setdefault(DOMAIN, {}).setdefault("reporting_save_locks", {})
    lock = locks.setdefault(entry.entry_id, asyncio.Lock())
    async with lock:
        current = reporting_config(effective_entry_config(entry))
        if payload.get("expected_config") != current:
            raise ValueError("Reporting settings changed. Reopen this screen before saving.")
        update = reporting_update(payload)
        await async_stop_reporting(hass, entry.entry_id)
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, REPORTING_KEY: update},
        )
        await async_setup_reporting(hass, entry)
        from .outage_reporting import OUTAGE_KEY, async_setup_outages
        if not update["enabled"]:
            hass.config_entries.async_update_entry(entry, options={**entry.options,
                OUTAGE_KEY: {"enabled": False, "consent": False, "policy_version": 1}})
        await async_setup_outages(hass, entry)
        return reporting_snapshot(hass, entry)


def register_reporting_commands(hass: Any, get_entry: Callable[[Any], Any]) -> None:
    import voluptuous as vol
    from homeassistant.components import websocket_api
    from .outage_api import register_outage_commands
    register_outage_commands(hass, get_entry)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/reporting/get"})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def get_reporting(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
        connection.send_result(msg["id"], reporting_snapshot(hass, get_entry(hass)))

    @websocket_api.websocket_command({
        vol.Required("type"): f"{DOMAIN}/reporting/update",
        vol.Required("expected_config"): dict,
        vol.Required("endpoint"): str,
        vol.Required("enabled"): bool,
        vol.Optional("consent", default=False): bool,
        vol.Optional("consent_endpoint", default=""): str,
        vol.Optional("policy_version", default=0): int,
    })
    @websocket_api.require_admin
    @websocket_api.async_response
    async def update_reporting(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
        try:
            result = await async_save_reporting(hass, get_entry(hass), msg)
        except ValueError as error:
            connection.send_error(msg["id"], "invalid_reporting", str(error))
            return
        connection.send_result(msg["id"], result)

    websocket_api.async_register_command(hass, get_reporting)
    websocket_api.async_register_command(hass, update_reporting)

    @websocket_api.websocket_command({
        vol.Required("type"): f"{DOMAIN}/reporting/audit",
        vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=15000)),
    })
    @websocket_api.require_admin
    @websocket_api.async_response
    async def get_audit(hass: Any, connection: Any, msg: dict[str, Any]) -> None:
        try:
            audit = await async_reporting_audit(hass, get_entry(hass).entry_id)
            snapshot = await audit.snapshot(msg["offset"])
        except Exception:
            connection.send_error(msg["id"], "audit_unavailable", "The local reporting audit could not be read")
            return
        connection.send_result(msg["id"], snapshot)

    websocket_api.async_register_command(hass, get_audit)
