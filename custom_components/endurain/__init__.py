"""The Endurain integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EndurainClient
from .const import AUTH_TYPE_API_KEY, CONF_AUTH_TYPE, CONF_REFRESH_TOKEN
from .coordinator import EndurainConfigEntry, EndurainCoordinator

PLATFORMS: list[Platform] = [Platform.EVENT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: EndurainConfigEntry) -> bool:
    """Set up Endurain from a config entry."""

    @callback
    def _persist_refresh_token(token: str) -> None:
        # Endurain rotates refresh tokens; losing the newest one would
        # force a re-login after the next restart.
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_REFRESH_TOKEN: token})

    session = async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True))
    if entry.data[CONF_AUTH_TYPE] == AUTH_TYPE_API_KEY:
        client = EndurainClient(session, entry.data[CONF_URL], api_key=entry.data[CONF_API_KEY])
    else:
        client = EndurainClient(
            session,
            entry.data[CONF_URL],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
            on_refresh_token=_persist_refresh_token,
        )

    coordinator = EndurainCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EndurainConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
