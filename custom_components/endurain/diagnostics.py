"""Diagnostics support for the Endurain integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH_TOKEN
from .coordinator import EndurainConfigEntry

TO_REDACT = {
    CONF_API_KEY,
    CONF_REFRESH_TOKEN,
    CONF_URL,
    CONF_USERNAME,
    "username",
    "email",
    "name",
    "city",
    "town",
    "country",
    "birthdate",
    "photo_path",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EndurainConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(
            {**asdict(data), "forbidden": sorted(data.forbidden)},
            TO_REDACT,
        ),
    }
