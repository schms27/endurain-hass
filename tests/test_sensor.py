"""Tests for Endurain sensors and the activity event."""

from __future__ import annotations

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import ACTIVITY, URL, mock_data_endpoints


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensor_values(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """Sensors expose the summary, activity and health values in suggested units."""
    mock_data_endpoints(aioclient_mock)
    await _setup(hass, api_key_entry)

    assert float(hass.states.get("sensor.jane_runner_this_week_distance").state) == 25.0  # km
    assert float(hass.states.get("sensor.jane_runner_this_week_duration").state) == 2.5  # h
    assert hass.states.get("sensor.jane_runner_this_week_activities").state == "3"
    assert float(hass.states.get("sensor.jane_runner_lifetime_distance").state) == 4200.0
    assert hass.states.get("sensor.jane_runner_steps").state == "11234"
    assert float(hass.states.get("sensor.jane_runner_weight").state) == 71.4
    assert float(hass.states.get("sensor.jane_runner_sleep_duration").state) == 7.5
    assert hass.states.get("sensor.jane_runner_sleep_score").state == "83"

    latest = hass.states.get("sensor.jane_runner_latest_activity")
    assert latest.state == "Morning run"
    assert latest.attributes["activity_type"] == "Run"
    assert latest.attributes["url"] == f"{URL}/activity/42"
    assert float(hass.states.get("sensor.jane_runner_latest_activity_distance").state) == 10.234


async def test_disabled_by_default(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    api_key_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Secondary metrics are registered but disabled."""
    mock_data_endpoints(aioclient_mock)
    await _setup(hass, api_key_entry)

    for entity_id in ("sensor.jane_runner_this_week_calories", "sensor.jane_runner_bmi"):
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_forbidden_sections_are_skipped(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """Without health:read the health sensors are not created at all."""
    mock_data_endpoints(aioclient_mock, forbidden=("/health/steps", "/health/weight", "/health/sleep"))
    await _setup(hass, api_key_entry)

    assert hass.states.get("sensor.jane_runner_steps") is None
    assert hass.states.get("sensor.jane_runner_weight") is None
    assert hass.states.get("sensor.jane_runner_this_week_distance") is not None


async def test_no_activities_yet(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """A fresh account has unknown latest-activity sensors."""
    mock_data_endpoints(aioclient_mock, activity=None)
    await _setup(hass, api_key_entry)

    assert hass.states.get("sensor.jane_runner_latest_activity").state == STATE_UNKNOWN


async def test_new_activity_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """The event fires for a newer activity, not at startup or after a deletion."""
    mock_data_endpoints(aioclient_mock)
    await _setup(hass, api_key_entry)
    coordinator = api_key_entry.runtime_data
    entity_id = "event.jane_runner_activity"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    aioclient_mock.clear_requests()
    mock_data_endpoints(aioclient_mock, activity={**ACTIVITY, "id": 43, "name": "Evening ride", "activity_type": 4})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state != STATE_UNKNOWN
    assert state.attributes["event_type"] == "new_activity"
    assert state.attributes["name"] == "Evening ride"
    assert state.attributes["activity_type"] == "Ride"
    fired_at = state.state

    # Deleting the newest activity makes an older one "latest" again: no event.
    aioclient_mock.clear_requests()
    mock_data_endpoints(aioclient_mock)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == fired_at


async def test_diagnostics_redact_secrets(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_key_entry: MockConfigEntry
) -> None:
    """Diagnostics never contain the key or personal data."""
    from custom_components.endurain.diagnostics import async_get_config_entry_diagnostics

    mock_data_endpoints(aioclient_mock)
    await _setup(hass, api_key_entry)

    diag = await async_get_config_entry_diagnostics(hass, api_key_entry)
    text = str(diag)
    for secret in ("endurain_secret", "jane@example.com", URL):
        assert secret not in text
    assert diag["data"]["summaries"]["week"]["activity_count"] == 3
