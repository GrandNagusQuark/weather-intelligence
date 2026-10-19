"""Small public error vocabulary. Never serialize arbitrary exception data."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from .const import PROTOTYPE_VERSION
from .mqtt_error_logging import build_error_payload
from .reporting_device import MOBILE_FIELDS, safe_mobile_context

ERROR_CODES = frozenset({
    "request_timeout", "phone_unavailable", "notification_delivery_failed",
    "official_source_failed", "invalid_data", "integration_error",
})
COMPONENTS = frozenset({
    "delivery", "automatic_delivery", "mobile_notification", "ha_coordinator",
    "nws_client", "official_sources", "panel", "mqtt_error_logging", "mrms_hail", "integration",
})
EXCEPTION_TYPES = frozenset({
    "TimeoutError", "ConnectionError", "OSError", "ValueError", "TypeError", "KeyError",
    "MobileTargetError", "NwsClientError", "AlertNormalizationError", "Error",
})
REPORT_FIELDS = (
    "schema_version", "integration_version", "home_assistant_version", "timestamp",
    "error_code", "component", "level", "exception_type", *MOBILE_FIELDS,
)


def build_report(record: logging.LogRecord, ha_version: str = "unknown") -> dict[str, Any]:
    """Reuse local classification, then rebuild an even smaller wire document."""
    classified = json.loads(build_error_payload(record, home_assistant_version=ha_version))
    component = classified["logger"].rsplit(".", 1)[-1]
    return {
        "schema_version": 2,
        "integration_version": PROTOTYPE_VERSION,
        "home_assistant_version": classified["home_assistant_version"],
        "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
        .replace(second=0, microsecond=0).isoformat(),
        "error_code": classified["error_code"],
        "component": component if component in COMPONENTS else "integration",
        "level": classified["level"],
        "exception_type": classified.get("exception_type", "Error"),
        **safe_mobile_context(getattr(record, "wi_mobile_context", None)),
    }


def report_preview() -> dict[str, Any]:
    record = logging.LogRecord(
        "custom_components.weather_intelligence.nws_client", logging.ERROR,
        "", 0, "Request timed out", (), None,
    )
    document = build_report(record)
    document["timestamp"] = "2026-01-01T00:00:00+00:00"
    return document
