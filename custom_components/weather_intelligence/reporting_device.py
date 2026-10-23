"""Read only coarse software versions for the phone involved in an error."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

MOBILE_FIELDS = ("mobile_platform", "mobile_os_version", "companion_app_version")
VERSION_CONTEXT_FIELDS = ('device_versions', 'device_versions_status')
VERSION_CONTEXT_STATES = {'available', 'partial', 'no_enrolled_devices', 'registration_unavailable'}
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


def safe_installation_context(value):
    """A bounded list of software combinations, without device names or counts."""
    if not isinstance(value, Mapping) or set(value) != set(VERSION_CONTEXT_FIELDS):
        raise ValueError('Invalid software context')
    rows, status = value['device_versions'], value['device_versions_status']
    if not isinstance(status, str) or status not in VERSION_CONTEXT_STATES or not isinstance(rows, list) or len(rows) > 8:
        raise ValueError('Invalid software context')
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(MOBILE_FIELDS) or safe_mobile_context(row) != row:
            raise ValueError('Invalid software context')
    if status == 'available' and not rows or status in {'no_enrolled_devices', 'registration_unavailable'} and rows:
        raise ValueError('Invalid software context')
    return {'device_versions': [dict(row) for row in rows], 'device_versions_status': status}


def installation_version_context(hass, config):
    """Read only phones enrolled in WI, for every error regardless of its origin."""
    from .config import profiles_from_config
    try:
        profiles = profiles_from_config(config)
        if not profiles:
            return {'device_versions': [], 'device_versions_status': 'no_enrolled_devices'}
        entries = list(hass.config_entries.async_entries('mobile_app'))
        combinations, missing = set(), False
        for profile in profiles:
            entry = next((item for item in entries if item.entry_id == profile.companion_device_id), None)
            if entry is None and profile.legacy_notify_service.startswith('notify.mobile_app_'):
                target = profile.legacy_notify_service.removeprefix('notify.mobile_app_')
                matches = [item for item in entries if target in {
                    re.sub(r'[^a-z0-9]+', '_', str(name).casefold()).strip('_')
                    for name in (getattr(item, 'title', ''), item.data.get('device_name', '')) if name}]
                if len(matches) == 1:
                    entry = matches[0]
            if entry is None:
                missing = True
                continue
            context = mobile_report_context(hass, entry.entry_id)
            missing = missing or 'unknown' in context.values()
            combinations.add(tuple(context[field] for field in MOBILE_FIELDS))
        rows = [dict(zip(MOBILE_FIELDS, row)) for row in sorted(combinations)[:8]]
        return safe_installation_context({'device_versions': rows,
            'device_versions_status': 'registration_unavailable' if not rows else
            'partial' if missing or len(combinations) > 8 else 'available'})
    except (AttributeError, TypeError, ValueError, KeyError):
        return {'device_versions': [], 'device_versions_status': 'registration_unavailable'}
