"""Concise NWS evidence and threat details, without changing alert eligibility."""

import re
from typing import Any

TORNADO_SHELTER_ACTION = (
    "Take shelter now in a basement or small interior room on the lowest floor."
)

_TORNADO_EVIDENCE = {"RADAR INDICATED", "OBSERVED", "POSSIBLE"}
_TORNADO_THREATS = {"CONSIDERABLE", "CATASTROPHIC"}
_STORM_THREATS = {"CONSIDERABLE", "DESTRUCTIVE"}


def _official_tag(alert: Any, field: str, label: str, allowed: set[str]) -> str:
    value = " ".join(str(getattr(alert, field, "") or "").upper().split())
    if value:
        return value if value in allowed else ""
    # Only the exact coded line is a fallback. Ordinary narrative mentioning a
    # possible tornado is not the standardized TORNADO...POSSIBLE tag.
    description = str(getattr(alert, "description", "") or "")
    match = re.search(r"(?im)^\s*" + re.escape(label) + r"\s*\.{3,}\s*([^\r\n]+)", description)
    candidate = " ".join(match.group(1).upper().split()) if match else ""
    return candidate if candidate in allowed else ""


def _tornado_threat(alert: Any) -> str:
    return _official_tag(alert, "tornado_damage_threat", "TORNADO DAMAGE THREAT", _TORNADO_THREATS)


def warning_title_suffix(alert: Any) -> str:
    if str(getattr(alert, "event", "")).casefold() != "tornado warning":
        return ""
    return {"CONSIDERABLE": " (PDS)", "CATASTROPHIC": " (Tornado Emergency)"}.get(
        _tornado_threat(alert), ""
    )


def _report_source(alert: Any) -> str:
    description = str(getattr(alert, "description", "") or "")
    match = re.search(
        r"(?ims)^\s*SOURCE\s*\.{3,}\s*(.{1,1000}?)(?=\n\s*\n|\n\s*(?:HAZARD|IMPACTS?|PRECAUTIONARY)\s*\.{3,}|\Z)",
        description,
    )
    if not match:
        return ""
    source = " ".join(match.group(1).split())
    source = "".join(character for character in source if character.isprintable())
    # The source is the official product's attribution, never an inferred role.
    if len(source) > 180:
        source = source[:177].rsplit(" ", 1)[0].rstrip(".,;") + "…"
    return "Source: " + source.rstrip(".") + "." if source else ""


def official_warning_details(alert: Any) -> str:
    event = str(getattr(alert, "event", "")).casefold()
    parts = []
    evidence = _official_tag(alert, "tornado_detection", "TORNADO", _TORNADO_EVIDENCE)
    if event == "tornado warning":
        parts.append(
            {
                "RADAR INDICATED": "Evidence: radar indicated; not confirmed.",
                "OBSERVED": "Evidence: observed (radar confirmation or reliable reports).",
            }.get(evidence, "Tornado evidence is not specified in this message.")
        )
        threat = _tornado_threat(alert)
        if threat == "CONSIDERABLE":
            parts.append("Damage threat: considerable — Particularly Dangerous Situation (PDS).")
        elif threat == "CATASTROPHIC":
            parts.append("Damage threat: catastrophic — Tornado Emergency.")
        else:
            # Missing fields on a follow-up are not an official downgrade.
            has_threat = bool(getattr(alert, "tornado_damage_threat", None)) or re.search(
                r"(?im)^\s*TORNADO DAMAGE THREAT\s*\.{3,}",
                str(getattr(alert, "description", "") or ""),
            )
            if str(getattr(alert, "message_type", "")).casefold() == "alert" and not has_threat:
                parts.append("Damage threat: Base (no additional NWS tag).")
            else:
                parts.append("Damage threat is not specified in this message.")
        source = _report_source(alert)
        if source:
            parts.append(source)
    elif event == "severe thunderstorm warning":
        if evidence == "POSSIBLE":
            parts.append("NWS tag: tornado possible.")
        threat = _official_tag(
            alert, "thunderstorm_damage_threat", "THUNDERSTORM DAMAGE THREAT", _STORM_THREATS
        )
        if threat:
            parts.append(f"Thunderstorm damage threat: {threat.lower()}.")
    return " ".join(parts)
