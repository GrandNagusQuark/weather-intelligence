"""Strict manual feedback payload. Free text is reviewed, never promised anonymous."""

from datetime import datetime
import ipaddress
import re
import unicodedata

FEEDBACK_PATH = "/v1/feedback"
MAX_FEEDBACK_BYTES = 8192
MAX_MESSAGE_CHARS = 1000
FIELDS = ("schema_version", "feedback_id", "category", "message", "integration_version",
          "home_assistant_version", "timestamp", "mobile_platform", "mobile_os_version", "companion_app_version")
CATEGORIES = {"bug", "idea", "other"}
VERSION = re.compile(r"\d{1,4}\.\d{1,4}(?:\.\d{1,4})?(?:(?:[a-z]\d+)|-alpha)?", re.ASCII)
MINUTE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\+00:00", re.ASCII)
PRIVATE_TEXT = re.compile(
    r"https?://|www\.|[\w.+%-]+@[\w.-]+\.[a-z]{2,}"
    r"|\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b"
    r"|[-+]?\d{1,3}\.\d{3,}\s*[, ]\s*[-+]?\d{1,3}\.\d{3,}"
    r"|\b(?:password|token|api[ _-]?key|authorization|secret)\s*[:=]\s*\S+"
    r"|\b[a-z0-9_-]{32,}\b", re.IGNORECASE)


def validate_message(value):
    if (not isinstance(value, str) or not 3 <= len(value) <= MAX_MESSAGE_CHARS
            or len(value.encode("utf-8")) > 4000 or not value.strip()
            or any(unicodedata.category(char) in {"Cc", "Cf"} and char not in "\n\t" for char in value)):
        raise ValueError("Write 3 to 1000 characters of plain feedback.")
    if PRIVATE_TEXT.search(value):
        raise ValueError("Remove links, addresses, coordinates, credentials and long identifiers before reviewing.")
    for candidate in re.findall(r"[0-9a-f:]+", value, re.IGNORECASE):
        if candidate.count(":") < 2:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        raise ValueError("Remove IP addresses before reviewing.")
    return value


def validate_feedback(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError("Unexpected feedback fields")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["feedback_id"], str)
            or re.fullmatch(r"[a-f0-9]{32}", value["feedback_id"]) is None
            or not isinstance(value["category"], str) or value["category"] not in CATEGORIES):
        raise ValueError("Invalid feedback")
    validate_message(value["message"])
    for field in ("integration_version", "home_assistant_version"):
        item = value[field]
        if item == "unknown" and field == "home_assistant_version":
            continue
        if not isinstance(item, str) or len(item) > 20 or VERSION.fullmatch(item) is None:
            raise ValueError("Invalid software version")
    if not isinstance(value["timestamp"], str) or MINUTE.fullmatch(value["timestamp"]) is None:
        raise ValueError("Invalid feedback time")
    datetime.fromisoformat(value["timestamp"])
    platform = value["mobile_platform"]
    if not isinstance(platform, str) or platform not in {"android", "ios", "unknown"}:
        raise ValueError("Invalid phone context")
    for field, pattern in (("mobile_os_version", r"\d{1,2}(?:\.\d{1,2}){0,2}"),
                           ("companion_app_version", r"20\d{2}\.(?:[1-9]|0[1-9]|1[0-2])(?:\.\d{1,3})?")):
        item = value[field]
        if (not isinstance(item, str) or item != "unknown" and re.fullmatch(pattern, item, re.ASCII) is None
                or platform == "unknown" and item != "unknown"):
            raise ValueError("Invalid phone context")
    return {field: value[field] for field in FIELDS}
