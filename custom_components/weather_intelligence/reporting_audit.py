"""Local receipt audit of the exact small report, never the source log record."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import re
from typing import Any
import uuid

from .reporting_config import validate_endpoint
from .reporting_device import safe_mobile_context
from .reporting_payload import COMPONENTS, ERROR_CODES, EXCEPTION_TYPES, REPORT_FIELDS
from .outage_protocol import PROJECT_ORIGIN, OUTAGE_PATH, validate_outage

RETENTION_DAYS = 30
MAX_ENTRIES = 15000
PAGE_SIZE = 100
_VERSION = re.compile(r"\d{1,4}\.\d{1,4}(?:\.\d{1,4})?(?:(?:[a-z]\d+)|-alpha)?", re.ASCII)
_MINUTE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\+00:00", re.ASCII)
RESULTS = {"prepared", "accepted", "not_accepted", "unconfirmed"}


def safe_report_copy(value: Any) -> dict[str, Any]:
    """The audit must not turn tampered storage or arbitrary logs into an export."""
    if isinstance(value, dict) and "feedback_id" in value:
        from .feedback_protocol import validate_feedback
        return validate_feedback(value)
    if isinstance(value, dict) and "installation_id" in value:
        return validate_outage(value)
    if not isinstance(value, dict) or set(value) != set(REPORT_FIELDS):
        raise ValueError("Invalid diagnostic report")
    if type(value["schema_version"]) is not int or value["schema_version"] != 2:
        raise ValueError("Invalid diagnostic report")
    for field in ("integration_version", "home_assistant_version"):
        item = value[field]
        if item == "unknown" and field == "home_assistant_version":
            continue
        if not isinstance(item, str) or len(item) > 20 or _VERSION.fullmatch(item) is None:
            raise ValueError("Invalid diagnostic report")
    for field, choices in (("component", COMPONENTS), ("error_code", ERROR_CODES),
                           ("exception_type", EXCEPTION_TYPES), ("level", {"ERROR", "CRITICAL"})):
        if not isinstance(value[field], str) or value[field] not in choices:
            raise ValueError("Invalid diagnostic report")
    timestamp = value["timestamp"]
    if not isinstance(timestamp, str) or _MINUTE.fullmatch(timestamp) is None:
        raise ValueError("Invalid diagnostic report")
    datetime.fromisoformat(timestamp)
    context = safe_mobile_context(value)
    if any(value[field] != item for field, item in context.items()):
        raise ValueError("Invalid diagnostic report")
    return {field: value[field] for field in REPORT_FIELDS}


def audit_endpoint(value):
    if value == PROJECT_ORIGIN + "/v1/feedback":
        return value
    if value == PROJECT_ORIGIN + OUTAGE_PATH:
        return value
    return validate_endpoint(value)


class ReportingAudit:
    def __init__(self, store):
        self.store = store
        self.entries = []
        self.lock = asyncio.Lock()

    def _pruned(self, now=None):
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat()
        # A future date in a corrupt store cannot extend retention indefinitely.
        latest = (now + timedelta(minutes=1)).isoformat()
        return [row for row in self.entries if cutoff <= row["attempted_at"] <= latest][-MAX_ENTRIES:]

    async def load(self):
        saved = await self.store.async_load()
        rows = saved.get("entries", []) if isinstance(saved, dict) else []
        sanitized = []
        for row in rows[-MAX_ENTRIES:] if isinstance(rows, list) else []:
            try:
                if (not isinstance(row, dict) or set(row) != {"audit_id", "attempted_at", "endpoint", "result", "report"}
                        or not isinstance(row["audit_id"], str) or re.fullmatch(r"[a-f0-9]{32}", row["audit_id"]) is None
                        or not isinstance(row["result"], str) or row["result"] not in RESULTS
                        or not isinstance(row["attempted_at"], str) or _MINUTE.fullmatch(row["attempted_at"]) is None):
                    continue
                datetime.fromisoformat(row["attempted_at"])
                endpoint = audit_endpoint(row["endpoint"])
                if not endpoint:
                    continue
                sanitized.append({"audit_id": row["audit_id"], "attempted_at": row["attempted_at"],
                    "endpoint": endpoint, "result": "unconfirmed" if row["result"] == "prepared" else row["result"],
                    "report": safe_report_copy(row["report"])})
            except (ValueError, TypeError, KeyError):
                continue
        self.entries = sanitized
        self.entries = self._pruned()
        if saved is not None:
            await self.store.async_save({"entries": self.entries})

    async def prepare(self, endpoint, report):
        endpoint = audit_endpoint(endpoint)
        if not endpoint:
            raise ValueError("Missing diagnostic destination")
        row = {"audit_id": uuid.uuid4().hex,
            "attempted_at": datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat(),
            "endpoint": endpoint, "result": "prepared", "report": safe_report_copy(report)}
        async with self.lock:
            entries = [*self._pruned(), row][-MAX_ENTRIES:]
            await self.store.async_save({"entries": entries})
            self.entries = entries
        return row["audit_id"]

    async def finish(self, audit_id, result):
        if result not in {"accepted", "not_accepted", "unconfirmed"}:
            raise ValueError("Invalid diagnostic outcome")
        async with self.lock:
            entries = [{**row, "result": result} if row["audit_id"] == audit_id else row for row in self._pruned()]
            await self.store.async_save({"entries": entries})
            self.entries = entries

    async def snapshot(self, offset=0):
        if type(offset) is not int or not 0 <= offset <= MAX_ENTRIES:
            raise ValueError("Invalid audit page")
        async with self.lock:
            pruned = self._pruned()
            if len(pruned) != len(self.entries):
                await self.store.async_save({"entries": pruned})
                self.entries = pruned
            rows = list(reversed(self.entries))
            return {"retention_days": RETENTION_DAYS, "total": len(rows), "offset": offset,
                    "limit": PAGE_SIZE, "entries": rows[offset:offset + PAGE_SIZE]}


async def async_reporting_audit(hass, entry_id):
    from homeassistant.helpers.storage import Store
    from homeassistant.helpers.event import async_track_time_interval
    from .const import DOMAIN
    data = hass.data.setdefault(DOMAIN, {})
    audits = data.setdefault("reporting_audits", {})
    lock = data.setdefault("audit_load_locks", {}).setdefault(entry_id, asyncio.Lock())
    async with lock:
        if entry_id not in audits:
            audit = ReportingAudit(Store(hass, 1, f"{DOMAIN}.reporting_audit.{entry_id}"))
            await audit.load()
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                raise ValueError("Reporting installation is unavailable")

            async def prune(_now):
                try:
                    await audit.snapshot()
                except Exception:
                    # A storage failure must not enter the log handler recursively.
                    data.setdefault("reporting_setup_errors", {})[entry_id] = "Reporting audit maintenance is unavailable"

            entry.async_on_unload(async_track_time_interval(hass, prune, timedelta(hours=1)))
            entry.async_on_unload(lambda: audits.pop(entry_id, None))
            audits[entry_id] = audit
        return audits[entry_id]
