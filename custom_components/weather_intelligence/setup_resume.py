"""Resume an existing household wizard in place, not a second draft editor."""
from typing import Any, Mapping


def progress_owner(actor: Any, requested: str | None = None) -> str:
    if requested and requested != actor.id and not actor.is_admin:
        raise ValueError("Only administrators can resume another account's setup.")
    return requested or actor.id


async def async_unfinished_setups(hass: Any, entry: Any, actor: Any) -> list[dict]:
    from .config import effective_entry_config
    from .onboarding_accounts import ACCOUNT_PROGRESS, account_devices, human_account
    from .onboarding_workflow import selected_ids

    states = effective_entry_config(entry).get(ACCOUNT_PROGRESS, {})
    if not states:
        return []
    users = {user.id: user for user in await hass.auth.async_get_users() if human_account(user)}
    result = []
    for source_id, state in states.items():
        source = users.get(source_id)
        owner = users.get(state.get("target_user_id", source_id))
        if (not source or not owner or (source_id != actor.id and not actor.is_admin)
                or (owner.id != source_id and not source.is_admin)
                or not state.get("initiated") or state.get("stage") == "notification_complete"):
            continue
        devices = {device["id"]: device for device in account_devices(hass, owner.id)}
        for device_id in selected_ids(state):
            if device_id in devices:
                result.append({"name": (owner.name or "Household member") + " · " + devices[device_id]["name"],
                               "companion_device_id": device_id, "unfinished_setup": {"progress_user_id": source_id}})
    return result
