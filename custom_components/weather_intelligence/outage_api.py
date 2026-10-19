"""Separate administrator consent for pseudonymous outage contributions."""

import asyncio

from .config import effective_entry_config
from .const import DOMAIN
from .outage_protocol import OUTAGE_POLICY_VERSION
from .outage_reporting import OUTAGE_KEY, async_setup_outages, outage_config
from .reporting_config import reporting_config


def outage_snapshot(hass, entry):
    runtime = getattr(hass, "data", {}).get(DOMAIN, {}).get("outage_reporting", {}).get(entry.entry_id)
    return runtime.snapshot() if runtime else {"config": outage_config(effective_entry_config(entry)),
        "status": {"state": "unknown", "source": "nws_alerts"}, "identity_created": False,
        "last_result": "Outage reporting is starting"}


def register_outage_commands(hass, get_entry):
    import voluptuous as vol
    from homeassistant.components import websocket_api

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/outages/get"})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def get_outages(hass, connection, msg):
        connection.send_result(msg["id"], outage_snapshot(hass, get_entry(hass)))

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/outages/update",
        vol.Required("expected_config"): dict, vol.Required("enabled"): bool,
        vol.Required("consent"): bool, vol.Required("policy_version"): int})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def update_outages(hass, connection, msg):
        entry = get_entry(hass)
        locks = hass.data.setdefault(DOMAIN, {}).setdefault("reporting_save_locks", {})
        async with locks.setdefault(entry.entry_id, asyncio.Lock()):
            config = effective_entry_config(entry)
            if (msg["expected_config"] != outage_config(config)
                    or type(msg["policy_version"]) is not int or msg["policy_version"] != OUTAGE_POLICY_VERSION
                    or msg["enabled"] and (not msg["consent"] or not reporting_config(config)["enabled"])):
                connection.send_error(msg["id"], "invalid_consent", "Review outage participation after enabling error reporting.")
                return
            hass.config_entries.async_update_entry(entry, options={**entry.options, OUTAGE_KEY: {
                "enabled": msg["enabled"], "consent": msg["consent"] if msg["enabled"] else False,
                "policy_version": OUTAGE_POLICY_VERSION}})
            await async_setup_outages(hass, entry)
            connection.send_result(msg["id"], outage_snapshot(hass, entry))

    websocket_api.async_register_command(hass, get_outages)
    websocket_api.async_register_command(hass, update_outages)
