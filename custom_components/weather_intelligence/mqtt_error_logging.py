"""Opt-in, privacy-filtered forwarding of integration errors over MQTT."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
import traceback
from typing import Any, Iterable

from .const import (
    CONF_MQTT_ERROR_LOGGING,
    CONF_MQTT_ERROR_TOPIC,
    DEFAULT_MQTT_ERROR_TOPIC,
    DOMAIN,
    PROTOTYPE_VERSION,
)

_LOGGER_NAME = f"custom_components.{DOMAIN}"
_MAX_MESSAGE = 2_000
_MAX_TRACEBACK = 6_000
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|token|password|authorization)"
    r"(\s*[=:]\s*|\s+)([^\s&,;]+)"
)


def validate_mqtt_topic(value: Any) -> str:
    """Validate a concrete publish topic; wildcards belong only to subscribers."""
    topic = str(value or DEFAULT_MQTT_ERROR_TOPIC).strip()
    if not topic or len(topic.encode("utf-8")) > 256:
        raise ValueError("MQTT error topic must contain 1–256 UTF-8 bytes")
    if "+" in topic or "#" in topic or "\x00" in topic:
        raise ValueError("MQTT error topic cannot contain wildcards or null bytes")
    return topic


def build_error_payload(
    record: logging.LogRecord,
    *,
    sensitive_values: Iterable[str] = (),
    home_assistant_version: str = "unknown",
) -> str:
    """Build a local allowlisted diagnostic, never transmit arbitrary log text."""
    # Regex redaction alone cannot prove absence of names, addresses or novel
    # secrets. Inspect locally, classify, then send only fixed safe wording.
    raw = _redact(record.getMessage(), sensitive_values)[:_MAX_MESSAGE]
    lowered = raw.casefold()
    if "timed out" in lowered or "timeout" in lowered:
        code, message = "request_timeout", "A weather-service request timed out."
    elif "notify entity" in lowered and "unavailable" in lowered:
        code, message = "phone_unavailable", "The configured phone notification target is unavailable."
    elif "delivery failed" in lowered:
        code, message = "notification_delivery_failed", "A configured notification could not be delivered."
    elif "nws" in lowered and ("failed" in lowered or "failure" in lowered):
        code, message = "official_source_failed", "An official weather-source request failed."
    elif "malformed" in lowered or "normalized" in lowered or "invalid" in lowered:
        code, message = "invalid_data", "The integration received invalid data or configuration."
    else:
        code, message = "integration_error", "An integration operation failed; review the local Home Assistant log."
    component = record.name.removeprefix(_LOGGER_NAME + ".")
    allowed_components = {"delivery", "automatic_delivery", "mobile_notification", "ha_coordinator",
                          "nws_client", "official_sources", "panel", "mqtt_error_logging", "mrms_hail"}
    logger = f"{_LOGGER_NAME}.{component}" if component in allowed_components else _LOGGER_NAME
    version = home_assistant_version if re.fullmatch(r"\d+\.\d+(?:\.\d+)?(?:[a-z]\d+)?", home_assistant_version) else "unknown"
    document = {
        "schema_version": 2,
        "integration": DOMAIN,
        "integration_version": PROTOTYPE_VERSION,
        "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        "home_assistant_version": version,
        "level": "CRITICAL" if record.levelno >= logging.CRITICAL else "ERROR",
        "logger": logger,
        "message": message,
        "error_code": code,
        "privacy_filter": "allowlisted; raw text and traceback [redacted]",
    }
    if record.exc_info and record.exc_info[0] is not None:
        error_type = record.exc_info[0].__name__
        document["exception_type"] = error_type if error_type in {
            "TimeoutError", "ConnectionError", "OSError", "ValueError", "TypeError", "KeyError",
            "MobileTargetError", "NwsClientError", "AlertNormalizationError",
        } else "Error"
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


class MqttErrorHandler(logging.Handler):
    """Send ERROR+ records without blocking the logging thread."""

    def __init__(
        self, hass: Any, topic: str, *, sensitive_values: Iterable[str] = ()
    ) -> None:
        super().__init__(logging.ERROR)
        self._hass = hass
        self.topic = validate_mqtt_topic(topic)
        self._sensitive_values = tuple(value for value in sensitive_values if value)
        try:
            from homeassistant.const import __version__
            self._ha_version = str(__version__)
        except ImportError:
            self._ha_version = "unknown"
        self.enabled = True
        self.published_count = 0
        self.failed_count = 0
        self.last_published_at: str | None = None
        self.last_failure = ""

    def emit(self, record: logging.LogRecord) -> None:
        if not self.enabled or not record.name.startswith(_LOGGER_NAME):
            return
        try:
            payload = build_error_payload(
                record, sensitive_values=self._sensitive_values,
                home_assistant_version=self._ha_version,
            )
            self._hass.loop.call_soon_threadsafe(self._schedule_publish, payload)
        except Exception:
            self.failed_count += 1
            self.last_failure = "The error record could not be prepared."

    def _schedule_publish(self, payload: str) -> None:
        if self.enabled:
            self._hass.loop.create_task(self._async_publish(payload))

    async def _async_publish(self, payload: str) -> None:
        try:
            from homeassistant.components.mqtt import async_publish

            await async_publish(
                self._hass,
                self.topic,
                payload,
                qos=1,
                retain=False,
            )
        except Exception as error:
            # Never log this through the integration logger: doing so would recurse.
            self.failed_count += 1
            self.last_failure = f"MQTT publish failed ({type(error).__name__})."
            return
        self.published_count += 1
        self.last_published_at = datetime.now(timezone.utc).isoformat()
        self.last_failure = ""

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "topic": self.topic,
            "published_errors": self.published_count,
            "failed_publishes": self.failed_count,
            "last_published_at": self.last_published_at,
            "last_failure": self.last_failure,
        }


def setup_mqtt_error_logging(hass: Any, entry: Any, config: dict[str, Any]) -> None:
    """Install one handler for an enabled config entry."""
    if not config.get(CONF_MQTT_ERROR_LOGGING, False):
        return
    data = hass.data.setdefault(DOMAIN, {})
    handlers = data.setdefault("mqtt_error_handlers", {})
    remove_mqtt_error_logging(hass, entry.entry_id)
    handler = MqttErrorHandler(
        hass,
        validate_mqtt_topic(config.get(CONF_MQTT_ERROR_TOPIC)),
        sensitive_values=(
            str(config.get("airnow_api_key", "")),
            str(config.get("contact", "")),
        ),
    )
    logging.getLogger(_LOGGER_NAME).addHandler(handler)
    handlers[entry.entry_id] = handler


def remove_mqtt_error_logging(hass: Any, entry_id: str) -> None:
    """Remove a handler without affecting Home Assistant's normal logging."""
    handlers = getattr(hass, "data", {}).get(DOMAIN, {}).get(
        "mqtt_error_handlers", {}
    )
    handler = handlers.pop(entry_id, None)
    if handler is not None:
        handler.enabled = False
        logging.getLogger(_LOGGER_NAME).removeHandler(handler)
        handler.close()


def mqtt_error_logging_status(hass: Any, entry: Any) -> dict[str, Any]:
    handler = getattr(hass, "data", {}).get(DOMAIN, {}).get(
        "mqtt_error_handlers", {}
    ).get(getattr(entry, "entry_id", ""))
    if handler is None:
        return {
            "enabled": False,
            "topic": DEFAULT_MQTT_ERROR_TOPIC,
            "published_errors": 0,
            "failed_publishes": 0,
            "last_published_at": None,
            "last_failure": "",
        }
    return handler.status()


def _redact(value: str, sensitive_values: Iterable[str]) -> str:
    result = value
    for sensitive in sensitive_values:
        if sensitive:
            result = result.replace(sensitive, "[redacted]")
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", result)
