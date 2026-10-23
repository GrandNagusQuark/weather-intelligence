"""Small public error vocabulary. Never serialize arbitrary exception data."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

from .const import PROTOTYPE_VERSION
from .mqtt_error_logging import build_error_payload
from .reporting_diagnostics import EXCEPTION_TYPES, build_diagnostics
from .reporting_device import MOBILE_FIELDS, VERSION_CONTEXT_FIELDS, safe_mobile_context, safe_installation_context

ERROR_CODES = frozenset({
    "request_timeout", "phone_unavailable", "notification_delivery_failed",
    "official_source_failed", "invalid_data", "integration_error",
})
COMPONENTS = frozenset({
    "delivery", "automatic_delivery", "mobile_notification", "ha_coordinator",
    "nws_client", "official_sources", "panel", "mqtt_error_logging", "mrms_hail", "integration",
})
REPORT_FIELDS = (
    "schema_version", "integration_version", "home_assistant_version", "timestamp",
    "error_code", "component", "level", "exception_type", *MOBILE_FIELDS,
)
LINKED_REPORT_FIELDS = (*REPORT_FIELDS, 'installation_id')
CONTEXT_REPORT_FIELDS = (*LINKED_REPORT_FIELDS, *VERSION_CONTEXT_FIELDS)
DIAGNOSTIC_REPORT_FIELDS = (*CONTEXT_REPORT_FIELDS, 'diagnostics')


def build_report(record: logging.LogRecord, ha_version: str = "unknown", installation_id: str | None = None, version_context=None) -> dict[str, Any]:
    """Reuse local classification, then rebuild an even smaller wire document."""
    classified = json.loads(build_error_payload(record, home_assistant_version=ha_version))
    component = classified["logger"].rsplit(".", 1)[-1]
    document = {
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
    if installation_id is not None:
        if not isinstance(installation_id,str) or re.fullmatch(r'[a-f0-9]{64}',installation_id) is None:
            raise ValueError('Invalid diagnostic installation number')
        document.update(schema_version=3,installation_id=installation_id)
        if version_context is not None:
            details = build_diagnostics(record)
            document.update(schema_version=5, **safe_installation_context(version_context), diagnostics=details)
            if details['causes']:
                document['exception_type'] = details['causes'][0]['type']
            if any(cause['type'] in {'TimeoutError','ServerTimeoutError'} for cause in details['causes']):
                document['error_code'] = 'request_timeout'
            elif document['error_code'] == 'integration_error' and any(
                    frame['module'] in {'mrms_hail','nws_client','official_sources'} for frame in details['frames']):
                document['error_code'] = 'official_source_failed'
    return document


def report_preview(ha_version='unknown', version_context=None) -> dict[str, Any]:
    record = logging.LogRecord(
        "custom_components.weather_intelligence.nws_client", logging.ERROR,
        "", 0, "Request timed out", (), (TimeoutError, TimeoutError(), None),
    )
    document = build_report(record, ha_version, installation_id='0'*64,
        version_context=version_context or {'device_versions': [], 'device_versions_status': 'registration_unavailable'})
    document["timestamp"] = "2026-01-01T00:00:00+00:00"
    return document
