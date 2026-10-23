"""One consent-scoped random installation number, stored only on this HA."""
from __future__ import annotations

import re
import secrets
from .config import effective_entry_config
from .const import DOMAIN
from .reporting_config import reporting_config, reporting_review_required


async def async_saved_reporting_identity(hass, entry, store=None):
    """Read an existing number for the administrator without creating or changing it."""
    if store is None:
        from homeassistant.helpers.storage import Store
        store = Store(hass, 1, f'{DOMAIN}.outage_identity.{entry.entry_id}')
    saved = await store.async_load()
    identifier = saved.get('installation_id') if isinstance(saved, dict) else None
    return identifier if isinstance(identifier, str) and re.fullmatch(r'[a-f0-9]{64}', identifier) else None


async def async_reporting_identity(hass, entry, store=None):
    if store is None:
        from homeassistant.helpers.storage import Store
        # Keep the existing outage identity when consent is renewed, rather than
        # silently splitting one participating installation into two identities.
        store=Store(hass,1,f'{DOMAIN}.outage_identity.{entry.entry_id}')
    config=effective_entry_config(entry)
    if not reporting_config(config)['enabled']:
        if not reporting_review_required(config):
            await store.async_remove()
        return None
    saved=await store.async_load()
    identifier=saved.get('installation_id') if isinstance(saved,dict) else None
    if not isinstance(identifier,str) or re.fullmatch(r'[a-f0-9]{64}',identifier) is None:
        identifier=secrets.token_hex(32)
        await store.async_save({'installation_id':identifier})
    return identifier
