"""Data update coordinator for the Endurain integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EndurainAuthError,
    EndurainClient,
    EndurainError,
    EndurainForbiddenError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, SUMMARY_PERIODS

_LOGGER = logging.getLogger(__name__)

HEALTH_KINDS = ("steps", "weight", "sleep")

type EndurainConfigEntry = ConfigEntry[EndurainCoordinator]


@dataclass
class EndurainData:
    """Snapshot of everything fetched in one update."""

    profile: dict[str, Any]
    summaries: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    latest_activity: dict[str, Any] | None = None
    health: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    # Sections the credential is not allowed to read (HTTP 403), e.g.
    # "summary:week", "latest_activity", "health:steps".
    forbidden: set[str] = field(default_factory=set)


class EndurainCoordinator(DataUpdateCoordinator[EndurainData]):
    """Poll an Endurain instance for one user."""

    config_entry: EndurainConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EndurainConfigEntry,
        client: EndurainClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> EndurainData:
        try:
            profile = await self.client.async_get_profile()
            data = EndurainData(profile=profile)

            sections: dict[str, Awaitable[dict[str, Any] | None]] = {
                f"summary:{period}": self.client.async_get_summary(period) for period in SUMMARY_PERIODS
            }
            sections["latest_activity"] = self.client.async_get_latest_activity(profile["id"])
            for kind in HEALTH_KINDS:
                sections[f"health:{kind}"] = self.client.async_get_latest_health_record(kind)

            results = await asyncio.gather(*sections.values(), return_exceptions=True)
        except EndurainAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EndurainError as err:
            raise UpdateFailed(str(err)) from err

        for key, result in zip(sections, results, strict=True):
            if isinstance(result, EndurainForbiddenError):
                data.forbidden.add(key)
                continue
            if isinstance(result, EndurainAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if isinstance(result, EndurainError):
                raise UpdateFailed(f"{key}: {result}") from result
            if isinstance(result, BaseException):
                raise result

            section, _, name = key.partition(":")
            if section == "summary":
                data.summaries[name] = result
            elif section == "health":
                data.health[name] = result
            else:
                data.latest_activity = result

        return data
