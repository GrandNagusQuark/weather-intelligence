"""Consent, local identity and periodic service checks for the outage network."""

import asyncio
from datetime import datetime, timedelta, timezone
import time

from .config import effective_entry_config
from .const import DOMAIN
from .outage_protocol import OUTAGE_PATH, STATUS_PATH, PROJECT_ORIGIN, OUTAGE_POLICY_VERSION, validate_status
from .reporting_config import reporting_config
from .reporting_http import ReportTransport
from .reporting_audit import async_reporting_audit
from .reporting_identity import async_reporting_identity

OUTAGE_KEY = "outage_reporting"
STARTUP_GRACE_SECONDS = 600
CHECK_SECONDS = 300


def outage_config(config):
    raw = config.get(OUTAGE_KEY, {})
    if not isinstance(raw, dict):
        raw = {}
    enabled = bool(raw.get("enabled") is True and raw.get("consent") is True
                   and type(raw.get("policy_version")) is int
                   and raw["policy_version"] == OUTAGE_POLICY_VERSION)
    return {"enabled": enabled, "policy_version": OUTAGE_POLICY_VERSION}


class OutageReporting:
    def __init__(self, hass, entry, identity_store, transport=None):
        self.hass, self.entry, self.identity_store = hass, entry, identity_store
        self.transport = transport or ReportTransport()
        self.installation_id = None
        self.started = time.monotonic()
        self.last_sequence = None
        self.failures = 0
        self.last_contribution = "No outage contributions sent"
        self.status = None
        self.status_checked = 0.0
        self.last_attempt = 0.0
        self.reported_failure = False
        self.audit_failed = False
        self.notices = None
        self.task = None
        self.stopped = False

    def permitted(self):
        config = effective_entry_config(self.entry)
        return reporting_config(config)["enabled"] and outage_config(config)["enabled"]

    async def initialize(self):
        self.installation_id = await async_reporting_identity(self.hass,self.entry,self.identity_store)

    async def tick(self):
        if self.stopped:
            return
        now = time.monotonic()
        if now - self.status_checked >= CHECK_SECONDS:
            self.status_checked = now
            try:
                self.status = validate_status(await self.transport.get_status(PROJECT_ORIGIN + STATUS_PATH))
            except Exception:
                self.status = None
        if self.notices is not None and self.status is not None:
            try:
                await self.notices.update(validate_status(self.status))
            except Exception:
                # Service notice delivery never stops the regular weather poller.
                pass
        if not self.permitted() or not self.installation_id or self.audit_failed:
            return
        coordinator = getattr(self.entry, "runtime_data", None)
        sequence = getattr(coordinator, "_poll_attempts", None)
        healthy = getattr(coordinator, "nws_request_healthy", None)
        if sequence is None or sequence == self.last_sequence or healthy is None:
            return
        self.last_sequence = sequence
        self.failures = self.failures + 1 if healthy is False else 0
        tracker = getattr(coordinator, "source_latency", None)
        delayed = bool(tracker and tracker.delayed(datetime.now(timezone.utc)))
        if now - self.started < STARTUP_GRACE_SECONDS or now - self.last_attempt < CHECK_SECONDS:
            return
        if healthy is not True and self.failures < 3:
            return
        # Recovery is sent only after this installation actually reported trouble.
        if healthy is True and not delayed and not self.reported_failure:
            return
        report = {"schema_version": 1, "installation_id": self.installation_id, "source": "nws_alerts",
                  "state": "unavailable" if healthy is not True else "delayed" if delayed else "recovered",
                  "timestamp": datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()}
        self.last_attempt = now
        try:
            audit = await async_reporting_audit(self.hass, self.entry.entry_id)
            audit_id = await audit.prepare(PROJECT_ORIGIN + OUTAGE_PATH, report)
        except Exception:
            self.audit_failed = True
            raise
        try:
            status, protocol = await self.transport.send(PROJECT_ORIGIN + OUTAGE_PATH, report)
            accepted = status == 202 and protocol is True
            try:
                await audit.finish(audit_id, "accepted" if accepted else "not_accepted")
            except Exception:
                self.audit_failed = True
                raise
            self.last_contribution = ("Receiver accepted outage contribution" if accepted
                                      else "Receiver did not accept outage contribution")
            if accepted and report["state"] == "recovered":
                self.last_contribution = "Receiver accepted recovery contribution"
            if accepted:
                self.reported_failure = report["state"] != "recovered"
        except BaseException:
            try:
                await audit.finish(audit_id, "unconfirmed")
            except Exception:
                self.audit_failed = True
            raise

    def snapshot(self):
        try:
            status = validate_status(self.status)
        except (ValueError, TypeError, KeyError):
            status = {"state": "unknown", "source": "nws_alerts"}
        return {"config": outage_config(effective_entry_config(self.entry)), "status": status,
                "identity_created": self.installation_id is not None, "last_result": self.last_contribution}

    async def stop(self):
        self.stopped = True
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.transport.close()


async def async_setup_outages(hass, entry):
    from homeassistant.helpers.storage import Store
    from homeassistant.helpers.event import async_track_time_interval
    runtimes = hass.data.setdefault(DOMAIN, {}).setdefault("outage_reporting", {})
    previous = runtimes.pop(entry.entry_id, None)
    if previous:
        previous.unsubscribe()
        await previous.stop()
    runtime = OutageReporting(hass, entry, Store(hass, 1, f"{DOMAIN}.outage_identity.{entry.entry_id}"))
    await runtime.initialize()
    from .outage_notices import OutageNotices
    runtime.notices = OutageNotices(hass, entry, Store(hass, 1, f"{DOMAIN}.outage_notices.{entry.entry_id}"))
    await runtime.notices.load()
    runtimes[entry.entry_id] = runtime

    async def check(_now):
        if runtime.task is not None and not runtime.task.done():
            return
        async def run():
            try:
                await runtime.tick()
            except Exception:
                runtime.last_contribution = "Outage contribution paused because sending or its local audit failed"
        runtime.task = hass.async_create_task(run())

    runtime.unsubscribe = async_track_time_interval(hass, check, timedelta(seconds=60))
    await check(None)


async def async_stop_outages(hass, entry_id):
    runtime = hass.data.get(DOMAIN, {}).get("outage_reporting", {}).pop(entry_id, None)
    if runtime:
        runtime.unsubscribe()
        await runtime.stop()
