"""Read only coarse software versions for the phone involved in an error."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

MOBILE_FIELDS = ("mobile_platform", "mobile_os_version", "companion_app_version")
_OS_VERSION = re.compile(r"\d{1,2}(?:\.\d{1,2}){0,2}", re.ASCII)
_APP_VERSION = re.compile(
    r"(20\d{2}\.(?:[1-9]|0[1-9]|1[0-2])(?:\.\d{1,3})?)(?:-(?:full|minimal))?(?: \([0-9.]{1,20}\))?",
    re.ASCII,
)


def safe_mobile_context(value: Any) -> dict[str, str]:
    result = dict.fromkeys(MOBILE_FIELDS, "unknown")
    if not isinstance(value, Mapping):
        return result
    platform = value.get("mobile_platform")
    if platform not in ("android", "ios"):
        return result
    result["mobile_platform"] = platform
    os_version = value.get("mobile_os_version")
    if isinstance(os_version, str) and _OS_VERSION.fullmatch(os_version):
        result["mobile_os_version"] = os_version
    app_version = value.get("companion_app_version")
    match = _APP_VERSION.fullmatch(app_version) if isinstance(app_version, str) else None
    if match:
        # Drop build numbers and app flavor, even if the registration provides them.
        result["companion_app_version"] = match[1]
    return result


def mobile_report_context(hass: Any, companion_entry_id: str) -> dict[str, str]:
    """No registry dumps or household inventory. Unknown means unknown."""
    try:
        entry = hass.config_entries.async_get_entry(companion_entry_id) if companion_entry_id else None
        data = entry.data if entry is not None and entry.domain == "mobile_app" else {}
        os_name = data.get("os_name")
        platform = {"Android": "android", "iOS": "ios"}.get(os_name, "unknown")
        return safe_mobile_context({"mobile_platform": platform,
            "mobile_os_version": data.get("os_version"), "companion_app_version": data.get("app_version")})
    except (AttributeError, KeyError, TypeError):
        return safe_mobile_context(None)
