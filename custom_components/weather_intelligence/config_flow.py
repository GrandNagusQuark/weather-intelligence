"""Guided configuration and household profile management."""
from __future__ import annotations

from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector, EntityFilterSelectorConfig, EntitySelector, EntitySelectorConfig,
    SelectSelector, SelectSelectorConfig, TextSelector,
)

from .config import effective_entry_config, normalize_profile_input, normalize_profiles, profile_to_dict, profiles_from_config, profile_input_with_saved_choices
from .const import (
    BRIEFING_LOCATION_BOTH, BRIEFING_LOCATION_HOME, BRIEFING_LOCATION_PERSON,
    CONF_AUTOMATIC_NOTIFICATIONS, CONF_CONTACT, CONF_CRITICAL_NOTIFICATIONS,
    CONF_BRIEFING_ENABLED, CONF_BRIEFING_LOCATION, CONF_HAZARD_FAMILIES,
    CONF_LEGACY_NOTIFY_SERVICE, CONF_NOTIFY_ENTITY, CONF_PERSON_ENTITY, CONF_PROFILES,
    CONF_MOBILE_PLATFORM,
    CONF_SHOW_LOCATION_ON_MAP,
    CONF_PROFILE_ENABLED, CONF_PROFILE_ID, CONF_PROFILE_NAME, CONF_RECEIVE_HOME_AWAY,
    CONF_RECEIVE_PERSONAL, DOMAIN,
    MOBILE_PLATFORM_ANDROID, MOBILE_PLATFORM_AUTO, MOBILE_PLATFORM_IOS,
)
from .hazard_policy import HazardFamily
from .models import HouseholdProfile


