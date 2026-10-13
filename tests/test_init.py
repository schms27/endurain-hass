"""Tests for setting up and tearing down the Endurain integration."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.endurain.const import CONF_REFRESH_TOKEN, DOMAIN

from .conftest import API, mock_data_endpoints, token_payload


async def test_setup_and_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """The entry loads and unloads cleanly."""
    mock_data_endpoints(aioclient_mock)
    api_key_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(api_key_entry.entry_id)
    await hass.async_block_till_done()
    assert api_key_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(api_key_entry.entry_id)
    assert api_key_entry.state is ConfigEntryState.NOT_LOADED


async def test_rotated_refresh_token_is_persisted(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, password_entry: MockConfigEntry
) -> None:
    """The refresh token issued at startup replaces the stored one."""
    aioclient_mock.post(f"{API}/auth/refresh", json=token_payload("refresh-2"))
    mock_data_endpoints(aioclient_mock)
    password_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(password_entry.entry_id)
    await hass.async_block_till_done()

    assert password_entry.state is ConfigEntryState.LOADED
    assert password_entry.data[CONF_REFRESH_TOKEN] == "refresh-2"


async def test_expired_session_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, password_entry: MockConfigEntry
) -> None:
    """A rejected refresh token puts the entry into re-authentication."""
    aioclient_mock.post(f"{API}/auth/refresh", status=401, json={"detail": "Refresh token expired"})
    password_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(password_entry.entry_id)
    await hass.async_block_till_done()

    assert password_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH


async def test_server_down_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """An unreachable server leaves the entry in retry mode."""
    aioclient_mock.get(f"{API}/profile", status=502)
    api_key_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(api_key_entry.entry_id)
    assert api_key_entry.state is ConfigEntryState.SETUP_RETRY
