"""First observation timing with continuous coverage and a verified clock."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from collections.abc import Mapping

SIGNIFICANT_DELAY_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 90


def response_server_time(headers):
    try:
        value = parsedate_to_datetime(headers.get("Date", ""))
        age = int(headers.get("Age", "0"))
        if value.tzinfo is None or not 0 <= age <= 86400:
            return None
        return value.astimezone(timezone.utc) + timedelta(seconds=age)
    except (ValueError, TypeError, OverflowError, AttributeError):
        return None


def collection_messages(payload):
    """Require a complete active collection before treating absence as evidence."""
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        return (), False
    features = payload.get("features")
    pagination = payload.get("pagination") or {}
    if (not isinstance(features, list) or len(features) >= 500
            or not isinstance(pagination, Mapping) or pagination.get("next")):
        return (), False
    messages = []
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, Mapping) else None
        if not isinstance(properties, Mapping):
            return (), False
        if properties.get("status") != "Actual" or properties.get("messageType") not in ("Alert", "Update"):
            continue
        identifier = properties.get("id") or feature.get("id")
        try:
            issued = datetime.fromisoformat(properties["sent"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError):
            return (), False
        if not isinstance(identifier, str) or issued.tzinfo is None:
            return (), False
        messages.append((identifier, issued))
    return messages, True


class SourceLatencyTracker:
    def __init__(self, max_gap_seconds=120):
        self.max_gap = timedelta(seconds=max_gap_seconds)
        self.scopes = {}
        self.delayed_until = None

    def observe(self, scope, messages, received_at, server_time, *, complete=True):
        self.scopes = {key: row for key, row in self.scopes.items()
                       if timedelta(0) <= received_at - row["checked"] <= self.max_gap}
        clock_valid = (isinstance(server_time, datetime) and server_time.tzinfo is not None
                       and abs((received_at - server_time).total_seconds()) <= MAX_CLOCK_SKEW_SECONDS)
        if not complete or not clock_valid:
            self.scopes.pop(scope, None)
            return False
        previous = self.scopes.get(scope)
        if previous and server_time < previous["source_checked"]:
            previous = None
        known = dict(previous["messages"]) if previous else {}
        significant = False
        for identifier, issued_at in messages:
            if not isinstance(identifier, str) or len(identifier) > 500:
                continue
            if (identifier not in known and previous and isinstance(issued_at, datetime)
                    and issued_at.tzinfo is not None
                    and previous["since"] < issued_at < previous["source_checked"]
                    and (server_time - issued_at).total_seconds() >= SIGNIFICANT_DELAY_SECONDS):
                significant = True
            known[identifier] = received_at
        # Keep only short lived public message references, never alert text or phone data.
        known = {key: seen for key, seen in known.items() if received_at - seen <= timedelta(hours=2)}
        self.scopes[scope] = {"since": previous["since"] if previous else server_time,
                             "source_checked": server_time, "checked": received_at,
                             "messages": dict(list(known.items())[-5000:])}
        if len(self.scopes) > 100:
            self.scopes = dict(list(self.scopes.items())[-100:])
        if significant:
            self.delayed_until = received_at + timedelta(minutes=15)
        return significant

    def delayed(self, now):
        return self.delayed_until is not None and now < self.delayed_until