class _ProfileEditor:
    def _start_editor(self, entry: Any) -> None:
        self._profiles = list(profiles_from_config(effective_entry_config(entry)))
        self._selected_profile_id = None
        self._pending_profile = None
        self._pending_index = None

    async def async_step_profile_menu(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="profile_menu", menu_options=[
            "review_profiles", "add_profile", "edit_profile", "remove_profile", "save_profiles"
        ])

    async def async_step_review_profiles(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_profile_menu()
        return self.async_show_form(step_id="review_profiles", data_schema=vol.Schema({
            vol.Optional("profile_summary"): SelectSelector(SelectSelectorConfig(options=[
                {"value": p.profile_id, "label": f"{p.name} — {'enabled' if p.enabled else 'disabled'}; automatic {'on' if p.automatic_notifications else 'off'}; critical {'on' if p.critical_notifications else 'off'}"}
                for p in self._profiles
            ]))
        }), errors={})

    async def async_step_add_profile(self, user_input=None) -> ConfigFlowResult:
        return await self._profile_form(user_input, None)

    async def async_step_edit_profile(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._selected_profile_id = str(user_input[CONF_PROFILE_ID])
            return await self.async_step_edit_profile_details()
        if not self._profiles:
            return await self.async_step_profile_menu()
        return self.async_show_form(step_id="edit_profile", data_schema=_choice_schema(self._profiles), errors={})

    async def async_step_edit_profile_details(self, user_input=None) -> ConfigFlowResult:
        return await self._profile_form(user_input, _profile_index(self._profiles, self._selected_profile_id))

    async def _profile_form(self, user_input, index) -> ConfigFlowResult:
        current = self._profiles[index] if index is not None else None
        errors = {}
        if user_input is not None:
            try:
                pending = normalize_profile_input(profile_input_with_saved_choices(user_input,current), existing_id=current.profile_id if current else None)
                proposed = list(self._profiles)
                proposed.append(pending) if index is None else proposed.__setitem__(index, pending)
                normalize_profiles([profile_to_dict(p) for p in proposed])
            except ValueError:
                errors["base"] = "invalid_profile"
            else:
                self._pending_profile, self._pending_index = pending, index
                if pending.automatic_notifications and (current is None or not current.automatic_notifications):
                    return self.async_show_form(step_id="confirm_automatic", data_schema=vol.Schema({}), errors={})
                if pending.critical_notifications and (current is None or not current.critical_notifications):
                    return self.async_show_form(step_id="confirm_critical", data_schema=vol.Schema({}), errors={})
                return await self._commit_pending()
        suggested = profile_to_dict(current) if current else {}
        return self.async_show_form(step_id="edit_profile_details" if current else "add_profile", data_schema=_profile_schema(self.hass, user_input or suggested), errors=errors)

    async def async_step_confirm_automatic(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="confirm_automatic", data_schema=vol.Schema({}), errors={})
        if self._pending_profile.critical_notifications:
            return self.async_show_form(step_id="confirm_critical", data_schema=vol.Schema({}), errors={})
        return await self._commit_pending()

    async def async_step_confirm_critical(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="confirm_critical", data_schema=vol.Schema({}), errors={})
        return await self._commit_pending()

    async def _commit_pending(self) -> ConfigFlowResult:
        if self._pending_index is None:
            self._profiles.append(self._pending_profile)
        else:
            self._profiles[self._pending_index] = self._pending_profile
        self._pending_profile, self._pending_index = None, None
        return await self.async_step_profile_menu()

    async def async_step_remove_profile(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._selected_profile_id = str(user_input[CONF_PROFILE_ID])
            return self.async_show_form(step_id="confirm_remove_profile", data_schema=vol.Schema({}), errors={})
        if not self._profiles:
            return await self.async_step_profile_menu()
        return self.async_show_form(step_id="remove_profile", data_schema=_choice_schema(self._profiles), errors={})

    async def async_step_confirm_remove_profile(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="confirm_remove_profile", data_schema=vol.Schema({}), errors={})
        self._profiles = [p for p in self._profiles if p.profile_id != self._selected_profile_id]
        self._selected_profile_id = None
        return await self.async_step_profile_menu()


class WeatherIntelligenceConfigFlow(_ProfileEditor, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 4

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> config_entries.OptionsFlow:
        return WeatherIntelligenceOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                contact = str(user_input.get(CONF_CONTACT, "")).strip()
                if not contact:
                    raise ValueError
                profile_input = {CONF_PROFILE_NAME: "Primary profile", **user_input}
                profile = normalize_profile_input(profile_input_with_saved_choices(profile_input))
            except ValueError:
                errors["base"] = "invalid_selection"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                self._initial_data = {
                    CONF_CONTACT: contact,
                    CONF_CRITICAL_NOTIFICATIONS: False,
                    CONF_PROFILES: [profile_to_dict(profile)],
                }
                if profile.automatic_notifications:
                    return self.async_show_form(step_id="confirm_initial_automatic", data_schema=vol.Schema({}), errors={})
                return self.async_create_entry(title="Weather Intelligence", data=self._initial_data)
        return self.async_show_form(step_id="user", data_schema=_initial_schema(self.hass, user_input or {}), errors=errors)

    async def async_step_confirm_initial_automatic(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="confirm_initial_automatic", data_schema=vol.Schema({}), errors={})
        if profiles_from_config(self._initial_data)[0].critical_notifications:
            return self.async_show_form(step_id="confirm_initial_critical", data_schema=vol.Schema({}), errors={})
        return self.async_create_entry(title="Weather Intelligence", data=self._initial_data)

    async def async_step_confirm_initial_critical(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="confirm_initial_critical", data_schema=vol.Schema({}), errors={})
        return self.async_create_entry(title="Weather Intelligence", data=self._initial_data)

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        # Native flows do not provide a verified acting-user identity. Keep
        # profile writes in the authenticated panel rather than guess an actor.
        return self.async_abort(reason="authenticated_panel_required")

    async def async_step_save_profiles(self, user_input=None) -> ConfigFlowResult:
        return self.async_abort(reason="authenticated_panel_required")


class WeatherIntelligenceOptionsFlow(_ProfileEditor, config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_abort(reason="authenticated_panel_required")

    async def async_step_save_profiles(self, user_input=None) -> ConfigFlowResult:
        return self.async_abort(reason="authenticated_panel_required")


def _initial_schema(hass: Any, suggested: dict[str, Any]) -> vol.Schema:
    return vol.Schema({_required(CONF_CONTACT, suggested): TextSelector(), **_profile_schema(hass, suggested).schema})


def _profile_schema(hass: Any, suggested: dict[str, Any]) -> vol.Schema:
    schema = {
        _required(CONF_PROFILE_NAME, suggested): TextSelector(),
        _required(CONF_PERSON_ENTITY, suggested): EntitySelector(EntitySelectorConfig(filter=EntityFilterSelectorConfig(domain="person"), multiple=False)),
        _optional(CONF_NOTIFY_ENTITY, suggested): EntitySelector(EntitySelectorConfig(filter=EntityFilterSelectorConfig(domain="notify", integration="mobile_app"), multiple=False)),
        vol.Optional(CONF_MOBILE_PLATFORM, default=suggested.get(CONF_MOBILE_PLATFORM, MOBILE_PLATFORM_AUTO)): SelectSelector(SelectSelectorConfig(options=[
            {"value": MOBILE_PLATFORM_AUTO, "label": "Detect automatically"},
            {"value": MOBILE_PLATFORM_ANDROID, "label": "Android"},
            {"value": MOBILE_PLATFORM_IOS, "label": "iPhone"},
        ])),
        vol.Optional(CONF_PROFILE_ENABLED, default=bool(suggested.get(CONF_PROFILE_ENABLED, True))): BooleanSelector(),
        vol.Optional(CONF_SHOW_LOCATION_ON_MAP, default=suggested.get(CONF_SHOW_LOCATION_ON_MAP, "inherit")): SelectSelector(SelectSelectorConfig(options=[
            {"value": "inherit", "label": "Follow Home Assistant entity visibility"},
            {"value": "show", "label": "Explicitly show available location here"},
            {"value": "hide", "label": "Hide location on this weather map"},
        ])),
        vol.Optional(CONF_RECEIVE_PERSONAL, default=bool(suggested.get(CONF_RECEIVE_PERSONAL, True))): BooleanSelector(),
        vol.Optional(CONF_RECEIVE_HOME_AWAY, default=bool(suggested.get(CONF_RECEIVE_HOME_AWAY, False))): BooleanSelector(),
        vol.Optional(CONF_AUTOMATIC_NOTIFICATIONS, default=bool(suggested.get(CONF_AUTOMATIC_NOTIFICATIONS, False))): BooleanSelector(),
        vol.Optional(CONF_CRITICAL_NOTIFICATIONS, default=bool(suggested.get(CONF_CRITICAL_NOTIFICATIONS, False))): BooleanSelector(),
        vol.Optional(CONF_BRIEFING_ENABLED, default=bool(suggested.get(CONF_BRIEFING_ENABLED, False))): BooleanSelector(),
        vol.Optional(CONF_BRIEFING_LOCATION, default=suggested.get(CONF_BRIEFING_LOCATION, BRIEFING_LOCATION_HOME)): SelectSelector(SelectSelectorConfig(options=[
            {"value": BRIEFING_LOCATION_HOME, "label": "Designated home"},
            {"value": BRIEFING_LOCATION_PERSON, "label": "This person's current location"},
            {"value": BRIEFING_LOCATION_BOTH, "label": "Designated home and current location"},
        ])),
    }
    legacy = _legacy_options(hass)
    if legacy:
        schema[_optional(CONF_LEGACY_NOTIFY_SERVICE, suggested)] = SelectSelector(SelectSelectorConfig(options=legacy))
    return vol.Schema(schema)


def _choice_schema(profiles):
    return vol.Schema({vol.Required(CONF_PROFILE_ID): SelectSelector(SelectSelectorConfig(options=[{"value": p.profile_id, "label": p.name} for p in profiles]))})


def _profile_index(profiles, profile_id):
    return next(i for i, p in enumerate(profiles) if p.profile_id == profile_id)


def _legacy_options(hass):
    return [{"value": f"notify.{s}", "label": s.removeprefix("mobile_app_").replace("_", " ").title()} for s in sorted(hass.services.async_services().get("notify", {})) if s.startswith("mobile_app_")]


def _required(name, suggested):
    return vol.Required(name, default=suggested[name]) if suggested.get(name) else vol.Required(name)


def _optional(name, suggested):
    return vol.Optional(name, default=suggested[name]) if suggested.get(name) else vol.Optional(name)
