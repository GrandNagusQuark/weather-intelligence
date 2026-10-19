"""Bounded opt in reporting, isolated from alert processing and other integrations."""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import threading
import time
from typing import Any

from .config import effective_entry_config
from .const import DOMAIN
from .reporting_config import PROJECT_REPORTING_ENDPOINT, reporting_config
from .reporting_http import ReportTransport
from .reporting_payload import build_report, report_preview
from .reporting_audit import async_reporting_audit

MAX_PENDING = 8
MAX_HOURLY = 20
DUPLICATE_SECONDS = 900
_LOGGER_NAME = f"custom_components.{DOMAIN}"


class MaintainerReportHandler(logging.Handler):
    def __init__(self, loop: Any, endpoint: str, transport: Any, ha_version: str, audit: Any = None,
                 startup_grace_seconds: int = 0) -> None:
        super().__init__(logging.ERROR)
        self.endpoint = endpoint
        self.enabled = True
        self._loop = loop
        self._transport = transport
        self._ha_version = ha_version
        self._audit = audit
        self._startup_until = time.monotonic() + startup_grace_seconds
        self._slots = threading.BoundedSemaphore(MAX_PENDING)
        self._rate_lock = threading.Lock()
        self._recent: dict[tuple[str, ...], float] = {}
        self._hourly: deque[float] = deque()
        self._queue: deque[dict[str, Any]] = deque()
        self._task: asyncio.Task | None = None
        self._backoff_until = 0.0
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self.last_result = "No reports sent"

    def emit(self, record: logging.LogRecord) -> None:
        if (
            not self.enabled or record.levelno < logging.ERROR
            or not (record.name == _LOGGER_NAME or record.name.startswith(_LOGGER_NAME + "."))
        ):
            return
        if not self._slots.acquire(blocking=False):
            self.dropped += 1
            return
        try:
            document = build_report(record, self._ha_version)
            if (time.monotonic() < self._startup_until
                    and document["component"] in {"ha_coordinator", "nws_client", "official_sources", "mrms_hail"}
                    and (document["error_code"] == "request_timeout"
                         or document["error_code"] == "official_source_failed"
                         and document["exception_type"] in {"TimeoutError", "ConnectionError", "OSError", "NwsClientError"})):
                self.dropped += 1
                self._slots.release()
                return
            key = tuple(str(document[field]) for field in ("error_code", "component", "level", "exception_type",
                "mobile_platform", "mobile_os_version", "companion_app_version"))
            now = time.monotonic()
            with self._rate_lock:
                self._recent = {key: seen for key, seen in self._recent.items() if now - seen < DUPLICATE_SECONDS}
                while self._hourly and now - self._hourly[0] >= 3600:
                    self._hourly.popleft()
                if now < self._backoff_until or key in self._recent or len(self._hourly) >= MAX_HOURLY:
                    self.dropped += 1
                    self._slots.release()
                    return
                self._recent[key] = now
                self._hourly.append(now)
            self._loop.call_soon_threadsafe(self._enqueue, document)
        except Exception:
            self._slots.release()
            self.dropped += 1

    def _enqueue(self, document: dict[str, Any]) -> None:
        if not self.enabled:
            self._slots.release()
            return
        self._queue.append(document)
        if self._task is None or self._task.done():
            self._task = self._loop.create_task(self._drain())

    async def _drain(self) -> None:
        while self.enabled and self._queue:
            document = self._queue.popleft()
            audit_id = None
            try:
                if self._audit is not None:
                    try:
                        audit_id = await self._audit.prepare(self.endpoint, document)
                    except Exception:
                        self.enabled = False
                        self.last_result = "Reporting paused because the local audit could not be saved"
                        self.dropped += 1
                        break
                status, protocol = await self._transport.send(self.endpoint, document)
                accepted = status == 202 and protocol is True
                if audit_id is not None:
                    try:
                        await self._audit.finish(audit_id, "accepted" if accepted else "not_accepted")
                    except Exception:
                        self.enabled = False
                        self.failed += 1
                        self.last_result = "Reporting paused because the local audit result could not be saved"
                        break
                self.last_result = "Receiver accepted report" if accepted else "Receiver did not accept report"
                if accepted:
                    self.sent += 1
                else:
                    self.failed += 1
                    self._backoff_until = time.monotonic() + (900 if status in (400, 401, 403, 404) else 60)
            except asyncio.CancelledError:
                if audit_id is not None:
                    try:
                        await self._audit.finish(audit_id, "unconfirmed")
                    except Exception:
                        pass
                raise
            except Exception:
                # Do not log a reporting failure through the logger we observe.
                self.failed += 1
                self.last_result = "Reporting connection unavailable"
                self._backoff_until = time.monotonic() + 60
                if audit_id is not None:
                    try:
                        await self._audit.finish(audit_id, "unconfirmed")
                    except Exception:
                        self.enabled = False
                        self.last_result = "Reporting paused because the local audit could not be saved"
            finally:
                self._slots.release()
            if time.monotonic() < self._backoff_until:
                break
        while self._queue:
            self._queue.popleft()
            self._slots.release()
            self.dropped += 1

    async def stop(self) -> None:
        self.enabled = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        while self._queue:
            self._queue.popleft()
            self._slots.release()
        try:
            await self._transport.close()
        except Exception:
            self.last_result = "Reporting transport could not close cleanly"
        finally:
            self.close()


async def async_stop_reporting(hass: Any, entry_id: str) -> None:
    handlers = getattr(hass, "data", {}).get(DOMAIN, {}).get("maintainer_reporters", {})
    handler = handlers.pop(entry_id, None)
    if handler is not None:
        handler.enabled = False
        logging.getLogger(_LOGGER_NAME).removeHandler(handler)
        await handler.stop()


async def async_setup_reporting(hass: Any, entry: Any) -> None:
    await async_stop_reporting(hass, entry.entry_id)
    config = reporting_config(effective_entry_config(entry))
    try:
        audit = await async_reporting_audit(hass, entry.entry_id)
    except Exception:
        hass.data.setdefault(DOMAIN, {}).setdefault("reporting_setup_errors", {})[entry.entry_id] = "Reporting paused because its local audit is unavailable"
        return
    hass.data.setdefault(DOMAIN, {}).setdefault("reporting_setup_errors", {}).pop(entry.entry_id, None)
    if not config["enabled"]:
        return
    try:
        from homeassistant.const import __version__
    except ImportError:
        __version__ = "unknown"
    handler = MaintainerReportHandler(hass.loop, config["endpoint"], ReportTransport(), __version__, audit,
                                      startup_grace_seconds=600)
    hass.data.setdefault(DOMAIN, {}).setdefault("maintainer_reporters", {})[entry.entry_id] = handler
    logging.getLogger(_LOGGER_NAME).addHandler(handler)


def reporting_snapshot(hass: Any, entry: Any) -> dict[str, Any]:
    config = reporting_config(effective_entry_config(entry))
    handler = getattr(hass, "data", {}).get(DOMAIN, {}).get("maintainer_reporters", {}).get(entry.entry_id)
    return {
        "config": config, "active": bool(handler and handler.enabled),
        "sent": handler.sent if handler else 0, "failed": handler.failed if handler else 0,
        "dropped": handler.dropped if handler else 0,
        "last_result": handler.last_result if handler else getattr(hass, "data", {}).get(DOMAIN, {}).get("reporting_setup_errors", {}).get(entry.entry_id, "Reporting is off"),
        "preview": report_preview(),
        "default_endpoint": PROJECT_REPORTING_ENDPOINT,
    }
