"""Explicit, recipient-scoped notification acknowledgements (not safety status)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Iterable, Mapping

ACTION_PREFIX = "WI_ACK_"


class Acknowledgements:
    """A random capability is sent only to the recipient, never to the panel."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    def action(self, profile_id: str, incident: Any, now: datetime) -> dict[str, str]:
        key = (profile_id, incident.incident_key)
        record = self._records.get(key)
        if record is None or record["revision"] != incident.revision:
            record = {
                "profile_id": profile_id, "incident_key": incident.incident_key,
                "revision": incident.revision, "action": ACTION_PREFIX + secrets.token_urlsafe(24),
                "expires_at": incident.latest_alert.expires_at or now + timedelta(hours=24),
                "acknowledged_at": None,
            }
            self._records[key] = record
        return {"action": record["action"], "title": "Acknowledge"}

    def status(self, profile_id: str, incident: Any) -> dict[str, Any]:
        record = self._records.get((profile_id, incident.incident_key))
        if record is None or record["revision"] != incident.revision:
            return {"acknowledged": False, "acknowledged_at": None, "ack_available": False}
        at = record["acknowledged_at"]
        return {"acknowledged": at is not None,
                "acknowledged_at": at.isoformat() if at else None, "ack_available": True}

    def consume(self, action: str, incidents: Iterable[Any], now: datetime) -> dict[str, Any] | None:
        """Reject forged, old-revision, resolved, and expired actions; accept once."""
        if not isinstance(action, str) or not action.startswith(ACTION_PREFIX):
            return None
        active = {item.incident_key: item for item in incidents if item.phase.value == "active"}
        for record in self._records.values():
            if not secrets.compare_digest(record["action"], action):
                continue
            incident = active.get(record["incident_key"])
            if (incident is None or incident.revision != record["revision"]
                    or now >= record["expires_at"] or record["acknowledged_at"] is not None):
                return None
            record["acknowledged_at"] = now
            return dict(record)
        return None

    def prune(self, incidents: Iterable[Any], profile_ids: set[str], now: datetime) -> None:
        active = {item.incident_key for item in incidents if item.phase.value == "active"}
        self._records = {key: record for key, record in self._records.items()
                         if key[0] in profile_ids and key[1] in active and now < record["expires_at"]}

    def serialize(self) -> list[dict[str, Any]]:
        return [{**record, "expires_at": record["expires_at"].isoformat(),
                 "acknowledged_at": record["acknowledged_at"].isoformat()
                 if record["acknowledged_at"] else None} for record in self._records.values()]

    def restore(self, values: Any, profile_ids: set[str]) -> None:
        """Optional old storage is empty; malformed records never imply a yes."""
        self._records = {}
        if not isinstance(values, list):
            return
        for value in values[:1000]:
            try:
                if not isinstance(value, Mapping) or value["profile_id"] not in profile_ids:
                    continue
                record = dict(value)
                expires = datetime.fromisoformat(record["expires_at"])
                at = datetime.fromisoformat(record["acknowledged_at"]) if record.get("acknowledged_at") else None
                if (expires.tzinfo is None or (at is not None and at.tzinfo is None)
                        or not str(record["action"]).startswith(ACTION_PREFIX)
                        or not isinstance(record["revision"], int)):
                    continue
                record["expires_at"], record["acknowledged_at"] = expires, at
                self._records[(str(record["profile_id"]), str(record["incident_key"]))] = record
            except (KeyError, ValueError, TypeError):
                continue
