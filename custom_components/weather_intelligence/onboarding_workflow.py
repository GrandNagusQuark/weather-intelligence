"""Persisted quick/guided/multiple-device flows; delivery remains a later step."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .onboarding_alerts import (
    SPECIAL_MARINE_EVENT, apply_alert_action, clear_alert_progress, selectable_pages,
)
from .onboarding_dnd import DND_FIELDS, DND_STAGES, apply_dnd_action, dnd_snapshot, enter_dnd_review
from .const import DEFAULT_BRIEFING_TIME
from .saved_device_settings import ADDITIONAL_PREFERENCE_FIELDS
from .marine_preferences import MARINE_NEARBY_FIELDS, marine_nearby_preferences

FLOW_STAGES = {"multiple_settings", "multiple_devices", "guided", "recommendations", "guided_marine", "intro", "saved_settings", "daily_outlook", *DND_STAGES}
CONFIGURATION_STAGES = {"single_device_setup", "guided", "recommendations", "guided_marine", "intro", "saved_settings", "alert_choices", "alert_dnd", "notification_setup", "daily_outlook", *DND_STAGES}
QUESTIONS = ("marine", "shoreline", "avalanche", "volcanic")
INTEREST_EVENTS = {
    "marine": {"special marine warning", "gale warning", "gale watch", "storm warning", "storm watch", "hazardous seas warning", "hazardous seas watch", "small craft advisory", "brisk wind advisory", "lake wind advisory", "low water advisory", "heavy freezing spray warning", "heavy freezing spray watch", "freezing spray advisory"},
    "shoreline": {"beach hazards statement", "coastal flood warning", "coastal flood advisory", "coastal flood watch", "coastal flood statement", "lakeshore flood warning", "lakeshore flood advisory", "lakeshore flood watch", "lakeshore flood statement", "high surf warning", "high surf advisory", "rip current statement", "storm surge warning", "storm surge watch", "tsunami warning", "tsunami advisory", "tsunami watch"},
    "avalanche": {"avalanche warning", "avalanche advisory", "avalanche watch"},
    "volcanic": {"volcano warning", "ashfall warning", "ashfall advisory"},
}
DRAFT_FIELDS = ("alert_path", "alert_answers", "alert_cursor", "alert_pages_version", "alert_selection_complete", "dnd_bypass", "marine_warning_mode", "guided_index", "guided_answers", "alert_intro_next", "daily_outlook_enabled", "daily_outlook_time", *DND_FIELDS, *ADDITIONAL_PREFERENCE_FIELDS, *MARINE_NEARBY_FIELDS)


def clear_choices(state: dict[str, Any]) -> None:
    clear_alert_progress(state)
    for key in ("guided_index", "guided_answers", "alert_intro_next", "daily_outlook_enabled", "daily_outlook_time", *ADDITIONAL_PREFERENCE_FIELDS):
        state.pop(key, None)


def selection_stage(state: Mapping[str, Any]) -> str:
    return "multiple_devices" if state.get("device_count") == "multiple" else "single_device"


def selected_ids(state: Mapping[str, Any]) -> list[str]:
    if state.get("device_count") == "multiple":
        return list(state.get("selected_device_ids") or [])
    return [state["selected_device_id"]] if state.get("selected_device_id") else []


def individual(state: Mapping[str, Any]) -> bool:
    return state.get("device_count") == "multiple" and state.get("multiple_settings") == "individual"


def active_ids(state: Mapping[str, Any]) -> list[str]:
    devices = selected_ids(state)
    index = state.get("active_device_index", 0)
    return devices[index:index + 1] if individual(state) else devices


def cache_choices(state: dict[str, Any]) -> None:
    if state.get("stage") not in CONFIGURATION_STAGES or state.get("stage") == "saved_settings":
        return
    draft = {key: deepcopy(state[key]) for key in DRAFT_FIELDS if key in state}
    draft.update(owner=state["target_user_id"], mode=state.get("setup_mode"))
    for device in active_ids(state):
        state.setdefault("device_drafts", {})[device] = deepcopy(draft)


def marine_included(state: Mapping[str, Any]) -> bool:
    if state.get("alert_path") in {"all", "life_only", "life_plus"}:
        return True
    return bool(state.get("alert_answers", {}).get(SPECIAL_MARINE_EVENT, False))


def recommendations(state: dict[str, Any]) -> None:
    answers = {}
    for page in selectable_pages("choose_all"):
        if page.get("kind") == "transition":
            continue
        for item in [page, *(page[tier] for tier in ("advisory", "watch", "statement") if page.get(tier))]:
            answers.update({event: bool(item["recommended"]) for event in item.get("event_ids", [item["id"]])})
    if state.get("setup_mode") == "guided":
        interests = state.get("guided_answers", {})
        if any(type(interests.get(question)) is not bool for question in QUESTIONS):
            raise ValueError("Answer each guided question before reviewing recommendations.")
        for question, events in INTEREST_EVENTS.items():
            for event in events:
                answers[event] = interests[question]
    for warning in ("tornado warning", "severe thunderstorm warning"):
        answers[warning.removesuffix(" warning") + " watch"] = answers.get(warning, False)
    state.update(alert_path="choose_all", alert_answers=answers, alert_cursor=0,
                 alert_selection_complete=True, stage="recommendations")
    if not answers.get(SPECIAL_MARINE_EVENT):
        state.pop("marine_warning_mode", None)


def show_intro(state: dict[str, Any]) -> None:
    """Explain alerts before preferences, not after an alert path was selected."""
    state["alert_intro_next"] = state["stage"]
    state["stage"] = "intro"


def configure(state: dict[str, Any], *, include_intro: bool = False, ask_saved: bool = True) -> None:
    devices = selected_ids(state)
    if not devices or (state.get("device_count") == "multiple" and
                       (len(devices) < 2 or state.get("multiple_settings") not in {"shared", "individual"})):
        raise ValueError("Choose the devices and their shared or individual setup first.")
    current = active_ids(state)
    if not current:
        raise ValueError("Choose an available device before continuing.")
    draft = state.get("device_drafts", {}).get(current[0], {})
    clear_choices(state)
    if draft.get("owner") == state["target_user_id"] and draft.get("mode") == state.get("setup_mode"):
        state.update({key: deepcopy(draft[key]) for key in DRAFT_FIELDS if key in draft})
    state["selected_device_id"] = current[0]
    mode = state.get("setup_mode")
    if mode == "quick":
        recommendations(state)
    elif mode == "guided":
        state["stage"] = "guided"
    elif mode == "custom":
        state["stage"] = "single_device_setup"
    else:
        raise ValueError("Choose a setup mode first.")
    if ask_saved:
        state["saved_settings_include_intro"] = include_intro
        state["stage"] = "saved_settings"
    elif include_intro:
        show_intro(state)


def load_saved_preferences(state: dict[str, Any], preferences: Mapping[str, Any], *, include_intro: bool) -> None:
    from .saved_device_settings import portable_preferences
    preferences = portable_preferences(preferences)
    if not preferences:
        raise ValueError("Choose saved alert preferences to copy.")
    clear_choices(state)
    state.update(deepcopy(preferences))
    if state.get("alert_selection_complete") and state.get("alert_path") in {"choose_all", "life_plus"}:
        from .hazard_policy import alert_choices
        answers = state.setdefault("alert_answers", {})
        for choice in alert_choices():
            answers.setdefault(choice["value"], False)
        for warning in ("tornado warning", "severe thunderstorm warning"):
            answers[warning.removesuffix(" warning") + " watch"] = answers[warning]
    state.update(alert_pages_version=3, alert_cursor=0, dnd_bypass_confirmed=False, copied_settings=True)
    ready = state.get("alert_path") in {"all", "life_only"} or state.get("alert_selection_complete") is True
    state["alert_selection_complete"] = ready
    if not ready:
        state["stage"] = "alert_choices"
    elif marine_included(state) and state.get("marine_warning_mode") not in {"always", "on_water"}:
        state["stage"] = "guided_marine"
    else:
        state["stage"] = "alert_dnd"
    if include_intro:
        show_intro(state)


def apply_workflow_action(state: dict[str, Any], payload: Mapping[str, Any], previous_stage: str,
                          *, saved_preferences: Mapping[str, Any] | None = None) -> bool:
    action = payload.get("workflow_action")
    if action is None:
        return False
    if payload.get("alert_action"):
        raise ValueError("Choose one onboarding action at a time.")
    allowed = {
        "configure_devices": {"single_device", "multiple_devices"},
        "saved_settings_fresh": {"saved_settings"}, "saved_settings_apply": {"saved_settings"}, "saved_settings_back": {"saved_settings"},
        "back_to_devices": CONFIGURATION_STAGES,
        "intro_next": {"intro"}, "intro_back": {"intro"},
        "guided_answer": {"guided"}, "guided_next": {"guided"}, "guided_back": {"guided"},
        "recommendations_next": {"recommendations"}, "recommendations_back": {"recommendations"},
        "marine_answer": {"guided_marine"}, "marine_next": {"guided_marine"}, "marine_back": {"guided_marine"},
        "delivery_next": {"alert_dnd"}, "delivery_back": {"alert_dnd"},
        "dnd_default": {"dnd_options"}, "dnd_custom": {"dnd_options"},
        "dnd_toggle": {"dnd_customize"}, "dnd_customize_next": {"dnd_customize"},
        "dnd_back": DND_STAGES, "dnd_confirm_next": {"dnd_confirm"},
        "daily_answer": {"daily_outlook"}, "daily_next": {"daily_outlook"}, "daily_back": {"daily_outlook"},
        "notification_back": {"notification_setup"},
    }
    if action not in allowed or previous_stage not in allowed[action] or state["stage"] != previous_stage:
        raise ValueError("Use the controls on the current onboarding screen.")
    if action == "configure_devices":
        state["active_device_index"] = 0
        configure(state, include_intro=True)
    elif action == "saved_settings_fresh":
        include_intro = state.get("saved_settings_include_intro", True)
        for device_id in active_ids(state):
            state.get("device_drafts", {}).pop(device_id, None)
        state.pop("copied_settings", None)
        configure(state, include_intro=include_intro, ask_saved=False)
    elif action == "saved_settings_apply":
        load_saved_preferences(state, saved_preferences or {}, include_intro=state.get("saved_settings_include_intro", True))
    elif action == "saved_settings_back":
        state["stage"] = selection_stage(state)
    elif action == "back_to_devices":
        cache_choices(state)
        if previous_stage == "single_device_setup":
            show_intro(state)
        else:
            state["stage"] = selection_stage(state)
    elif action == "intro_next":
        state["stage"] = state.get("alert_intro_next", "single_device_setup")
    elif action == "intro_back":
        state.update(stage="saved_settings", saved_settings_include_intro=True)
    elif action.startswith("guided_"):
        index = min(max(int(state.get("guided_index", 0)), 0), len(QUESTIONS) - 1)
        question = QUESTIONS[index]
        answers = state.setdefault("guided_answers", {})
        if action == "guided_answer":
            if payload.get("guided_question") != question or type(payload.get("guided_answer")) is not bool:
                raise ValueError("Answer the current guided question.")
            answers[question] = payload["guided_answer"]
        elif action == "guided_next":
            if type(answers.get(question)) is not bool:
                raise ValueError("Answer this question before continuing.")
            if index + 1 == len(QUESTIONS):
                recommendations(state)
            else:
                state["guided_index"] = index + 1
        elif index:
            state["guided_index"] = index - 1
        else:
            cache_choices(state)
            show_intro(state)
    elif action == "recommendations_next":
        state["stage"] = "guided_marine" if marine_included(state) else "alert_dnd"
    elif action == "recommendations_back":
        if state.get("setup_mode") == "guided":
            state.update(stage="guided", guided_index=len(QUESTIONS) - 1)
        else:
            cache_choices(state)
            show_intro(state)
    elif action == "marine_answer":
        if payload.get("marine_warning_mode") not in {"always", "on_water"}:
            raise ValueError("Choose when to receive Special Marine Warnings.")
        state["marine_warning_mode"] = payload["marine_warning_mode"]
        state.update(marine_nearby_preferences({**state, **{key: payload[key] for key in MARINE_NEARBY_FIELDS if key in payload}}))
    elif action == "marine_next":
        if state.get("marine_warning_mode") not in {"always", "on_water"}:
            raise ValueError("Choose when to receive Special Marine Warnings.")
        state["stage"] = "alert_dnd"
    elif action == "marine_back":
        if state.get("copied_settings"):
            show_intro(state)
        else:
            state["stage"] = "recommendations"
    elif apply_dnd_action(state, payload):
        pass
    elif action == "delivery_back":
        if state.get("setup_mode") in {"quick", "guided"}:
            state["stage"] = "guided_marine" if marine_included(state) else "recommendations"
        else:
            apply_alert_action(state, {"alert_action": "back_to_alerts"}, previous_stage)
    elif action in {"delivery_next", "dnd_confirm_next"}:
        if type(state.get("dnd_bypass")) is not bool or not state.get("alert_selection_complete"):
            raise ValueError("Finish choosing alerts and a Do Not Disturb preference first.")
        if marine_included(state) and state.get("marine_warning_mode") not in {"always", "on_water"}:
            raise ValueError("Choose when to receive Special Marine Warnings first.")
        if action == "delivery_next":
            enter_dnd_review(state)
            return True
        if state.get("dnd_bypass") and state.get("dnd_bypass_mode") not in {"default", "custom"}:
            raise ValueError("Choose default or custom Do Not Disturb alerts first.")
        state["dnd_bypass_rules"] = dnd_snapshot(state)["selected"]
        state["dnd_bypass_confirmed"] = True
        state["stage"] = "daily_outlook"
    elif action == "daily_answer":
        if type(payload.get("daily_outlook_enabled")) is not bool:
            raise ValueError("Choose whether to receive a daily outlook.")
        state["daily_outlook_enabled"] = payload["daily_outlook_enabled"]
        value = payload.get("daily_outlook_time", state.get("daily_outlook_time", DEFAULT_BRIEFING_TIME))
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":" or not value[:2].isdigit() or not value[3:].isdigit() or int(value[:2]) > 23 or int(value[3:]) > 59:
            raise ValueError("Choose a valid daily outlook time.")
        state["daily_outlook_time"] = value
    elif action == "daily_back":
        state["stage"] = "dnd_confirm"
    elif action == "daily_next":
        if not state.get("dnd_bypass_confirmed") or type(state.get("daily_outlook_enabled")) is not bool:
            raise ValueError("Confirm your DND and daily outlook choices first.")
        cache_choices(state)
        if individual(state) and state.get("active_device_index", 0) + 1 < len(selected_ids(state)):
            state["active_device_index"] = state.get("active_device_index", 0) + 1
            configure(state)
        else:
            state["stage"] = "notification_setup"
            state["notification_device_index"] = 0
    elif action == "notification_back":
        state["stage"] = "daily_outlook" if type(state.get("daily_outlook_enabled")) is bool else "alert_dnd"
    return True
