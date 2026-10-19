"""Explicit destination and consent for optional maintainer reports."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit

REPORTING_KEY = "maintainer_reporting"
POLICY_VERSION = 2
REPORT_PATH = "/v1/errors"
PROJECT_REPORTING_ENDPOINT = "https://reports.weatherintelligence.app/v1/errors"
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_RESERVED_SUFFIXES = ("local", "localhost", "internal", "lan", "home", "test", "invalid", "example", "onion")


def validate_endpoint(value: Any) -> str:
    """Accept only a public DNS hostname and the fixed HTTPS reporting path."""
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("Enter a valid reporting destination.")
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as error:
        raise ValueError("Enter a valid reporting destination.") from error
    labels = host.split(".")
    if (
        parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
        or port not in (None, 443) or parsed.path != REPORT_PATH
        or parsed.query or parsed.fragment or len(labels) < 2
        or not all(_HOSTNAME.fullmatch(label) for label in labels)
        or not labels[-1].isalpha() or labels[-1] in _RESERVED_SUFFIXES
        or "example" in labels or any(ord(char) < 33 for char in value)
    ):
        raise ValueError("Use a public HTTPS domain ending in /v1/errors, without credentials or query parameters.")
    return f"https://{host}{REPORT_PATH}"


def reporting_config(config: Mapping[str, Any]) -> dict[str, Any]:
    raw = config.get(REPORTING_KEY, {})
    if not isinstance(raw, Mapping):
        raw = {}
    try:
        endpoint = validate_endpoint(raw.get("endpoint", ""))
    except ValueError:
        endpoint = ""
    enabled = bool(
        endpoint and raw.get("enabled") is True
        and raw.get("consent_endpoint") == endpoint
        and type(raw.get("policy_version")) is int and raw["policy_version"] == POLICY_VERSION
    )
    return {"endpoint": endpoint, "enabled": enabled, "policy_version": POLICY_VERSION}


def reporting_update(payload: Mapping[str, Any]) -> dict[str, Any]:
    endpoint = validate_endpoint(payload.get("endpoint", ""))
    enabled = payload.get("enabled", False)
    if type(enabled) is not bool:
        raise ValueError("Choose whether to enable reporting.")
    if enabled and (
        not endpoint or payload.get("consent") is not True
        or payload.get("consent_endpoint") != endpoint
        or type(payload.get("policy_version")) is not int
        or payload["policy_version"] != POLICY_VERSION
    ):
        raise ValueError("Review this destination and the report fields before enabling reporting.")
    return {
        "endpoint": endpoint, "enabled": enabled,
        "consent_endpoint": endpoint if enabled else "", "policy_version": POLICY_VERSION,
    }
