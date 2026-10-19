"""Small outage contract, deliberately separate from ordinary diagnostics."""

from datetime import datetime, timedelta, timezone
import re

OUTAGE_FIELDS = frozenset({"schema_version", "installation_id", "source", "state", "timestamp"})
OUTAGE_PATH = "/v1/outages"
STATUS_PATH = "/v1/status"
PROJECT_ORIGIN = "https://reports.weatherintelligence.app"
OUTAGE_POLICY_VERSION = 1


def validate_outage(value):
    if not isinstance(value, dict) or set(value) != OUTAGE_FIELDS:
        raise ValueError("Invalid outage contribution")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["installation_id"], str)
            or re.fullmatch(r"[a-f0-9]{64}", value["installation_id"]) is None
            or value["source"] != "nws_alerts" or value["state"] not in ("unavailable", "delayed", "recovered")):
        raise ValueError("Invalid outage contribution")
    minute = value["timestamp"]
    if not isinstance(minute, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\+00:00", minute) is None:
        raise ValueError("Invalid outage contribution")
    datetime.fromisoformat(minute)
    return dict(value)


def validate_status(value, now=None):
    now = now or datetime.now(timezone.utc)
    fields = {"schema_version", "source", "state", "generated_at", "expires_at", "affected_installations", "threshold"}
    if (not isinstance(value, dict) or set(value) != fields or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or value["source"] != "nws_alerts"
            or value["state"] not in ("unknown", "available", "possible_outage", "corroborated_outage", "possible_delay", "corroborated_delay")):
        raise ValueError("Invalid service status")
    for field in ("affected_installations", "threshold"):
        if type(value[field]) is not int or not 0 <= value[field] <= 50000:
            raise ValueError("Invalid service count")
    generated = datetime.fromisoformat(value["generated_at"])
    expires = datetime.fromisoformat(value["expires_at"])
    if (generated.tzinfo is None or expires.tzinfo is None or generated > now + timedelta(minutes=1)
            or expires <= now or not generated < expires <= generated + timedelta(minutes=10)):
        raise ValueError("Stale service status")
    return dict(value)
